"""Strict cognition event and gateway intent contracts."""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

EVENT_SCHEMA = "glitch.crypto.cognition-event.v1"
INTENT_SCHEMA = "glitch.crypto.intent.v1"
EVENT_TYPES = {"CANDIDATE", "POSITION"}
ENTRY_ACTIONS = {"ENTER_LONG", "ENTER_SHORT"}
MANAGEMENT_ACTIONS = {"HOLD", "MOVE_STOP", "MOVE_TARGET", "REDUCE", "EXIT"}
ALL_ACTIONS = ENTRY_ACTIONS | MANAGEMENT_ACTIONS | {"NOTHING"}
SENSITIVE_NAMES = {
    "api_key",
    "api_secret",
    "authorization",
    "jwt",
    "private_key",
    "seed_phrase",
    "signature",
}


class ContractError(ValueError):
    """A fail-closed schema or authority violation."""


def validate_cognition_event(value: Any) -> dict[str, Any]:
    event = _object(value, "cognition event")
    event_type = _enum(event.get("event_type"), EVENT_TYPES, "event type")
    required = {
        "schema_version",
        "event_id",
        "event_type",
        "packet_id",
        "created_utc",
        "expires_utc",
        "reason",
        "trigger",
    }
    if event_type == "POSITION":
        required.add("tranche_id")
    _exact_keys(event, required, "cognition event")
    if event.get("schema_version") != EVENT_SCHEMA:
        raise ContractError(f"cognition event schema must be {EVENT_SCHEMA}")
    event_id = _canonical_uuid(event.get("event_id"), "event ID")
    packet_id = _packet_id(event.get("packet_id"))
    created = _utc(event.get("created_utc"), "created UTC")
    expires = _utc(event.get("expires_utc"), "expires UTC")
    if expires <= created:
        raise ContractError("cognition event expiry must follow creation")
    reason = _bounded_text(event.get("reason"), "event reason")
    trigger = _object(event.get("trigger"), "event trigger")
    _reject_sensitive_names(trigger)
    normalized: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA,
        "event_id": event_id,
        "event_type": event_type,
        "packet_id": packet_id,
        "created_utc": _format_utc(created),
        "expires_utc": _format_utc(expires),
        "reason": reason,
        "trigger": trigger,
    }
    if event_type == "POSITION":
        normalized["tranche_id"] = _bounded_text(event.get("tranche_id"), "tranche ID", 200)
    return normalized


