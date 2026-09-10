"""Shared SHA256 distribution inventory helpers."""
from __future__ import annotations

import hashlib
import json
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
            data = candidate.read_bytes()
            if relative == "distribution.yaml":
                # The installer serializes YAML and owns name/source/installed_at.
                # Hash the complete distribution-owned semantic manifest instead;
                # all non-manifest payload files still use exact byte hashes.
                data = manifest_payload(data)
            result[relative] = hashlib.sha256(data).hexdigest()
    return dict(sorted(result.items()))


def manifest_payload(data: bytes) -> bytes:
    fields: dict[str, object] = {}
    current_list: list[str] | None = None
    for raw in data.decode("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and current_list is not None:
            current_list.append(line[2:].strip().strip("\"'"))
            continue
        if raw.startswith(" ") or ":" not in line:
            raise RuntimeError("unsupported distribution manifest syntax")
        key, value = line.split(":", 1)
        if key in fields:
            raise RuntimeError("duplicate distribution manifest key")
        value = value.strip().strip("\"'")
        if not value:
            current_list = []
            fields[key] = current_list
        else:
            current_list = None
            fields[key] = value
    for metadata in ("name", "source", "installed_at"):
        fields.pop(metadata, None)
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
