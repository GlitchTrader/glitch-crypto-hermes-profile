# Glitch Crypto Hermes profile ontology

## Architectonic knowledge classes

| Class | Profile form | Rule |
|---|---|---|
| Fact | authenticated gateway packet, receipt, outcome, or journal event | Preserve identity, provenance, and observation time. |
| Assumption | candidate analysis or experiment premise | Name uncertainty and a validation path. |
| Decision | strict trading intent or versioned promotion decision | Record evidence, alternatives, and the responsible actor. |
| Rule | constitution, authority contract, skill invariant, or schema | It cannot be weakened by memory or inference. |
| Question | event-triggered cognition request or Wayfinder ticket | Resolve it from current evidence or leave it explicit. |
| Risk | contradictory evidence, stale state, malformed output, or unprotected exposure | Fail closed at the gateway and retain the evidence. |

Authority descends from the human and constitution to authenticated gateway
truth, accepted evidence, source contracts, and then cognition. Memory never
overwrites a higher-authority fact.

## Entities

### GatewayPacket

Immutable sanitized market, account, position, policy, capability, and evidence
state. It is the only factual input to a trading turn.

### CandidateEvent

Durable idempotent request to compare long, short, and no-trade alternatives.
It carries no credential or mutation authority.

### PositionEvent

Higher-priority durable request to compare hold, amend, partial, and exit paths
for a gateway-proven open position.

### TradingIntent

Strict `glitch.crypto.intent.v1` decision. Geometry and requested risk express
cognition; final quantity, identity, protection, and mutation remain gateway-owned.

### OperatorCommand

Deterministic status, start, stop, flatten, daily-lock, or usable-limit action
invoked by a human through separate operator authority.

### LearningEpisode

Attributable completed trade, matured no-trade observation, decision review, or
position-management result. Operational defects remain a separate evidence class.

### CognitiveInfluence

Versioned hypothesis, model/prompt treatment, or bounded lesson with evidence,
metric, expiry, contradiction state, and rollback.

## Invariants

- Gateway packets and receipts outrank memory and inference.
- A failed or malformed model call creates no exposure.
- Position events preempt candidate analysis and slow learning.
- Quantity and venue mutation are never profile-owned.
- One outcome cannot activate a lesson.
- The daily objective is portfolio context, never edge or a quota.
