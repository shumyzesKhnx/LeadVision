"""Reusable, owned vector cache; finite float32 BLOBs, never pickle."""
import numpy as np
from app.modules.foundation.hashing import snapshot_hash
from app.modules.semantics.embeddings_repository import lookup
from app.modules.semantics.embedding_model import Embedding, EmbeddingRuntime, EmbeddingLead
from app.modules.processing.job_model import Job
from app.modules.processing.workflow_service import StageFailure
from app.modules.foundation.clock import utc_now


def normalize(vector, dimensions=384):
    array = np.asarray(vector, dtype=np.float64)
    if array.shape != (dimensions,): raise StageFailure('VECTOR_DIMENSION_MISMATCH')
    if not np.isfinite(array).all(): raise StageFailure('NONFINITE_VECTOR')
    norm = float(np.linalg.norm(array))
    if norm <= 1e-12: raise StageFailure('ZERO_VECTOR')
    return np.asarray(array / norm, dtype='<f4')


def cosine(left, right, left_space, right_space):
    if left_space != right_space: raise StageFailure('MODEL_SPACE_MISMATCH')
    if len(left) == 0: raise StageFailure('ZERO_VECTOR')
    a = normalize(left, len(left)); b = normalize(right, len(left))
    raw = float(np.clip(np.dot(a.astype(np.float64), b.astype(np.float64)), -1, 1))
    return raw, float(100 * np.clip(raw, 0, 1))


def rank(query, candidates, *, space_hash, limit=5):
    """Caller provides already-owned/current candidates; mismatched spaces are rejected."""
    if len(candidates) > 1000 or not 1 <= limit <= 20: raise ValueError('Ranking exceeds its bound.')
    scored = [(key, cosine(query, vector, space_hash, candidate_space)[0])
              for key, vector, candidate_space in candidates]
    return sorted(scored, key=lambda item: (-item[1], item[0]))[:limit]


def refresh_runtime(database, settings):
    from app.modules.semantics.embedding_model_client import model_info
    info = model_info(settings)
    with database.transaction(immediate=True) as session:
        row = session.get(EmbeddingRuntime, 1)
        if row is None: session.add(EmbeddingRuntime(id=1, **info))
        else: row.status, row.identity, row.checked_at = info['status'], info['identity'], utc_now()


def vector_for(context, encoder, agency_id, purpose, text):
    selection = encoder.select(text)
    space = snapshot_hash(encoder.identity)
    def link(session, embedding_id):
        if purpose == 'company':
            lead_id = session.get(Job, context.job_id).lead_id
            if session.get(EmbeddingLead, (embedding_id, lead_id)) is None:
                session.add(EmbeddingLead(embedding_id=embedding_id, lead_id=lead_id))
    with context.worker.database.transaction(immediate=True) as session:
        cached = lookup(session, agency_id, purpose, selection['input_hash'], space)
        if cached:
            if cached.dimensions != 384 or len(cached.vector) != 1536: raise StageFailure('VECTOR_DIMENSION_MISMATCH')
            if cached.metadata_json.get('model') != encoder.identity: raise StageFailure('MODEL_SPACE_MISMATCH')
            vector = normalize(np.frombuffer(cached.vector, dtype='<f4'))
            link(session, cached.id)
            return cached.id, vector, selection, True
    vector = normalize(encoder.encode(selection, context.checkpoint))
    context.checkpoint()
    with context.worker.database.transaction(immediate=True) as session:
        existing = lookup(session, agency_id, purpose, selection['input_hash'], space)
        if existing:
            link(session, existing.id)
            return existing.id, normalize(np.frombuffer(existing.vector, dtype='<f4')), selection, True
        metadata = {key: value for key, value in selection.items() if key != 'input_ids'}
        metadata['model'] = encoder.identity
        row = Embedding(agency_id=agency_id, purpose=purpose, input_hash=selection['input_hash'], space_hash=space,
                        dimensions=384, vector=vector.tobytes(), metadata_json=metadata)
        session.add(row); session.flush()
        link(session, row.id)
        return row.id, vector, selection, False
