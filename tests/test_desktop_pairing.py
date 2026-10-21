from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from desktop_pairing import Pairing


class PairingTests(unittest.TestCase):
    def test_tokens_expire_are_bound_to_peer_and_are_revoked_on_disable(self):
        now = [0]
        pairing = Pairing(clock=lambda: now[0])
        self.assertEqual(pairing.pair("000000", "peer", "agent")[0], "invalid")
        pairing.reset(True)
        code = pairing.current_code()
        self.assertRegex(code, r"^[0-9]{6}$")
        outcome, token = pairing.pair(code, "peer", "agent")
        self.assertEqual(outcome, "ok")
        self.assertNotIn(token, repr(pairing.sessions))
        self.assertTrue(pairing.authorize(token, "peer", "agent"))
        self.assertFalse(pairing.authorize(token, "other", "agent"))
        self.assertFalse(pairing.authorize(token, "peer", "other"))
        now[0] = 8 * 3600
        self.assertFalse(pairing.authorize(token, "peer", "agent"))
        _, token = pairing.pair(code, "peer", "agent")
        pairing.reset()
        self.assertEqual(pairing.current_code(), "")
        self.assertFalse(pairing.authorize(token, "peer", "agent"))

    def test_wrong_unicode_codes_rate_limits_and_recovery(self):
        now = [0]
        pairing = Pairing(clock=lambda: now[0])
        pairing.reset(True)
        for code in (None, "", "x", "１２３４５６", "invalid"):
            self.assertEqual(pairing.pair(code, "peer", "agent")[0], "invalid")
        self.assertEqual(pairing.pair(pairing.current_code(), "peer", "agent")[0], "limited")
        now[0] = 301
        self.assertEqual(pairing.pair(pairing.current_code(), "peer", "agent")[0], "ok")
        for i in range(59):
            pairing.pair("", str(i), "agent")
        self.assertEqual(pairing.pair(pairing.current_code(), "new", "agent")[0], "limited")


if __name__ == "__main__":
    unittest.main()
