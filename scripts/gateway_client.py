"""Authenticated standard-library client for the local Glitch Crypto gateway."""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROFILE_NAME = "glitch-crypto"


def profile_root() -> Path:
    explicit = os.environ.get("HERMES_HOME")
    if explicit:
        return Path(explicit).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data) / "hermes" / "profiles" / PROFILE_NAME).resolve()
    return (Path.home() / ".hermes" / "profiles" / PROFILE_NAME).resolve()


def load_dotenv() -> None:
    path = profile_root() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def validated_gateway_url(value: str) -> str:
    origin = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(origin)
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("gateway URL must not include credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise RuntimeError("gateway URL must be a bare origin")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("gateway URL must use HTTP(S)")
    if parsed.scheme == "http" and host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("non-loopback gateway URLs must use HTTPS")
    return origin


class GatewayClient:
    def __init__(self) -> None:
        load_dotenv()
        self.base_url = validated_gateway_url(
            os.environ.get("GLITCH_CRYPTO_GATEWAY_URL", "http://127.0.0.1:8791")
        )
        self.local_token = _required_token("GLITCH_CRYPTO_LOCAL_TOKEN")
        self.operator_token = _required_token("GLITCH_CRYPTO_OPERATOR_TOKEN")
        if self.local_token == self.operator_token:
            raise RuntimeError("model and operator tokens must differ")

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        auth: str = "model",
        timeout: float = 20.0,
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Accept": "application/json"}
        if auth == "model":
            headers["Authorization"] = f"Bearer {self.local_token}"
        elif auth == "operator":
            headers["Authorization"] = f"Bearer {self.operator_token}"
        elif auth != "none":
            raise ValueError(f"unsupported auth role: {auth}")
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            headers=headers,
            data=data,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
                return int(response.status), _json_object(payload)
        except urllib.error.HTTPError as error:
            payload = error.read().decode("utf-8", errors="replace")
            return int(error.code), _json_object(payload)

    def require(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        auth: str = "model",
    ) -> dict[str, Any]:
        status, value = self.request(path, method=method, body=body, auth=auth)
        if status < 200 or status >= 300:
            raise RuntimeError(f"gateway returned {status}: {json.dumps(value, separators=(',', ':'))}")
        return value

    def health(self) -> dict[str, Any]:
        return self.require("/health", auth="none")

    def state(self) -> dict[str, Any]:
        return self.require("/state")

    def packet(self) -> dict[str, Any]:
        return self.require("/packet")

    def policy(self) -> dict[str, Any]:
        return self.require("/policy")

    def performance(self) -> dict[str, Any]:
        return self.require("/performance")

    def trades(self, limit: int = 20) -> dict[str, Any]:
        return self.require(f"/trades?limit={_bounded_limit(limit)}")

    def journal(self, limit: int = 20) -> dict[str, Any]:
        return self.require(f"/journal?limit={_bounded_limit(limit)}")

    def start(self) -> dict[str, Any]:
        return self.require("/control/start", method="POST", body={}, auth="operator")

    def stop(self) -> dict[str, Any]:
        return self.require("/control/stop", method="POST", body={}, auth="operator")

    def flatten(self, reason: str = "hermes_operator_flatten") -> dict[str, Any]:
        return self.require(
            "/control/flatten",
            method="POST",
            body={"reason": reason},
            auth="operator",
        )

    def set_daily_lock(self, percentage: float) -> dict[str, Any]:
        if percentage <= 0:
            raise ValueError("daily lock percentage must be positive")
        return self.require(
            "/control/policy",
            method="PUT",
            body={"daily_lock_target_pct": percentage},
            auth="operator",
        )

    def set_usable_limit(self, value: float | None) -> dict[str, Any]:
        if value is not None and value <= 0:
            raise ValueError("usable balance limit must be positive")
        return self.require(
            "/control/policy",
            method="PUT",
            body={"usable_balance_limit_usd": value},
            auth="operator",
        )

    def submit_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        return self.require("/intent", method="POST", body=intent, auth="model")


def status_summary(client: GatewayClient) -> str:
    health = client.health()
    state = client.state()
    account = state.get("account") if isinstance(state, dict) else {}
    risk = state.get("risk") if isinstance(state, dict) else {}
    control = state.get("control") if isinstance(state, dict) else {}
    return (
        f"Glitch Crypto venue={health.get('venue', 'unknown')} "
        f"mode={control.get('gateway_mode', health.get('gateway_mode', 'unknown'))} "
        f"running={control.get('running', health.get('running', False))} "
        f"equity=${account.get('equity_usd', 'unknown')} "
        f"usable=${account.get('usable_pot_usd', 'unknown')} "
        f"protected=${risk.get('protected_equity_usd', 'unknown')} "
        f"target=${risk.get('daily_target_profit_usd', 'unknown')} "
        f"lock_reached={risk.get('daily_lock_reached', False)} "
        f"new_exposure={risk.get('new_exposure_allowed', False)}."
    )


def _required_token(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) < 16:
        raise RuntimeError(f"{name} must be configured with at least 16 characters")
    return value


def _json_object(payload: str) -> dict[str, Any]:
    try:
        value = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {"error": "invalid_json_response", "body": payload}
    return value if isinstance(value, dict) else {"body": value}


def _bounded_limit(value: int) -> int:
    if value < 1:
        raise ValueError("limit must be positive")
    return min(value, 1000)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("health", "status", "policy", "pnl", "start", "stop", "flatten"):
        sub.add_parser(command)
    trades = sub.add_parser("trades")
    trades.add_argument("--limit", type=int, default=20)
    journal = sub.add_parser("journal")
    journal.add_argument("--limit", type=int, default=20)
    lock = sub.add_parser("set-lock")
    lock.add_argument("percentage", type=float)
    usable = sub.add_parser("set-usable-limit")
    usable.add_argument("usd", type=float)
    sub.add_parser("clear-usable-limit")
    intent = sub.add_parser("intent")
    intent.add_argument("path", type=Path)
    args = parser.parse_args()
    client = GatewayClient()
    if args.command == "health":
        value = client.health()
    elif args.command == "status":
        value = client.state()
    elif args.command == "policy":
        value = client.policy()
    elif args.command == "pnl":
        value = client.performance()
    elif args.command == "trades":
        value = client.trades(args.limit)
    elif args.command == "journal":
        value = client.journal(args.limit)
    elif args.command == "start":
        value = client.start()
    elif args.command == "stop":
        value = client.stop()
    elif args.command == "flatten":
        value = client.flatten()
    elif args.command == "set-lock":
        value = client.set_daily_lock(args.percentage)
    elif args.command == "set-usable-limit":
        value = client.set_usable_limit(args.usd)
    elif args.command == "clear-usable-limit":
        value = client.set_usable_limit(None)
    elif args.command == "intent":
        value = client.submit_intent(json.loads(args.path.read_text(encoding="utf-8")))
    else:
        raise AssertionError(args.command)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
