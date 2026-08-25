# Feature Specification: Durable event-triggered cognition boundary

**Rail item**: `GCHP-002`
**Created**: `2026-08-25`
**Status**: Active
**Input**: Consolidated Glitch Crypto build brief and gateway GC-001/GC-002 contracts

## Outcomes and non-goals

- **Outcome**: Candidate and position cognition work can be durably enqueued,
  claimed, preempted, validated, staged, submitted, and recovered without giving
  the profile quantity, venue, or credential authority.
- **Non-goal**: Install a schedule, poll for trades, invoke a specific model,
  generate candidate events, enable live venue execution, or activate learning.

## User scenarios and independent tests

### User Story 1 - Durable idempotent event intake (Priority: P1)

A gateway or future event source can deliver the same immutable event more than
once without duplicating cognition work.

**Independent test**: An event ID/body replay returns the original event; the
same ID with different content conflicts; queued state survives restart.

### User Story 2 - Position work preempts slower work (Priority: P1)

A position event arriving while a candidate is under analysis requests
preemption before that candidate can stage an intent.

**Independent test**: The candidate cannot stage after preemption, the position
event claims first, and the candidate can be safely requeued afterward.

### User Story 3 - Strict bounded output and durable submission (Priority: P1)

Only one schema-valid intent for the exact current packet can be staged. Staging
precedes gateway submission; ambiguous client failure leaves the exact intent
available for idempotent replay.

**Independent test**: Malformed, stale, unsupported, or quantity-bearing output
never calls the gateway; one outer JSON fence is the only repair; a transport
failure retries the same UUID/body after restart.

## Requirements

- **FR-001**: Event ID and canonical body MUST be immutable and replay-safe.
- **FR-002**: Candidate and position events MUST persist in SQLite before claim.
- **FR-003**: Claims MUST use bounded leases and expired claims MUST be recoverable.
- **FR-004**: Position events MUST outrank queued candidate work and request preemption of unstaged candidate work.
- **FR-005**: Preempted work MUST NOT stage or submit an intent.
- **FR-006**: Model output MUST be exactly one `glitch.crypto.intent.v1` object after at most one syntactic outer-fence removal.
- **FR-007**: Action, packet, account, instrument, tranche, and action-specific fields MUST agree with the current authenticated packet.
- **FR-008**: Quantity, credential, native-order, policy, and unknown fields MUST be rejected.
- **FR-009**: A validated intent MUST be durably staged before gateway submission.
- **FR-010**: A staged intent MUST retain the exact UUID/body across transport error and restart.
- **FR-011**: Packet drift before staging MUST fail closed with zero gateway submission.
- **FR-012**: No setup or distribution file MAY install a schedule in this phase.

## Edge cases and failure states

- Duplicate event delivery, changed-body conflict, lease expiry, process restart.
- Position event arriving during candidate analysis.
- JSON prose, multiple objects, unknown fields, forbidden quantity, stale packet.
- Gateway transport failure after possible receipt processing.
- Receipt is retained only after the gateway returns it; staged intent remains
  authoritative until then.

## Key entities and ontology changes

- `CognitionEvent`, `EventClaim`, `StagedIntent`, and `CognitionReceipt`.

## Measurable success criteria

- **SC-001**: Deterministic tests prove replay, conflict, restart, preemption,
  strict validation, stage-before-submit, and exact retry.
- **SC-002**: Failed parsing/validation and stale packets result in zero calls to
  `GatewayClient.submit_intent`.
- **SC-003**: Distribution verification and the complete test suite pass.

## Assumptions and open questions

- **Assumption**: A later accepted gateway event source will provide immutable
  candidate/position events; this phase validates the consumer boundary first.
- **Question**: The final Hermes model-invocation adapter remains unselected and
  cannot be scheduled until the gateway event and numerical contracts are accepted.
