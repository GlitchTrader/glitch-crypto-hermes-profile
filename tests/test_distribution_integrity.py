from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from distribution_integrity import inventory, distribution_roots

ROOT = Path(__file__).resolve().parents[1]


class InstalledDistributionTests(unittest.TestCase):
    def test_installer_alias_and_bundled_skills_do_not_weaken_owned_file_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "profiles" / "cryptoglitch"
            installed.mkdir(parents=True)
            # Test only shipped payload, never copy .env/auth/session/runtime data.
            for relative in distribution_roots(ROOT):
                source = ROOT / relative
                target = installed / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(source, target)
            manifest = installed / "distribution.yaml"
            manifest.write_text(manifest.read_text(encoding="utf-8").replace(
                "name: glitch-crypto\n", "name: cryptoglitch\n", 1), encoding="utf-8", newline="\n")
            manifest.write_text("\n".join(line for line in manifest.read_text(encoding="utf-8").splitlines()
                if not line.startswith("installed_at:")) .replace(
                'description: "Experimental Glitch Crypto AI operator profile"',
                'description: Experimental Glitch Crypto AI operator profile'
            ) + "\ninstalled_at: '2026-09-10T00:00:00Z'\n", encoding="utf-8", newline="\n")
            extra = installed / "skills" / "hermes-bundled" / "SKILL.md"
            extra.parent.mkdir(parents=True)
            extra.write_text("Not owned by this distribution", encoding="utf-8")
            self.assertEqual(inventory(ROOT), inventory(installed))
            soul = installed / "SOUL.md"
            soul.write_text("unexpected alteration", encoding="utf-8")
            self.assertNotEqual(inventory(ROOT)["SOUL.md"], inventory(installed)["SOUL.md"])
            manifest.write_text("\n".join(
                "version: intentionally-altered-test-version" if line.startswith("version:") else line
                for line in manifest.read_text(encoding="utf-8").splitlines()
            ) + "\n", encoding="utf-8")
            self.assertNotEqual(inventory(ROOT)["distribution.yaml"], inventory(installed)["distribution.yaml"])
