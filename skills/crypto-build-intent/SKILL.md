---
name: crypto-build-intent
description: Encode a chosen Glitch Crypto decision into the strict gateway contract without inventing quantity, state, or strategy.
---

# Build a Glitch Crypto intent

Use only actions listed in the current packet's `execution.supported_actions`.

## Common fields

```json
{
  "schema_version": "glitch.crypto.intent.v1",
  "intent_id": "fresh UUID",
  "packet_id": "exact current packet_id",
  "account": "exact sanitized account alias",
  "instrument": "exact packet instrument",
  "action": "SUPPORTED_ACTION",
  "reason": "compact falsifiable rationale"
}
```

Never reuse a UUID with changed content. Never include exchange credentials or native order IDs not explicitly supplied for selection.

## Entry

```json
{
  "action": "ENTER_LONG",
  "stop_price": 59400,
  "target_price": 61200,
  "requested_risk_pct": 0.5,
  "requested_leverage": 3
}
```

`ENTER_SHORT` has the same shape. Omit quantity. The gateway derives it from current equity, usable pot, structural stop, cost reserve, leverage, margin, venue step, minimum notional, open risk, daily loss, and active floor.

The stop and target are absolute prices. Do not manufacture geometry from the daily target.

## Management

```json
{"action":"HOLD","tranche_id":"TR-..."}
{"action":"MOVE_STOP","tranche_id":"TR-...","stop_price":60100}
{"action":"MOVE_TARGET","tranche_id":"TR-...","target_price":61500}
{"action":"REDUCE","tranche_id":"TR-...","reduce_fraction_pct":50}
{"action":"EXIT","tranche_id":"TR-..."}
```

`REDUCE` is strictly between 0 and 100 percent. The gateway rounds to venue step and rejects dust. Unspecified protection remains unchanged unless the venue requires exact re-arming, which the gateway owns.

## No trade

```json
{"action":"NOTHING","reason":"No current path retains conservative net edge after noise and costs."}
```
