# Part 5 (2026-07-23): outbound Telegram messages are logged at INFO with the
# stable [tg-out] prefix, truncated, and REDACTED so no token/key can appear.
# Offline — no network.

import io
import logging
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_redaction import tg_out_log, RedactingFilter, TG_OUT_MAX

SECRET = "Tti8FhS23cC8TOOo4PIEAbcd1234"


def _capture_logger(name):
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.addFilter(RedactingFilter())  # the prod filter, installed on root handlers
    lg = logging.getLogger(name)
    lg.handlers = [h]
    lg.setLevel(logging.INFO)
    lg.propagate = False
    return lg, buf


class TestTgOutLog(unittest.TestCase):
    def test_prefix_and_redaction(self):
        lg, buf = _capture_logger("tgout_test_1")
        tg_out_log(lg, f"🚀 New Pool https://api.geckoterminal.com/x?apikey={SECRET}&y=1")
        out = buf.getvalue()
        self.assertIn("[tg-out]", out)
        self.assertNotIn(SECRET, out)           # key never appears
        self.assertIn("apikey=***", out)        # redacted form

    def test_truncated(self):
        lg, buf = _capture_logger("tgout_test_2")
        tg_out_log(lg, "A" * (TG_OUT_MAX + 500))
        line = buf.getvalue()
        self.assertIn("[tg-out]", line)
        self.assertIn("…", line)
        # body (after prefix) capped near TG_OUT_MAX
        body = line.split("[tg-out] ", 1)[1]
        self.assertLessEqual(len(body), TG_OUT_MAX + 5)

    def test_newlines_flattened(self):
        lg, buf = _capture_logger("tgout_test_3")
        tg_out_log(lg, "line1\nline2\nline3")
        body = buf.getvalue().split("[tg-out] ", 1)[1]
        self.assertNotIn("\n", body.rstrip("\n"))


class TestWorkerSendPath(unittest.TestCase):
    def test_worker_send_telegram_logs_redacted(self):
        import asyncio
        import worker
        lg, buf = _capture_logger("worker")
        worker.logger = lg  # capture the module logger used by send_telegram
        # no token/chat -> returns after logging, no network
        with mock.patch.object(worker, "TELEGRAM_BOT_TOKEN", ""), \
             mock.patch.object(worker, "TELEGRAM_CHAT_ID", ""):
            asyncio.get_event_loop().run_until_complete(
                worker.send_telegram(f"paper buy apikey={SECRET}"))
        out = buf.getvalue()
        self.assertIn("[tg-out]", out)
        self.assertNotIn(SECRET, out)


if __name__ == "__main__":
    unittest.main()
