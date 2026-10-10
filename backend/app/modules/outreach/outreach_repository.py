from sqlalchemy import select
from app.modules.outreach.outreach_model import OutreachDraft, OutreachRevision, DraftSource


def revisions(session, draft_id):
    return list(session.scalars(select(OutreachRevision).where(OutreachRevision.draft_id == draft_id)
                               .order_by(OutreachRevision.number.desc())))


def sources(session, draft_id):
    return [row.snapshot for row in session.scalars(select(DraftSource).where(DraftSource.draft_id == draft_id)
                                                  .order_by(DraftSource.source_id))]


def list_for_lead(session, lead_id):
    return list(session.scalars(select(OutreachDraft).where(OutreachDraft.lead_id == lead_id)
                               .order_by(OutreachDraft.created_at.desc(), OutreachDraft.id.desc()).limit(100)))
