"""Versioned industrial Agent contracts. Scopes are issued by the server."""
import hashlib
import json
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Outcome(StrEnum):
    SUCCESS = "success"
    NEEDS_EVIDENCE = "needs_evidence"
    HANDOFF = "handoff_required"
    RETRYABLE = "retryable_failure"
    FAILED = "terminal_failure"


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str
    tenant_id: str
    project_id: str
    factory_id: str = "demo-factory"
    stage: Literal["analysis", "review", "archived"] = "analysis"


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    capability: str
    agent_version: str = "1.0.0"
    depends_on: tuple[str, ...] = ()
    required: bool = True
    condition: Literal["always", "conflict"] = "always"
    max_attempts: int = Field(default=2, ge=1, le=2)


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Outcome = Outcome.SUCCESS
    patch: dict = Field(default_factory=dict)
    evidence: list[dict] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    handoff: dict | None = None


class QueryIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric: Literal["batch_count", "batch_overlimit_rate", "parameter_overlimit_rate", "data_completeness"]
    group_by: Literal["total", "device_id", "day", "batch_id"] = "total"
    start: str
    end: str
    batch_id: str = ""
    limit: int = Field(default=100, ge=1, le=200)
