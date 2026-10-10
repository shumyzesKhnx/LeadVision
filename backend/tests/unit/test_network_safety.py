import pytest
from app.modules.evidence.network_safety import destination
from app.modules.processing.workflow_service import StageFailure
from app.modules.evidence.text_extraction_service import extract_html


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.1.1', '169.254.169.254',
    '0.0.0.0', '224.0.0.1', '192.0.2.1', '::1', '::', 'fe80::1', 'fc00::1', 'ff02::1', '::ffff:8.8.8.8'])
def test_any_forbidden_dns_answer_blocks_all_connections(ip):
    with pytest.raises(StageFailure, match='UNSAFE_DESTINATION'):
        destination('https://company.example', resolver=lambda *args: ['8.8.8.8', ip])


@pytest.mark.parametrize('url', ['file:///tmp/a','data:text/html,a','http://localhost', 'http://user:password@company.example',
    'http://127.0.0.1','http://2130706433','http://0x7f000001','http://company.example\\@127.0.0.1'])
def test_unsafe_url_is_rejected_before_dns(url):
    def unexpected(*args): raise AssertionError('DNS must not be called')
    with pytest.raises(StageFailure): destination(url, resolver=unexpected)


def test_public_dns_and_unresolved():
    assert destination('https://company.example/about', resolver=lambda *args: ['8.8.8.8'])[3] == '8.8.8.8'
    with pytest.raises(StageFailure, match='DNS_FAILURE'): destination('https://company.example', resolver=lambda *args: [])


def test_extraction_removes_hidden_boilerplate_and_keeps_only_same_host_support_links():
    result = extract_html(b'''<title>Company &amp; Services</title><nav>Menu</nav><h1>Software</h1>
        <script>secret</script><p>We build tools.</p><p>We build tools.</p>
        <a href="/about">About</a><a href="https://other.example/services">External</a>''', 'https://company.example/')
    assert result['title'] == 'Company & Services'
    assert 'secret' not in result['text'] and 'Menu' not in result['text']
    assert result['text'].count('We build tools.') == 1
    assert result['supporting_urls'] == ['https://company.example/about']
