# Review Agent 2026-06-09: Basic unit tests for the Phase 1 price helper.
# Tests focus on defensive behavior: cache, graceful fallback, timeout simulation, partial results.
# These can run standalone without the rest of the PnL system.

import unittest
from unittest.mock import patch, MagicMock
import time

from core.price_service import PriceService


class TestPriceService(unittest.TestCase):
    def test_graceful_fallback_for_invalid_symbol(self):
        """Invalid/unknown symbols should return None without raising."""
        service = PriceService()
        prices = service.get_current_prices(["CRO", "TOTALLYFAKE123456789"])
        self.assertIn("CRO", prices)
        self.assertIn("TOTALLYFAKE123456789", prices)
        # We don't assert the value of CRO (network dependent), but the fake must be None
        self.assertIsNone(prices.get("TOTALLYFAKE123456789"))
        service.close()

    def test_cache_hits_avoid_repeated_calls(self):
        """Second call for same symbol within TTL should hit cache (no extra HTTP)."""
        service = PriceService(cache_ttl=10)

        with patch.object(service, "client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"crypto-com-chain": {"usd": 0.085}}
            mock_client.get.return_value = mock_response

            p1 = service.get_current_prices(["CRO"])
            p2 = service.get_current_prices(["CRO"])

            self.assertEqual(p1.get("CRO"), p2.get("CRO"))
            # Only one actual HTTP call due to cache
            self.assertEqual(mock_client.get.call_count, 1)

        service.close()

    def test_partial_results_on_mixed_input(self):
        """When some symbols succeed and others fail, return partial dict without crashing."""
        service = PriceService()

        with patch.object(service, "client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            # Only CRO succeeds, the other id is missing from response
            mock_response.json.return_value = {"crypto-com-chain": {"usd": 0.085}}
            mock_client.get.return_value = mock_response

            prices = service.get_current_prices(["CRO", "USDC", "FAKE"])

            self.assertIsInstance(prices, dict)
            self.assertIn("CRO", prices)
            self.assertIn("USDC", prices)
            self.assertIn("FAKE", prices)
            # USDC and FAKE should be None (no data in response)
            self.assertIsNone(prices.get("USDC"))
            self.assertIsNone(prices.get("FAKE"))

        service.close()

    def test_timeout_simulation_does_not_raise(self):
        """Simulate timeout: the call should fallback gracefully instead of propagating exception."""
        service = PriceService(timeout=0.0001)  # extremely short to encourage timeout path

        # We don't patch here so real call may succeed or timeout depending on network;
        # the important thing is that no exception escapes the public API.
        try:
            prices = service.get_current_prices(["CRO"])
            self.assertIsInstance(prices, dict)
        except Exception as exc:
            self.fail(f"get_current_prices should never raise, but got: {exc}")

        service.close()

    def test_empty_input_returns_empty_dict(self):
        service = PriceService()
        self.assertEqual(service.get_current_prices([]), {})
        service.close()


if __name__ == "__main__":
    # Allow running the tests directly: python -m tests.test_price_service
    unittest.main()
