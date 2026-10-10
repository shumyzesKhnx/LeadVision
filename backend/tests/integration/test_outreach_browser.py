"""Exercise preparation and human review through the actual frontend and APIs."""
import socket
import threading
import time
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from test_model_failure import nlp_worker
from test_draft_history import draft_environment


def test_browser_prepare_review_edit_and_history(settings, job_lead, draft_environment):
    worker, *_ = draft_environment
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); settings.api_port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1', port=settings.api_port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
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
            page.goto(f'http://127.0.0.1:{settings.api_port}/#lead/{job_lead["id"]}')
            page.get_by_role('heading', name='Outreach drafts', exact=True).wait_for()
            page.get_by_role('button', name='Prepare draft', exact=True).click()
            page.locator('dialog').get_by_role('button', name='Prepare draft', exact=True).click()
            page.get_by_text('Preparing draft', exact=True).wait_for()
            assert worker.run_once()
            page.get_by_role('button', name='Review', exact=True).wait_for()
            page.get_by_role('button', name='Review', exact=True).click()
            page.get_by_label('Your name', exact=True).fill('Browser reviewer')
            page.locator('dialog input[type=checkbox]').check()
            page.get_by_role('button', name='Save review', exact=True).click()
            page.get_by_role('button', name='Copy approved text', exact=True).wait_for()
            page.get_by_role('button', name='Edit', exact=True).click()
            page.get_by_label('Message', exact=True).fill('Hello,\nWe offer connected security systems. Would a brief conversation be useful?')
            page.get_by_role('button', name='Save new revision', exact=True).click()
            page.get_by_text('Edited', exact=True).wait_for()
            assert page.get_by_role('button', name='Copy approved text', exact=True).count() == 0
            page.get_by_text('Revision history (3)', exact=True).click()
            assert page.get_by_text('Approved ·', exact=False).count() >= 1
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit = True; thread.join(timeout=10)
