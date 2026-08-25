"""Durable cognition event inbox with leases, preemption, and staged intents."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from cognition_contracts import ContractError, body_hash, canonical_json, validate_cognition_event


@dataclass(frozen=True)
class EventClaim:
    event: dict[str, Any]
    lease_token: str
    lease_owner: str
    lease_expires_utc: str
    attempt: int
    staged_intent: dict[str, Any] | None


class CognitionInbox:
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

    def enqueue(self, value: Any) -> dict[str, Any]:
        event = validate_cognition_event(value)
        event_json = canonical_json(event)
        digest = body_hash(event)
        now = self._now_text()
        self._begin()
        try:
            existing = self._db.execute(
                "SELECT body_hash, state FROM cognition_events WHERE event_id = ?",
                (event["event_id"],),
            ).fetchone()
            if existing is not None:
                if existing["body_hash"] != digest:
                    raise ContractError("cognition event ID was reused with changed content")
                self._commit()
                return {
                    "event_id": event["event_id"],
                    "state": existing["state"],
                    "replayed": True,
                }
            if event["event_type"] == "POSITION":
                self._db.execute(
                    """
                    UPDATE cognition_events
                       SET state = 'preempt_requested', updated_utc = ?
                     WHERE state = 'in_progress'
                       AND event_type != 'POSITION'
                       AND intent_json IS NULL
                    """,
                    (now,),
                )
            self._db.execute(
                """
                INSERT INTO cognition_events (
                    event_id, body_hash, event_json, event_type, priority,
                    created_utc, expires_utc, state, attempt, updated_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?)
                """,
                (
                    event["event_id"],
                    digest,
                    event_json,
                    event["event_type"],
                    100 if event["event_type"] == "POSITION" else 50,
                    event["created_utc"],
                    event["expires_utc"],
                    now,
                ),
            )
            self._commit()
            return {"event_id": event["event_id"], "state": "queued", "replayed": False}
        except Exception:
            self._rollback()
            raise

    def claim(self, worker_id: str, lease_seconds: int = 120) -> EventClaim | None:
        owner = _required_text(worker_id, "worker ID", 200)
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 5 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be an integer between 5 and 3600")
        now_dt = self._now_utc()
        now = _format_utc(now_dt)
        lease_expires = _format_utc(now_dt + timedelta(seconds=lease_seconds))
        token = str(uuid.uuid4())
        self._begin()
        try:
            self._recover_expired_leases(now)
            self._db.execute(
                """
                UPDATE cognition_events
                   SET state = 'expired', updated_utc = ?
                 WHERE state = 'queued' AND expires_utc <= ?
                """,
                (now, now),
            )
            row = self._db.execute(
                """
                SELECT * FROM cognition_events
                 WHERE (state = 'intent_staged' AND lease_token IS NULL)
                    OR state = 'queued'
                 ORDER BY CASE WHEN state = 'intent_staged' THEN 1 ELSE 0 END DESC,
                          priority DESC, created_utc ASC, event_id ASC
                 LIMIT 1
                """
            ).fetchone()
            if row is None:
                self._commit()
                return None
            next_state = "intent_staged" if row["state"] == "intent_staged" else "in_progress"
            updated = self._db.execute(
                """
                UPDATE cognition_events
                   SET state = ?, attempt = attempt + 1,
                       lease_token = ?, lease_owner = ?, lease_expires_utc = ?, updated_utc = ?
                 WHERE event_id = ? AND state = ? AND lease_token IS NULL
                """,
                (next_state, token, owner, lease_expires, now, row["event_id"], row["state"]),
            )
            if updated.rowcount != 1:
                raise RuntimeError("cognition claim lost its transactional race")
            claimed = self._db.execute(
                "SELECT * FROM cognition_events WHERE event_id = ?",
                (row["event_id"],),
            ).fetchone()
            self._commit()
            return _claim(claimed)
        except Exception:
            self._rollback()
            raise

    def preemption_requested(self, event_id: str, lease_token: str) -> bool:
        row = self._lease_row(event_id, lease_token)
        return row["state"] == "preempt_requested"

    def acknowledge_preemption(self, event_id: str, lease_token: str) -> None:
        now = self._now_text()
        self._begin()
        try:
            updated = self._db.execute(
                """
                UPDATE cognition_events
                   SET state = CASE WHEN expires_utc <= ? THEN 'expired' ELSE 'queued' END,
                       lease_token = NULL, lease_owner = NULL, lease_expires_utc = NULL,
                       updated_utc = ?
                 WHERE event_id = ? AND lease_token = ? AND state = 'preempt_requested'
                """,
                (now, now, event_id, lease_token),
            )
            if updated.rowcount != 1:
                raise ContractError("cognition event is not preemptible under this lease")
            self._commit()
        except Exception:
            self._rollback()
            raise

    def stage_intent(self, event_id: str, lease_token: str, intent: dict[str, Any]) -> dict[str, Any]:
        intent_json = canonical_json(intent)
        digest = body_hash(intent)
        now = self._now_text()
        self._begin()
        try:
            row = self._db.execute(
                "SELECT * FROM cognition_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None or row["lease_token"] != lease_token:
                raise ContractError("cognition event lease does not own staging")
            if row["state"] == "preempt_requested":
                raise ContractError("preempted cognition cannot stage an intent")
            if row["state"] == "intent_staged":
                if row["intent_hash"] != digest:
                    raise ContractError("staged intent content cannot change")
                self._commit()
                return json.loads(row["intent_json"])
            if row["state"] != "in_progress" or row["lease_expires_utc"] <= now:
                raise ContractError("cognition event is not stageable under this lease")
            if row["expires_utc"] <= now:
                raise ContractError("expired cognition event cannot stage an intent")
            self._db.execute(
                """
                UPDATE cognition_events
                   SET state = 'intent_staged', intent_hash = ?, intent_json = ?, updated_utc = ?
                 WHERE event_id = ?
                """,
                (digest, intent_json, now, event_id),
            )
            self._commit()
            return dict(intent)
        except Exception:
            self._rollback()
            raise

    def complete(self, event_id: str, lease_token: str, receipt: dict[str, Any]) -> None:
        now = self._now_text()
        self._begin()
        try:
            updated = self._db.execute(
                """
                UPDATE cognition_events
                   SET state = 'completed', receipt_json = ?,
                       lease_token = NULL, lease_owner = NULL, lease_expires_utc = NULL,
                       last_error = NULL, updated_utc = ?
                 WHERE event_id = ? AND lease_token = ? AND state = 'intent_staged'
                """,
                (canonical_json(receipt), now, event_id, lease_token),
            )
            if updated.rowcount != 1:
                raise ContractError("staged cognition event is not completable under this lease")
            self._commit()
        except Exception:
            self._rollback()
            raise

    def fail_unstaged(self, event_id: str, lease_token: str, reason: str) -> None:
        message = _required_text(reason, "failure reason", 2000)
        now = self._now_text()
        self._begin()
        try:
            updated = self._db.execute(
                """
                UPDATE cognition_events
                   SET state = 'failed', last_error = ?,
                       lease_token = NULL, lease_owner = NULL, lease_expires_utc = NULL,
                       updated_utc = ?
                 WHERE event_id = ? AND lease_token = ?
                   AND state IN ('in_progress', 'preempt_requested') AND intent_json IS NULL
                """,
                (message, now, event_id, lease_token),
            )
            if updated.rowcount != 1:
                raise ContractError("cognition event cannot fail after intent staging")
            self._commit()
        except Exception:
            self._rollback()
            raise

    def release_unstaged(self, event_id: str, lease_token: str, reason: str) -> None:
        message = _required_text(reason, "release reason", 2000)
        now = self._now_text()
        self._begin()
        try:
            updated = self._db.execute(
                """
                UPDATE cognition_events
                   SET state = CASE WHEN expires_utc <= ? THEN 'expired' ELSE 'queued' END,
                       lease_token = NULL, lease_owner = NULL, lease_expires_utc = NULL,
                       last_error = ?, updated_utc = ?
                 WHERE event_id = ? AND lease_token = ?
                   AND state = 'in_progress' AND intent_json IS NULL
                """,
                (now, message, now, event_id, lease_token),
            )
            if updated.rowcount != 1:
                raise ContractError("unstaged cognition event is not releasable under this lease")
            self._commit()
        except Exception:
            self._rollback()
            raise

    def release_staged(self, event_id: str, lease_token: str, reason: str) -> None:
        message = _required_text(reason, "release reason", 2000)
        now = self._now_text()
        self._begin()
        try:
            updated = self._db.execute(
                """
                UPDATE cognition_events
                   SET lease_token = NULL, lease_owner = NULL, lease_expires_utc = NULL,
                       last_error = ?, updated_utc = ?
                 WHERE event_id = ? AND lease_token = ? AND state = 'intent_staged'
                """,
                (message, now, event_id, lease_token),
            )
            if updated.rowcount != 1:
                raise ContractError("staged cognition event is not releasable under this lease")
            self._commit()
        except Exception:
            self._rollback()
            raise

    def get(self, event_id: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM cognition_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return None if row is None else _view(row)

    def _lease_row(self, event_id: str, lease_token: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM cognition_events WHERE event_id = ? AND lease_token = ?",
            (event_id, lease_token),
        ).fetchone()
        if row is None:
            raise ContractError("cognition event lease is not current")
        return row

    def _recover_expired_leases(self, now: str) -> None:
        self._db.execute(
            """
            UPDATE cognition_events
               SET state = CASE
                     WHEN state = 'intent_staged' THEN 'intent_staged'
                     WHEN expires_utc <= ? THEN 'expired'
                     ELSE 'queued'
                   END,
                   lease_token = NULL, lease_owner = NULL, lease_expires_utc = NULL,
                   updated_utc = ?
             WHERE lease_token IS NOT NULL AND lease_expires_utc <= ?
            """,
            (now, now, now),
        )

    def _initialize(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS cognition_events (
                event_id TEXT PRIMARY KEY,
                body_hash TEXT NOT NULL,
                event_json TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN ('CANDIDATE', 'POSITION')),
                priority INTEGER NOT NULL,
                created_utc TEXT NOT NULL,
                expires_utc TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN (
                    'queued', 'in_progress', 'preempt_requested', 'intent_staged',
                    'completed', 'failed', 'expired'
                )),
                attempt INTEGER NOT NULL,
                lease_token TEXT,
                lease_owner TEXT,
                lease_expires_utc TEXT,
                intent_hash TEXT,
                intent_json TEXT,
                receipt_json TEXT,
                last_error TEXT,
                updated_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS cognition_events_claim
                ON cognition_events(state, priority DESC, created_utc ASC);
            """
        )

    def _now_utc(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("cognition inbox clock must be timezone-aware")
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


def _claim(row: sqlite3.Row) -> EventClaim:
    return EventClaim(
        event=json.loads(row["event_json"]),
        lease_token=row["lease_token"],
        lease_owner=row["lease_owner"],
        lease_expires_utc=row["lease_expires_utc"],
        attempt=int(row["attempt"]),
        staged_intent=None if row["intent_json"] is None else json.loads(row["intent_json"]),
    )


def _view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event": json.loads(row["event_json"]),
        "state": row["state"],
        "attempt": int(row["attempt"]),
        "lease_owner": row["lease_owner"],
        "lease_expires_utc": row["lease_expires_utc"],
        "staged_intent": None if row["intent_json"] is None else json.loads(row["intent_json"]),
        "receipt": None if row["receipt_json"] is None else json.loads(row["receipt_json"]),
        "last_error": row["last_error"],
        "updated_utc": row["updated_utc"],
    }


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_text(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain 1-{maximum} characters")
    return value.strip()
