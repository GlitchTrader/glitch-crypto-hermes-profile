"""Strict attributable learning episode, lesson, and promotion contracts."""
from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from cognition_contracts import body_hash, canonical_json

EPISODE_SCHEMA = "glitch.crypto.learning-episode.v1"
LESSON_SCHEMA = "glitch.crypto.lesson-proposal.v1"
PROMOTION_SCHEMA = "glitch.crypto.promotion-decision.v1"
TRADING_LANES = {"market_model", "decision_metacognition", "portfolio_management"}
ALL_LANES = TRADING_LANES | {"operational"}
EPISODE_TYPES = {
    "completed_trade",
    "matured_no_trade",
    "decision_review",
    "position_management",
    "operational_fault",
}
PROMOTION_ACTIONS = {"ACTIVATE", "REJECT", "RETIRE"}


class LearningContractError(ValueError):
    """A fail-closed learning evidence or governance violation."""


def validate_learning_episode(value: Any) -> dict[str, Any]:
    episode = _object(value, "learning episode")
    required = {
        "schema_version",
        "episode_id",
        "lane",
        "episode_type",
        "occurred_utc",
        "correlation_group",
        "evidence_refs",
        "summary",
        "treatment",
        "metrics",
    }
    optional = {"realized_pnl_usd"}
    _exact_keys(episode, required, "learning episode", optional)
    if episode.get("schema_version") != EPISODE_SCHEMA:
        raise LearningContractError(f"learning episode schema must be {EPISODE_SCHEMA}")
    lane = _enum(episode.get("lane"), ALL_LANES, "learning lane")
    episode_type = _enum(episode.get("episode_type"), EPISODE_TYPES, "episode type")
    if (lane == "operational") != (episode_type == "operational_fault"):
        raise LearningContractError("operational faults and trading-learning lanes must remain separate")
    if lane == "portfolio_management" and episode_type not in {"completed_trade", "position_management"}:
        raise LearningContractError("portfolio-management lane requires trade or management evidence")
    if episode_type == "completed_trade" and "realized_pnl_usd" not in episode:
        raise LearningContractError("completed trade episode requires realized PnL")
    if episode_type != "completed_trade" and "realized_pnl_usd" in episode:
        raise LearningContractError("only completed trades may report realized PnL")

    evidence_refs = _unique_text_list(episode.get("evidence_refs"), "evidence references", minimum=1)
    metrics = _metrics(episode.get("metrics"))
    if episode_type == "matured_no_trade" and any(key.lower().startswith("realized") for key in metrics):
        raise LearningContractError("no-trade counterfactual cannot be represented as realized performance")
    normalized = dict(episode)
    normalized.update({
        "episode_id": _canonical_uuid(episode.get("episode_id"), "episode ID"),
        "lane": lane,
        "episode_type": episode_type,
        "occurred_utc": _format_utc(_utc(episode.get("occurred_utc"), "episode time")),
        "correlation_group": _text(episode.get("correlation_group"), "correlation group", 200),
        "evidence_refs": evidence_refs,
        "summary": _text(episode.get("summary"), "episode summary", 2000),
        "treatment": validate_treatment_identity(episode.get("treatment")),
        "metrics": metrics,
    })
    if "realized_pnl_usd" in episode:
        normalized["realized_pnl_usd"] = _finite_number(episode["realized_pnl_usd"], "realized PnL")
    return normalized


