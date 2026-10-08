"""Bounded file validation first, then independently committed import rows."""

import csv
import io

from pydantic import ValidationError

from app.core.errors import AppError
from app.db.session import Database
from app.schemas.common import ErrorDetail
from app.schemas.imports import ImportReport, ImportRow
from app.schemas.lead import LeadCreate
from app.services.campaign import require_campaign
from app.services.leads import create_lead
from app.services.maintenance import is_maintenance_active

MAX_CSV_BYTES = 5_000_000
MAX_CSV_ROWS = 100
HEADERS = ['company_name', 'website', 'industry', 'country', 'employee_count', 'contact_name', 'contact_email', 'description', 'notes']
csv.field_size_limit(MAX_CSV_BYTES)


def parse_csv(content: bytes):
    if len(content) > MAX_CSV_BYTES:
        raise AppError('CSV_TOO_LARGE', 'CSV files must be at most 5 MB.', 413)
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise AppError('CSV_INVALID_ENCODING', 'Save the CSV using UTF-8 encoding.', 422) from None
    if '\x00' in text:
        raise AppError('CSV_INVALID_FORMAT', 'CSV cannot contain null bytes.', 422)
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    try:
        raw_headers = next(reader, None)
        headers = [value.strip().casefold() for value in raw_headers or []]
        if len(headers) != len(set(headers)):
            raise AppError('CSV_DUPLICATE_HEADERS', 'CSV column names must be unique.', 422)
        if not {'company_name', 'website'}.issubset(headers):
            raise AppError('CSV_HEADERS_MISSING', 'CSV requires company_name and website columns.', 422)
        if any(not value for value in headers):
            raise AppError('CSV_INVALID_HEADERS', 'Every CSV column needs a name.', 422)
        rows = []
        for row in reader:
            if not row:  # Completely empty separator lines are not data rows.
                continue
            rows.append(row)
            if len(rows) > MAX_CSV_ROWS:
                raise AppError('CSV_ROW_LIMIT', 'CSV imports support at most 100 data rows.', 422)
    except csv.Error:
        raise AppError('CSV_INVALID_FORMAT', 'Check CSV quoting and formatting.', 422) from None
    warnings = ['Extra CSV columns were ignored.'] if set(headers) - set(HEADERS) else []
    return headers, rows, warnings


def row_payload(headers, values, campaign_id: str):
    if len(headers) != len(values):
        raise AppError('CSV_ROW_COLUMNS', 'Row column count does not match its header.', 422)
    payload = {'campaign_id': campaign_id}
    for field, value in zip(headers, values, strict=True):
        if field not in HEADERS:
            continue
        value = value.strip()
        if not value and field not in {'company_name', 'website'}:
            continue
        if field == 'employee_count':
            if not value.isascii() or not value.isdecimal():
                raise AppError('INVALID_EMPLOYEE_COUNT', 'Employee count must be a nonnegative whole number.', 422,
                               [ErrorDetail(field=field, reason='Enter a nonnegative whole number.')])
            # Reject huge integers before Python's digit-conversion resource limit.
            if len(value) > 10:
                raise AppError('INVALID_EMPLOYEE_COUNT', 'Employee count exceeds its maximum.', 422)
            payload[field] = int(value)
        else:
            payload[field] = value
    return LeadCreate.model_validate(payload)


def import_csv(database: Database, campaign_id: str, content: bytes) -> ImportReport:
    headers, rows, warnings = parse_csv(content)
    with database.sessions() as session:
        require_campaign(session, campaign_id, for_work=True)
    report = ImportReport(warnings=warnings)
    for index, values in enumerate(rows):
        row_number = index + 2
        try:
            body = row_payload(headers, values, campaign_id)
        except ValidationError as exc:
            report.items.append(ImportRow(row=row_number, status='invalid', errors=[
                ErrorDetail(field='.'.join(str(part) for part in error['loc'])[:200], reason='Invalid or missing value.')
                for error in exc.errors()[:10]]))
            report.invalid += 1
            continue
        except AppError as exc:
            report.items.append(ImportRow(row=row_number, status='invalid', errors=exc.details or [ErrorDetail(reason=exc.message)]))
            report.invalid += 1
            continue
        try:
            if is_maintenance_active(database):
                raise AppError('MAINTENANCE_MODE', 'Import paused for maintenance.', 503)
            with database.transaction(immediate=True) as session:
                created = create_lead(session, body, origin='import')
        except AppError as exc:
            if exc.code == 'DUPLICATE_DOMAIN':
                report.items.append(ImportRow(row=row_number, status='duplicate', lead_id=exc.details[0].reason,
                                             errors=[ErrorDetail(field='website', reason=exc.message)]))
                report.duplicate += 1
                continue
            if exc.status_code == 422:
                report.items.append(ImportRow(row=row_number, status='invalid', errors=exc.details or [ErrorDetail(reason=exc.message)]))
                report.invalid += 1
                continue
            stop_import(report, rows, index, exc.code)
        except Exception:
            # Every unexpected storage/business failure stops the file and retains its report.
            # Row validation and expected duplicate conflicts were handled above.
            stop_import(report, rows, index, 'IMPORT_STORAGE_FAILURE')
        report.items.append(ImportRow(row=row_number, status='accepted', lead_id=created.id, warnings=created.warnings))
        report.accepted += 1
    return report


def stop_import(report: ImportReport, rows: list, index: int, code: str):
    for remaining in range(index, len(rows)):
        report.items.append(ImportRow(row=remaining + 2, status='not_processed',
                                     errors=[ErrorDetail(reason='Import stopped; retry after resolving the reported failure.')]))
        report.not_processed += 1
    raise AppError(code, 'Import stopped. Earlier accepted rows remain saved; see import_report.', 503,
                   import_report=report.model_dump(mode='json'))
