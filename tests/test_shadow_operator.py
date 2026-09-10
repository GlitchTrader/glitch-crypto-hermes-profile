from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
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
    def test_prompt_binds_identity_and_does_not_claim_calibration(self) -> None:
        packet = FakeGateway().packet()
        prompt = operator.build_shadow_prompt(
            packet, "11111111-1111-4111-8111-111111111111"
        )
        self.assertIn("NOT calibrated", prompt)
        self.assertIn("daily lock is portfolio policy", prompt)
        self.assertIn("11111111-1111-4111-8111-111111111111", prompt)
        self.assertIn("a" * 64, prompt)
        self.assertNotIn("API_SECRET", prompt)
        self.assertIn("do not generate a replacement intent_id", prompt)

    def test_model_input_preserves_facts_without_baseline_recommendations(self) -> None:
        packet = FakeGateway().packet()
        packet["market_observation"].update({
            "state": "actionable", "observation_id": "original-observation",
            "evidence": {"momentum_15s_bps": 2, "range_15s_bps": 4,
                "noise_15s_bps": 1, "directional_pressure_bps": 99},
            "economics": {"conservative_edge_bps": -8, "minimum_edge_bps": 1.5},
            "geometry": {"suggested_stop_price": 59999, "suggested_target_price": 60001},
        })
        packet["policy"]["estimated_round_trip_cost_pct"] = 0.1
        packet["price_context"] = {"completed_1m": [{"close": 60000}], "windows": [{"minutes": 60}]}
        packet["decision_event"].update({"suggested_action": "ENTER_LONG", "reason": "baseline advice"})
        original = json.loads(json.dumps(packet))
        compact = json.loads(operator.build_shadow_prompt(packet, "supplied-id").split("CURRENT_PACKET_JSON=", 1)[1])
        facts = compact["market_observation"]
        self.assertEqual(facts["data_state"], "ready")
        self.assertEqual(facts["evidence"], {"momentum_15s_bps": 2, "range_15s_bps": 4, "noise_15s_bps": 1})
        self.assertEqual(facts["market"], original["market_observation"]["market"])
        for key in ("action", "actionable", "reason", "economics", "geometry"):
            self.assertNotIn(key, facts)
        self.assertNotIn("suggested_action", compact["decision_event"])
        self.assertNotIn("reason", compact["decision_event"])
        for key in ("packet_id", "state", "policy", "execution", "price_context", "recent_trades"):
            self.assertEqual(compact[key], original[key])
        self.assertEqual(packet, original, "the full journal packet must not be modified")

        packet["market_observation"].update({"state": "ready", "action": "NOTHING", "actionable": False,
            "economics": {"conservative_edge_bps": 400}, "geometry": None})
        packet["decision_event"]["suggested_action"] = "NOTHING"
        second = json.loads(operator.build_shadow_prompt(packet, "supplied-id").split("CURRENT_PACKET_JSON=", 1)[1])
        self.assertEqual(compact, second, "baseline verdict must not change the model's evidence")
        self.assertEqual(operator._market_facts({"state": "stale"})["data_state"], "stale")
        self.assertIsNone(operator._market_facts(None))

    def test_valid_entry_and_management_are_not_gated_by_baseline_nothing(self) -> None:
        actions = {
            "ENTER_LONG": {"stop_price": 59800, "target_price": 60600},
            "ENTER_SHORT": {"stop_price": 60200, "target_price": 59400},
            "HOLD": {"tranche_id": "owned"},
            "MOVE_STOP": {"tranche_id": "owned", "stop_price": 59900},
            "MOVE_TARGET": {"tranche_id": "owned", "target_price": 60400},
            "REDUCE": {"tranche_id": "owned", "reduce_fraction_pct": 50},
            "EXIT": {"tranche_id": "owned"},
        }
        for action, fields in actions.items():
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                gateway = FakeGateway()
                gateway.packet_value["market_observation"].update({"action": "NOTHING", "actionable": False})
                gateway.packet_value["execution"]["supported_actions"] = [action]
                if "tranche_id" in fields:
                    gateway.packet_value["state"]["positions"] = [{"tranche_id": "owned", "side": "LONG"}]
                    gateway.packet_value["decision_event"].update({"event_type": "POSITION", "position_tranche_ids": ["owned"]})
                intent = {"schema_version": "glitch.crypto.intent.v1", "intent_id": "11111111-1111-4111-8111-111111111111",
                    "packet_id": "a" * 64, "account": "paper-main", "instrument": "BTCUSDT-PERP",
                    "action": action, "reason": "Supported structural path independent of diagnostic verdict.", **fields}
                with patch.object(operator, "profile_root", return_value=Path(directory)), patch.object(
                    operator, "invoke_hermes", return_value=json.dumps(intent)
                ), patch.object(operator.uuid, "uuid4", return_value=intent["intent_id"]):
                    operator.run_shadow_operator(hermes_executable="hermes", client=gateway, sleep=lambda _: None)
                self.assertEqual(gateway.submitted, [intent])

    def test_wrong_supplied_id_is_rejected_without_retry_or_submission(self) -> None:
        gateway = FakeGateway()
        def wrong_id(*args, **kwargs):
            gateway.running = False
            return json.dumps({"schema_version": "glitch.crypto.intent.v1",
                "intent_id": "33333333-3333-4333-8333-333333333333", "packet_id": "a" * 64,
                "account": "paper-main", "instrument": "BTCUSDT-PERP", "action": "NOTHING", "reason": "test"})
        with tempfile.TemporaryDirectory() as directory, patch.object(
            operator, "profile_root", return_value=Path(directory)
        ), patch.object(operator, "invoke_hermes", side_effect=wrong_id) as model, patch.object(
            operator.uuid, "uuid4", return_value="11111111-1111-4111-8111-111111111111"
        ):
            operator.run_shadow_operator(hermes_executable="hermes", client=gateway, sleep=lambda _: None)
            records = [json.loads(line) for line in (Path(directory) / "state/shadow-operator/events.jsonl").read_text().splitlines()]
        self.assertEqual(gateway.submitted, [])
        self.assertEqual(model.call_count, 1)
        self.assertTrue(any(item.get("error") == "ValueError:model changed the supplied intent ID" for item in records))

    def test_stopped_gateway_spends_no_model_call(self) -> None:
        gateway = FakeGateway()
        gateway.running = False
        with tempfile.TemporaryDirectory() as directory, patch.object(
            operator, "profile_root", return_value=Path(directory)
        ), patch.object(operator, "invoke_hermes", side_effect=AssertionError("no model while stopped")) as model:
            operator.run_shadow_operator(hermes_executable="hermes", client=gateway, sleep=lambda _: None)
        model.assert_not_called()
        self.assertEqual(gateway.submitted, [])

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
