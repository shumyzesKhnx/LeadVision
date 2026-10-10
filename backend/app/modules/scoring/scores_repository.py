from sqlalchemy import select, func
from app.modules.scoring.score_model import ScoreRun


def latest(session, lead_id):
    return session.scalar(select(ScoreRun).where(ScoreRun.lead_id == lead_id)
                          .order_by(ScoreRun.created_at.desc(), ScoreRun.id.desc()).limit(1))


def history(session, lead_id, page, page_size):
    query = select(ScoreRun).where(ScoreRun.lead_id == lead_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    return list(session.scalars(query.order_by(ScoreRun.created_at.desc(), ScoreRun.id.desc())
                               .offset((page - 1) * page_size).limit(page_size))), total
