"""Shared SHA256 distribution inventory helpers."""
from __future__ import annotations

import hashlib
from pathlib import Path


def distribution_roots(profile_root: Path) -> list[str]:
    lines = (profile_root / "distribution.yaml").read_text(encoding="utf-8").splitlines()
    roots: list[str] = []
    in_owned = False
    for line in lines:
        if line.strip() == "distribution_owned:":
            in_owned = True
            continue
        if in_owned:
            if line.startswith("  - "):
                roots.append(line[4:].strip())
            elif line and not line.startswith(" "):
                break
    if not roots:
        raise RuntimeError("distribution.yaml has no distribution_owned entries")
    return roots


def inventory(profile_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for root_name in distribution_roots(profile_root):
        if root_name == "SHA256SUMS":
            continue
        path = profile_root / root_name
        if not path.exists():
            raise RuntimeError(f"distribution-owned path is missing: {root_name}")
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        for candidate in candidates:
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(profile_root).as_posix()
            if relative == "SHA256SUMS" or "__pycache__" in candidate.parts or candidate.suffix == ".pyc":
                continue
            result[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return dict(sorted(result.items()))
