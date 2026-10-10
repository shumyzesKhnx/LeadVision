from sqlalchemy import select
from app.modules.semantics.embedding_model import Embedding


def lookup(session, agency_id, purpose, input_hash, space_hash):
    return session.scalar(select(Embedding).where(Embedding.agency_id == agency_id, Embedding.purpose == purpose,
        Embedding.input_hash == input_hash, Embedding.space_hash == space_hash))
