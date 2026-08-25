from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "crypto_control", ROOT / "plugins" / "crypto-control" / "__init__.py"
)
assert SPEC and SPEC.loader
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)


class FakeContext:
    def __init__(self) -> None:
        self.commands = {}

    def register_command(self, name, *, handler, description) -> None:
        self.commands[name] = (handler, description)


class FakeClient:
    def __init__(self) -> None:
        self.lock = 0.5
        self.limit = None

    def health(self):
        return {"venue": "paper", "gateway_mode": "shadow", "running": False}

    def state(self):
        return {
            "control": {"gateway_mode": "shadow", "running": False},
            "account": {"equity_usd": 1000, "usable_pot_usd": 1000},
            "risk": {
                "protected_equity_usd": 1000,
                "daily_target_profit_usd": 5,
                "daily_lock_reached": False,
                "new_exposure_allowed": True,
            },
        }

    def start(self):
        value = self.state()
        value["control"]["running"] = True
        return value

    def stop(self):
        return self.state()

    def flatten(self, reason):
        return self.state()

    def policy(self):
        return {
            "daily_lock_target_pct": self.lock,
            "usable_balance_limit_usd": self.limit,
        }

    def set_daily_lock(self, value):
        self.lock = value
        return self.policy()

    def set_usable_limit(self, value):
        self.limit = value
        return self.policy()

    def performance(self):
        return {"realized_pnl_usd": 0}

    def trades(self, limit):
        return {"trades": [], "limit": limit}

    def journal(self, limit):
        return {"journal": [], "limit": limit}


class FakeOperator:
    @staticmethod
    def launch_shadow_operator():
        return {"started": True, "already_running": False, "pid": 1234}

    @staticmethod
    def shadow_operator_status():
        return {
            "running": True,
            "pid": 1234,
            "last_event_id": "event-1",
            "last_result": "submitted",
        }


class PluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()
        self.original_client = plugin._client
        self.original_operator = plugin._operator_module
        plugin._client = lambda: self.client
        plugin._operator_module = lambda: FakeOperator

    def tearDown(self) -> None:
        plugin._client = self.original_client
        plugin._operator_module = self.original_operator

    def test_registers_hyphen_and_underscore_commands(self) -> None:
        context = FakeContext()
        plugin.register(context)
        for name in (
            "crypto-status",
            "crypto_status",
            "crypto-operator",
            "crypto_operator",
            "daily-lock",
            "daily_lock",
            "usable-limit",
            "usable_limit",
            "flatten-all",
            "flatten_all",
        ):
            self.assertIn(name, context.commands)

    def test_daily_lock_and_usable_limit_commands(self) -> None:
        self.assertIn("0.5%", plugin._daily_lock(""))
        self.assertIn("0.75%", plugin._daily_lock("0.75"))
        self.assertIn("$500.0", plugin._usable_limit("500"))
        self.assertIn("cleared", plugin._usable_limit("full"))

    def test_start_launches_the_event_worker_and_flatten_stops_exposure(self) -> None:
        started = plugin._trade("")
        self.assertIn("running=True", started)
        self.assertIn("operator_pid=1234", started)
        self.assertIn("operator_started=True", started)
        self.assertIn("flat and stopped", plugin._flatten("test"))


if __name__ == "__main__":
    unittest.main()
