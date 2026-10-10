"""Campaign operations and reusable preflight checks for later imports/jobs."""

from sqlalchemy.orm import Session

from app.modules.foundation.clock import utc_now
from app.modules.foundation.errors import AppError
from app.modules.foundation.revisions import check_revision
from app.modules.campaigns import campaign_repository as repository
from app.modules.icp import icp_repository
from app.modules.leads.leads_repository import count_for_campaign
from app.modules.campaigns.campaign_schema import CampaignCreate, CampaignPatch, CampaignResponse, CampaignInvalidation
from app.modules.processing.activity_service import record_activity
from app.modules.agency.agency_service import require_workspace


def selected_icp(session: Session, icp_id: str, agency_id: str, *, active: bool = False):
    profile = icp_repository.get_icp(session, icp_id, agency_id)
    if profile is None:
        raise AppError('ICP_NOT_FOUND', 'Customer profile not found in your agency.', 404)
    if active and (profile.archived or profile.current_version_id is None):
        raise AppError('ICP_UNAVAILABLE', 'Select an active customer profile or reactivate the selected one.')
    return profile


def require_campaign(session: Session, campaign_id: str, *, for_work: bool = False):
    agency = require_workspace(session)
    campaign = repository.get_campaign(session, campaign_id, agency.id)
    if campaign is None:
        raise AppError('CAMPAIGN_NOT_FOUND', 'Campaign not found.', 404)
    if for_work:
        if campaign.archived:
            raise AppError('CAMPAIGN_ARCHIVED', 'Reactivate this campaign before adding leads or starting analysis.')
        selected_icp(session, campaign.icp_id, agency.id, active=True)
    return campaign


def campaign_response(session: Session, campaign, *, targeting_changed: bool = False) -> CampaignResponse:
    profile = selected_icp(session, campaign.icp_id, campaign.agency_id)
    version = icp_repository.current_version(session, profile)
    blocked = 'CAMPAIGN_ARCHIVED' if campaign.archived else ('ICP_UNAVAILABLE' if profile.archived else None)
    return CampaignResponse(id=campaign.id, agency_id=campaign.agency_id, icp_id=campaign.icp_id,
                            name=campaign.name, description=campaign.description, archived=campaign.archived,
                            revision=campaign.revision, created_at=campaign.created_at, updated_at=campaign.updated_at,
                            icp_name=profile.name, current_icp_version_id=version.id, current_icp_version=version.version,
                            analysis_allowed=blocked is None, analysis_blocked_reason=blocked,
                            lead_count=count_for_campaign(session, campaign.id),
                            invalidation=CampaignInvalidation(targeting_changed=targeting_changed))


def create_campaign(session: Session, body: CampaignCreate) -> CampaignResponse:
    agency = require_workspace(session)
    values = body.model_dump(mode='json')
    selected_icp(session, values['icp_id'], agency.id, active=True)
    campaign = repository.insert_campaign(session, agency.id, values)
    record_activity(session, action='campaign.created', origin='api', agency_id=agency.id, campaign_id=campaign.id,
                    new_value={'icp_id': campaign.icp_id, 'revision': 1})
    return campaign_response(session, campaign)


def edit_campaign(session: Session, campaign_id: str, body: CampaignPatch, expected: int) -> CampaignResponse:
    campaign = require_campaign(session, campaign_id)
    check_revision(campaign.revision, expected)
    supplied = body.model_dump(mode='json', exclude_unset=True)
    changes = {key: value for key, value in supplied.items() if getattr(campaign, key) != value}
    if 'icp_id' in changes or changes.get('archived') is False:
        selected_icp(session, changes.get('icp_id', campaign.icp_id), campaign.agency_id, active=True)
    if not changes:
        return campaign_response(session, campaign)
    old_icp_id = campaign.icp_id
    fields = sorted(changes)
    changes.update(revision=expected + 1, updated_at=utc_now())
    if not repository.update_campaign(session, campaign, expected, changes):
        raise AppError('EDIT_CONFLICT', 'This record changed. Reload before saving.')
    record_activity(session, action='campaign.updated', origin='api', agency_id=campaign.agency_id,
                    campaign_id=campaign.id, old_value={'icp_id': old_icp_id, 'revision': expected},
                    new_value={'icp_id': campaign.icp_id, 'revision': campaign.revision, 'fields': fields})
    result = campaign_response(session, campaign, targeting_changed=old_icp_id != campaign.icp_id)
    if result.invalidation.targeting_changed:
        result.invalidation.affected_leads = result.lead_count
    return result
