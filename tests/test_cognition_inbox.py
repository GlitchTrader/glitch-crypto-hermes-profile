from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cognition_contracts import ContractError
from cognition_inbox import CognitionInbox
from test_cognition_contracts import candidate_event


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 25, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


class CognitionInboxTests(unittest.TestCase):
    def test_replay_conflict_and_restart_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cognition.sqlite"
            clock = Clock()
            inbox = CognitionInbox(path, now=clock)
            event = candidate_event()
            self.assertFalse(inbox.enqueue(event)["replayed"])
            self.assertTrue(inbox.enqueue(event)["replayed"])
            changed = dict(event)
            changed["reason"] = "Changed immutable content."
            with self.assertRaisesRegex(ContractError, "changed content"):
                inbox.enqueue(changed)
            inbox.close()

            reopened = CognitionInbox(path, now=clock)
            claim = reopened.claim("worker-1")
            self.assertIsNotNone(claim)
            self.assertEqual(claim.event["event_id"], event["event_id"])
            reopened.close()

    def test_expired_lease_is_recovered_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cognition.sqlite"
            clock = Clock()
            inbox = CognitionInbox(path, now=clock)
            inbox.enqueue(candidate_event())
            first = inbox.claim("worker-1", lease_seconds=5)
            self.assertIsNotNone(first)
            inbox.close()

            clock.value += timedelta(seconds=6)
            reopened = CognitionInbox(path, now=clock)
            second = reopened.claim("worker-2", lease_seconds=5)
            self.assertIsNotNone(second)
            self.assertEqual(second.attempt, 2)
            self.assertNotEqual(first.lease_token, second.lease_token)
            reopened.close()

    def test_position_event_preempts_unstaged_candidate_and_claims_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = Clock()
            inbox = CognitionInbox(Path(directory) / "cognition.sqlite", now=clock)
            candidate = candidate_event()
            inbox.enqueue(candidate)
            candidate_claim = inbox.claim("candidate-worker")
            self.assertIsNotNone(candidate_claim)

            position = position_event()
            inbox.enqueue(position)
            self.assertTrue(inbox.preemption_requested(candidate["event_id"], candidate_claim.lease_token))
            with self.assertRaisesRegex(ContractError, "preempted"):
                inbox.stage_intent(candidate["event_id"], candidate_claim.lease_token, {"intent_id": "x"})
            inbox.acknowledge_preemption(candidate["event_id"], candidate_claim.lease_token)

            position_claim = inbox.claim("position-worker")
            self.assertIsNotNone(position_claim)
            self.assertEqual(position_claim.event["event_type"], "POSITION")
            inbox.fail_unstaged(position["event_id"], position_claim.lease_token, "test_complete")
            resumed_candidate = inbox.claim("candidate-worker")
            self.assertIsNotNone(resumed_candidate)
            self.assertEqual(resumed_candidate.event["event_id"], candidate["event_id"])
            inbox.close()


def position_event() -> dict:
    value = candidate_event("33333333-3333-4333-8333-333333333333")
    value["event_type"] = "POSITION"
    value["tranche_id"] = "TR-1"
    value["reason"] = "Protected position state materially changed."
    value["trigger"] = {"type": "risk_state_changed"}
    return value


if __name__ == "__main__":
    unittest.main()
