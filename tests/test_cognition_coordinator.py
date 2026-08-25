from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cognition_contracts import ContractError
from cognition_coordinator import CognitionCoordinator
from cognition_inbox import CognitionInbox
from test_cognition_contracts import candidate_event, entry_intent, packet


class FakeGateway:
    def __init__(self, current_packet: dict, *, fail_first: bool = False) -> None:
        self.current_packet = current_packet
        self.fail_first = fail_first
        self.submissions: list[dict] = []

    def packet(self) -> dict:
        return self.current_packet

    def submit_intent(self, intent: dict) -> dict:
        self.submissions.append(intent)
        if self.fail_first and len(self.submissions) == 1:
            raise TimeoutError("outcome unknown")
        return {
            "schema_version": "glitch.crypto.intent-receipt.v1",
            "intent_id": intent["intent_id"],
            "state": "open_protected",
            "accepted": True,
        }


class CognitionCoordinatorTests(unittest.TestCase):
    def test_stale_or_malformed_output_creates_no_gateway_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cognition.sqlite"
            inbox = CognitionInbox(path, now=fixed_now)
            inbox.enqueue(candidate_event())
            stale = packet()
            stale["packet_id"] = "b" * 64
            gateway = FakeGateway(stale)
            coordinator = CognitionCoordinator(inbox, gateway)
            claim = coordinator.claim_next("worker")
            self.assertIsNotNone(claim)
            with self.assertRaisesRegex(ContractError, "no longer current"):
                coordinator.stage_and_submit(claim, json.dumps(entry_intent()))
            self.assertEqual(gateway.submissions, [])
            self.assertEqual(inbox.get(claim.event["event_id"])["state"], "failed")
            inbox.close()

        with tempfile.TemporaryDirectory() as directory:
            inbox = CognitionInbox(Path(directory) / "cognition.sqlite", now=fixed_now)
            inbox.enqueue(candidate_event())
            gateway = FakeGateway(packet())
            coordinator = CognitionCoordinator(inbox, gateway)
            claim = coordinator.claim_next("worker")
            self.assertIsNotNone(claim)
            with self.assertRaises(ContractError):
                coordinator.stage_and_submit(claim, "not-json")
            self.assertEqual(gateway.submissions, [])
            inbox.close()

    def test_staged_intent_retries_exactly_after_transport_failure_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cognition.sqlite"
            inbox = CognitionInbox(path, now=fixed_now)
            inbox.enqueue(candidate_event())
            first_gateway = FakeGateway(packet(), fail_first=True)
            coordinator = CognitionCoordinator(inbox, first_gateway)
            claim = coordinator.claim_next("worker-1")
            self.assertIsNotNone(claim)
            with self.assertRaises(TimeoutError):
                coordinator.stage_and_submit(claim, json.dumps(entry_intent()))
            staged = inbox.get(claim.event["event_id"])
            self.assertEqual(staged["state"], "intent_staged")
            self.assertEqual(staged["staged_intent"], first_gateway.submissions[0])
            inbox.close()

            reopened = CognitionInbox(path, now=fixed_now)
            second_gateway = FakeGateway(packet())
            resumed = CognitionCoordinator(reopened, second_gateway)
            resumed_claim = resumed.claim_next("worker-2")
            self.assertIsNotNone(resumed_claim)
            self.assertEqual(resumed_claim.staged_intent, first_gateway.submissions[0])
            receipt = resumed.submit_staged(resumed_claim)
            self.assertTrue(receipt["accepted"])
            self.assertEqual(second_gateway.submissions[0], first_gateway.submissions[0])
            self.assertEqual(reopened.get(claim.event["event_id"])["state"], "completed")
            reopened.close()


def fixed_now() -> datetime:
    return datetime(2026, 8, 25, 1, 1, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