def validate_treatment_identity(value: Any) -> dict[str, Any]:
    treatment = _object(value, "treatment identity")
    required = {
        "model_provider",
        "model_id",
        "reasoning_effort",
        "soul_hash",
        "prompt_hash",
        "skill_hashes",
        "memory_version",
        "numerical_model_versions",
        "feature_version",
    }
    _exact_keys(treatment, required, "treatment identity")
    skill_hashes = _version_map(treatment.get("skill_hashes"), "skill hashes", require_hash=True)
    numerical_versions = _version_map(
        treatment.get("numerical_model_versions"),
        "numerical model versions",
        require_hash=False,
    )
    return {
        "model_provider": _text(treatment.get("model_provider"), "model provider", 200),
        "model_id": _text(treatment.get("model_id"), "model ID", 200),
        "reasoning_effort": _text(treatment.get("reasoning_effort"), "reasoning effort", 100),
        "soul_hash": _sha256(treatment.get("soul_hash"), "SOUL hash"),
        "prompt_hash": _sha256(treatment.get("prompt_hash"), "prompt hash"),
        "skill_hashes": skill_hashes,
        "memory_version": _text(treatment.get("memory_version"), "memory version", 200),
        "numerical_model_versions": numerical_versions,
        "feature_version": _text(treatment.get("feature_version"), "feature version", 200),
    }


def validate_lesson_proposal(value: Any) -> dict[str, Any]:
    lesson = _object(value, "lesson proposal")
    required = {
        "schema_version",
        "lesson_id",
        "lane",
        "claim",
        "conditions",
        "supporting_episode_ids",
        "contradicting_episode_ids",
        "contradiction_disposition",
        "contradiction_review",
        "confidence",
        "metric",
        "created_utc",
        "expires_utc",
        "rollback_condition",
        "status",
    }
    _exact_keys(lesson, required, "lesson proposal")
    if lesson.get("schema_version") != LESSON_SCHEMA:
        raise LearningContractError(f"lesson schema must be {LESSON_SCHEMA}")
    if lesson.get("status") != "proposed":
        raise LearningContractError("new lessons must begin in proposed status")
    created = _utc(lesson.get("created_utc"), "lesson creation time")
    expires = _utc(lesson.get("expires_utc"), "lesson expiry time")
    if expires <= created:
        raise LearningContractError("lesson expiry must follow creation")
    supports = _uuid_list(lesson.get("supporting_episode_ids"), "supporting episode IDs", minimum=1)
    contradictions = _uuid_list(lesson.get("contradicting_episode_ids"), "contradicting episode IDs", minimum=0)
    if set(supports) & set(contradictions):
        raise LearningContractError("one episode cannot both support and contradict a lesson")
    disposition = _enum(
        lesson.get("contradiction_disposition"),
        {"none", "bounded", "unresolved"},
        "contradiction disposition",
    )
    if not contradictions and disposition != "none":
        raise LearningContractError("lesson without contradictions must use none disposition")
    if contradictions and disposition == "none":
        raise LearningContractError("lesson with contradictions must review their disposition")
    confidence = _finite_number(lesson.get("confidence"), "lesson confidence")
    if not 0 <= confidence <= 1:
        raise LearningContractError("lesson confidence must be between 0 and 1")
    return {
        "schema_version": LESSON_SCHEMA,
        "lesson_id": _canonical_uuid(lesson.get("lesson_id"), "lesson ID"),
        "lane": _enum(lesson.get("lane"), TRADING_LANES, "lesson lane"),
        "claim": _text(lesson.get("claim"), "lesson claim", 2000),
        "conditions": _unique_text_list(lesson.get("conditions"), "lesson conditions", minimum=1),
        "supporting_episode_ids": supports,
        "contradicting_episode_ids": contradictions,
        "contradiction_disposition": disposition,
        "contradiction_review": _text(lesson.get("contradiction_review"), "contradiction review", 2000),
        "confidence": confidence,
        "metric": _text(lesson.get("metric"), "lesson metric", 500),
        "created_utc": _format_utc(created),
        "expires_utc": _format_utc(expires),
        "rollback_condition": _text(lesson.get("rollback_condition"), "rollback condition", 1000),
        "status": "proposed",
    }


