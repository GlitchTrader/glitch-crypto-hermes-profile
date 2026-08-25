# Tasks: Durable event-triggered cognition boundary

**Rail item**: `GCHP-002` | **Inputs**: `spec.md`, `plan.md`, paired gateway schemas

## Contract tests

- [x] T001 Add replay/conflict/restart and lease tests.
- [x] T002 Add position-preemption-before-staging tests.
- [x] T003 Add strict output, stale packet, no-submit, and exact-retry tests.

## Implementation

- [x] T004 Implement strict event and packet-bound intent contracts.
- [x] T005 Implement the durable SQLite inbox and state machine.
- [x] T006 Implement two-phase stage-before-submit coordination.
- [x] T007 Update ontology and paired/operator schema metadata.

## Verification and evidence

- [x] T008 Regenerate `SHA256SUMS`, verify distribution, and run all tests.
- [x] T009 Update Rail and tracker evidence without overstating activation.

## Dependencies and stop lines

- Gateway event generation and calibrated candidate inputs remain external dependencies.
- Do not install a schedule, activate a model route, use exchange credentials, or
  claim autonomous/live readiness in this phase.
