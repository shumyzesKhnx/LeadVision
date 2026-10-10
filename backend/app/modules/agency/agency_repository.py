from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.agency.agency_model import Agency


def get_workspace(session: Session) -> Agency | None:
    return session.scalar(select(Agency).where(Agency.singleton_key == 1))


def insert_workspace(session: Session, values: dict) -> Agency:
    agency = Agency(**values)
    session.add(agency)
    session.flush()
    return agency


def update_workspace(session: Session, agency: Agency, expected: int, changes: dict) -> bool:
    result = session.execute(
        update(Agency).where(Agency.id == agency.id, Agency.revision == expected).values(**changes)
    )
    session.refresh(agency)
    return result.rowcount == 1
