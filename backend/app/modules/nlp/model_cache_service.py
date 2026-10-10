from sqlalchemy import select
from app.modules.foundation.clock import utc_now
from app.modules.nlp.business_analysis_model import RuntimeModel, BusinessAnalysis
from app.modules.nlp.ollama_client import model_info


def refresh_runtime(database, settings):
    info = model_info(settings)  # No transaction spans HTTP.
    with database.transaction(immediate=True) as session:
        model = session.get(RuntimeModel, 1)
        if model is None:
            session.add(RuntimeModel(name=settings.generation_model, **info))
        else:
            model.name, model.digest, model.status = settings.generation_model, info['digest'], info['status']
            model.checked_at = utc_now()
    from app.modules.semantics.embeddings_service import refresh_runtime as refresh_embeddings
    refresh_embeddings(database, settings)


def lookup(session, input_hash):
    return session.scalar(select(BusinessAnalysis).where(BusinessAnalysis.input_hash == input_hash)
                          .order_by(BusinessAnalysis.created_at.desc(), BusinessAnalysis.id.desc()).limit(1))
