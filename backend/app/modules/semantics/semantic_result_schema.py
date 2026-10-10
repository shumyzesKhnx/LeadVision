from pydantic import Field, model_validator
from app.modules.foundation.common_schema import StrictModel


class SemanticValue(StrictModel):
    available: bool
    reason: str | None = None
    raw_cosine: float | None = Field(default=None, ge=-1, le=1)
    normalized_similarity: float | None = Field(default=None, ge=0, le=100)
    interpretation: str = 'Text similarity, not a probability of fit or conversion.'

    @model_validator(mode='after')
    def coherent(self):
        if self.available:
            if self.raw_cosine is None or self.normalized_similarity is None or self.reason is not None:
                raise ValueError('Available similarity requires both values.')
        elif self.raw_cosine is not None or self.normalized_similarity is not None or not self.reason:
            raise ValueError('Unavailable similarity requires a reason and null values.')
        return self
