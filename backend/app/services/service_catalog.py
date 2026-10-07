"""Services belong to the local workspace; deactivation retains their records."""

from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.revisions import check_revision
from app.db.repositories import service as repository
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceList, ServicePatch, ServiceResponse
from app.services.activity import record_activity
from app.services.agency import require_workspace


def require_service(session: Session, service_id: str) -> Service:
    agency = require_workspace(session)
    service = repository.get_service(session, service_id, agency.id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found.", 404)
    return service


def require_active_service(session: Session, service_id: str) -> Service:
    """Outreach will call this prerequisite when that module is implemented."""
    service = require_service(session, service_id)
    if not service.active:
        raise AppError("NO_ACTIVE_SERVICE", "Choose an active service before generating outreach.")
    return service


def create_service(session: Session, body: ServiceCreate) -> ServiceResponse:
    agency = require_workspace(session)
    service = repository.insert_service(session, agency.id, body.model_dump())
    record_activity(
        session, action="service.created", origin="api", agency_id=agency.id,
        new_value={"service_id": service.id, "revision": service.revision, "active": service.active},
    )
    return ServiceResponse.model_validate(service)


def get_catalog(session: Session, *, page: int, page_size: int, include_inactive: bool) -> ServiceList:
    agency = require_workspace(session)
    records = repository.list_services(
        session, agency.id, page=page, page_size=page_size, include_inactive=include_inactive
    )
    return ServiceList(
        items=[ServiceResponse.model_validate(service) for service in records],
        page=page, page_size=page_size,
        total=repository.count_services(session, agency.id, include_inactive=include_inactive),
    )


def edit_service(session: Session, service_id: str, body: ServicePatch, expected: int) -> ServiceResponse:
    service = require_service(session, service_id)
    check_revision(service.revision, expected)
    changes = body.model_dump(exclude_unset=True)
    changes = {key: value for key, value in changes.items() if getattr(service, key) != value}
    if not changes:
        return ServiceResponse.model_validate(service)
    fields = sorted(changes)
    was_active = service.active
    changes.update(revision=expected + 1, updated_at=utc_now())
    if not repository.update_service(session, service, expected, changes):
        raise AppError("EDIT_CONFLICT", "This service changed. Reload before saving.")
    action = "service.updated"
    if was_active != service.active:
        action = "service.reactivated" if service.active else "service.deactivated"
    record_activity(
        session, action=action, origin="api", agency_id=service.agency_id,
        old_value={"service_id": service.id, "revision": expected, "active": was_active},
        new_value={"service_id": service.id, "revision": service.revision, "active": service.active, "fields": fields},
    )
    # Future drafts snapshot service revision; changes will be detected by their freshness checks.
    return ServiceResponse.model_validate(service)
