"""Phase 1 contract. Missing data is nullable; unknown fields and non-finite values fail."""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class EvidenceStatus(StrEnum):
    MEASURED = "MEASURED"
    DOCUMENTED = "DOCUMENTED"
    IMPORTED = "IMPORTED"
    ASSUMED = "ASSUMED"
    AI_INFERRED = "AI_INFERRED"
    MISSING = "MISSING"


class Building(Contract):
    use: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=200)
    region: str = Field(min_length=1, max_length=40)
    area_m2: float = Field(gt=0, le=10000000)
    floors: int | None = Field(default=None, gt=0, le=300)
    floor_height_m: float | None = Field(default=None, gt=0, le=50)
    window_wall_ratio: float | None = Field(default=None, ge=0, le=1)
    envelope: str | None = Field(default=None, max_length=4000)
    hvac: str | None = Field(default=None, max_length=4000)
    schedules: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="before")
    @classmethod
    def reject_boolean_numbers(cls, value):
        if isinstance(value, dict):
            for key in ("area_m2", "floors", "floor_height_m", "window_wall_ratio"):
                if isinstance(value.get(key), bool):
                    raise ValueError(key + " cannot be boolean")
        return value


class ProjectCreate(Contract):
    name: str = Field(min_length=1, max_length=160)
    building: Building
    data_nature: Literal["user_project", "engineering_reference"] = "user_project"


class Project(ProjectCreate):
    project_id: str
    revision: int
    created_at: str
    updated_at: str


class BuildingUpdate(Contract):
    expected_revision: int = Field(ge=1)
    building: Building


class EvidenceCreate(Contract):
    type: Literal["drawing", "bill", "equipment_table", "bim", "idf", "epw", "sensor", "manual_input", "literature", "assumption", "ai_inference"]
    name: str = Field(min_length=1, max_length=160)
    source_file: str | None = None
    source_locator: str = Field(min_length=1, max_length=1000)
    value: JsonValue = None
    unit: str | None = Field(default=None, max_length=80)
    authority: str = Field(min_length=1, max_length=300)
    permission: str = Field(min_length=1, max_length=1000)
    uncertainty: str | None = Field(default=None, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    acquisition_method: str = Field(min_length=1, max_length=300)
    responsible_person: str = Field(min_length=1, max_length=100)
    status: EvidenceStatus = EvidenceStatus.IMPORTED
    scheme_id: Literal["baseline", "R1", "R2"] | None = None

    @model_validator(mode="after")
    def require_model_file(self):
        if self.type in {"idf", "epw"} and not self.source_file:
            raise ValueError("IDF/EPW evidence requires a registered file")
        if self.type == "idf" and self.scheme_id is None:
            raise ValueError("IDF requires scheme_id")
        if self.type != "idf" and self.scheme_id is not None:
            raise ValueError("Only IDF binds a scheme")
        return self


class Evidence(EvidenceCreate):
    evidence_id: str
    project_id: str
    revision: int
    timestamp: str
    hash: str
    review_state: Literal["pending", "confirmed", "rejected"] = "pending"
    review_note: str | None = None


class EvidenceReview(Contract):
    expected_revision: int = Field(ge=1)
    review_state: Literal["confirmed", "rejected", "pending"]
    responsible_person: str = Field(min_length=1, max_length=100)
    review_note: str = Field(min_length=5, max_length=2000)


class RunCreate(Contract):
    project_id: str
    scheme_id: Literal["baseline", "R1", "R2"]
    factor_profile_id: str = "none"


class Provenance(Contract):
    run_id: str
    project_id: str
    case_id: str
    scheme_id: str
    model_hash: str
    weather_hash: str
    engine_version: str
    code_version: str
    parser_version: str
    factor_version: str
    timestamp: str


class RunView(Contract):
    run_id: str
    project_id: str
    case_id: str
    scheme_id: str
    status: Literal["queued", "running", "succeeded", "failed", "stale"]
    data_nature: str
    created_at: str
    finished_at: str | None = None
    metrics: dict | None = None
    carbon: dict | None = None
    provenance: Provenance | None = None
    error: str | None = None
    stale_reasons: list[str] = Field(default_factory=list)
    warnings_count: int | None = None
    review_status: str = "pending_engineer_review"
    engine_calls_executed: int = 0
    limitations: list[str] = Field(default_factory=list)


class ComparisonRequest(Contract):
    run_ids: list[str] = Field(min_length=2, max_length=3)
