import asyncio

import httpx
import pytest

from app.api.health import probe_ollama


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient

    def client(**kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)


def test_runtime_probe_accepts_valid_tags_without_claiming_model_readiness(monkeypatch):
    install_transport(monkeypatch, lambda request: httpx.Response(200, json={"models": []}))
    result = asyncio.run(probe_ollama("http://127.0.0.1:11434"))
    assert result.status == "available"
    assert "separately" in result.message


@pytest.mark.parametrize("response", [
    httpx.Response(500, text="private diagnostic"),
    httpx.Response(302, headers={"location": "https://external.example"}),
    httpx.Response(200, text="not JSON"),
    httpx.Response(200, json={"unexpected": True}),
])
def test_bad_runtime_response_is_unavailable_without_leaking_body(monkeypatch, response):
    install_transport(monkeypatch, lambda request: response)
    result = asyncio.run(probe_ollama("http://127.0.0.1:11434"))
    assert result.status == "unavailable"
    assert "private diagnostic" not in result.message


def test_runtime_timeout_does_not_crash_health(monkeypatch):
    def timeout(request):
        raise httpx.ConnectTimeout("secret detail", request=request)

    install_transport(monkeypatch, timeout)
    assert asyncio.run(probe_ollama("http://127.0.0.1:11434")).status == "unavailable"
