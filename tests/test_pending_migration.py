"""Part 1 follow-up (2026-07-24) — pending-maturity legacy address cleanup.

Live deploy b3f30d9 ran the Solana force-fetch cleanly but matured 0 pools for
hours. Root cause: the 3180 pending pools carried over from before the fix stored
their address only inside the lowercased dedup key ({chain}:{addr.lower()}), and
`load_pending_pools` recovered the address from that key. Solana base58 addresses
are case-sensitive, so every lowercased address returned 0 rows from pools/multi
— and at 30 addresses/cycle they consumed the whole force-fetch budget, starving
the correctly-cased new pending pools. `migrate_pending` drops these unrecoverable
legacy entries so maturation can proceed. These tests pin that behavior.
"""
import worker


class TestAddrRecoverable:
    def test_lowercased_solana_addr_is_unrecoverable(self):
        # a real base58 address always has uppercase; all-lowercase == corrupted
        assert worker._addr_recoverable("solana", "9zofeh8n7rsgebclpt5hplgjdmvmzmahv63uxq48tanw") is False

    def test_mixedcase_solana_addr_is_recoverable(self):
        assert worker._addr_recoverable("solana", "9zofeh8n7RSGeBcLpt5hPLGjDMVmzmAhV63uXQ48TAnW") is True

    def test_lowercase_evm_addr_is_recoverable(self):
        # Cronos/EVM hex is case-insensitive; lowercase is legitimate
        assert worker._addr_recoverable("cro", "0xabc1234567890abcdef1234567890abcdef123456") is True

    def test_lowercase_sui_addr_is_recoverable(self):
        assert worker._addr_recoverable("sui-network", "0xdeadbeefcafe0011") is True

    def test_empty_addr_never_recoverable(self):
        assert worker._addr_recoverable("solana", "") is False
        assert worker._addr_recoverable("cro", "") is False


class TestMigratePending:
    def test_drops_lowercased_solana_keeps_the_rest(self):
        data = {
            # poisoned legacy Solana (dict form, lowercased addr recovered from key)
            "solana:9zofeh8n7rsgebclpt5hplgjdmvmzmahv63uxq48tanw":
                {"ca": "2026-07-24T10:00:00+00:00", "addr": "9zofeh8n7rsgebclpt5hplgjdmvmzmahv63uxq48tanw"},
            # healthy Solana with original case
            "solana:GOODpoolAddrWithUppercaseXYZ123":
                {"ca": "2026-07-24T18:00:00+00:00", "addr": "GOODpoolAddrWithUppercaseXYZ123"},
            # EVM lowercase is fine
            "cro:0xabc1234567890abcdef1234567890abcdef123456":
                {"ca": "2026-07-24T18:00:00+00:00", "addr": "0xabc1234567890abcdef1234567890abcdef123456"},
        }
        clean, dropped = worker.migrate_pending(data)
        assert dropped == 1
        assert "solana:9zofeh8n7rsgebclpt5hplgjdmvmzmahv63uxq48tanw" not in clean
        assert "solana:GOODpoolAddrWithUppercaseXYZ123" in clean
        assert "cro:0xabc1234567890abcdef1234567890abcdef123456" in clean

    def test_legacy_string_format_migrates(self):
        # old on-disk form was {key: created_at_str}; address comes from the key
        data = {"cro:0xdeadbeef00": "2026-07-24T18:00:00+00:00"}
        clean, dropped = worker.migrate_pending(data)
        assert dropped == 0
        assert clean["cro:0xdeadbeef00"]["addr"] == "0xdeadbeef00"
        assert clean["cro:0xdeadbeef00"]["ca"] == "2026-07-24T18:00:00+00:00"

    def test_empty_input_safe(self):
        assert worker.migrate_pending({}) == ({}, 0)
        assert worker.migrate_pending(None) == ({}, 0)
