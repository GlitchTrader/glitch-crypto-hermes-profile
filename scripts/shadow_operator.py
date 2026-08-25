"""Run the real Glitch Crypto live-shadow cognition loop.

This worker consumes only gateway decision events. It calls Hermes once per fresh
event, validates one strict intent, and submits it back to the paper/shadow gateway.
No exchange credential or direct venue method is available in this process.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cognition_contracts import ContractError, parse_model_intent
from gateway_client import GatewayClient, profile_root

PROFILE = "glitch-crypto"
SESSION_NAME = "Glitch Crypto Trading"
MAXIMUM_SEEN_EVENTS = 1_000


def launch_shadow_operator() -> dict[str, Any]:
    root = profile_root()
    paths = _paths(root)
    paths["state_dir"].mkdir(parents=True, exist_ok=True)
    existing = _read_pid(paths["pid"])
    if existing is not None and _pid_alive(existing):
        return {"started": False, "already_running": True, "pid": existing}

    hermes = os.environ.get("HERMES_EXECUTABLE") or shutil.which("hermes")
    if not hermes:
        raise RuntimeError("hermes executable was not found")
    log = paths["log"].open("a", encoding="utf-8", newline="\n")
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--run", "--hermes", hermes],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        close_fds=True,
        env=_sanitized_environment(os.environ),
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    log.close()
    _write_text_atomic(paths["pid"], f"{process.pid}\n")
    return {"started": True, "already_running": False, "pid": process.pid}


def shadow_operator_status() -> dict[str, Any]:
    paths = _paths(profile_root())
    pid = _read_pid(paths["pid"])
    state = _read_json(paths["state"], {})
    return {
        "running": pid is not None and _pid_alive(pid),
        "pid": pid,
        "last_event_id": state.get("last_event_id"),
        "last_result": state.get("last_result"),
        "updated_utc": state.get("updated_utc"),
    }


def run_shadow_operator(
    *,
    hermes_executable: str,
    client: GatewayClient | None = None,
    sleep: Any = time.sleep,
) -> int:
    root = profile_root()
    paths = _paths(root)
    paths["state_dir"].mkdir(parents=True, exist_ok=True)
    gateway = client or GatewayClient()
    poll_seconds = _bounded_float(
        os.environ.get("GLITCH_CRYPTO_OPERATOR_POLL_SECONDS"), 0.5, 0.1, 30.0
    )
    minimum_interval = _bounded_float(
        os.environ.get("GLITCH_CRYPTO_OPERATOR_MIN_INTERVAL_SECONDS"),
        5.0,
        0.0,
        300.0,
    )
    model_timeout = _bounded_float(
        os.environ.get("GLITCH_CRYPTO_OPERATOR_MODEL_TIMEOUT_SECONDS"),
        120.0,
        5.0,
        900.0,
    )
    state = _read_json(paths["state"], {})
    seen = [item for item in state.get("seen_event_ids", []) if isinstance(item, str)]
    seen_set = set(seen)
    last_model_call = 0.0
    _append_jsonl(paths["events"], {
        "event": "shadow_operator_started",
        "utc": _utc_now(),
        "pid": os.getpid(),
    })

    try:
        while True:
            try:
                packet = gateway.packet()
            except Exception as error:
                _append_failure(paths["events"], "gateway_packet_failed", error)
                sleep(min(5.0, max(poll_seconds, 1.0)))
                continue

            if not _gateway_running(packet):
                _save_state(paths["state"], seen, None, "gateway_stopped")
                return 0

            event = packet.get("decision_event")
            if not isinstance(event, dict):
                sleep(poll_seconds)
                continue
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                sleep(poll_seconds)
                continue
            if event_id in seen_set:
                sleep(poll_seconds)
                continue
            if not _event_is_fresh(event):
                _remember(seen, seen_set, event_id)
                _save_state(paths["state"], seen, event_id, "expired")
                continue
            elapsed = time.monotonic() - last_model_call
            if elapsed < minimum_interval:
                sleep(min(poll_seconds, minimum_interval - elapsed))
                continue

            last_model_call = time.monotonic()
            intent_id = str(uuid.uuid4())
            prompt = build_shadow_prompt(packet, intent_id)
            started = time.monotonic()
            result: dict[str, Any]
            try:
                raw = invoke_hermes(
                    hermes_executable,
                    prompt,
                    timeout_seconds=model_timeout,
                    cwd=root,
                )
                intent, repaired = parse_model_intent(raw, packet)
                current = gateway.packet()
                if not _same_fresh_event(current, event_id):
                    result = {
                        "status": "superseded",
                        "event_id": event_id,
                        "intent": intent,
                        "bounded_repair_used": repaired,
                    }
                else:
                    receipt = gateway.submit_intent(intent)
                    result = {
                        "status": "submitted",
                        "event_id": event_id,
                        "intent": intent,
                        "receipt": receipt,
                        "bounded_repair_used": repaired,
                    }
            except Exception as error:
                result = {
                    "status": "failed",
                    "event_id": event_id,
                    "error": f"{type(error).__name__}:{error}",
                }
            result["model_duration_seconds"] = round(time.monotonic() - started, 3)
            result["recorded_utc"] = _utc_now()
            _append_jsonl(paths["events"], result)
            _remember(seen, seen_set, event_id)
            _save_state(paths["state"], seen, event_id, result["status"])
    finally:
        pid = _read_pid(paths["pid"])
        if pid == os.getpid():
            paths["pid"].unlink(missing_ok=True)
        _append_jsonl(paths["events"], {
            "event": "shadow_operator_stopped",
            "utc": _utc_now(),
            "pid": os.getpid(),
        })


def build_shadow_prompt(packet: dict[str, Any], intent_id: str) -> str:
    state = packet.get("state") if isinstance(packet.get("state"), dict) else {}
    account = state.get("account") if isinstance(state.get("account"), dict) else {}
    market = state.get("market") if isinstance(state.get("market"), dict) else {}
    execution = packet.get("execution") if isinstance(packet.get("execution"), dict) else {}
    compact = {
        "packet_id": packet.get("packet_id"),
        "state": state,
        "policy": packet.get("policy"),
        "execution": execution,
        "market_observation": packet.get("market_observation"),
        "decision_event": packet.get("decision_event"),
        "recent_trades": packet.get("recent_trades"),
    }
    supported = execution.get("supported_actions")
    return (
        "You are processing one live Binance market / paper-execution Glitch Crypto turn.\n"
        "Return exactly one glitch.crypto.intent.v1 JSON object and no prose or markdown.\n\n"
        "The microstructure baseline is transparent and explicitly NOT calibrated. Challenge it. "
        "A leveraged dollar amount is not edge. Choose entry only when the current path retains "
        "positive conservative value after noise, spread, fees, slippage and latency.\n"
        "The configured daily lock is portfolio policy, never a fixed trade target or activity quota.\n"
        "Use only a currently supported action. Omit quantity; the gateway owns sizing and risk.\n"
        "For an entry, use an absolute structural stop and target on the correct side of current mark.\n"
        "For position management, HOLD is not automatic; compare HOLD, stop/target changes, partial and EXIT.\n"
        "Do not include model metadata, credentials, native order IDs, comments or unknown fields.\n\n"
        f"Copy these exact identity values:\n"
        f"intent_id={intent_id}\n"
        f"packet_id={packet.get('packet_id')}\n"
        f"account={account.get('alias')}\n"
        f"instrument={market.get('instrument')}\n"
        f"supported_actions={json.dumps(supported, separators=(',', ':'))}\n\n"
        "Required common fields: schema_version, intent_id, packet_id, account, instrument, action, reason.\n"
        "ENTER_LONG/ENTER_SHORT additionally require stop_price and target_price; requested_risk_pct and "
        "requested_leverage are optional. HOLD/EXIT require tranche_id. MOVE_STOP requires tranche_id and "
        "stop_price. MOVE_TARGET requires tranche_id and target_price. REDUCE requires tranche_id and "
        "reduce_fraction_pct. NOTHING has only the common fields.\n\n"
        f"CURRENT_PACKET_JSON={json.dumps(compact, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}"
    )


def invoke_hermes(
    executable: str,
    prompt: str,
    *,
    timeout_seconds: float,
    cwd: Path,
) -> str:
    command = [
        executable,
        "-p",
        PROFILE,
        "chat",
        "-Q",
        "--query-file",
        "-",
        "--toolsets",
        "skills",
        "--skills",
        "crypto-market,crypto-build-intent,crypto-position-management",
    ]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        cwd=str(cwd),
        env=_sanitized_environment(os.environ),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Hermes call failed").strip()
        raise RuntimeError(message[-4_000:])
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("Hermes produced no final response")
    return output


def _gateway_running(packet: dict[str, Any]) -> bool:
    state = packet.get("state")
    control = state.get("control") if isinstance(state, dict) else None
    runtime = packet.get("runtime")
    return (
        isinstance(control, dict)
        and control.get("running") is True
        and isinstance(runtime, dict)
        and runtime.get("mode") == "binance-shadow"
        and runtime.get("running") is True
        and runtime.get("mutation_authority") is False
    )


def _same_fresh_event(packet: dict[str, Any], event_id: str) -> bool:
    if not _gateway_running(packet):
        return False
    event = packet.get("decision_event")
    return isinstance(event, dict) and event.get("event_id") == event_id and _event_is_fresh(event)


def _event_is_fresh(event: dict[str, Any]) -> bool:
    expires = event.get("expires_utc")
    if not isinstance(expires, str):
        return False
    try:
        value = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError:
        return False
    return value.astimezone(timezone.utc) > datetime.now(timezone.utc)


def _sanitized_environment(source: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in dict(source).items():
        upper = str(key).upper()
        if "BINANCE" in upper or upper.startswith("EXCHANGE_API_"):
            continue
        result[str(key)] = str(value)
    result["HERMES_HOME"] = str(profile_root())
    return result


def _paths(root: Path) -> dict[str, Path]:
    state_dir = root / "state" / "shadow-operator"
    return {
        "state_dir": state_dir,
        "pid": state_dir / "operator.pid",
        "state": state_dir / "operator.json",
        "events": state_dir / "events.jsonl",
        "log": state_dir / "operator.log",
    }


def _read_pid(path: Path) -> int | None:
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return value if value > 0 else None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _remember(seen: list[str], seen_set: set[str], event_id: str) -> None:
    if event_id in seen_set:
        return
    seen.append(event_id)
    seen_set.add(event_id)
    while len(seen) > MAXIMUM_SEEN_EVENTS:
        removed = seen.pop(0)
        seen_set.discard(removed)


def _save_state(path: Path, seen: list[str], event_id: str | None, result: str) -> None:
    _write_json_atomic(path, {
        "schema_version": "glitch.crypto.shadow-operator-state.v1",
        "seen_event_ids": seen[-MAXIMUM_SEEN_EVENTS:],
        "last_event_id": event_id,
        "last_result": result,
        "updated_utc": _utc_now(),
    })


def _append_failure(path: Path, event: str, error: Exception) -> None:
    _append_jsonl(path, {
        "event": event,
        "error": f"{type(error).__name__}:{error}",
        "utc": _utc_now(),
    })


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback)
    return value if isinstance(value, dict) else dict(fallback)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _bounded_float(value: str | None, fallback: float, minimum: float, maximum: float) -> float:
    parsed = fallback if value is None or not value.strip() else float(value)
    if not minimum <= parsed <= maximum:
        raise ValueError(f"value must be between {minimum} and {maximum}")
    return parsed


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--hermes", default=os.environ.get("HERMES_EXECUTABLE") or shutil.which("hermes"))
    args = parser.parse_args()
    if not args.run:
        print(json.dumps(launch_shadow_operator(), separators=(",", ":")))
        return 0
    if not args.hermes:
        raise RuntimeError("hermes executable was not found")
    return run_shadow_operator(hermes_executable=args.hermes)


if __name__ == "__main__":
    raise SystemExit(main())
