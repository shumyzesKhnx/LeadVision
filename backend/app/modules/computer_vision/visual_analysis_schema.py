from pydantic import Field, model_validator
from app.modules.foundation.common_schema import StrictModel


class VisualMetrics(StrictModel):
    edge_density: float = Field(ge=0, le=1)
    brightness_mean: float = Field(ge=0, le=1)
    brightness_std: float = Field(ge=0, le=1)
    brightness_histogram: list[float] = Field(min_length=16, max_length=16)
    rgb_histograms: dict[str, list[float]]
    dominant_colors: list[dict] = Field(max_length=5)
    low_variation_area_fraction: float = Field(ge=0, le=1)
    original_width: int = Field(gt=0)
    original_height: int = Field(gt=0)
    oriented_width: int = Field(gt=0)
    oriented_height: int = Field(gt=0)
    working_width: int = Field(gt=0)
    working_height: int = Field(gt=0)
    orientation_applied: bool

    @model_validator(mode='after')
    def normalized_histograms(self):
        if set(self.rgb_histograms) != {'red', 'green', 'blue'}:
            raise ValueError('Expected three RGB histograms.')
        for histogram, length in [(self.brightness_histogram, 16), *[(values, 8) for values in self.rgb_histograms.values()]]:
            if len(histogram) != length or any(not 0 <= value <= 1 for value in histogram) or abs(sum(histogram) - 1) > 1e-6:
                raise ValueError('Histograms must be normalized.')
        return self


class VisualResult(StrictModel):
    available: bool
    reason: str | None = None
    metrics: VisualMetrics | None = None
    limitations: list[str]
    review_score: None = None
    calibration_id: None = None

    @model_validator(mode='after')
    def availability(self):
        if self.available != (self.metrics is not None) or self.available == (self.reason is not None):
            raise ValueError('Available results require metrics; unavailable results require a reason.')
        return self
