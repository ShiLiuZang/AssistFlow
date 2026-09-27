from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )


class CostReportMeta(ReportModel):
    source: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    scope: Literal["provided_generations"]
    pricing_basis: Literal["input_output_only"]


class CostReportRow(ReportModel):
    intent: str = Field(min_length=1)
    requests: int = Field(ge=0)
    generations: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    unknown_usage: int = Field(ge=0)
    unpriced: int = Field(ge=0)

    priced_subtotals: dict[str, str]
    price_versions: list[str]
    estimate_complete: bool

    duration_samples: int = Field(ge=0)
    p95_generation_ms: float | None = Field(ge=0)


class CostReportSummary(ReportModel):
    requests: int = Field(ge=0)
    generations: int = Field(ge=0)
    known_input_tokens: int = Field(ge=0)
    known_output_tokens: int = Field(ge=0)
    unknown_usage: int = Field(ge=0)
    unpriced: int = Field(ge=0)
    usage_complete: bool
    estimate_complete: bool


class CostReport(ReportModel):
    schema_version: Literal[1]
    meta: CostReportMeta
    rows: list[CostReportRow]
    summary: CostReportSummary