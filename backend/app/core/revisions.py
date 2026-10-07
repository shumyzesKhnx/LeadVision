"""Use an edit revision to prevent one form overwriting another form's changes."""

import re
from typing import Annotated

from fastapi import Header

from app.core.errors import AppError
from app.schemas.common import ErrorDetail


def expected_revision(
    if_match: Annotated[str | None, Header(alias="If-Match", description='Copy the current ETag, including quotes, e.g. "1".')] = None,
) -> int:
    if if_match is None:
        raise AppError("PRECONDITION_REQUIRED", "Provide If-Match from the latest resource ETag.", 428)
    match = re.fullmatch(r'"([1-9][0-9]{0,9})"', if_match)
    if match is None:
        raise AppError(
            "INVALID_REVISION", 'If-Match must be a quoted positive revision, such as "1".', 422,
            [ErrorDetail(field="header.If-Match", reason="Use the ETag returned by the latest GET.")],
        )
    return int(match.group(1))


def check_revision(current: int, expected: int) -> None:
    if current != expected:
        raise AppError("EDIT_CONFLICT", "This record changed. Reload it before saving.", 409)
