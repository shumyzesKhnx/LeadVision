"""Real Chrome exercises forms against an isolated API/database, never user data.

Only worker readiness is stubbed: jobs are queued and cancelled, not AI results.
"""
import socket
import threading
import time
from io import BytesIO

import uvicorn
from playwright.sync_api import sync_playwright
from PIL import Image

from app.main import create_app
from app.modules.foundation.common_schema import DependencyHealth
from app.modules.processing.worker_main import Worker


def test_beginner_frontend_journey(settings, monkeypatch, tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    settings.api_port = port
    monkeypatch.setattr('app.modules.processing.jobs_service.worker_readiness', lambda *_: DependencyHealth(status='available', message='Test worker readiness'))
    monkeypatch.setattr('app.modules.nlp.model_cache_service.model_info', lambda *_: {'status': 'missing', 'digest': None})
    application = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}/')
            page.get_by_role('heading', name='Your research journey').wait_for()
            page.get_by_role('link', name='Agency & services 02').click()
            page.get_by_role('button', name='Add your agency').click()
            page.get_by_label('Agency name').fill('Demo Agency')
            page.get_by_label('Business email').fill('hello@example.com')
            page.get_by_role('button', name='Save', exact=True).click()
            page.get_by_role('heading', name='Demo Agency').wait_for()
            page.get_by_role('button', name='Add service').click()
            page.get_by_label('Service name').fill('Website redesign')
            page.get_by_label('Describe the service').fill('We redesign company websites.')
            page.get_by_role('button', name='Save', exact=True).click()
            page.get_by_role('heading', name='Website redesign').wait_for()
            page.get_by_role('button', name='Deactivate', exact=True).click()
            page.get_by_role('button', name='Activate', exact=True).click()
            page.get_by_role('button', name='Deactivate', exact=True).wait_for()
            page.get_by_role('link', name='Customer profiles 03').click()
            page.get_by_role('button', name='Create profile').click()
            page.get_by_label('Profile name').fill('Pakistan software companies')
            page.get_by_label('Describe your ideal client').fill('Software companies in Pakistan needing a website redesign.')
            page.get_by_label('Industries (comma separated)', exact=True).fill('software')
            page.get_by_role('button', name='Save', exact=True).click()
            page.get_by_role('heading', name='Pakistan software companies').wait_for()
            page.get_by_role('link', name='Campaigns 04').click()
            page.get_by_role('button', name='Create campaign').click()
            page.get_by_label('Campaign name').fill('Website prospects')
            page.get_by_role('button', name='Save', exact=True).click()
            page.get_by_role('heading', name='Website prospects').wait_for()
            page.get_by_role('button', name='View companies').click()
            page.get_by_role('button', name='Add company').click()
            # Website-controlled text must display literally, never execute.
            company = '<img src=x onerror=alert(1)> Test company'
            page.get_by_label('Company name', exact=True).fill(company)
            page.get_by_label('Company website').fill('https://example.com')
            page.get_by_label('Country code').fill('PK')
            page.get_by_label('Industry (optional)').fill('software')
            page.get_by_role('button', name='Save', exact=True).click()
            page.get_by_role('button', name='Open →').click()
            page.get_by_role('heading', name=company, exact=True).wait_for()
            assert page.locator('#content img').count() == 0
            page.get_by_role('button', name='Edit details').click()
            page.get_by_label('Your notes').fill('Reviewed by instructor')
            page.get_by_role('button', name='Save', exact=True).click()
            page.get_by_text('Reviewed by instructor', exact=True).wait_for()
            page.get_by_role('button', name='Start research', exact=True).click()
            page.get_by_label('Evidence source').select_option('uploaded')
            # No file shows an actionable form error, including plain Error objects.
            page.get_by_role('button', name='Start research', exact=True).last.click()
            page.get_by_text('Choose at least one saved file.', exact=True).wait_for()
            page.get_by_label('Website text').set_input_files({'name': 'website.txt', 'mimeType': 'text/plain', 'buffer': b'Example Company builds software for business customers.'})
            page.get_by_role('button', name='Start research', exact=True).last.click()
            page.get_by_role('heading', name='Research in progress').wait_for()
            page.get_by_role('button', name='Cancel research').click()
            page.get_by_role('heading', name='Research attempt').wait_for()
            page.get_by_role('button', name='Start research', exact=True).click()
            page.get_by_label('Evidence source').select_option('uploaded')
            page.get_by_label('Website text').set_input_files({'name': 'website.txt', 'mimeType': 'text/plain', 'buffer': b'Example Company builds software for business customers.'})
            image = BytesIO()
            Image.new('RGB', (80, 40), 'green').save(image, format='PNG')
            page.get_by_label('Website screenshot').set_input_files({'name': 'screen.png', 'mimeType': 'image/png', 'buffer': image.getvalue()})
            page.get_by_role('button', name='Start research', exact=True).last.click()
            page.get_by_role('heading', name='Research in progress').wait_for()
            # Real production processing preserves CV/evidence/scoring when
            # local models are absent. No website or model network is needed.
            with Worker(application.state.database, settings) as worker:
                assert worker.run_once()
            page.get_by_role('heading', name='Research attempt').wait_for()
            page.get_by_text('Average brightness', exact=True).wait_for()
            assert page.locator('.evidence-image').count() == 1
            page.get_by_text('Why this score?', exact=True).click()
            page.get_by_text('Entered country is in the target area.', exact=True).wait_for()
            assert page.get_by_text('Weight: 20', exact=False).count() == 1
            page.get_by_role('button', name='Mark unusable').first.click()
            page.get_by_label('Reason for this decision').fill('Screenshot does not represent the current site.')
            page.get_by_role('button', name='Save', exact=True).click()
            page.get_by_role('button', name='Restore evidence').wait_for()
            page.get_by_role('button', name='Correction history').click()
            page.get_by_role('heading', name='Correction history').wait_for()
            page.get_by_role('button', name='Done', exact=True).click()
            page.get_by_role('button', name='Delete company', exact=True).click()
            page.get_by_label('I confirm that I want to delete this company.').check()
            page.get_by_role('button', name='Delete company', exact=True).last.click()
            page.get_by_role('heading', name='No companies found').wait_for()
            page.get_by_role('link', name='How it works ↗').click()
            page.get_by_role('heading', name='How Lead Vision works').wait_for()
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
