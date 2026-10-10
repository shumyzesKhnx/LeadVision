"""Versioned deterministic measurements; no visual-quality score or calibration."""
import cv2
import numpy as np
import PIL
from typing import Literal
from pydantic import Field
from app.modules.foundation.common_schema import StrictModel


class VisionConfig(StrictModel):
    version: Literal['visual_metrics_v1'] = 'visual_metrics_v1'
    max_width: int = Field(default=683, ge=16, le=2048)
    max_height: int = Field(default=2048, ge=16, le=4096)
    canny_low: Literal[100] = 100
    canny_high: Literal[200] = 200
    tile_size: Literal[16] = 16
    low_variation_std: Literal[5] = 5


def vision_identity():
    return {'config': VisionConfig().model_dump(), 'libraries': {'opencv': cv2.__version__,
            'numpy': np.__version__, 'pillow': PIL.__version__}, 'interpolation': 'INTER_AREA',
            'grayscale': 'OpenCV COLOR_RGB2GRAY, uint8; weights R=.299 G=.587 B=.114',
            'canny': {'aperture': 3, 'l2gradient': True, 'additional_blur': False},
            'alpha_background': 'white', 'opencv_threads': 1, 'opencl': False,
            'brightness_bin_edges': list(range(0, 257, 16)),
            'rgb_bin_edges': list(range(0, 257, 32)), 'dominant_color_bin_width': 32,
            'histogram_normalization': 'count / working pixels',
            'boundary_tiles': 'include partial tiles weighted by their pixel area'}
