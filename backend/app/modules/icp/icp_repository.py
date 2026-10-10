from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.icp.icp_model import ICP, ICPVersion


def get_icp(session: Session, icp_id: str, agency_id: str) -> ICP | None:
    return session.scalar(select(ICP).where(ICP.id == icp_id, ICP.agency_id == agency_id))


def list_icps(session: Session, agency_id: str, page: int, page_size: int, include_archived: bool):
    condition = [ICP.agency_id == agency_id]
    if not include_archived:
        condition.append(ICP.archived.is_(False))
    total = session.scalar(select(func.count()).select_from(ICP).where(*condition))
    items = list(session.scalars(select(ICP).where(*condition).order_by(ICP.created_at, ICP.id)
                                .offset((page - 1) * page_size).limit(page_size)))
    return items, total


def current_version(session: Session, profile: ICP) -> ICPVersion:
    return session.execute(select(ICPVersion).where(
        ICPVersion.id == profile.current_version_id, ICPVersion.icp_id == profile.id
    )).scalar_one()


def add_profile(session: Session, agency_id: str, name: str) -> ICP:
    profile = ICP(agency_id=agency_id, name=name)
    session.add(profile)
    session.flush()
    return profile


def add_version(session: Session, icp_id: str, number: int, config: dict, content_hash: str,
                semantic_input_hash: str, score_rule_version: str) -> ICPVersion:
    version = ICPVersion(icp_id=icp_id, version=number, config=config, content_hash=content_hash,
                         semantic_input_hash=semantic_input_hash, score_rule_version=score_rule_version)
    session.add(version)
    session.flush()
    return version


def update_profile(session: Session, profile: ICP, expected: int, changes: dict) -> bool:
    result = session.execute(update(ICP).where(ICP.id == profile.id, ICP.revision == expected).values(**changes))
    session.refresh(profile)
    return result.rowcount == 1


def list_versions(session: Session, icp_id: str, page: int, page_size: int):
    total = session.scalar(select(func.count()).select_from(ICPVersion).where(ICPVersion.icp_id == icp_id))
    items = list(session.scalars(select(ICPVersion).where(ICPVersion.icp_id == icp_id)
                                .order_by(ICPVersion.version.desc()).offset((page - 1) * page_size).limit(page_size)))
    return items, total
