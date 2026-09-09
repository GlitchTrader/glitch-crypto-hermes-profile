from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shadow_operator", ROOT / "scripts" / "shadow_operator.py"
)
assert SPEC and SPEC.loader
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


class FakeGateway:
    def __init__(self) -> None:
        self.running = True
        self.submitted = []
        self.packet_value = {
            "packet_id": "a" * 64,
            "state": {
                "control": {"running": True, "gateway_mode": "shadow"},
                "account": {"alias": "paper-main"},
                "market": {"instrument": "BTCUSDT-PERP", "mark_price": 60000},
                "positions": [],
            },
            "policy": {"daily_lock_target_pct": 0.5},
            "execution": {"supported_actions": ["ENTER_LONG", "ENTER_SHORT", "NOTHING"]},
            "runtime": {
                "mode": "binance-shadow",
                "running": True,
                "mutation_authority": False,
            },
            "market_observation": {
                "state": "ready",
                "market": {"market_age_ms": 5},
                "calibrated": False,
                "actionable": True,
                "action": "ENTER_LONG",
                "reason": "transparent baseline candidate",
            },
            "decision_event": {
                "event_id": "22222222-2222-4222-8222-222222222222",
                "event_type": "CANDIDATE",
                "created_utc": "2026-08-25T10:00:00.000Z",
                "expires_utc": "2099-08-25T10:00:00.000Z",
            },
            "recent_trades": [],
        }

    def packet(self):
        value = json.loads(json.dumps(self.packet_value))
        if not self.running:
            value["state"]["control"]["running"] = False
        return value

    def submit_intent(self, intent):
        self.submitted.append(intent)
        self.running = False
        return {
            "schema_version": "glitch.crypto.intent-receipt.v1",
            "intent_id": intent["intent_id"],
            "accepted": True,
            "state": "observed",
        }


