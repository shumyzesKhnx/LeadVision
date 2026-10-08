"""Store customer profiles and version their entire analytical configuration atomically."""

import json

from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.hashing import content_hash
from app.core.revisions import check_revision
from app.db.repositories import icp as repository
from app.db.repositories.campaign import count_for_icp
from app.schemas.common import ErrorDetail
from app.schemas.icp import AnalyticalConfig, ICPCreate, ICPPatch, ICPResponse, ICPVersionResponse
from app.services.activity import record_activity
from app.services.agency import require_workspace
from app.services.criteria import eligible_components, target_countries
from app.services.freshness import configuration_change

SCORE_RULE_VERSION = 'weighted-fit-v1'


def digest(value: dict) -> str:
    return content_hash(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                   allow_nan=False).encode('utf-8'))


def validate_config(values: dict) -> dict:
    config = AnalyticalConfig.model_validate(values).model_dump(mode='json')
    if config['weights']['visual'] > 0 or config['visual_calibration_id'] is not None:
        raise AppError('VISUAL_CALIBRATION_REQUIRED',
                       'Visual scoring is unavailable until a reviewed calibration is implemented.', 409)
    if config['weights']['semantic'] > 0 and not config['target_text']:
        raise AppError('INVALID_WEIGHTS', 'A positive semantic weight requires target_text.', 422,
                       [ErrorDetail(field='target_text', reason='Describe your desired customers or set semantic weight to zero.')])
    if not eligible_components(config):
        raise AppError('INVALID_WEIGHTS', 'Select at least one applicable criterion with a positive weight.', 422,
                       [ErrorDetail(field='weights', reason='Unselected criteria do not contribute to scoring.')])
    return config


def make_version(session: Session, icp_id: str, number: int, config: dict):
    semantic_input = {key: config[key] for key in ('target_text', 'desired_needs', 'preferences_text')}
    return repository.add_version(session, icp_id, number, config,
                                  digest({'config': config, 'score_rule_version': SCORE_RULE_VERSION}),
                                  digest(semantic_input), SCORE_RULE_VERSION)


def require_icp(session: Session, icp_id: str, *, selectable: bool = False):
    agency = require_workspace(session)
    profile = repository.get_icp(session, icp_id, agency.id)
    if profile is None:
        raise AppError('ICP_NOT_FOUND', 'Customer profile not found.', 404)
    if selectable and profile.archived:
        raise AppError('ICP_ARCHIVED', 'Reactivate this customer profile before selecting it.')
    return profile


def profile_response(session: Session, profile, invalidation=None) -> ICPResponse:
    version = repository.current_version(session, profile)
    values = dict(id=profile.id, agency_id=profile.agency_id, name=profile.name,
                  archived=profile.archived, revision=profile.revision, created_at=profile.created_at,
                  updated_at=profile.updated_at, current_version=ICPVersionResponse.model_validate(version),
                  eligible_components=eligible_components(version.config),
                  resolved_countries=target_countries(version.config['criteria']))
    if invalidation is not None:
        values['invalidation'] = invalidation
    return ICPResponse(**values)


def create_icp(session: Session, body: ICPCreate) -> ICPResponse:
    agency = require_workspace(session)
    config = validate_config(body.model_dump(mode='json', exclude={'name'}))
    profile = repository.add_profile(session, agency.id, body.name)
    version = make_version(session, profile.id, 1, config)
    profile.current_version_id = version.id
    session.flush()
    record_activity(session, action='icp.created', origin='api', agency_id=agency.id,
                    new_value={'icp_id': profile.id, 'revision': 1, 'version': 1})
    return profile_response(session, profile)


def edit_icp(session: Session, icp_id: str, body: ICPPatch, expected: int) -> ICPResponse:
    profile = require_icp(session, icp_id)
    check_revision(profile.revision, expected)
    previous = repository.current_version(session, profile)
    supplied = body.model_dump(mode='json', exclude_unset=True)
    config_changes = {key: value for key, value in supplied.items() if key not in {'name', 'archived'}}
    config = validate_config({**previous.config, **config_changes})
    changed_config = config != previous.config
    changes = {key: supplied[key] for key in ('name', 'archived')
               if key in supplied and supplied[key] != getattr(profile, key)}
    current = previous
    if changed_config:
        current = make_version(session, profile.id, previous.version + 1, config)
        changes['current_version_id'] = current.id
    if not changes:
        return profile_response(session, profile)
    fields = sorted(key for key in supplied if key not in {'name', 'archived'}) if changed_config else []
    fields.extend(key for key in ('name', 'archived') if key in changes)
    changes.update(revision=expected + 1, updated_at=utc_now())
    if not repository.update_profile(session, profile, expected, changes):
        raise AppError('EDIT_CONFLICT', 'This record changed. Reload before saving.')
    record_activity(session, action='icp.updated', origin='api', agency_id=profile.agency_id,
                    old_value={'revision': expected, 'version': previous.version},
                    new_value={'icp_id': profile.id, 'revision': profile.revision,
                               'version': current.version, 'fields': sorted(fields)})
    invalidation = configuration_change(previous, current)
    if changed_config or 'archived' in changes:
        invalidation.affected_campaigns = count_for_icp(session, profile.id)
    return profile_response(session, profile, invalidation)
