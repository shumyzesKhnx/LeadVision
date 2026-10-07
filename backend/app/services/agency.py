"""Singleton workspace operations, with activity changes in the same transaction."""

from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.revisions import check_revision
from app.db.repositories import agency as repository
from app.db.repositories.service import count_services
from app.models.agency import Agency
from app.schemas.agency import AgencyCreate, AgencyPatch, AgencyResponse
from app.services.activity import record_activity


def require_workspace(session: Session) -> Agency:
    agency = repository.get_workspace(session)
    if agency is None:
        raise AppError("AGENCY_NOT_FOUND", "Create your agency profile first.", 404)
    return agency


def workspace_response(session: Session, agency: Agency) -> AgencyResponse:
    return AgencyResponse.model_validate(agency).model_copy(
        update={"active_service_count": count_services(session, agency.id)}
    )


def create_workspace(session: Session, body: AgencyCreate) -> AgencyResponse:
    if repository.get_workspace(session) is not None:
        raise AppError("AGENCY_EXISTS", "An agency already exists. Edit its profile instead.")
    agency = repository.insert_workspace(session, body.model_dump(mode="json"))
    record_activity(
        session, action="agency.created", origin="api", agency_id=agency.id,
        new_value={"id": agency.id, "revision": agency.revision},
    )
    return workspace_response(session, agency)


def edit_workspace(session: Session, body: AgencyPatch, expected: int) -> AgencyResponse:
    agency = require_workspace(session)
    check_revision(agency.revision, expected)
    changes = body.model_dump(mode="json", exclude_unset=True)
    changes = {key: value for key, value in changes.items() if getattr(agency, key) != value}
    if not changes:
        return workspace_response(session, agency)
    fields = sorted(changes)
    changes.update(revision=expected + 1, updated_at=utc_now())
    if not repository.update_workspace(session, agency, expected, changes):
        raise AppError("EDIT_CONFLICT", "This record changed. Reload before saving.")
    record_activity(
        session, action="agency.updated", origin="api", agency_id=agency.id,
        old_value={"revision": expected}, new_value={"revision": agency.revision, "fields": fields},
    )
    return workspace_response(session, agency)
