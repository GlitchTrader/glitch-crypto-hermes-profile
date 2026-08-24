# GCHP-001 Plan

## Components

- `SOUL.md`: durable authority, objective, edge, management, and learning principles.
- `skills/`: procedural overlays with no execution implementation.
- `scripts/gateway_client.py`: authenticated local client and standalone CLI.
- `plugins/crypto-control/`: deterministic slash commands.
- `paired-contract.json`: schema compatibility metadata.
- `setup.ps1`: verify distribution, initialize `.env`, and run tests.

## Failure behavior

- Missing/short/equal tokens: fail visibly.
- Insecure gateway URL: fail visibly.
- Gateway HTTP error: return exact status/body.
- Unknown command argument: fail without mutation.
- No scheduled worker is created, avoiding false autonomy.

## Verification

- `py_compile` for scripts/plugins.
- Unit tests for URL/token boundaries and command registration/behavior.
- Static contract tests for schemas, skills, and absence of credential fields.
- SHA256 distribution verification.