def parse_model_intent(raw: str, packet: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Parse one JSON object; the only repair is removing one outer JSON fence."""
    if not isinstance(raw, str) or not raw.strip():
        raise ContractError("model output must be non-empty text")
    if len(raw.encode("utf-8")) > 1_000_000:
        raise ContractError("model output exceeds 1 MB")
    text = raw.strip()
    repaired = False
    try:
        value = json.loads(text)
    except json.JSONDecodeError as direct_error:
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            raise ContractError("model output must be exactly one JSON object") from direct_error
        repaired = True
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError as repair_error:
            raise ContractError("bounded outer-fence repair did not yield JSON") from repair_error
    return validate_intent(value, packet), repaired


def validate_intent(value: Any, packet: dict[str, Any]) -> dict[str, Any]:
    intent = _object(value, "intent")
    action = _enum(intent.get("action"), ALL_ACTIONS, "intent action")
    required = {
        "schema_version",
        "intent_id",
        "packet_id",
        "account",
        "instrument",
        "action",
        "reason",
    }
    optional: set[str] = set()
    if action in ENTRY_ACTIONS:
        required |= {"stop_price", "target_price"}
        optional |= {"requested_risk_pct", "requested_leverage"}
    elif action == "HOLD" or action == "EXIT":
        required.add("tranche_id")
    elif action == "MOVE_STOP":
        required |= {"tranche_id", "stop_price"}
    elif action == "MOVE_TARGET":
        required |= {"tranche_id", "target_price"}
    elif action == "REDUCE":
        required |= {"tranche_id", "reduce_fraction_pct"}
    _exact_keys(intent, required, "intent", optional)
    if intent.get("schema_version") != INTENT_SCHEMA:
        raise ContractError(f"intent schema must be {INTENT_SCHEMA}")

    state = _object(packet.get("state"), "packet state")
    account = _object(state.get("account"), "packet account")
    market = _object(state.get("market"), "packet market")
    execution = _object(packet.get("execution"), "packet execution")
    supported = execution.get("supported_actions")
    if not isinstance(supported, list) or any(not isinstance(item, str) for item in supported):
        raise ContractError("packet supported actions must be a string array")
    if action not in supported:
        raise ContractError("intent action is not supported by the current packet")

    packet_id = _packet_id(packet.get("packet_id"))
    if intent.get("packet_id") != packet_id:
        raise ContractError("intent packet ID does not match current packet")
    account_alias = _bounded_text(account.get("alias"), "packet account alias", 200)
    if intent.get("account") != account_alias:
        raise ContractError("intent account does not match current packet")
    instrument = _bounded_text(market.get("instrument"), "packet instrument", 100)
    if intent.get("instrument") != instrument:
        raise ContractError("intent instrument does not match current packet")

    normalized = dict(intent)
    normalized["intent_id"] = _canonical_uuid(intent.get("intent_id"), "intent ID")
    normalized["reason"] = _bounded_text(intent.get("reason"), "intent reason")
    mark = _positive_number(market.get("mark_price"), "packet mark price")
    if action in ENTRY_ACTIONS:
        stop = _positive_number(intent.get("stop_price"), "stop price")
        target = _positive_number(intent.get("target_price"), "target price")
        _entry_geometry(action, mark, stop, target)
        normalized["stop_price"] = stop
        normalized["target_price"] = target
        if "requested_risk_pct" in intent:
            normalized["requested_risk_pct"] = _positive_number(
                intent["requested_risk_pct"], "requested risk percentage"
            )
        if "requested_leverage" in intent:
            normalized["requested_leverage"] = _positive_integer(
                intent["requested_leverage"], "requested leverage"
            )
    elif action in MANAGEMENT_ACTIONS:
        tranche_id, position = _packet_position(intent.get("tranche_id"), state)
        normalized["tranche_id"] = tranche_id
        side = position.get("side")
        if side not in {"LONG", "SHORT"}:
            raise ContractError("packet position side must be LONG or SHORT")
        if action == "MOVE_STOP":
            stop = _positive_number(intent.get("stop_price"), "stop price")
            if (side == "LONG" and stop >= mark) or (side == "SHORT" and stop <= mark):
                raise ContractError("stop is not on the protective side of current mark")
            normalized["stop_price"] = stop
        elif action == "MOVE_TARGET":
            target = _positive_number(intent.get("target_price"), "target price")
            if (side == "LONG" and target <= mark) or (side == "SHORT" and target >= mark):
                raise ContractError("target is not on the objective side of current mark")
            normalized["target_price"] = target
        elif action == "REDUCE":
            fraction = _positive_number(intent.get("reduce_fraction_pct"), "reduction percentage")
            if fraction >= 100:
                raise ContractError("reduction percentage must be less than 100")
            normalized["reduce_fraction_pct"] = fraction
    _reject_sensitive_names(normalized)
    return normalized


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def body_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _packet_position(value: Any, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    tranche_id = _bounded_text(value, "tranche ID", 200)
    positions = state.get("positions")
    if not isinstance(positions, list):
        raise ContractError("packet positions must be an array")
    for item in positions:
        position = _object(item, "packet position")
        if position.get("tranche_id") == tranche_id:
            return tranche_id, position
    raise ContractError("intent tranche is not present in the current packet")


def _entry_geometry(action: str, mark: float, stop: float, target: float) -> None:
    if action == "ENTER_LONG" and not stop < mark < target:
        raise ContractError("long entry requires stop below mark and target above mark")
    if action == "ENTER_SHORT" and not target < mark < stop:
        raise ContractError("short entry requires target below mark and stop above mark")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be an object")
    return value


def _exact_keys(
    value: dict[str, Any],
    required: set[str],
    name: str,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing or unknown:
        raise ContractError(f"{name} fields invalid: missing={missing}, unknown={unknown}")


def _enum(value: Any, allowed: set[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{name} must be one of {sorted(allowed)}")
    return value


def _canonical_uuid(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise ContractError(f"{name} must be a UUID string") from error
    canonical = str(parsed)
    if canonical != value.lower() or parsed.version not in {1, 2, 3, 4, 5}:
        raise ContractError(f"{name} must be a canonical UUID")
    return canonical


def _packet_id(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ContractError("packet ID must be a lowercase SHA-256 digest")
    return value


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{name} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ContractError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise ContractError(f"{name} must be UTC")
    return parsed


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _bounded_text(value: Any, name: str, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ContractError(f"{name} must contain 1-{maximum} characters")
    return value.strip()


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ContractError(f"{name} must be finite and positive")
    return number


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{name} must be a positive integer")
    return value


def _reject_sensitive_names(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in SENSITIVE_NAMES:
                raise ContractError(f"credential-bearing field is forbidden: {key}")
            _reject_sensitive_names(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive_names(item)
