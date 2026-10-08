"""Saved readable text validation; live HTML extraction follows at the live milestone."""
from app.core.errors import AppError

MAX_TEXT_BYTES = 1_000_000
MAX_TEXT_CHARACTERS = 30_000


def validate_saved_text(content: bytes):
    if len(content) > MAX_TEXT_BYTES:
        raise AppError('TEXT_TOO_LARGE', 'Saved text must be at most 1 MB.', 413)
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise AppError('INVALID_TEXT', 'Save the text file as UTF-8.', 422) from None
    if '\x00' in text:
        raise AppError('INVALID_TEXT', 'Choose a readable UTF-8 text file.', 422)
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        raise AppError('EMPTY_TEXT', 'The text file has no readable content.', 422)
    truncated = len(text) > MAX_TEXT_CHARACTERS
    return text[:MAX_TEXT_CHARACTERS], {'characters': min(len(text), MAX_TEXT_CHARACTERS),
                                      'original_characters': len(text), 'truncated': truncated}
