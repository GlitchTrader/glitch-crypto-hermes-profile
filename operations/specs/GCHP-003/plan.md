# Implementation Plan: Attributable three-lane learning supervisor

**Rail item**: `GCHP-003` | **Date**: `2026-08-25` | **Spec**: `operations/specs/GCHP-003/spec.md`

## Summary

Add strict standard-library learning schemas and a SQLite WAL/FULL-sync store.
Separate eligibility calculation from explicit human promotion. Expose no source
editing, policy mutation, model routing, scheduler, or gateway call.

## Source truth inspected

- Profile constitution, SOUL learning doctrine, learning skill, ontology, and Rail.
- GCHP-002 immutable event/treatment identity and paired gateway evidence boundary.
- Consolidated brief requirements for three learning lanes, episode attribution,
  experimental treatments, independent confirmation, contradiction, expiry, and rollback.

## Technical context

- **Runtime**: Python 3.12+ standard library and SQLite.
- **Distribution**: source/spec/test/docs are SHA-bound.
- **Testing**: distribution verification plus `unittest` discovery.
- **Constraints**: no automatic activation, self-edit, schedule, gateway mutation,
  credential, counterfactual-as-realized, or operational-to-market leakage.

## Constitution and authority check

- Current evidence outranks memory: evidence references and episode identity required.
- Three-lane reversible learning: encoded in separate lanes and promotion states.
- One outcome cannot activate: two independent correlation groups required.
- Governance: a distinct human approval ID is mandatory for activation.

## Design and affected paths

- `scripts/learning_contracts.py`: exact episode, lesson, and promotion schemas.
- `scripts/learning_store.py`: replay-safe storage, eligibility, activation, expiry, retirement.
- `tests/test_learning_*.py`: lane, evidence, restart, and governance cases.
- `docs/LEARNING_SUPERVISOR.md`, ontology, SOUL, skill, and operator metadata.

## Acceptance evidence

Deterministic fixtures prove source behavior only. Gateway episode production,
replay calibration, model improvement, installed-profile operation, and live
performance remain unaccepted until their own evidence exists.

## Promotion and rollback boundary

No lesson is active by default and no schedule is installed. Deleting the local
learning database removes proposed/active local influence without changing source
or gateway state. Production promotion remains a separate human-authorized gate.
