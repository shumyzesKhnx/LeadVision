import pytest
from app.services import csv_import
from app.services.csv_import import MAX_CSV_BYTES
from test_leads import setup_campaign


def upload(client, campaign, content, name='companies.csv', media='text/csv'):
    return client.post(f"/api/v1/campaigns/{campaign['id']}/imports", files={'file': (name, content, media)})


def test_mixed_import_reports_every_row_and_retry_is_duplicate(client):
    campaign = setup_campaign(client)
    content = ('company_name,website,employee_count,contact_email,extra\n'
               'Company,https://example.com,20,hello@example.com,x\n'
               'Duplicate,http://www.example.com:80/a,20,,x\n'
               'Bad size,https://bad.example.com,-1,,x\n'
               ',https://missing.example.com,10,,x\n'
               '"شرکت, Demo",https://unicode.example.com,,,x\n').encode()
    result = upload(client, campaign, content)
    assert result.status_code == 200, result.text
    report = result.json()
    assert [row['status'] for row in report['items']] == ['accepted', 'duplicate', 'invalid', 'invalid', 'accepted']
    assert [row['row'] for row in report['items']] == [2, 3, 4, 5, 6]
    assert (report['accepted'], report['duplicate'], report['invalid'], report['not_processed']) == (2, 1, 2, 0)
    assert report['warnings']
    assert report['items'][0]['lead_id'] == report['items'][1]['lead_id']
    retry = upload(client, campaign, content).json()
    assert retry['accepted'] == 0 and retry['duplicate'] == 3
    detail = client.get('/api/v1/leads/' + report['items'][0]['lead_id']).json()
    assert detail['activities'][0]['origin'] == 'import'
    assert all(fact['source_category'] == 'user_provided' for fact in detail['provenance'])


@pytest.mark.parametrize('content', [b'wrong,website\nCompany,https://example.com\n',
    b'company_name,website,website\n', b'company_name,website\n\xff',
    b'company_name,website\n' + b'Company,https://example.com\n' * 101])
def test_file_level_errors_save_zero_rows(client, content):
    campaign = setup_campaign(client)
    assert upload(client, campaign, content).status_code == 422
    assert client.get('/api/v1/leads').json()['total'] == 0


def test_size_type_empty_template_and_bom(client):
    campaign = setup_campaign(client)
    assert upload(client, campaign, b'x' * (MAX_CSV_BYTES + 1)).status_code == 413
    assert upload(client, campaign, b'x' * (MAX_CSV_BYTES + 100_000)).status_code == 413
    assert upload(client, campaign, b'', name='file.exe').status_code == 415
    assert upload(client, campaign, b'company_name,website\n').json()['items'] == []
    template = client.get('/api/v1/imports/template')
    assert template.status_code == 200 and 'company_name,website' in template.text
    assert 'attachment' in template.headers['content-disposition']
    result = upload(client, campaign, '\ufeffcompany_name,website\nشرکت,https://example.com\n'.encode())
    assert result.json()['accepted'] == 1


def test_mid_import_failure_retains_committed_rows_and_reports_unprocessed(client, monkeypatch):
    campaign = setup_campaign(client)
    original = csv_import.create_lead
    attempts = 0
    def fail_second(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError('private diagnostic must not be exposed')
        return original(*args, **kwargs)
    monkeypatch.setattr(csv_import, 'create_lead', fail_second)
    result = upload(client, campaign, b'company_name,website\nA,https://a.example.com\nB,https://b.example.com\nC,https://c.example.com\n')
    assert result.status_code == 503
    report = result.json()['error']['import_report']
    assert report['accepted'] == 1 and report['not_processed'] == 2
    assert [row['status'] for row in report['items']] == ['accepted', 'not_processed', 'not_processed']
    assert 'private diagnostic' not in result.text
    assert client.get('/api/v1/leads').json()['total'] == 1


def test_archiving_campaign_between_rows_stops_import(client, monkeypatch):
    campaign = setup_campaign(client)
    original = csv_import.create_lead
    calls = 0
    def archive_after_first(session, body, **kwargs):
        nonlocal calls
        result = original(session, body, **kwargs)
        calls += 1
        if calls == 1:
            from app.models.campaign import Campaign
            session.get(Campaign, campaign['id']).archived = True
        return result
    monkeypatch.setattr(csv_import, 'create_lead', archive_after_first)
    result = upload(client, campaign, b'company_name,website\nA,https://a.example.com\nB,https://b.example.com\n')
    assert result.status_code == 503
    assert result.json()['error']['code'] == 'CAMPAIGN_ARCHIVED'
    assert result.json()['error']['import_report']['accepted'] == 1


def test_chunked_upload_without_content_length_is_bounded(client):
    campaign = setup_campaign(client)
    def body():
        yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="companies.csv"\r\nContent-Type: text/csv\r\n\r\n'
        yield b'x' * (MAX_CSV_BYTES + 100_000)
        yield b'\r\n--boundary--\r\n'
    result = client.post(f"/api/v1/campaigns/{campaign['id']}/imports", content=body(),
                         headers={'Content-Type': 'multipart/form-data; boundary=boundary'})
    assert result.status_code == 413
    assert result.json()['error']['code'] == 'CSV_TOO_LARGE'
