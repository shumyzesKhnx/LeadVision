"""Local curated trial without modifying the application database."""
from pathlib import Path
import sys
import json
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.modules.foundation.config import Settings
from app.modules.semantics.embedding_model_client import model_info, LocalEncoder
from app.modules.semantics.embeddings_service import cosine


def peak_process_ram():
    if sys.platform != 'win32': return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
            *[(name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
              'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]]
    memory = Counters(); memory.cb = ctypes.sizeof(memory)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    query = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    return int(memory.PeakWorkingSetSize) if query(kernel.GetCurrentProcess(), ctypes.byref(memory), memory.cb) else None


def main():
    settings = Settings(); info = model_info(settings)
    if info['status'] != 'available': raise SystemExit('Run scripts/setup_embeddings.py first.')
    started = time.monotonic(); encoder = LocalEncoder(settings, info['identity']); load_seconds = time.monotonic() - started
    texts = {
        'icp': 'Accounting software companies providing invoicing and bookkeeping tools to small businesses.',
        'accounting': 'CloudBooks sells subscription accounting software, invoice automation and bookkeeping tools for small businesses.',
        'construction': 'StoneBridge builds roads and concrete bridges, operates excavators and supplies construction aggregates.',
        'long_text': 'Accounting software for small businesses. ' * 200}
    vectors, timings, selections = {}, {}, {}
    for key, text in texts.items():
        started = time.monotonic(); selections[key] = encoder.select(text)
        vectors[key] = encoder.encode(selections[key], lambda: None); timings[key] = time.monotonic() - started
    repeated = encoder.encode(selections['accounting'], lambda: None)
    repeat_difference = float(np.max(np.abs(repeated - vectors['accounting'])))
    similarities = {key: dict(zip(('raw_cosine', 'normalized_similarity'), cosine(vectors['icp'], vectors[key], 'same', 'same')))
                    for key in ('accounting', 'construction')}
    assert similarities['accounting']['raw_cosine'] > similarities['construction']['raw_cosine'], 'Investigate unexpected curated ordering.'
    assert repeat_difference <= 1e-5 and selections['long_text']['truncated']
    report = {'identity': info['identity'], 'load_seconds': load_seconds, 'encode_seconds': timings,
        'similarities': similarities, 'repeat_max_absolute_difference': repeat_difference,
        'long_text_tokens': selections['long_text']['token_count'], 'peak_process_ram_bytes': peak_process_ram(),
        'scope': 'Curated synthetic English texts; no population accuracy or conversion probability claim.'}
    path = ROOT / '.cache' / 'phase-10' / 'embedding-trial.json'; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
