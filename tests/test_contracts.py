from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_paired_contract_and_operator_have_no_credential_authority(self) -> None:
        paired = json.loads((ROOT / "paired-contract.json").read_text(encoding="utf-8"))
        operator = json.loads((ROOT / "operator.json").read_text(encoding="utf-8"))
        self.assertFalse(paired["execution_credentials_in_profile"])
        self.assertIn("gateway", operator["principles"]["quantity"])
        serialized = json.dumps({"paired": paired, "operator": operator}).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("seed_phrase", serialized)

    def test_required_skills_exist_and_preserve_target_semantics(self) -> None:
        for name in (
            "crypto-market",
            "crypto-build-intent",
            "crypto-position-management",
            "crypto-learn",
            "crypto-event-worker",
        ):
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())
        soul = (ROOT / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("0.5%", soul)
        self.assertIn("not calibrated probability", soul)
        self.assertIn("omit quantity", soul)

    def test_profile_does_not_install_a_fake_cron_worker(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertNotIn("cron", setup.lower())
        self.assertIn("No scheduled trading job", setup)


if __name__ == "__main__":
    unittest.main()
