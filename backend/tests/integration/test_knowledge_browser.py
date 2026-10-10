"""The Knowledge screen uses real APIs and worker indexing in an isolated database."""
import socket
import threading
import time
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from test_knowledge import agency, knowledge_worker


def test_knowledge_browser_review_index_search_and_edit(settings,knowledge_worker):
    worker,*_=knowledge_worker
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));settings.api_port=sock.getsockname()[1]
    application=create_app(settings)
    server=uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=settings.api_port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    deadline=time.monotonic()+10
    while not server.started and time.monotonic()<deadline: time.sleep(.05)
    assert server.started
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{settings.api_port}/#knowledge')
            page.get_by_role('heading',name='Agency knowledge',exact=True).wait_for()
            page.get_by_role('button',name='Add knowledge',exact=True).click()
            page.get_by_label('Title',exact=True).fill('Website redesign example')
            page.get_by_label('Material',exact=True).select_option('true')
            page.get_by_label('Agency facts',exact=True).fill('We redesigned a software company website. <script>alert(1)</script>')
            page.get_by_role('button',name='Save',exact=True).click()
            page.get_by_role('button',name='Review & approve',exact=True).wait_for()
            assert page.locator('#content script').count()==0
            page.get_by_role('button',name='Review & approve',exact=True).click()
            page.get_by_role('button',name='Approve this version',exact=True).click()
            page.get_by_role('button',name='Prepare for use',exact=True).wait_for()
            page.get_by_role('button',name='Prepare for use',exact=True).click()
            page.get_by_role('button',name='Cancel indexing',exact=True).wait_for()
            assert worker.run_once()
            page.get_by_text('Ready to use',exact=False).first.wait_for()
            page.get_by_text('Advanced: test knowledge search',exact=True).click()
            page.get_by_role('button',name='Try retrieval',exact=True).click()
            page.get_by_label('Describe the company or its needs').fill('A software company needs website redesign.')
            page.get_by_role('button',name='Find sources',exact=True).click()
            page.get_by_text('No relevant approved knowledge found.',exact=False).wait_for()
            page.get_by_text('Advanced: test knowledge search',exact=True).click()
            page.get_by_role('button',name='Try retrieval',exact=True).click()
            page.get_by_label('Fictional demo material',exact=True).select_option('true')
            page.get_by_role('button',name='Find sources',exact=True).click()
            page.get_by_role('heading',name='Knowledge preview',exact=True).wait_for()
            assert not page.get_by_text('100.0% text similarity',exact=False).is_visible()
            page.get_by_text('View sources (1 passages)',exact=True).click()
            page.get_by_text('100.0% text similarity',exact=False).wait_for()
            page.get_by_role('button',name='View & manage',exact=True).click()
            page.get_by_role('button',name='Edit',exact=True).click()
            page.get_by_role('heading',name='Edit knowledge',exact=True).wait_for()
            page.get_by_label('Agency facts',exact=True).fill('Our updated website redesign experience.')
            page.get_by_role('button',name='Save',exact=True).click()
            page.get_by_text('Version 2',exact=True).first.wait_for()
            page.get_by_role('button',name='Review & approve',exact=True).wait_for()
            assert page.get_by_role('button',name='Prepare for use',exact=True).count()==0
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
