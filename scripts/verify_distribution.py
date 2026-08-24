"""Verify SHA256SUMS exactly matches distribution-owned profile files."""
from __future__ import annotations

from pathlib import Path
from distribution_integrity import inventory

ROOT = Path(__file__).resolve().parents[1]
expected: dict[str, str] = {}
for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, path = line.split("  ", 1)
    expected[path] = digest
actual = inventory(ROOT)
if expected != actual:
    missing = sorted(set(actual) - set(expected))
    stale = sorted(set(expected) - set(actual))
    changed = sorted(path for path in set(actual) & set(expected) if actual[path] != expected[path])
    raise SystemExit(
        "Distribution verification failed: "
        f"missing={missing}, stale={stale}, changed={changed}"
    )
print(f"Verified {len(actual)} distribution files.")
