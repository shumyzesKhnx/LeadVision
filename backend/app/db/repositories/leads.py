"""Scoped lead queries and shared domain identity; no shared mutable company facts."""

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.lead import Lead
from app.models.lead_fact import LeadFact
from app.models.campaign import Campaign
from app.models.activity import Activity


def company_for_domain(session: Session, domain: str) -> Company:
    session.execute(insert(Company).values(normalized_domain=domain)
                    .on_conflict_do_nothing(index_elements=[Company.normalized_domain]))
    return session.execute(select(Company).where(Company.normalized_domain == domain)).scalar_one()


def get_lead(session: Session, lead_id: str, agency_id: str) -> Lead | None:
    return session.scalar(select(Lead).join(Campaign).where(Lead.id == lead_id, Campaign.agency_id == agency_id))


def duplicate_domain(session: Session, campaign_id: str, company_id: str, exclude_id: str | None = None):
    query = select(Lead).where(Lead.campaign_id == campaign_id, Lead.company_id == company_id)
    if exclude_id is not None:
        query = query.where(Lead.id != exclude_id)
    return session.scalar(query)


def duplicate_name(session: Session, lead: Lead) -> bool:
    return session.scalar(select(Lead.id).where(Lead.campaign_id == lead.campaign_id,
                                              Lead.name_key == lead.name_key, Lead.id != lead.id).limit(1)) is not None


def list_leads(session: Session, agency_id: str, *, campaign_id, pipeline_state, q, direction, page, page_size):
    conditions = [Campaign.agency_id == agency_id]
    if campaign_id is not None:
        conditions.append(Lead.campaign_id == campaign_id)
    if pipeline_state is not None:
        conditions.append(Lead.pipeline_state == pipeline_state)
    if q:
        conditions.append(Lead.name_key.contains(' '.join(q.casefold().split()), autoescape=True))
    query = select(Lead).join(Campaign).where(*conditions)
    total = session.scalar(select(func.count()).select_from(Lead).join(Campaign).where(*conditions))
    order = [Lead.created_at.desc(), Lead.id.desc()] if direction == 'desc' else [Lead.created_at, Lead.id]
    return list(session.scalars(query.order_by(*order).offset((page - 1) * page_size).limit(page_size))), total


def count_for_campaign(session: Session, campaign_id: str) -> int:
    return session.scalar(select(func.count()).select_from(Lead).where(Lead.campaign_id == campaign_id))


def latest_facts(session: Session, lead_id: str) -> list[LeadFact]:
    latest = select(LeadFact.field_name, func.max(LeadFact.revision).label('revision')).where(
        LeadFact.lead_id == lead_id).group_by(LeadFact.field_name).subquery()
    return list(session.scalars(select(LeadFact).join(latest, (LeadFact.field_name == latest.c.field_name) &
                                                    (LeadFact.revision == latest.c.revision))
                               .where(LeadFact.lead_id == lead_id).order_by(LeadFact.field_name)))


def append_fact(session: Session, lead_id: str, field_name: str, value, correction_reason: str | None):
    previous = session.scalar(select(LeadFact).where(LeadFact.lead_id == lead_id, LeadFact.field_name == field_name)
                              .order_by(LeadFact.revision.desc()).limit(1))
    session.add(LeadFact(lead_id=lead_id, field_name=field_name, value=value,
                         source_category='user_provided', verified=False, actor_label='operator',
                         revision=previous.revision + 1 if previous else 1,
                         supersedes_fact_id=previous.id if previous else None, correction_reason=correction_reason))
    session.flush()


def fact_history(session: Session, lead_id: str, page: int, page_size: int):
    total = session.scalar(select(func.count()).select_from(LeadFact).where(LeadFact.lead_id == lead_id))
    facts = list(session.scalars(select(LeadFact).where(LeadFact.lead_id == lead_id)
                                .order_by(LeadFact.recorded_at.desc(), LeadFact.id.desc())
                                .offset((page - 1) * page_size).limit(page_size)))
    return facts, total


def recent_activities(session: Session, lead_id: str):
    total = session.scalar(select(func.count()).select_from(Activity).where(Activity.lead_id == lead_id))
    items = list(session.scalars(select(Activity).where(Activity.lead_id == lead_id)
                                .order_by(Activity.created_at.desc(), Activity.id.desc()).limit(25)))
    return items, total


def update_lead(session: Session, lead: Lead, expected: int, changes: dict) -> bool:
    result = session.execute(update(Lead).where(Lead.id == lead.id, Lead.revision == expected).values(**changes))
    session.refresh(lead)
    return result.rowcount == 1


def remove_unused_company(session: Session, company_id: str) -> None:
    if session.scalar(select(Lead.id).where(Lead.company_id == company_id).limit(1)) is None:
        session.execute(delete(Company).where(Company.id == company_id))
