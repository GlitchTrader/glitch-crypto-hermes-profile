---
name: crypto-event-worker
description: Process one durable Glitch Crypto candidate or position event without bypassing packet identity, preemption, staging, or gateway authority.
---

# Durable cognition event worker

Use this skill only for a claimed `glitch.crypto.cognition-event.v1` work item.
It does not create events, poll the market, select a model, or install a schedule.

## Work order

1. If the claim already contains a staged intent, do not call a model. Resume the
   exact staged UUID/body through the coordinator.
2. Position work outranks candidate work. Honor a preemption request before any
   intent is staged.
3. Load the current authenticated gateway packet and require exact `packet_id`.
4. For position work, require the exact event tranche in the current packet.
5. Apply `crypto-market` or `crypto-position-management` as appropriate, then
   `crypto-build-intent`.
6. Return exactly one strict JSON object. The only bounded syntactic repair is
   removal of one outer JSON code fence; no semantic field repair is allowed.
7. Let the coordinator validate and durably stage the intent before gateway
   submission.
8. Trust only the gateway receipt. A transport error leaves the exact staged
   intent for idempotent replay; never regenerate or change its UUID/body.

Model failure, malformed output, stale packet identity, unsupported action, or
preemption before staging creates no submission.
