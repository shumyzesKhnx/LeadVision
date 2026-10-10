from io import BytesIO
import struct
import zlib
import pytest
from PIL import Image
from app.modules.foundation.errors import AppError
from app.modules.evidence.image_validation_service import validate_image, MAX_IMAGE_BYTES
from app.modules.evidence.text_extraction_service import validate_saved_text, MAX_TEXT_BYTES


def picture(format='PNG', size=(40, 20), **options):
    output = BytesIO()
    Image.new('RGB', size, 'navy').save(output, format=format, **options)
    return output.getvalue()


@pytest.mark.parametrize('format', ['PNG', 'JPEG'])
def test_static_image_and_bounded_thumbnail(format):
    original = picture(format, (800, 400))
    metadata, thumb = validate_image(original)
    assert metadata['format'] == format
    assert (metadata['width'], metadata['height']) == (800, 400)
    with Image.open(BytesIO(thumb)) as image:
        assert image.format == 'JPEG' and image.size == (400, 200)


def test_exif_orientation_preserves_original_dimensions():
    exif = Image.Exif(); exif[274] = 6
    metadata, thumb = validate_image(picture('JPEG', exif=exif))
    assert (metadata['width'], metadata['height']) == (20, 40)
    assert (metadata['original_width'], metadata['original_height']) == (40, 20)
    assert metadata['orientation_applied']
    with Image.open(BytesIO(thumb)) as image:
        assert image.size == (20, 40) and not image.getexif()


@pytest.mark.parametrize('content', [b'not an image', b'\x89PNG\r\n\x1a\ntruncated', picture('GIF')], ids=['fake', 'truncated', 'gif'])
def test_invalid_images(content):
    with pytest.raises(AppError) as error:
        validate_image(content)
    assert error.value.code == 'INVALID_IMAGE'


def test_animation_and_pixel_bomb_rejected_before_decode():
    output = BytesIO()
    Image.new('RGB', (10, 10), 'red').save(output, format='PNG', save_all=True,
                                       append_images=[Image.new('RGB', (10, 10), 'blue')], duration=100)
    with pytest.raises(AppError, match='INVALID_IMAGE'):
        validate_image(output.getvalue())
    header = struct.pack('>IIBBBBB', 6000, 4000, 8, 2, 0, 0, 0)
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    bomb = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', b'') + chunk(b'IEND', b'')
    with pytest.raises(AppError, match='IMAGE_TOO_LARGE'):
        validate_image(bomb)


def test_byte_limits_and_utf8_text_boundaries():
    with pytest.raises(AppError, match='IMAGE_TOO_LARGE'):
        validate_image(b'x' * (MAX_IMAGE_BYTES + 1))
    text, info = validate_saved_text(b'\xef\xbb\xbf hello\r\nworld ')
    assert text == 'hello\nworld' and not info['truncated']
    text, info = validate_saved_text(('hello ' * 10000).encode())
    assert len(text) == 30000 and info['truncated']
    for content, code in [(b' ', 'EMPTY_TEXT'), (b'\xff', 'INVALID_TEXT'), (b'a\x00b', 'INVALID_TEXT'), (b'x' * (MAX_TEXT_BYTES + 1), 'TEXT_TOO_LARGE')]:
        with pytest.raises(AppError, match=code):
            validate_saved_text(content)
