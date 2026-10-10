from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.campaigns.campaign_model import Campaign


def get_campaign(session: Session, campaign_id: str, agency_id: str) -> Campaign | None:
    return session.scalar(select(Campaign).where(Campaign.id == campaign_id, Campaign.agency_id == agency_id))


def count_for_icp(session: Session, icp_id: str) -> int:
    return session.scalar(select(func.count()).select_from(Campaign).where(Campaign.icp_id == icp_id))


def list_campaigns(session: Session, agency_id: str, page: int, page_size: int, include_archived: bool):
    conditions = [Campaign.agency_id == agency_id]
    if not include_archived:
        conditions.append(Campaign.archived.is_(False))
    total = session.scalar(select(func.count()).select_from(Campaign).where(*conditions))
    items = list(session.scalars(select(Campaign).where(*conditions).order_by(Campaign.created_at, Campaign.id)
                                .offset((page - 1) * page_size).limit(page_size)))
    return items, total


def insert_campaign(session: Session, agency_id: str, values: dict) -> Campaign:
    campaign = Campaign(agency_id=agency_id, **values)
    session.add(campaign)
    session.flush()
    return campaign


def update_campaign(session: Session, campaign: Campaign, expected: int, changes: dict) -> bool:
    result = session.execute(update(Campaign).where(Campaign.id == campaign.id, Campaign.revision == expected).values(**changes))
    session.refresh(campaign)
    return result.rowcount == 1
