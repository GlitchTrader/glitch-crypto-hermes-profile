# Implementation Plan: Durable event-triggered cognition boundary

**Rail item**: `GCHP-002` | **Date**: `2026-08-25` | **Spec**: `operations/specs/GCHP-002/spec.md`

## Summary

Add a standard-library SQLite event inbox, strict packet-bound intent parser, and
two-phase coordinator. Keep event generation, model invocation, scheduling, and
venue execution outside this source increment.

## Source truth inspected

- Profile constitution, SOUL, authority, operator metadata, skills, and gateway client.
- Paired gateway packet, intent, receipt, UUID/body replay, operator-token, and native-protection contracts.
- Glitch NT doctrine for event-specific reassessment, frozen evidence identity, and operational-versus-learning separation.

## Technical context

- **Runtime**: Python 3.12+ standard library.
- **Distribution**: every added source/spec/test is distribution-owned and SHA-bound.
- **Testing**: distribution verifier plus `unittest` discovery.
- **Constraints**: no exchange credentials, no quantity, no direct venue calls,
  no schedule, packet identity at staging, position preemption before staging.

## Constitution and authority check

- Cognition without credentials: enforced by exact field allowlists and static tests.
- Current evidence outranks memory: exact current packet is required at staging.
- Objective is not edge: event contract contains no target-derived trigger.
- Quantity/mutation remain deterministic: gateway client is the only submission boundary.
- Reversible learning: not activated in this phase.

## Design and affected paths

- `scripts/cognition_contracts.py`: event and strict intent validation.
- `scripts/cognition_inbox.py`: durable event/lease/staged-intent state machine.
- `scripts/cognition_coordinator.py`: packet check, stage-before-submit, retry.
- `tests/test_cognition_*.py`: independent contract and recovery tests.
- `operations/ontology.md`, `operator.json`, `paired-contract.json`: declared entities and schemas.

## Acceptance evidence

All failure paths are exercised with fake packets/gateway calls. No test substitutes
for accepted gateway event generation, calibrated numerical evidence, profile
installation, authenticated Testnet evidence, or production activation.

## Promotion and rollback boundary

The source is dormant and no scheduled job is installed. Removing the three
scripts and their local spool removes the capability without gateway migration.
