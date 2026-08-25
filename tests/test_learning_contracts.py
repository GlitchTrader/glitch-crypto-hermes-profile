from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from learning_contracts import LearningContractError, validate_learning_episode, validate_promotion_decision


class LearningContractTests(unittest.TestCase):
    def test_complete_treatment_identity_is_mandatory(self) -> None:
        value = episode()
        self.assertEqual(validate_learning_episode(value)["lane"], "decision_metacognition")
        del value["treatment"]["prompt_hash"]
        with self.assertRaisesRegex(LearningContractError, "missing"):
            validate_learning_episode(value)

    def test_no_trade_counterfactual_cannot_claim_realized_pnl(self) -> None:
        value = episode(episode_type="matured_no_trade")
        value["realized_pnl_usd"] = 12.0
        with self.assertRaisesRegex(LearningContractError, "only completed trades"):
            validate_learning_episode(value)
        del value["realized_pnl_usd"]
        value["metrics"] = {"realized_counterfactual_usd": 12.0}
        with self.assertRaisesRegex(LearningContractError, "counterfactual"):
            validate_learning_episode(value)

    def test_promotion_requires_human_actor_and_approval_identity(self) -> None:
        value = promotion()
        value["actor"] = "model"
        with self.assertRaisesRegex(LearningContractError, "must be human"):
            validate_promotion_decision(value)
        value["actor"] = "human"
        value["human_approval_id"] = ""
        with self.assertRaisesRegex(LearningContractError, "human approval"):
            validate_promotion_decision(value)


def treatment() -> dict:
    return {
        "model_provider": "openai-codex",
        "model_id": "gpt-test",
        "reasoning_effort": "medium",
        "soul_hash": "a" * 64,
        "prompt_hash": "b" * 64,
        "skill_hashes": {"crypto-market": "c" * 64},
        "memory_version": "memory-v1",
        "numerical_model_versions": {"target-first": "baseline-v1"},
        "feature_version": "features-v1",
    }


def episode(
    episode_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
    *,
    lane: str = "decision_metacognition",
    episode_type: str = "decision_review",
    correlation_group: str = "market-idea-1",
) -> dict:
    return {
        "schema_version": "glitch.crypto.learning-episode.v1",
        "episode_id": episode_id,
        "lane": lane,
        "episode_type": episode_type,
        "occurred_utc": "2026-08-25T01:00:00Z",
        "correlation_group": correlation_group,
        "evidence_refs": ["packet:abc", "intent:def", "receipt:ghi"],
        "summary": "The decision remained attributable to the frozen treatment.",
        "treatment": treatment(),
        "metrics": {"decision_quality_score": 0.7},
    }


def promotion(
    decision_id: str = "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
    lesson_id: str = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
    action: str = "ACTIVATE",
    decided_utc: str = "2026-08-25T01:04:00Z",
) -> dict:
    return {
        "schema_version": "glitch.crypto.promotion-decision.v1",
        "decision_id": decision_id,
        "lesson_id": lesson_id,
        "action": action,
        "actor": "human",
        "human_approval_id": "approval:operator:2026-08-25:1",
        "decided_utc": decided_utc,
        "reason": "Independent evidence and rollback contract reviewed.",
    }


if __name__ == "__main__":
    unittest.main()