class ShadowOperatorTests(unittest.TestCase):
    def test_prompt_binds_identity_and_treats_baseline_as_uncalibrated(self) -> None:
        packet = FakeGateway().packet()
        prompt = operator.build_shadow_prompt(
            packet, "11111111-1111-4111-8111-111111111111"
        )
        self.assertIn("NOT calibrated", prompt)
        self.assertIn("daily lock is portfolio policy", prompt)
        self.assertIn("11111111-1111-4111-8111-111111111111", prompt)
        self.assertIn("a" * 64, prompt)
        self.assertNotIn("API_SECRET", prompt)

    def test_environment_removes_exchange_credentials_only(self) -> None:
        value = operator._sanitized_environment(
            {
                "BINANCE_API_KEY": "secret",
                "GLITCH_BINANCE_USDM_API_SECRET": "secret2",
                "OPENAI_API_KEY": "provider-key",
                "PATH": "path-value",
            }
        )
        self.assertNotIn("BINANCE_API_KEY", value)
        self.assertNotIn("GLITCH_BINANCE_USDM_API_SECRET", value)
        self.assertEqual(value["OPENAI_API_KEY"], "provider-key")
        self.assertEqual(value["PATH"], "path-value")

    def test_hermes_uses_the_profile_home_without_double_profile_routing(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            operator, "profile_root", return_value=Path(directory)
        ), patch.object(operator.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess(
                ["hermes", "chat"], 0, stdout="{}", stderr=""
            )
            operator.invoke_hermes(
                "hermes",
                "prompt",
                timeout_seconds=10,
                cwd=Path(directory),
            )
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["hermes", "chat"])
        self.assertNotIn("-p", command)
        self.assertEqual(run.call_args.kwargs["env"]["HERMES_HOME"], directory)

    def test_worker_consumes_one_fresh_event_and_submits_one_strict_intent(self) -> None:
        gateway = FakeGateway()
        with tempfile.TemporaryDirectory() as directory:
            response = json.dumps(
                {
                    "schema_version": "glitch.crypto.intent.v1",
                    "intent_id": "11111111-1111-4111-8111-111111111111",
                    "packet_id": "a" * 64,
                    "account": "paper-main",
                    "instrument": "BTCUSDT-PERP",
                    "action": "NOTHING",
                    "reason": "The uncalibrated candidate does not justify entry after uncertainty.",
                }
            )
            with patch.object(operator, "profile_root", return_value=Path(directory)), patch.object(
                operator, "invoke_hermes", return_value=response
            ), patch.object(operator.uuid, "uuid4", return_value="11111111-1111-4111-8111-111111111111"), patch.dict(
                operator.os.environ,
                {
                    "GLITCH_CRYPTO_OPERATOR_MIN_INTERVAL_SECONDS": "0",
                    "GLITCH_CRYPTO_OPERATOR_POLL_SECONDS": "0.1",
                },
                clear=False,
            ):
                result = operator.run_shadow_operator(
                    hermes_executable="hermes",
                    client=gateway,
                    sleep=lambda _seconds: None,
                )
        self.assertEqual(result, 0)
        self.assertEqual(len(gateway.submitted), 1)
        self.assertEqual(gateway.submitted[0]["action"], "NOTHING")

    def test_windows_status_probe_does_not_signal_or_kill(self) -> None:
        with patch.object(operator.os, "kill", side_effect=AssertionError("must not signal on Windows")):
            if os.name == "nt":
                self.assertTrue(operator._pid_alive(os.getpid()))

    def test_worker_lock_excludes_a_second_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory, operator.worker_lock(Path(directory)):
            with self.assertRaises(OSError):
                with operator.worker_lock(Path(directory)):
                    self.fail("two workers acquired the same profile lock")

    def test_model_environment_has_no_gateway_operator_token(self) -> None:
        result = operator._sanitized_environment({"GLITCH_CRYPTO_OPERATOR_TOKEN": "secret",
            "GLITCH_CRYPTO_LOCAL_TOKEN": "local", "PATH": "path"}, model_call=True)
        self.assertNotIn("GLITCH_CRYPTO_OPERATOR_TOKEN", result)
        self.assertNotIn("GLITCH_CRYPTO_LOCAL_TOKEN", result)

    def test_fresh_bookkeeping_does_not_hide_stale_market_or_changed_position(self) -> None:
        gateway = FakeGateway()
        wrapper = operator.FrozenPacketGateway(gateway, gateway.packet())
        gateway.packet_value["market_observation"]["state"] = "stale"
        with self.assertRaises(ValueError):
            wrapper.packet()
        gateway.packet_value["market_observation"]["state"] = "ready"
        gateway.packet_value["state"]["positions"] = [{"tranche_id": "new"}]
        with self.assertRaises(ValueError):
            wrapper.packet()

    def test_lost_receipt_replays_exact_staged_intent_without_model(self) -> None:
        gateway = FakeGateway()
        with tempfile.TemporaryDirectory() as directory:
            inbox = operator.CognitionInbox(Path(directory) / "state/shadow-operator/inbox.sqlite")
            event = operator._cognition_event(gateway.packet())
            inbox.enqueue(event)
            claim = inbox.claim("first")
            intent = {"schema_version": "glitch.crypto.intent.v1",
                "intent_id": "11111111-1111-4111-8111-111111111111", "packet_id": "a" * 64,
                "account": "paper-main", "instrument": "BTCUSDT-PERP", "action": "NOTHING", "reason": "test"}
            inbox.stage_intent(event["event_id"], claim.lease_token, intent)
            inbox.release_staged(event["event_id"], claim.lease_token, "receipt lost")
            inbox.close()
            with patch.object(operator, "profile_root", return_value=Path(directory)), patch.object(
                operator, "invoke_hermes", side_effect=AssertionError("must recover without model")
            ):
                operator.run_shadow_operator(hermes_executable="hermes", client=gateway, sleep=lambda _: None)
            self.assertEqual(gateway.submitted, [intent])


if __name__ == "__main__":
    unittest.main()
