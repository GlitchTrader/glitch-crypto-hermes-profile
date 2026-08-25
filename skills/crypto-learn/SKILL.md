---
name: crypto-learn
description: Debrief attributable crypto decisions and outcomes across market, metacognitive, and portfolio-management learning lanes.
---

# Evidence-gated learning

## Lane 1 — market/model

Evaluate feature usefulness, calibration, venue/regime drift, fill probability, slippage, adverse selection, and delay sensitivity. A model candidate remains a challenger until frozen holdout, replay, shadow, and canary evidence justify promotion.

## Lane 2 — decision/metacognition

Evaluate whether the operator selected the best candidate, entered late or early, used a genuine invalidation, repeated a stale thesis, abstained correctly, or missed supported participation.

## Lane 3 — portfolio/management

Evaluate MAE/MFE, rollback, partial timing, stop/target changes, duration, re-entry, capital utilization, and daily-floor preservation.

## Lesson contract

Every proposed lesson names:

```text
lesson_id
claim
applicable conditions
supporting episode IDs
contradicting episode IDs
confidence
metric
expiry
rollback condition
status
```

One outcome cannot activate a lesson. Correlated trades are one market idea unless independence is proven. Counterfactuals remain simulated and never become realized PnL. Infrastructure defects go to the operational ledger, not trading memory.

## Durable supervisor contract

- Retain only strict `glitch.crypto.learning-episode.v1` episodes with complete
  treatment identity and evidence references.
- Require at least two supporting episodes from two correlation groups in the
  same lane before eligibility.
- Record contradicting episode IDs, disposition, and review; unresolved or
  dominating contradiction blocks eligibility.
- Produce proposals only. Activation, rejection, and retirement require a
  separate chronological `glitch.crypto.promotion-decision.v1` with an external
  human approval ID.
- Never edit SOUL, skills, source, policy, model routes, or gateway state.
- Never install or imply a schedule from the existence of the source store.
