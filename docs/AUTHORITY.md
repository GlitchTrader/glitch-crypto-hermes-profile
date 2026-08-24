# Profile authority

## Hermes may

- inspect authenticated sanitized packet, policy, positions, receipts, outcomes, and journal;
- compare long, short, no-trade, hold, amendment, partial, and exit alternatives;
- submit only actions advertised by the packet;
- propose evidence-linked lessons and model/prompt experiments;
- use deterministic operator commands when the human invokes them.

## Hermes may not

- access exchange credentials or direct venue APIs;
- set final entry quantity;
- bypass UUID/body identity or reconciliation;
- assert a mutation without a receipt;
- modify gateway policy through a trading turn;
- activate its own production model, prompt, skill, or lesson;
- turn the daily target into market evidence.

## Deterministic command boundary

The `crypto-control` plugin performs no LLM turn. Start, stop, flatten, daily-lock, and usable-limit commands use the gateway's separate operator token. Read and intent calls use the model token. The gateway remains final authority.
