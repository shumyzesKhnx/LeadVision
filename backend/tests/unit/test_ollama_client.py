import asyncio
import json
import time
from types import SimpleNamespace
import httpx
import pytest
from app.integrations import ollama_client
from app.services.workflow import StageFailure


def context(settings):
    return SimpleNamespace(worker=SimpleNamespace(settings=settings), stage_deadline=time.monotonic()+10,
                           job_deadline=time.monotonic()+10, checkpoint=lambda: None)


def test_metadata_rejects_redirect_and_requires_valid_digest(settings, monkeypatch):
    original = httpx.Client
    def install(response):
        monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(lambda request: response), **kwargs))
    install(httpx.Response(302, headers={'location': 'https://outside.example'}))
    assert ollama_client.model_info(settings)['status'] == 'unavailable'
    install(httpx.Response(200, json={'models': [{'name': settings.generation_model, 'digest': 'wrong'}]}))
    assert ollama_client.model_info(settings)['status'] == 'unavailable'
    install(httpx.Response(200, json={'models': [{'name': settings.generation_model, 'digest': 'a'*64}]}))
    assert ollama_client.model_info(settings)['digest'] == 'a'*64


@pytest.mark.parametrize('case', ['valid', 'redirect', 'limit', 'truncated', 'json'])
def test_generation_protocol_is_bounded(settings, monkeypatch, case):
    original = httpx.AsyncClient
    response = httpx.Response(200, json={'done': True, 'response': '{}', 'prompt_eval_count': 10})
    if case == 'redirect': response = httpx.Response(302, headers={'location':'https://outside.example'})
    if case == 'limit': response = httpx.Response(200, content=b'x'*131073)
    if case == 'truncated': response = httpx.Response(200, json={'done':True,'response':'{}','done_reason':'length'})
    if case == 'json': response = httpx.Response(200, content=b'wrong')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(lambda request: response), **kwargs))
    payload = {'options': {'num_predict':768,'num_ctx':4096}}
    if case == 'valid': assert ollama_client.generate(context(settings),payload)[0] == '{}'
    else:
        with pytest.raises(StageFailure): ollama_client.generate(context(settings),payload)


def test_generation_cancellation_closes_pending_request(settings, monkeypatch):
    original = httpx.AsyncClient
    cancelled = []
    checks = 0
    async def hanging(request):
        try: await asyncio.sleep(60)
        finally: cancelled.append(True)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(hanging), **kwargs))
    ctx = context(settings)
    def checkpoint():
        nonlocal checks
        checks += 1
        if checks >= 2: raise StageFailure('JOB_CANCELLED')
    ctx.checkpoint = checkpoint
    start = time.monotonic()
    with pytest.raises(StageFailure, match='JOB_CANCELLED'):
        ollama_client.generate(ctx, {'options':{'num_predict':768,'num_ctx':4096}})
    assert time.monotonic()-start < 2 and cancelled
