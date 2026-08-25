# Attributable three-lane learning supervisor

GCHP-003 provides a dormant evidence and governance store. It does not create
episodes, schedule reviews, train/deploy a model, edit the profile, or call the
gateway.

## Lanes

- `market_model`: calibration, features, fills, slippage, regime, venue, delay;
- `decision_metacognition`: ranking, timing, geometry, abstention, stale thesis;
- `portfolio_management`: MAE/MFE, rollback, partials, amendments, duration, floor;
- `operational`: quarantined infrastructure faults, never trading-lesson support.

## Episode contract

`glitch.crypto.learning-episode.v1` retains:

- immutable episode UUID/body;
- lane and episode type;
- evidence references and correlation group;
- observed metrics and, only for completed trades, realized PnL;
- provider/model/reasoning treatment;
- SOUL, prompt, and skill hashes;
- memory, numerical-model, and feature versions.

Matured no-trade counterfactuals cannot claim realized PnL. Missing treatment or
attribution fails closed.

## Lesson and promotion lifecycle

```text
proposed → active → retired
         ↘ rejected
         ↘ inactive after expiry
```

A proposal names claim, conditions, support, contradictions, contradiction
disposition/review, confidence, metric, expiry, and rollback. Eligibility requires
at least two supporting episodes from at least two correlation groups in the same
learning lane. Operational evidence, unresolved contradiction, dominating
contradiction, missing evidence, or expiry blocks activation.

`glitch.crypto.promotion-decision.v1` is a separate immutable record. Activation
requires `actor: human` and an external `human_approval_id`. Decisions must be
chronological. There is no automatic-promotion method.

Only nonexpired `active` lessons appear as `ActiveInfluence`, with their evidence,
promotion decision, metric, expiry, and rollback condition. Retiring a lesson
removes it immediately.

## Activation stop line

Fixture-backed source correctness does not prove that a lesson improves trading.
Gateway episode production, replay/holdout evaluation, promotion authentication,
operator UI, installed-profile behavior, and any scheduled or live influence
remain separate evidence gates.
