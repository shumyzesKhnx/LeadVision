"""Local Ollama only; bounded responses and cooperative cancellation during I/O."""
import asyncio
import json
import time
import httpx
from app.services.workflow import StageFailure


def model_info(settings):
    try:
        with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
            with client.stream('GET', settings.ollama_base_url + '/api/tags') as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 262144:
                        raise ValueError('Runtime metadata limit')
            data = json.loads(content)
            for model in data['models']:
                if model['name'] == settings.generation_model:
                    digest = model['digest']
                    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                        raise ValueError('Invalid model digest')
                    return {'status': 'available', 'digest': digest}
            return {'status': 'missing', 'digest': None}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {'status': 'unavailable', 'digest': None}


async def _request(context, payload):
    async def transfer():
        async with httpx.AsyncClient(timeout=context.worker.settings.nlp_timeout_seconds,
                                    trust_env=False, follow_redirects=False) as client:
            async with client.stream('POST', context.worker.settings.ollama_base_url + '/api/generate', json=payload) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 131072:
                        raise StageFailure('MODEL_OUTPUT_INVALID')
                return bytes(content)
    task = asyncio.create_task(transfer())
    deadline = min(context.stage_deadline, context.job_deadline,
                   time.monotonic() + context.worker.settings.nlp_timeout_seconds)
    try:
        while not task.done():
            context.checkpoint()
            if time.monotonic() >= deadline:
                raise StageFailure('MODEL_TIMEOUT')
            await asyncio.wait({task}, timeout=0.1)
        raw = await task
        data = json.loads(raw)
        if data.get('done') is not True or data.get('done_reason') == 'length' or not isinstance(data.get('response'), str):
            raise StageFailure('MODEL_OUTPUT_INVALID')
        if len(data['response'].encode('utf-8')) > 32768:
            raise StageFailure('MODEL_OUTPUT_INVALID')
        count = data.get('prompt_eval_count')
        if isinstance(count, int) and count + payload['options']['num_predict'] > payload['options']['num_ctx']:
            raise StageFailure('CONTEXT_LIMIT')
        return data['response'], {key: data.get(key) for key in ('prompt_eval_count', 'eval_count', 'total_duration')}
    except httpx.TimeoutException:
        raise StageFailure('MODEL_TIMEOUT', retryable=True) from None
    except httpx.HTTPError:
        raise StageFailure('MODEL_UNAVAILABLE', retryable=True) from None
    except (ValueError, TypeError):
        raise StageFailure('MODEL_OUTPUT_INVALID') from None
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def generate(context, payload):
    return asyncio.run(_request(context, payload))
