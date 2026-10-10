import numpy as np
import pytest
from tokenizers import Tokenizer, models, pre_tokenizers
from app.modules.semantics.embedding_model_client import LocalEncoder
from app.modules.processing.workflow_service import StageFailure


def encoder():
    value = LocalEncoder.__new__(LocalEncoder)
    value.tokenizer = Tokenizer(models.WordPiece({'[UNK]': 0, '[CLS]': 1, '[SEP]': 2, 'hello': 3}, unk_token='[UNK]'))
    value.tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    return value


def test_tokenizer_limit_is_explicit_and_preserves_special_tokens():
    selected = encoder().select('hello ' * 500)
    assert selected['truncated'] and selected['token_count'] == 256
    assert selected['input_ids'][0] == 1 and selected['input_ids'][-1] == 2
    assert len(selected['input_ids']) == 256 and selected['original_tokens_in_bounded_prefix'] == 500
    assert not encoder().select('hello')['truncated']


def test_character_limit_and_empty_text():
    selected = encoder().select('hello ' * 10000)
    assert selected['character_prefix_truncated']
    with pytest.raises(StageFailure, match='EMPTY_TEXT'): encoder().select('  ')


def test_cpu_adapter_mask_mean_and_dimension_validation():
    value = encoder()
    class Session:
        def get_inputs(self):
            return [type('Input', (), {'name': name})() for name in ('input_ids', 'attention_mask', 'token_type_ids')]
        def run(self, names, inputs):
            assert inputs['attention_mask'].tolist() == [[1, 1, 1]]
            assert inputs['token_type_ids'].tolist() == [[0, 0, 0]]
            output = np.zeros((1, 3, 384), dtype=np.float32)
            output[0, :, 0] = [1, 2, 3]
            return [output]
    value.session = Session()
    result = value.encode(value.select('hello'), lambda: None)
    assert result[0] == 1 and np.count_nonzero(result) == 1
