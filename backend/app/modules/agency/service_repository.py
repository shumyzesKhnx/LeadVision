from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.agency.service_model import Service


def get_service(session: Session, service_id: str, agency_id: str) -> Service | None:
    return session.scalar(select(Service).where(Service.id == service_id, Service.agency_id == agency_id))


def count_services(session: Session, agency_id: str, *, include_inactive: bool = False) -> int:
    query = select(func.count()).select_from(Service).where(Service.agency_id == agency_id)
    if not include_inactive:
        query = query.where(Service.active.is_(True))
    return session.scalar(query)


def list_services(session: Session, agency_id: str, *, page: int, page_size: int, include_inactive: bool) -> list[Service]:
    query = select(Service).where(Service.agency_id == agency_id)
    if not include_inactive:
        query = query.where(Service.active.is_(True))
    return list(session.scalars(
        query.order_by(Service.created_at, Service.id).offset((page - 1) * page_size).limit(page_size)
    ))


def insert_service(session: Session, agency_id: str, values: dict) -> Service:
    service = Service(agency_id=agency_id, **values)
    session.add(service)
    session.flush()
    return service


def update_service(session: Session, service: Service, expected: int, changes: dict) -> bool:
    result = session.execute(
        update(Service).where(Service.id == service.id, Service.revision == expected).values(**changes)
    )
    session.refresh(service)
    return result.rowcount == 1
