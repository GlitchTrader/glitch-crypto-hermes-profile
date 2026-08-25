from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gateway_client", ROOT / "scripts" / "gateway_client.py")
assert SPEC and SPEC.loader
client_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client_module)


class GatewayClientTests(unittest.TestCase):
    def test_loopback_http_is_allowed(self) -> None:
        self.assertEqual(
            client_module.validated_gateway_url("http://127.0.0.1:8791/"),
            "http://127.0.0.1:8791",
        )

    def test_non_loopback_http_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "must use HTTPS"):
            client_module.validated_gateway_url("http://example.com:8791")

    def test_tokens_must_be_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "GLITCH_CRYPTO_LOCAL_TOKEN=same-token-123456789\n"
                "GLITCH_CRYPTO_OPERATOR_TOKEN=same-token-123456789\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"HERMES_HOME": directory}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "must differ"):
                    client_module.GatewayClient()

    def test_terminal_intent_receipt_is_returned_for_gateway_rejection(self) -> None:
        client = object.__new__(client_module.GatewayClient)
        receipt = {
            "schema_version": "glitch.crypto.intent-receipt.v1",
            "intent_id": "22222222-2222-4222-8222-222222222222",
            "state": "rejected",
            "accepted": False,
        }
        client.request = lambda *args, **kwargs: (422, receipt)
        self.assertEqual(client.submit_intent({"intent_id": receipt["intent_id"]}), receipt)


if __name__ == "__main__":
    unittest.main()
