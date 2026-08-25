from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from learning_contracts import LearningContractError
from learning_store import LearningStore
from test_learning_contracts import episode, promotion


class LearningStoreTests(unittest.TestCase):
    def test_episode_replay_conflict_and_restart_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "learning.sqlite"
            store = LearningStore(path, now=fixed_now)
            value = episode()
            self.assertFalse(store.add_episode(value)["replayed"])
            self.assertTrue(store.add_episode(value)["replayed"])
            changed = dict(value)
            changed["summary"] = "Changed immutable evidence."
            with self.assertRaisesRegex(LearningContractError, "changed content"):
                store.add_episode(changed)
            store.close()

            reopened = LearningStore(path, now=fixed_now)
            lesson = lesson_proposal([value["episode_id"]])
            reopened.propose_lesson(lesson)
            self.assertEqual(reopened.get_lesson(lesson["lesson_id"])["state"], "proposed")
            reopened.close()

    def test_independent_groups_are_required_and_operational_evidence_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LearningStore(Path(directory) / "learning.sqlite", now=fixed_now)
            first = episode()
            correlated = episode(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
                correlation_group="market-idea-1",
            )
            independent = episode(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3",
                correlation_group="market-idea-2",
            )
            operational = episode(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4",
                lane="operational",
                episode_type="operational_fault",
                correlation_group="incident-1",
            )
            for value in (first, correlated, independent, operational):
                store.add_episode(value)

            one = lesson_proposal([first["episode_id"]])
            store.propose_lesson(one)
            self.assertIn("independent_support_count_below_two", store.eligibility(one["lesson_id"])["blockers"])

            same_group = lesson_proposal(
                [first["episode_id"], correlated["episode_id"]],
                lesson_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc2",
            )
            store.propose_lesson(same_group)
            self.assertIn(
                "independent_correlation_groups_below_two",
                store.eligibility(same_group["lesson_id"])["blockers"],
            )

            eligible = lesson_proposal(
                [first["episode_id"], independent["episode_id"]],
                lesson_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc3",
            )
            store.propose_lesson(eligible)
            self.assertTrue(store.eligibility(eligible["lesson_id"])["eligible"])

            invalid = lesson_proposal(
                [first["episode_id"], operational["episode_id"]],
                lesson_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc4",
            )
            with self.assertRaisesRegex(LearningContractError, "operational evidence"):
                store.propose_lesson(invalid)
            store.close()

    def test_unresolved_contradiction_blocks_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LearningStore(Path(directory) / "learning.sqlite", now=fixed_now)
            episodes = [
                episode(cast_id(1), correlation_group="idea-1"),
                episode(cast_id(2), correlation_group="idea-2"),
                episode(cast_id(3), correlation_group="idea-3"),
            ]
            for value in episodes:
                store.add_episode(value)
            lesson = lesson_proposal(
                [episodes[0]["episode_id"], episodes[1]["episode_id"]],
                contradictions=[episodes[2]["episode_id"]],
                disposition="unresolved",
            )
            store.propose_lesson(lesson)
            self.assertIn("contradiction_unresolved", store.eligibility(lesson["lesson_id"])["blockers"])
            with self.assertRaisesRegex(LearningContractError, "not eligible"):
                store.record_promotion(promotion(lesson_id=lesson["lesson_id"]))
            store.close()

    def test_human_activation_expiry_retirement_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "learning.sqlite"
            store = LearningStore(path, now=fixed_now)
            first = episode(cast_id(1), correlation_group="idea-1")
            second = episode(cast_id(2), correlation_group="idea-2")
            store.add_episode(first)
            store.add_episode(second)
            lesson = lesson_proposal([first["episode_id"], second["episode_id"]])
            store.propose_lesson(lesson)
            activation = promotion(lesson_id=lesson["lesson_id"])
            self.assertEqual(store.record_promotion(activation)["state"], "active")
            self.assertEqual(len(store.active_influences()), 1)
            self.assertEqual(
                store.active_influences(as_of=datetime(2026, 9, 2, tzinfo=timezone.utc)),
                [],
            )
            store.close()

            reopened = LearningStore(path, now=fixed_now)
            self.assertEqual(len(reopened.active_influences()), 1)
            retirement = promotion(
                decision_id="dddddddd-dddd-4ddd-8ddd-ddddddddddd2",
                lesson_id=lesson["lesson_id"],
                action="RETIRE",
                decided_utc="2026-08-25T01:05:00Z",
            )
            self.assertEqual(reopened.record_promotion(retirement)["state"], "retired")
            self.assertEqual(reopened.active_influences(), [])
            reopened.close()


def lesson_proposal(
    supports: list[str],
    *,
    lesson_id: str = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
    contradictions: list[str] | None = None,
    disposition: str | None = None,
) -> dict:
    contradictions = contradictions or []
    return {
        "schema_version": "glitch.crypto.lesson-proposal.v1",
        "lesson_id": lesson_id,
        "lane": "decision_metacognition",
        "claim": "This bounded decision treatment improves abstention quality in the named regime.",
        "conditions": ["BTCUSDT", "spread regime normal", "candidate maturity early"],
        "supporting_episode_ids": supports,
        "contradicting_episode_ids": contradictions,
        "contradiction_disposition": disposition or ("bounded" if contradictions else "none"),
        "contradiction_review": "Contradictions are absent or explicitly bounded by the named conditions.",
        "confidence": 0.7,
        "metric": "incremental calibrated net EV versus frozen baseline",
        "created_utc": "2026-08-25T01:02:00Z",
        "expires_utc": "2026-09-01T00:00:00Z",
        "rollback_condition": "Retire if holdout incremental EV is nonpositive or calibration degrades.",
        "status": "proposed",
    }


def cast_id(index: int) -> str:
    return f"bbbbbbbb-bbbb-4bbb-8bbb-{index:012x}"


def fixed_now() -> datetime:
    return datetime(2026, 8, 25, 1, 3, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
