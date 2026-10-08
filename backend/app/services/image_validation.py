"""Validate bounded static PNG/JPEG; preserve original and derive oriented thumbnail."""
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from app.core.errors import AppError

MAX_IMAGE_BYTES = 10_000_000
MAX_IMAGE_PIXELS = 20_000_000


def validate_image(content: bytes):
    if len(content) > MAX_IMAGE_BYTES:
        raise AppError('IMAGE_TOO_LARGE', 'Images must be at most 10 MB.', 413)
    signature = 'PNG' if content.startswith(b'\x89PNG\r\n\x1a\n') else ('JPEG' if content.startswith(b'\xff\xd8\xff') else None)
    if signature is None:
        raise AppError('INVALID_IMAGE', 'Choose a valid static PNG or JPEG image.', 422)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=['PNG', 'JPEG']) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise AppError('IMAGE_TOO_LARGE', 'Images must have at most 20 million pixels.', 413)
                if source.format != signature or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Animated/mismatched image')
                source.verify()
            with Image.open(BytesIO(content), formats=['PNG', 'JPEG']) as source:
                source.load()
                working = ImageOps.exif_transpose(source)
                width, height = working.size
                thumbnail = working.copy()
                thumbnail.thumbnail((400, 300), Image.Resampling.LANCZOS)
                thumbnail = thumbnail.convert('RGB')
                buffer = BytesIO()
                thumbnail.save(buffer, format='JPEG', quality=85)
                return {'format': signature, 'width': width, 'height': height,
                        'original_width': source.width, 'original_height': source.height,
                        'orientation_applied': working.size != source.size or source.getexif().get(274, 1) != 1,
                        'thumbnail_width': thumbnail.width, 'thumbnail_height': thumbnail.height}, buffer.getvalue()
    except AppError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AppError('IMAGE_TOO_LARGE', 'The decoded image exceeds the safety limit.', 413) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise AppError('INVALID_IMAGE', 'Choose a complete static PNG or JPEG image.', 422) from None
