"""Deterministic Glitch Crypto controls and live-shadow operator lifecycle."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _profile_root() -> Path:
    import os

    explicit = os.environ.get("HERMES_HOME")
    if explicit:
        return Path(explicit).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data) / "hermes" / "profiles" / "glitch-crypto").resolve()
    return (Path.home() / ".hermes" / "profiles" / "glitch-crypto").resolve()


def _scripts_path() -> Path:
    scripts = _profile_root() / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return scripts


def _client():
    _scripts_path()
    from gateway_client import GatewayClient

    return GatewayClient()


def _operator_module():
    _scripts_path()
    import shadow_operator

    return shadow_operator


def _status(_raw_args: str) -> str:
    client = _client()
    _scripts_path()
    from gateway_client import status_summary

    operator = _operator_module().shadow_operator_status()
    return (
        f"{status_summary(client)} operator_running={operator.get('running', False)}; "
        f"operator_last_event={operator.get('last_event_id')}; "
        f"operator_last_result={operator.get('last_result')}."
    )


def _trade(_raw_args: str) -> str:
    client = _client()
    state = client.start()
    try:
        operator = _operator_module().launch_shadow_operator()
    except Exception:
        client.stop()
        raise
    operator_text = (
        f"operator_pid={operator.get('pid')}; "
        f"operator_started={operator.get('started', False)}"
    )
    return f"{_state_message('Glitch Crypto is ON', state)} {operator_text}."


def _pause(_raw_args: str) -> str:
    state = _client().stop()
    return _state_message("Glitch Crypto is OFF; native protection remains venue-owned", state)


def _flatten(raw_args: str) -> str:
    state = _client().flatten(raw_args.strip() or "authenticated Hermes operator flatten")
    return _state_message("Glitch Crypto is flat and stopped", state)


def _daily_lock(raw_args: str) -> str:
    raw = raw_args.strip()
    client = _client()
    if not raw:
        policy = client.policy()
        return f"Daily protected-profit lock is {policy.get('daily_lock_target_pct')}% of the starting usable pot."
    value = float(raw)
    policy = client.set_daily_lock(value)
    return f"Daily protected-profit lock set to {policy.get('daily_lock_target_pct')}%. It remains portfolio policy, not trade geometry."


def _usable_limit(raw_args: str) -> str:
    raw = raw_args.strip().lower()
    client = _client()
    if not raw:
        policy = client.policy()
        value = policy.get("usable_balance_limit_usd")
        return "Usable balance limit is full current equity." if value is None else f"Usable balance limit is ${value}."
    if raw in {"full", "blank", "none", "clear"}:
        policy = client.set_usable_limit(None)
    else:
        policy = client.set_usable_limit(float(raw))
    value = policy.get("usable_balance_limit_usd")
    return "Usable balance limit cleared; full current equity is eligible for policy calculations." if value is None else f"Usable balance limit set to ${value}."


def _pnl(_raw_args: str) -> str:
    return json.dumps(_client().performance(), indent=2, sort_keys=True)


def _trades(raw_args: str) -> str:
    limit = int(raw_args.strip() or "20")
    return json.dumps(_client().trades(limit), indent=2, sort_keys=True)


def _journal(raw_args: str) -> str:
    limit = int(raw_args.strip() or "20")
    return json.dumps(_client().journal(limit), indent=2, sort_keys=True)


def _operator_status(_raw_args: str) -> str:
    return json.dumps(_operator_module().shadow_operator_status(), indent=2, sort_keys=True)


def _state_message(prefix: str, state: dict[str, Any]) -> str:
    control = state.get("control") if isinstance(state, dict) else {}
    account = state.get("account") if isinstance(state, dict) else {}
    risk = state.get("risk") if isinstance(state, dict) else {}
    return (
        f"{prefix}; mode={control.get('gateway_mode', 'unknown')}; "
        f"running={control.get('running', False)}; equity=${account.get('equity_usd', 'unknown')}; "
        f"protected=${risk.get('protected_equity_usd', 'unknown')}."
    )


def register(ctx) -> None:
    commands = {
        "crypto-status": (_status, "Show gateway, live-shadow operator, target, and risk state."),
        "crypto-operator": (_operator_status, "Show the live-shadow cognition worker state."),
        "trade": (_trade, "Start the gateway and the event-driven live-shadow Hermes operator."),
        "pause-trading": (_pause, "Stop new cognition/exposure without canceling native protection."),
        "flatten-all": (_flatten, "Stop and flatten all configured Glitch Crypto exposure."),
        "daily-lock": (_daily_lock, "Read or set the protected daily objective percentage, for example /daily_lock 0.5."),
        "usable-limit": (_usable_limit, "Read or set usable capital; use full to clear the cap."),
        "crypto-pnl": (_pnl, "Show the current performance summary."),
        "crypto-trades": (_trades, "Show recent attributable trades."),
        "crypto-journal": (_journal, "Show recent performance and operational journal entries."),
    }
    for name, (handler, description) in commands.items():
        ctx.register_command(name, handler=handler, description=description)
        ctx.register_command(name.replace("-", "_"), handler=handler, description=description)
