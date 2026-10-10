"""Pinned local MiniLM artifacts and compatible encoder settings."""
from importlib.metadata import version, PackageNotFoundError

MODEL_ID = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
MODEL_SHA256 = '6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452'
SMALL_FILES = {'tokenizer.json': 'cb202bfe2e3c98645018a6d12f182a434c9d3e02',
               'README.md': '44af2e3b0fa3a0b6239e48422972bf755f28fde0',
               'sentence_bert_config.json': '59d594003bf59880a884c574bf88ef7555bb0202',
               '1_Pooling/config.json': 'd1514c3162bbe87b343f565fadc62e6c06f04f03'}


def encoder_config():
    libraries = {}
    for package in ('onnxruntime', 'tokenizers', 'numpy'):
        try: libraries[package] = version(package)
        except PackageNotFoundError: libraries[package] = 'uninstalled'
    return {'version': 'minilm_mean_pool_v1', 'max_tokens': 256, 'max_input_characters': 12000,
            'dimensions': 384, 'pooling': 'attention_mask_mean', 'normalize': 'L2',
            'provider': 'CPUExecutionProvider', 'threads': 1, 'libraries': libraries}
