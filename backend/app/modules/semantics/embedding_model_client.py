"""Offline CPU ONNX MiniLM, explicit token selection, mask mean pooling."""
import hashlib
import json
import numpy as np
from app.modules.semantics.embedding_config import MODEL_ID, REVISION, MODEL_SHA256, SMALL_FILES, encoder_config
from app.modules.foundation.storage import reject_links
from app.modules.foundation.errors import AppError
from app.modules.processing.workflow_service import StageFailure


def model_info(settings):
    root = settings.embedding_model_dir
    try:
        reject_links(root)
        model = root / 'onnx' / 'model.onnx'
        reject_links(model)
        if not model.is_file() or model.stat().st_size != 90405214:
            return {'status': 'unavailable', 'identity': {}}
        digest = hashlib.sha256()
        with model.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''): digest.update(chunk)
        if digest.hexdigest() != MODEL_SHA256: raise ValueError('Model changed')
        hashes = {}
        for name, expected in SMALL_FILES.items():
            path = root / name; reject_links(path)
            if path.stat().st_size > 1_000_000: raise ValueError('Metadata too large')
            content = path.read_bytes()
            if hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() != expected:
                raise ValueError('Tokenizer/config changed')
            hashes[name] = hashlib.sha256(content).hexdigest()
        if json.loads((root / 'sentence_bert_config.json').read_text())['max_seq_length'] != 256:
            raise ValueError('Context changed')
        pooling = json.loads((root / '1_Pooling/config.json').read_text())
        if not pooling['pooling_mode_mean_tokens'] or pooling['pooling_mode_cls_token'] or pooling['pooling_mode_max_tokens']:
            raise ValueError('Pooling changed')
        return {'status': 'available', 'identity': {'model': MODEL_ID, 'revision': REVISION,
                'model_sha256': MODEL_SHA256, 'artifact_hashes': hashes, 'config': encoder_config()}}
    except (OSError, ValueError, KeyError, AppError):
        return {'status': 'unavailable', 'identity': {}}


class LocalEncoder:
    def __init__(self, settings, identity):
        from tokenizers import Tokenizer
        import onnxruntime as ort
        if model_info(settings) != {'status': 'available', 'identity': identity}:
            raise StageFailure('EMBEDDING_UNAVAILABLE')
        self.identity = identity
        self.tokenizer = Tokenizer.from_file(str(settings.embedding_model_dir / 'tokenizer.json'))
        self.tokenizer.no_truncation(); self.tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1; options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(settings.embedding_model_dir / 'onnx' / 'model.onnx'),
                                          sess_options=options, providers=['CPUExecutionProvider'])

    def select(self, text):
        original = text.strip()
        if not original: raise StageFailure('EMPTY_TEXT')
        bounded = original[:12000]
        encoding = self.tokenizer.encode(bounded, add_special_tokens=False)
        selected = encoding.ids[:254]
        if not selected: raise StageFailure('EMPTY_TEXT')
        cls_id, sep_id = self.tokenizer.token_to_id('[CLS]'), self.tokenizer.token_to_id('[SEP]')
        if cls_id is None or sep_id is None: raise StageFailure('MODEL_SPACE_MISMATCH')
        return {'input_ids': [cls_id, *selected, sep_id],
                'input_hash': hashlib.sha256(original.encode()).hexdigest(),
                'selected_text': self.tokenizer.decode(selected), 'original_tokens_in_bounded_prefix': len(encoding.ids),
                'token_count': len(selected) + 2, 'truncated': len(encoding.ids) > 254 or len(original) > 12000,
                'character_prefix_truncated': len(original) > 12000}

    def encode(self, selection, checkpoint):
        checkpoint()
        ids = np.array([selection['input_ids']], dtype=np.int64)
        inputs = {'input_ids': ids, 'attention_mask': np.ones_like(ids), 'token_type_ids': np.zeros_like(ids)}
        expected = {item.name for item in self.session.get_inputs()}
        if not expected <= set(inputs): raise StageFailure('MODEL_SPACE_MISMATCH')
        values = self.session.run(None, {name: inputs[name] for name in expected})[0]
        checkpoint()
        if values.shape != (1, ids.shape[1], 384): raise StageFailure('VECTOR_DIMENSION_MISMATCH')
        # No padding in single-text encoding: the all-one attention mask mean is exact.
        vector = values[0].mean(axis=0, dtype=np.float64)
        from app.modules.semantics.embeddings_service import normalize
        return normalize(vector)


def get_encoder(worker, identity):
    encoder = getattr(worker, '_embedding_encoder', None)
    if encoder is None or encoder.identity != identity:
        encoder = LocalEncoder(worker.settings, identity)
        worker._embedding_encoder = encoder
    elif model_info(worker.settings) != {'status': 'available', 'identity': identity}:
        raise StageFailure('EMBEDDING_UNAVAILABLE')
    return encoder
