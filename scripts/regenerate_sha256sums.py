"""Regenerate SHA256SUMS for distribution-owned profile files."""
from __future__ import annotations

from pathlib import Path
from distribution_integrity import inventory

ROOT = Path(__file__).resolve().parents[1]
values = inventory(ROOT)
(ROOT / "SHA256SUMS").write_text(
    "".join(f"{digest}  {path}\n" for path, digest in values.items()),
    encoding="utf-8",
    newline="\n",
)
print(f"Wrote {len(values)} checksums.")
