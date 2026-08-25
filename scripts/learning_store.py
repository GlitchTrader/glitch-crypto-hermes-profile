"""Durable evidence-gated learning store with explicit human promotion."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from learning_contracts import (
    LearningContractError,
    body_hash,
    canonical_json,
    validate_learning_episode,
    validate_lesson_proposal,
    validate_promotion_decision,
)


class LearningStore:
    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._db = sqlite3.connect(self.path, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._initialize()

    def close(self) -> None:
        self._db.close()

    def add_episode(self, value: Any) -> dict[str, Any]:
        episode = validate_learning_episode(value)
        digest = body_hash(episode)
        payload = canonical_json(episode)
        self._begin()
        try:
            existing = self._db.execute(
                "SELECT body_hash FROM learning_episodes WHERE episode_id = ?",
                (episode["episode_id"],),
            ).fetchone()
            if existing is not None:
                if existing["body_hash"] != digest:
                    raise LearningContractError("learning episode ID was reused with changed content")
                self._commit()
                return {"episode_id": episode["episode_id"], "replayed": True}
            self._db.execute(
                """
                INSERT INTO learning_episodes (
                    episode_id, body_hash, episode_json, lane, episode_type,
                    correlation_group, occurred_utc, recorded_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode["episode_id"],
                    digest,
                    payload,
                    episode["lane"],
                    episode["episode_type"],
                    episode["correlation_group"],
                    episode["occurred_utc"],
                    self._now_text(),
                ),
            )
            self._commit()
            return {"episode_id": episode["episode_id"], "replayed": False}
        except Exception:
            self._rollback()
            raise

    def propose_lesson(self, value: Any) -> dict[str, Any]:
        lesson = validate_lesson_proposal(value)
        digest = body_hash(lesson)
        payload = canonical_json(lesson)
        self._begin()
        try:
            existing = self._db.execute(
                "SELECT body_hash, status FROM lessons WHERE lesson_id = ?",
                (lesson["lesson_id"],),
            ).fetchone()
            if existing is not None:
                if existing["body_hash"] != digest:
                    raise LearningContractError("lesson ID was reused with changed content")
                self._commit()
                return {
                    "lesson_id": lesson["lesson_id"],
                    "state": existing["status"],
                    "replayed": True,
                }
            self._require_episode_links(lesson)
            now = self._now_text()
            self._db.execute(
                """
                INSERT INTO lessons (
                    lesson_id, body_hash, lesson_json, lane, status,
                    created_utc, expires_utc, updated_utc
                ) VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?)
                """,
                (
                    lesson["lesson_id"],
                    digest,
                    payload,
                    lesson["lane"],
                    lesson["created_utc"],
                    lesson["expires_utc"],
                    now,
                ),
            )
            self._commit()
            return {"lesson_id": lesson["lesson_id"], "state": "proposed", "replayed": False}
        except Exception:
            self._rollback()
            raise

    def eligibility(self, lesson_id: str, *, as_of: datetime | None = None) -> dict[str, Any]:
        row = self._lesson_row(lesson_id)
        return self._eligibility(row, self._as_of(as_of))

    def record_promotion(self, value: Any) -> dict[str, Any]:
        decision = validate_promotion_decision(value)
        digest = body_hash(decision)
        payload = canonical_json(decision)
        self._begin()
        try:
            existing = self._db.execute(
                "SELECT body_hash FROM promotion_decisions WHERE decision_id = ?",
                (decision["decision_id"],),
            ).fetchone()
            if existing is not None:
                if existing["body_hash"] != digest:
                    raise LearningContractError("promotion decision ID was reused with changed content")
                lesson = self._lesson_row(decision["lesson_id"])
                self._commit()
                return {
                    "decision_id": decision["decision_id"],
                    "lesson_id": decision["lesson_id"],
                    "state": lesson["status"],
                    "replayed": True,
                }
            lesson = self._lesson_row(decision["lesson_id"])
            action = decision["action"]
            decided_at = _parse_utc(decision["decided_utc"])
            if decided_at < _parse_utc(lesson["created_utc"]):
                raise LearningContractError("promotion decision cannot predate the lesson")
            if lesson["latest_decision_id"] is not None:
                previous = self._db.execute(
                    "SELECT decided_utc FROM promotion_decisions WHERE decision_id = ?",
                    (lesson["latest_decision_id"],),
                ).fetchone()
                if previous is None or decision["decided_utc"] <= previous["decided_utc"]:
                    raise LearningContractError("promotion decisions must be strictly chronological")
            next_state: str
            if action == "ACTIVATE":
                report = self._eligibility(lesson, decided_at)
                if not report["eligible"]:
                    raise LearningContractError(
                        "lesson is not eligible for activation: " + ",".join(report["blockers"])
                    )
                next_state = "active"
            elif action == "REJECT":
                if lesson["status"] != "proposed":
                    raise LearningContractError("only a proposed lesson can be rejected")
                next_state = "rejected"
            else:
                if lesson["status"] != "active":
                    raise LearningContractError("only an active lesson can be retired")
                next_state = "retired"
            self._db.execute(
                """
                INSERT INTO promotion_decisions (
                    decision_id, body_hash, decision_json, lesson_id, action, decided_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision["decision_id"],
                    digest,
                    payload,
                    decision["lesson_id"],
                    action,
                    decision["decided_utc"],
                ),
            )
            self._db.execute(
                """
                UPDATE lessons
                   SET status = ?, latest_decision_id = ?, updated_utc = ?
                 WHERE lesson_id = ?
                """,
                (next_state, decision["decision_id"], self._now_text(), decision["lesson_id"]),
            )
            self._commit()
            return {
                "decision_id": decision["decision_id"],
                "lesson_id": decision["lesson_id"],
                "state": next_state,
                "replayed": False,
            }
        except Exception:
            self._rollback()
            raise

    def active_influences(self, *, as_of: datetime | None = None) -> list[dict[str, Any]]:
        instant = self._as_of(as_of)
        rows = self._db.execute(
            """
            SELECT lesson_json, latest_decision_id
              FROM lessons
             WHERE status = 'active' AND expires_utc > ?
             ORDER BY lane ASC, created_utc ASC, lesson_id ASC
            """,
            (_format_utc(instant),),
        ).fetchall()
        result = []
        for row in rows:
            lesson = json.loads(row["lesson_json"])
            result.append({
                "lesson_id": lesson["lesson_id"],
                "lane": lesson["lane"],
                "claim": lesson["claim"],
                "conditions": lesson["conditions"],
                "supporting_episode_ids": lesson["supporting_episode_ids"],
                "contradicting_episode_ids": lesson["contradicting_episode_ids"],
                "confidence": lesson["confidence"],
                "metric": lesson["metric"],
                "expires_utc": lesson["expires_utc"],
                "rollback_condition": lesson["rollback_condition"],
                "promotion_decision_id": row["latest_decision_id"],
            })
        return result

    def get_lesson(self, lesson_id: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM lessons WHERE lesson_id = ?",
            (lesson_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "lesson": json.loads(row["lesson_json"]),
            "state": row["status"],
            "latest_decision_id": row["latest_decision_id"],
            "updated_utc": row["updated_utc"],
        }

    def _require_episode_links(self, lesson: dict[str, Any]) -> None:
        episode_ids = lesson["supporting_episode_ids"] + lesson["contradicting_episode_ids"]
        for episode_id in episode_ids:
            row = self._db.execute(
                "SELECT lane FROM learning_episodes WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
            if row is None:
                raise LearningContractError(f"lesson episode evidence is missing: {episode_id}")
            if row["lane"] == "operational":
                raise LearningContractError("operational evidence cannot support or contradict a trading lesson")
            if row["lane"] != lesson["lane"]:
                raise LearningContractError("lesson episode evidence must belong to the same learning lane")

    def _eligibility(self, row: sqlite3.Row, as_of: datetime) -> dict[str, Any]:
        lesson = json.loads(row["lesson_json"])
        support_rows = [self._episode_row(item) for item in lesson["supporting_episode_ids"]]
        contradiction_rows = [self._episode_row(item) for item in lesson["contradicting_episode_ids"]]
        blockers: list[str] = []
        if row["status"] != "proposed":
            blockers.append("lesson_not_proposed")
        if lesson["expires_utc"] <= _format_utc(as_of):
            blockers.append("lesson_expired")
        if len(support_rows) < 2:
            blockers.append("independent_support_count_below_two")
        correlation_groups = {item["correlation_group"] for item in support_rows}
        if len(correlation_groups) < 2:
            blockers.append("independent_correlation_groups_below_two")
        if any(item["lane"] != lesson["lane"] for item in support_rows + contradiction_rows):
            blockers.append("learning_lane_mismatch")
        if any(item["lane"] == "operational" for item in support_rows + contradiction_rows):
            blockers.append("operational_evidence_quarantined")
        if lesson["contradiction_disposition"] == "unresolved":
            blockers.append("contradiction_unresolved")
        if len(contradiction_rows) >= len(support_rows) and contradiction_rows:
            blockers.append("contradiction_not_outweighed_by_support")
        return {
            "schema_version": "glitch.crypto.lesson-eligibility.v1",
            "lesson_id": lesson["lesson_id"],
            "eligible": not blockers,
            "blockers": sorted(blockers),
            "supporting_episode_count": len(support_rows),
            "independent_correlation_group_count": len(correlation_groups),
            "contradicting_episode_count": len(contradiction_rows),
            "evaluated_utc": _format_utc(as_of),
        }

    def _episode_row(self, episode_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM learning_episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
        if row is None:
            raise LearningContractError(f"learning episode is missing: {episode_id}")
        return row

    def _lesson_row(self, lesson_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM lessons WHERE lesson_id = ?",
            (lesson_id,),
        ).fetchone()
        if row is None:
            raise LearningContractError("lesson does not exist")
        return row

    def _initialize(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS learning_episodes (
                episode_id TEXT PRIMARY KEY,
                body_hash TEXT NOT NULL,
                episode_json TEXT NOT NULL,
                lane TEXT NOT NULL CHECK (lane IN (
                    'market_model', 'decision_metacognition', 'portfolio_management', 'operational'
                )),
                episode_type TEXT NOT NULL,
                correlation_group TEXT NOT NULL,
                occurred_utc TEXT NOT NULL,
                recorded_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_id TEXT PRIMARY KEY,
                body_hash TEXT NOT NULL,
                lesson_json TEXT NOT NULL,
                lane TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN (
                    'proposed', 'active', 'rejected', 'retired'
                )),
                created_utc TEXT NOT NULL,
                expires_utc TEXT NOT NULL,
                latest_decision_id TEXT,
                updated_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS promotion_decisions (
                decision_id TEXT PRIMARY KEY,
                body_hash TEXT NOT NULL,
                decision_json TEXT NOT NULL,
                lesson_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK (action IN ('ACTIVATE', 'REJECT', 'RETIRE')),
                decided_utc TEXT NOT NULL,
                FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id)
            );
            CREATE INDEX IF NOT EXISTS learning_episode_lane_time
                ON learning_episodes(lane, occurred_utc);
            CREATE INDEX IF NOT EXISTS lesson_state_expiry
                ON lessons(status, expires_utc);
            """
        )

    def _as_of(self, value: datetime | None) -> datetime:
        instant = self._now_utc() if value is None else value
        if instant.tzinfo is None:
            raise ValueError("learning clock must be timezone-aware")
        return instant.astimezone(timezone.utc)

    def _now_utc(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("learning store clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _now_text(self) -> str:
        return _format_utc(self._now_utc())

    def _begin(self) -> None:
        self._db.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self._db.execute("COMMIT")

    def _rollback(self) -> None:
        if self._db.in_transaction:
            self._db.execute("ROLLBACK")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
