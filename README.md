# Glitch Crypto Hermes Profile

Hermes cognition, skills, evidence-gated learning doctrine, and deterministic operator controls for [`GlitchTrader/glitch-crypto`](https://github.com/GlitchTrader/glitch-crypto).

```text
Glitch Crypto packet
        ↓ sanitized evidence
Hermes profile
  long · short · no trade · manage · review · learn
        ↓ strict glitch.crypto.intent.v1
Glitch Crypto gateway
  validate · size · protect · execute · reconcile · journal
```

## Current state

`main` provides:

- constitutional authority and objective doctrine;
- crypto market, intent, position-management, and learning skills;
- deterministic slash commands for status, start, stop, flatten, daily lock, usable limit, PnL, trades, and journal;
- a standard-library authenticated gateway client;
- strict paired schema metadata and tests;
- a durable SQLite cognition-event inbox with UUID/body replay protection;
- position-before-candidate priority and preemption before intent staging;
- strict packet-bound model-output validation with one bounded fence repair;
- durable stage-before-submit and exact restart replay through gateway idempotency;
- no exchange credentials and no direct venue mutation.

The event-worker source is dormant. No schedule or market poller is installed,
and the profile does not claim autonomous operation before an accepted gateway
candidate/position event source and calibrated numerical contracts exist.

The source integration and restart protocol are documented in
[`docs/COGNITION_EVENTS.md`](docs/COGNITION_EVENTS.md).

## Requirements

- Hermes 0.18.2 or newer.
- Python 3.12 or newer.
- The paired Glitch Crypto gateway running locally.

## Install

```powershell
hermes profile install github.com/GlitchTrader/glitch-crypto-hermes-profile --name glitch-crypto --alias
hermes -p glitch-crypto auth add openai-codex --type oauth
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch-crypto\setup.ps1"
```

Edit the installed `.env`:

```text
GLITCH_CRYPTO_GATEWAY_URL=http://127.0.0.1:8791
GLITCH_CRYPTO_LOCAL_TOKEN=<same as gateway GLITCH_LOCAL_TOKEN>
GLITCH_CRYPTO_OPERATOR_TOKEN=<same as gateway GLITCH_OPERATOR_TOKEN>
```

The two tokens must be different. The profile never stores an exchange key, signing key, seed phrase, or JWT.

## Commands

```text
/crypto_status
/trade
/pause_trading
/flatten_all [reason]
/daily_lock
/daily_lock 0.5
/usable_limit
/usable_limit 500
/usable_limit full
/crypto_pnl
/crypto_trades [limit]
/crypto_journal [limit]
```

`/daily_lock 0.5` configures 0.5% of the starting usable pot. It does not set a per-trade target or pressure Hermes to trade.

`/pause_trading` stops new runtime activity but does not cancel venue-native protection. `/flatten_all` stops and closes all configured exposure through the gateway's operator control surface.

## Standalone client

```bash
python scripts/gateway_client.py health
python scripts/gateway_client.py status
python scripts/gateway_client.py policy
python scripts/gateway_client.py pnl
python scripts/gateway_client.py start
python scripts/gateway_client.py stop
python scripts/gateway_client.py flatten
python scripts/gateway_client.py set-lock 0.5
python scripts/gateway_client.py set-usable-limit 500
python scripts/gateway_client.py clear-usable-limit
```

## Verify

```bash
python scripts/verify_distribution.py
python -m unittest discover -s tests -p "test_*.py"
```

## Method

- Wayfinder map and frontier ticket live in the gateway repository.
- Spec Kit constitution: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- Architectonic rail: [`operations/ledger.json`](operations/ledger.json)
- Profile spec set: [`operations/specs/GCHP-001/`](operations/specs/GCHP-001/)
