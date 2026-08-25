from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cognition_contracts import ContractError, parse_model_intent, validate_cognition_event


class CognitionContractTests(unittest.TestCase):
    def test_event_contract_is_exact_and_credential_free(self) -> None:
        event = candidate_event()
        self.assertEqual(validate_cognition_event(event)["event_id"], event["event_id"])
        changed = dict(event)
        changed["trigger"] = {"api_key": "forbidden"}
        with self.assertRaisesRegex(ContractError, "credential-bearing"):
            validate_cognition_event(changed)
        changed = dict(event)
        changed["unknown"] = True
        with self.assertRaisesRegex(ContractError, "unknown"):
            validate_cognition_event(changed)

    def test_model_output_allows_only_one_outer_fence_repair(self) -> None:
        intent = entry_intent()
        direct, repaired = parse_model_intent(json.dumps(intent), packet())
        self.assertFalse(repaired)
        self.assertEqual(direct["intent_id"], intent["intent_id"])

        fenced, repaired = parse_model_intent(
            "```json\n" + json.dumps(intent) + "\n```",
            packet(),
        )
        self.assertTrue(repaired)
        self.assertEqual(fenced, direct)
        with self.assertRaisesRegex(ContractError, "exactly one JSON"):
            parse_model_intent("Decision:\n" + json.dumps(intent), packet())

    def test_quantity_unknown_fields_and_stale_identity_fail_closed(self) -> None:
        intent = entry_intent()
        intent["quantity"] = "0.01"
        with self.assertRaisesRegex(ContractError, "unknown"):
            parse_model_intent(json.dumps(intent), packet())

        intent = entry_intent()
        intent["packet_id"] = "b" * 64
        with self.assertRaisesRegex(ContractError, "does not match"):
            parse_model_intent(json.dumps(intent), packet())

    def test_position_management_requires_current_tranche_and_geometry(self) -> None:
        value = common_intent("MOVE_STOP")
        value.update({"tranche_id": "TR-1", "stop_price": 59_900})
        parsed, _ = parse_model_intent(json.dumps(value), positioned_packet())
        self.assertEqual(parsed["tranche_id"], "TR-1")
        value["stop_price"] = 60_100
        with self.assertRaisesRegex(ContractError, "protective side"):
            parse_model_intent(json.dumps(value), positioned_packet())


def candidate_event(event_id: str = "11111111-1111-4111-8111-111111111111") -> dict:
    return {
        "schema_version": "glitch.crypto.cognition-event.v1",
        "event_id": event_id,
        "event_type": "CANDIDATE",
        "packet_id": "a" * 64,
        "created_utc": "2026-08-25T01:00:00Z",
        "expires_utc": "2026-08-25T01:05:00Z",
        "reason": "A bounded candidate crossed the numerical review threshold.",
        "trigger": {"type": "candidate_threshold", "candidate_id": "C-1"},
    }


def packet() -> dict:
    return {
        "schema_version": "glitch.crypto.packet.v1",
        "packet_id": "a" * 64,
        "state": {
            "account": {"alias": "paper-main"},
            "market": {"instrument": "BTCUSDT-PERP", "mark_price": 60_000},
            "positions": [],
        },
        "execution": {
            "supported_actions": ["ENTER_LONG", "ENTER_SHORT", "NOTHING"],
        },
    }


def positioned_packet() -> dict:
    value = packet()
    value["state"]["positions"] = [{"tranche_id": "TR-1", "side": "LONG"}]
    value["execution"]["supported_actions"] = ["HOLD", "MOVE_STOP", "MOVE_TARGET", "REDUCE", "EXIT"]
    return value


def common_intent(action: str) -> dict:
    return {
        "schema_version": "glitch.crypto.intent.v1",
        "intent_id": "22222222-2222-4222-8222-222222222222",
        "packet_id": "a" * 64,
        "account": "paper-main",
        "instrument": "BTCUSDT-PERP",
        "action": action,
        "reason": "Current path remains favorable after costs and uncertainty.",
    }


def entry_intent() -> dict:
    value = common_intent("ENTER_LONG")
    value.update({"stop_price": 59_500, "target_price": 61_000, "requested_leverage": 3})
    return value


if __name__ == "__main__":
    unittest.main()
