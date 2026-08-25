# Feature Specification: Attributable three-lane learning supervisor

**Rail item**: `GCHP-003`
**Created**: `2026-08-25`
**Status**: Active
**Input**: Consolidated build brief, profile constitution, and GCHP-002 evidence boundary

## Outcomes and non-goals

- **Outcome**: Durable episodes, proposed lessons, contradiction evidence, and
  explicit human promotion decisions remain attributable, lane-separated,
  expiring, reversible, and treatment-versioned.
- **Non-goal**: Automatically edit SOUL/skills/source, install a learning
  schedule, infer an episode from incomplete gateway data, train a model, or
  activate any live influence from this source increment.

## User scenarios and independent tests

### User Story 1 - Retain attributable episodes (Priority: P1)

Completed trades, matured no-trade observations, decision reviews, position
management results, and operational faults retain immutable evidence/treatment
identity without mixing operational defects into trading learning.

**Independent test**: Same ID/body replays, changed body conflicts, treatment
fields are mandatory, and operational episodes cannot support a market lesson.

### User Story 2 - Evaluate lessons conservatively (Priority: P1)

A proposed lesson remains inactive until repeated independent supporting evidence,
contradiction review, metric, expiry, and rollback are present.

**Independent test**: One episode and correlated episodes fail eligibility; two
independent same-lane episodes can become eligible; unresolved contradiction and
expiry fail closed.

### User Story 3 - Human promotion and rollback (Priority: P1)

Only an explicit recorded human decision can activate, reject, revise, or retire
a lesson, and active influence disappears on expiry or retirement.

**Independent test**: Activation without an eligible lesson or human approval ID
is rejected; retirement is durable; restart reconstructs the same active set.

## Requirements

- **FR-001**: Episodes and lessons MUST use immutable UUID/body replay semantics.
- **FR-002**: Market/model, decision/metacognition, and portfolio/management lanes MUST remain distinct.
- **FR-003**: Operational faults MUST use a quarantined operational lane and MUST NOT support trading lessons.
- **FR-004**: Each episode MUST record evidence references, correlation group, and complete model/prompt/skill/memory/numerical/feature treatment identity.
- **FR-005**: Counterfactual no-trade observations MUST NOT be represented as realized PnL.
- **FR-006**: A lesson MUST name conditions, support, contradictions, confidence, metric, expiry, rollback, and proposed status.
- **FR-007**: Eligibility MUST require at least two supporting episodes from at least two correlation groups.
- **FR-008**: Missing support, lane mismatch, unresolved contradiction, expiry, or missing evidence MUST fail closed.
- **FR-009**: Activation MUST require a separate explicit human promotion record.
- **FR-010**: Active influence MUST exclude expired, retired, rejected, revised, and merely proposed lessons.
- **FR-011**: The supervisor MUST NOT mutate profile source, prompts, skills, policy, model routes, or gateway state.
- **FR-012**: No setup or distribution file MAY install a learning schedule in this phase.

## Edge cases and failure states

- Duplicate IDs, changed bodies, missing treatment hashes, correlated support,
  support/contradiction overlap, operational evidence, expiry, restart, and
  attempted activation without human approval.

## Key entities and ontology changes

- `LearningEpisode`, `TreatmentIdentity`, `LessonProposal`, `PromotionDecision`,
  and `ActiveInfluence`.

## Measurable success criteria

- **SC-001**: Tests prove replay/conflict, lane quarantine, independent-evidence
  eligibility, contradiction handling, explicit activation, expiry, retirement,
  and restart reconstruction.
- **SC-002**: Static distribution tests prove no schedule or self-edit path exists.
- **SC-003**: Distribution verification and the complete test suite pass.

## Assumptions and open questions

- **Assumption**: Gateway GC-003 will later supply attributable completed and
  matured episodes; fixtures validate this consumer contract without fabricating acceptance.
- **Question**: Promotion authentication and operator UI remain later integration
  choices; this phase requires a durable external human approval identifier.
