"""Two-phase packet-bound cognition coordination; no model or schedule is installed."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cognition_contracts import ContractError, parse_model_intent
from cognition_inbox import CognitionInbox, EventClaim


class GatewayBoundary(Protocol):
    def packet(self) -> dict[str, Any]: ...

    def submit_intent(self, intent: dict[str, Any]) -> dict[str, Any]: ...


class CognitionPreempted(RuntimeError):
    """Position work requested preemption before intent staging."""


@dataclass(frozen=True)
class StagedDecision:
    event_id: str
    intent: dict[str, Any]
    bounded_repair_used: bool


class CognitionCoordinator:
    def __init__(self, inbox: CognitionInbox, gateway: GatewayBoundary) -> None:
        self.inbox = inbox
        self.gateway = gateway

    def claim_next(self, worker_id: str, lease_seconds: int = 120) -> EventClaim | None:
        return self.inbox.claim(worker_id, lease_seconds)

    def stage_model_output(self, claim: EventClaim, raw_output: str) -> StagedDecision:
        event_id = claim.event["event_id"]
        if claim.staged_intent is not None:
            raise ContractError("event already has a staged intent; resume it without another model call")
        if self.inbox.preemption_requested(event_id, claim.lease_token):
            self.inbox.acknowledge_preemption(event_id, claim.lease_token)
            raise CognitionPreempted("position work preempted unstaged cognition")
        try:
            packet = self.gateway.packet()
        except Exception as error:
            self.inbox.release_unstaged(event_id, claim.lease_token, f"packet_unavailable:{type(error).__name__}")
            raise
        if packet.get("packet_id") != claim.event.get("packet_id"):
            self.inbox.fail_unstaged(event_id, claim.lease_token, "event_packet_is_stale")
            raise ContractError("event packet is no longer current")
        if claim.event["event_type"] == "POSITION":
            try:
                _require_position_event_is_current(claim.event, packet)
            except Exception as error:
                self.inbox.fail_unstaged(event_id, claim.lease_token, f"position_event_invalid:{type(error).__name__}")
                raise
        try:
            intent, repaired = parse_model_intent(raw_output, packet)
        except Exception as error:
            self.inbox.fail_unstaged(event_id, claim.lease_token, f"model_output_invalid:{type(error).__name__}")
            raise
        try:
            self.inbox.stage_intent(event_id, claim.lease_token, intent)
        except ContractError:
            if self.inbox.preemption_requested(event_id, claim.lease_token):
                self.inbox.acknowledge_preemption(event_id, claim.lease_token)
                raise CognitionPreempted("position work preempted cognition before staging")
            raise
        return StagedDecision(event_id=event_id, intent=intent, bounded_repair_used=repaired)

    def submit_staged(self, claim: EventClaim) -> dict[str, Any]:
        staged = claim.staged_intent
        if staged is None:
            view = self.inbox.get(claim.event["event_id"])
            staged = None if view is None else view["staged_intent"]
        if staged is None:
            raise ContractError("event has no staged intent to submit")
        try:
            receipt = self.gateway.submit_intent(staged)
        except Exception as error:
            self.inbox.release_staged(
                claim.event["event_id"],
                claim.lease_token,
                f"gateway_submission_unresolved:{type(error).__name__}",
            )
            raise
        try:
            _require_receipt_matches(staged, receipt)
        except Exception as error:
            self.inbox.release_staged(
                claim.event["event_id"],
                claim.lease_token,
                f"gateway_receipt_invalid:{type(error).__name__}",
            )
            raise
        self.inbox.complete(claim.event["event_id"], claim.lease_token, receipt)
        return receipt

    def stage_and_submit(self, claim: EventClaim, raw_output: str) -> dict[str, Any]:
        self.stage_model_output(claim, raw_output)
        return self.submit_staged(claim)


def _require_position_event_is_current(event: dict[str, Any], packet: dict[str, Any]) -> None:
    state = packet.get("state")
    positions = state.get("positions") if isinstance(state, dict) else None
    if not isinstance(positions, list):
        raise ContractError("packet positions are unavailable for position event")
    tranche_id = event.get("tranche_id")
    if not any(isinstance(position, dict) and position.get("tranche_id") == tranche_id for position in positions):
        raise ContractError("position event tranche is no longer current")


def _require_receipt_matches(intent: dict[str, Any], receipt: Any) -> None:
    if not isinstance(receipt, dict):
        raise ContractError("gateway receipt must be an object")
    if receipt.get("schema_version") != "glitch.crypto.intent-receipt.v1":
        raise ContractError("gateway receipt schema is invalid")
    if receipt.get("intent_id") != intent.get("intent_id"):
        raise ContractError("gateway receipt intent identity does not match staged intent")
