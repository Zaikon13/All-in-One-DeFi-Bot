# Part D (2026-07-13): API keys must never appear in logs. Offline.

import io
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_redaction import redact, RedactingFilter, install_log_redaction

SECRET = "Tti8FhS23cC8TOOo4PIEAbcd1234"


class TestRedact(unittest.TestCase):
    def test_redacts_apikey_in_url(self):
        url = f"GET https://explorer-api.cronos.org/mainnet/api/v2?module=account&action=tokenbalance&apikey={SECRET}&tag=latest"
        out = redact(url)
        self.assertNotIn(SECRET, out)
        self.assertIn("apikey=***", out)
        # non-secret params preserved
        self.assertIn("action=tokenbalance", out)

    def test_redacts_api_key_variant_and_is_case_insensitive(self):
        self.assertNotIn(SECRET, redact(f"?API_KEY={SECRET}"))
        self.assertNotIn(SECRET, redact(f"?ApiKey={SECRET}&x=1"))

    def test_non_string_safe(self):
        self.assertEqual(redact(12345), 12345)
        self.assertIsNone(redact(None))


class TestFilterCapturesRealLogging(unittest.TestCase):
    def _logger_with_filter(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.addFilter(RedactingFilter())
        logger = logging.getLogger("test_redact_" + self._testMethodName)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return logger, buf

    def test_no_log_line_contains_the_key(self):
        logger, buf = self._logger_with_filter()
        # log the exact leak shape httpx produced, plus an args-based line
        logger.info("HTTP Request: GET https://x/api/v2?apikey=%s&tag=latest", SECRET)
        logger.warning("[explorer] ethproxy/getBlockNumber?apikey=" + SECRET)
        out = buf.getvalue()
        self.assertNotIn(SECRET, out)
        self.assertIn("apikey=***", out)

    def test_install_attaches_filter_to_root_and_quiets_httpx(self):
        install_log_redaction()
        root = logging.getLogger()
        self.assertTrue(any(
            any(isinstance(f, RedactingFilter) for f in h.filters) for h in root.handlers))
        self.assertGreaterEqual(logging.getLogger("httpx").level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
