import pytest
from app.modules.foundation.errors import AppError
from app.modules.leads.csv_import_service import MAX_CSV_BYTES, parse_csv, row_payload


@pytest.mark.parametrize('content,code', [
    (b'website\nhttps://example.com\n', 'CSV_HEADERS_MISSING'),
    (b'company_name,website,website\n', 'CSV_DUPLICATE_HEADERS'),
    (b'company_name,website,\n', 'CSV_INVALID_HEADERS'),
    (b'company_name,website\n\xff', 'CSV_INVALID_ENCODING'),
    (b'company_name,website\n\x00', 'CSV_INVALID_FORMAT'),
    (b'company_name,website\n"unclosed', 'CSV_INVALID_FORMAT'),
    (b'company_name,website\n' + b'Name,https://example.com\n' * 101, 'CSV_ROW_LIMIT'),
    (b'x' * (MAX_CSV_BYTES + 1), 'CSV_TOO_LARGE'),
], ids=['missing-headers', 'duplicate-headers', 'blank-header', 'invalid-utf8',
        'null-byte', 'bad-quoting', 'too-many-rows', 'too-large'])
def test_file_errors_before_import(content, code):
    with pytest.raises(AppError, match=code):
        parse_csv(content)


def test_bom_unicode_quoted_commas_and_exact_size_boundary():
    headers, rows, warnings = parse_csv('\ufeffcompany_name,website,extra\r\n"شرکت, Demo",https://example.com,x\r\n'.encode())
    assert rows[0][0] == 'شرکت, Demo'
    assert warnings
    prefix = b'company_name,website\n'
    assert parse_csv(prefix + b'x' * (MAX_CSV_BYTES - len(prefix)))[1]


def test_csv_empty_values_stay_missing_and_zero_is_preserved():
    headers = ['company_name', 'website', 'employee_count', 'country']
    profile = row_payload(headers, ['Company', 'https://example.com', '', ''], '12345678-1234-1234-1234-123456789012')
    assert profile.employee_count is None
    assert profile.country is None
    assert row_payload(headers, ['Company', 'https://example.com', '0', 'PK'], str(profile.campaign_id)).employee_count == 0