def validate_promotion_decision(value: Any) -> dict[str, Any]:
    decision = _object(value, "promotion decision")
    required = {
        "schema_version",
        "decision_id",
        "lesson_id",
        "action",
        "actor",
        "human_approval_id",
        "decided_utc",
        "reason",
    }
    _exact_keys(decision, required, "promotion decision")
    if decision.get("schema_version") != PROMOTION_SCHEMA:
        raise LearningContractError(f"promotion schema must be {PROMOTION_SCHEMA}")
    if decision.get("actor") != "human":
        raise LearningContractError("lesson promotion actor must be human")
    return {
        "schema_version": PROMOTION_SCHEMA,
        "decision_id": _canonical_uuid(decision.get("decision_id"), "decision ID"),
        "lesson_id": _canonical_uuid(decision.get("lesson_id"), "lesson ID"),
        "action": _enum(decision.get("action"), PROMOTION_ACTIONS, "promotion action"),
        "actor": "human",
        "human_approval_id": _text(decision.get("human_approval_id"), "human approval ID", 500),
        "decided_utc": _format_utc(_utc(decision.get("decided_utc"), "decision time")),
        "reason": _text(decision.get("reason"), "promotion reason", 2000),
    }


def _metrics(value: Any) -> dict[str, float]:
    metrics = _object(value, "episode metrics")
    if not metrics:
        raise LearningContractError("episode metrics must not be empty")
    normalized: dict[str, float] = {}
    for key, item in metrics.items():
        name = _text(key, "metric name", 200)
        normalized[name] = _finite_number(item, f"metric {name}")
    return normalized


def _version_map(value: Any, name: str, *, require_hash: bool) -> dict[str, str]:
    items = _object(value, name)
    if not items:
        raise LearningContractError(f"{name} must not be empty")
    result: dict[str, str] = {}
    for key, item in items.items():
        map_key = _text(key, f"{name} key", 200)
        result[map_key] = _sha256(item, f"{name} value") if require_hash else _text(item, f"{name} value", 200)
    return result


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LearningContractError(f"{name} must be an object")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], name: str, optional: set[str] | None = None) -> None:
    optional = optional or set()
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing or unknown:
        raise LearningContractError(f"{name} fields invalid: missing={missing}, unknown={unknown}")


def _enum(value: Any, allowed: set[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise LearningContractError(f"{name} must be one of {sorted(allowed)}")
    return value


def _canonical_uuid(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise LearningContractError(f"{name} must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise LearningContractError(f"{name} must be a UUID string") from error
    canonical = str(parsed)
    if value.lower() != canonical or parsed.version not in {1, 2, 3, 4, 5}:
        raise LearningContractError(f"{name} must be a canonical UUID")
    return canonical


def _uuid_list(value: Any, name: str, *, minimum: int) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise LearningContractError(f"{name} must contain at least {minimum} items")
    result = [_canonical_uuid(item, name) for item in value]
    if len(set(result)) != len(result):
        raise LearningContractError(f"{name} must not contain duplicates")
    return result


def _unique_text_list(value: Any, name: str, *, minimum: int) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise LearningContractError(f"{name} must contain at least {minimum} items")
    result = [_text(item, name, 1000) for item in value]
    if len(set(result)) != len(result):
        raise LearningContractError(f"{name} must not contain duplicates")
    return result


def _text(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise LearningContractError(f"{name} must contain 1-{maximum} characters")
    return value.strip()


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise LearningContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LearningContractError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise LearningContractError(f"{name} must be finite")
    return number


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LearningContractError(f"{name} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise LearningContractError(f"{name} must be ISO-8601") from error
    if parsed.tzinfo != timezone.utc:
        raise LearningContractError(f"{name} must be UTC")
    return parsed


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "EPISODE_SCHEMA",
    "LESSON_SCHEMA",
    "PROMOTION_SCHEMA",
    "LearningContractError",
    "body_hash",
    "canonical_json",
    "validate_learning_episode",
    "validate_lesson_proposal",
    "validate_promotion_decision",
    "validate_treatment_identity",
]
