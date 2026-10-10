import numpy as np
import pytest
from app.modules.semantics.embeddings_service import cosine, normalize, rank
from app.modules.processing.workflow_service import StageFailure
from app.modules.semantics.semantic_result_schema import SemanticValue
from app.modules.semantics.semantic_matching_service import choose_company
from app.modules.semantics.semantic_matching_service import target_text


@pytest.mark.parametrize('other,raw,value', [([1, 0], 1, 100), ([0, 1], 0, 0), ([-1, 0], -1, 0)])
def test_known_vectors(other, raw, value):
    assert cosine([1, 0], other, 'space', 'space') == pytest.approx((raw, value))


@pytest.mark.parametrize('left,right,code', [([0, 0], [1, 0], 'ZERO_VECTOR'),
    ([], [], 'ZERO_VECTOR'), ([float('nan'), 1], [1, 0], 'NONFINITE_VECTOR'),
    ([float('inf'), 1], [1, 0], 'NONFINITE_VECTOR'), ([1, 0], [1], 'VECTOR_DIMENSION_MISMATCH')])
def test_invalid_vectors_are_missing(left, right, code):
    with pytest.raises(StageFailure, match=code): cosine(left, right, 'space', 'space')


def test_model_spaces_cannot_mix_and_float32_is_normalized():
    with pytest.raises(StageFailure, match='MODEL_SPACE_MISMATCH'): cosine([1, 0], [1, 0], 'a', 'b')
    vector = normalize(np.arange(384))
    assert vector.dtype == np.dtype('<f4') and np.linalg.norm(vector) == pytest.approx(1)


def test_ranking_is_stable_bounded_and_rejects_mixed_spaces():
    assert rank([1, 0], [('b', [1, 0], 's'), ('a', [1, 0], 's')], space_hash='s') == [('a', 1), ('b', 1)]
    with pytest.raises(StageFailure): rank([1, 0], [('bad', [1, 0], 'different')], space_hash='s')
    with pytest.raises(ValueError): rank([1, 0], [], space_hash='s', limit=21)


def test_selection_precedence_and_missing_values():
    snapshot = {'lead': {'description': 'Entered description'}}
    outputs = {'business_analysis': {'available': True, 'analysis': {'summary': 'Generated'},
        'provenance': {'evidence_id': 'id', 'evidence_revision': 1}},
        'acquire_text': {'available': True, 'text': 'Extracted', 'evidence_id': 'id'}}
    assert choose_company(snapshot, outputs)[0] == 'Entered description'
    snapshot['lead']['description'] = None
    assert choose_company(snapshot, outputs)[0] == 'Generated'
    outputs['business_analysis']['available'] = False
    assert choose_company(snapshot, outputs)[0] == 'Extracted'
    assert choose_company(snapshot, {})[0] == ''
    with pytest.raises(ValueError): SemanticValue(available=False, reason='EMPTY_TEXT', raw_cosine=0)


def test_soft_needs_and_preferences_are_included_in_target():
    value = target_text({'target_text': 'Software companies', 'desired_needs': ['Website redesign'], 'preferences_text': 'Prefer Pakistan'})
    assert 'Website redesign' in value and 'Prefer Pakistan' in value
    assert target_text({'target_text': '', 'desired_needs': ['Website redesign']}) == ''
