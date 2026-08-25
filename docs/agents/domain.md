# Domain-modeling and grilling context

Use `operations/ontology.md` as the canonical model and the paired gateway
packet/intent schemas as factual contracts.

Before a material change, determine:

- whether the input is a gateway fact, probabilistic evidence, memory, or assumption;
- whether this is a candidate, position, operator-command, or learning event;
- the stable identity, idempotency key, lock, preemption, and retry behavior;
- the strict output schema and bounded repair behavior;
- how malformed, stale, contradictory, or failed cognition creates no exposure;
- which completed or matured evidence can attribute an outcome;
- the evaluation, expiry, contradiction, promotion, and rollback path.

Never use the daily objective as edge, frequency pressure, geometry, or quantity.
