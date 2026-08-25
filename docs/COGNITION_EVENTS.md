# Durable cognition event boundary

GCHP-002 provides a dormant standard-library boundary for candidate and position
work. It does not generate events, invoke a model, or install a schedule.

## Event contract

An accepted source supplies one immutable `glitch.crypto.cognition-event.v1`:

```json
{
  "schema_version": "glitch.crypto.cognition-event.v1",
  "event_id": "11111111-1111-4111-8111-111111111111",
  "event_type": "CANDIDATE",
  "packet_id": "<lowercase SHA-256 packet ID>",
  "created_utc": "2026-08-25T01:00:00Z",
  "expires_utc": "2026-08-25T01:05:00Z",
  "reason": "A bounded candidate crossed the numerical review threshold.",
  "trigger": {"type": "candidate_threshold", "candidate_id": "C-1"}
}
```

`POSITION` events additionally require `tranche_id`. Credential-bearing fields
and unknown top-level fields are rejected.

## State and recovery

```text
queued → in_progress → intent_staged → completed
                    ↘ failed
       ↘ preempt_requested → queued
       ↘ expired
```

- SQLite WAL/FULL-sync persists event identity, leases, staged intent, receipt,
  errors, and attempts.
- Same event ID/body is a replay; changed body is a conflict.
- Expired claims are recoverable.
- Position events outrank candidate events and request preemption only while a
  candidate is unstaged.
- Staged work outranks new cognition because its gateway outcome may be unresolved.

## Caller sequence

1. Enqueue the immutable event in `CognitionInbox`.
2. Claim one event with a bounded lease.
3. If `staged_intent` is present, skip the model and call `submit_staged`.
4. Otherwise obtain exactly one model JSON object under the event-worker skill.
5. Call `stage_model_output`; it reloads the current packet, rejects staleness,
   validates the exact paired intent schema, and durably stages the normalized intent.
6. Call `submit_staged` through `GatewayClient`.
7. Retain the gateway receipt. On transport error, the exact staged intent stays
   replayable without another model turn.

The only model-output repair is removal of one outer JSON fence. There is no
semantic repair, quantity inference, credential access, direct venue call, or
automatic retry with changed content.

## Activation stop line

Source tests do not accept event generation, numerical calibration, model route,
profile installation, authenticated Testnet mutation, scheduling, or live use.
Those require their own accepted evidence and human authorization boundaries.
