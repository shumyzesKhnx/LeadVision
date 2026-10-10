from io import BytesIO
import numpy as np
import pytest
from PIL import Image
from app.modules.computer_vision.vision_service import measure
from app.modules.foundation.errors import AppError


def encoded(image, **options):
    output = BytesIO()
    image.save(output, **options)
    return output.getvalue()


def test_uniform_and_grid_metrics_are_deterministic_and_normalized():
    plain = encoded(Image.new('RGB', (80, 40), 'white'), format='PNG')
    uniform = measure(plain)
    grid = np.zeros((80, 80, 3), dtype=np.uint8)
    grid[::8] = 255
    grid[:, ::8] = 255
    content = encoded(Image.fromarray(grid), format='PNG')
    textured = measure(content)
    assert uniform['edge_density'] == 0
    assert uniform['brightness_mean'] == 1 and uniform['brightness_std'] == 0
    assert uniform['low_variation_area_fraction'] == 1
    assert textured['edge_density'] > uniform['edge_density']
    assert textured['low_variation_area_fraction'] < uniform['low_variation_area_fraction']
    assert measure(content) == textured
    assert sum(textured['brightness_histogram']) == pytest.approx(1)
    assert all(sum(hist) == pytest.approx(1) for hist in textured['rgb_histograms'].values())


def test_orientation_and_resize_preserve_original_bytes():
    exif = Image.Exif(); exif[274] = 6
    content = encoded(Image.new('RGB', (1400, 700), 'red'), format='JPEG', exif=exif)
    original = bytes(content)
    result = measure(content)
    assert content == original
    assert result['orientation_applied']
    assert (result['original_width'], result['original_height']) == (1400, 700)
    assert (result['oriented_width'], result['oriented_height']) == (700, 1400)
    assert (result['working_width'], result['working_height']) == (683, 1366)


def test_transparent_pixels_are_composited_on_white():
    content = encoded(Image.new('RGBA', (17, 19), (0, 0, 0, 0)), format='PNG')
    result = measure(content)
    assert result['brightness_mean'] == 1
    assert result['low_variation_area_fraction'] == 1


def test_tall_images_have_bounded_working_height():
    content = encoded(Image.new('RGB', (100, 6000), 'blue'), format='PNG')
    result = measure(content)
    assert result['working_height'] == 2048 and result['working_width'] < 100


def test_invalid_image_is_rejected():
    with pytest.raises(AppError):
        measure(b'invalid')


@pytest.mark.parametrize('kind', ['black', 'white', 'grid', 'gradient', 'noise', 'blocks'])
def test_six_varied_pixel_fixtures_have_bounded_metrics(kind):
    yy, xx = np.indices((96, 128))
    if kind == 'black': pixels = np.zeros((96, 128, 3), dtype=np.uint8)
    elif kind == 'white': pixels = np.full((96, 128, 3), 255, dtype=np.uint8)
    elif kind == 'grid': pixels = np.repeat((((xx // 8 + yy // 8) % 2) * 255)[..., None], 3, axis=2).astype(np.uint8)
    elif kind == 'gradient': pixels = np.repeat((xx * 2)[..., None], 3, axis=2).astype(np.uint8)
    elif kind == 'noise': pixels = np.random.default_rng(42).integers(0, 256, (96, 128, 3), dtype=np.uint8)
    else: pixels = np.stack((xx > 64, yy > 48, xx < 64), axis=2).astype(np.uint8) * 255
    result = measure(encoded(Image.fromarray(pixels), format='PNG'))
    for key in ('edge_density', 'brightness_mean', 'brightness_std', 'low_variation_area_fraction'):
        assert 0 <= result[key] <= 1
    assert result == measure(encoded(Image.fromarray(pixels), format='PNG'))
