import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import imei_generator as g  # noqa: E402
from tacdb import TacDB  # noqa: E402

# Known-good IMEIs (check digit verified independently).
KNOWN = ["490154203237518", "356938035643809", "352099001761481"]


class LuhnTests(unittest.TestCase):
    def test_known_imeis(self):
        for imei in KNOWN:
            self.assertEqual(g.luhn_check_digit(imei[:-1]), int(imei[-1]), imei)
            self.assertTrue(g.validate_imei(imei)[0])

    def test_rejects_bad_check_digit(self):
        ok, msg = g.validate_imei("490154203237519")
        self.assertFalse(ok)
        self.assertEqual(msg, "Invalid IMEI")

    def test_accepts_formatted_input(self):
        self.assertTrue(g.validate_imei("49-015420-323751-8")[0])
        self.assertTrue(g.validate_imei(" 49 015420 323751 8 ")[0])

    def test_wrong_length(self):
        ok, msg = g.validate_imei("49015420323751")
        self.assertFalse(ok)
        self.assertIn("15 digits", msg)

    def test_messages_do_not_reveal_method(self):
        samples = ["490154203237518", "490154203237519", "49015420323751", "4901X", ""]
        for s in samples:
            msg = g.validate_imei(s)[1].lower()
            for word in ("luhn", "checksum", "check digit", "should be", "mod"):
                self.assertNotIn(word, msg, (s, msg))

    def test_rejects_non_digits(self):
        self.assertFalse(g.validate_imei("49015420323751X")[0])
        self.assertFalse(g.validate_imei("")[0])
        with self.assertRaises(ValueError):
            g.luhn_check_digit("")


class GenerateTests(unittest.TestCase):
    def test_generated_are_valid(self):
        for _ in range(2000):
            imei = g.generate_imei("35104463")
            self.assertEqual(len(imei), 15)
            self.assertTrue(imei.startswith("35104463"))
            self.assertTrue(g.validate_imei(imei)[0], imei)

    def test_bad_tac(self):
        for bad in ["1234567", "123456789", "abcdefgh", ""]:
            with self.assertRaises(ValueError):
                g.generate_imei(bad)

    def test_batch_unique_and_bounds(self):
        out = g.generate_batch(["35104463", "35727609"], g.MAX_BATCH)
        imeis = [i for i, _ in out]
        self.assertEqual(len(set(imeis)), g.MAX_BATCH)
        self.assertTrue(all(i.startswith(t) for i, t in out))
        with self.assertRaises(ValueError):
            g.generate_batch(["35104463"], 0)
        with self.assertRaises(ValueError):
            g.generate_batch(["35104463"], g.MAX_BATCH + 1)
        with self.assertRaises(ValueError):
            g.generate_batch([], 1)

    def test_legacy_alias(self):
        self.assertTrue(g.validate_imei(g.generate_imei_with_tac("35104463"))[0])


class InspectTests(unittest.TestCase):
    def setUp(self):
        self.db = TacDB()

    def test_known_device(self):
        r = g.inspect_imei(g.generate_imei("35104463"), self.db.lookup)
        self.assertEqual(r["status"], g.STATUS_KNOWN_DEVICE)
        self.assertEqual(r["device"]["model"], "iPhone 13")
        self.assertEqual(r["issuer"], "BABT (UK)")

    def test_any_single_digit_change_is_caught(self):
        imei = g.generate_imei("35104463")
        for pos in range(15):
            for d in "0123456789":
                if d == imei[pos]:
                    continue
                changed = imei[:pos] + d + imei[pos + 1:]
                self.assertEqual(g.inspect_imei(changed)["status"], g.STATUS_INVALID, changed)

    def test_unknown_tac_is_not_reported_as_known(self):
        r = g.inspect_imei(g.generate_imei("35999999"), self.db.lookup)
        self.assertEqual(r["status"], g.STATUS_UNKNOWN_DEVICE)
        self.assertIn("unknown", r["headline"].lower())

    def test_test_imei_and_placeholders(self):
        r = g.inspect_imei(g.generate_imei("00123456"), self.db.lookup)
        self.assertEqual(r["status"], g.STATUS_TEST)
        base = "11111111111111"
        r = g.inspect_imei(base + str(g.luhn_check_digit(base)))
        self.assertTrue(any("placeholder" in n for n in r["notes"]))
        base = "35104463000000"
        r = g.inspect_imei(base + str(g.luhn_check_digit(base)), self.db.lookup)
        self.assertTrue(any("placeholder" in n.lower() for n in r["notes"]))

    def test_unrecognised_prefix_noted(self):
        r = g.inspect_imei(g.generate_imei("77123456"))
        self.assertEqual(r["issuer"], "")  # shown as "Unrecognised prefix" in the UI
        self.assertEqual(r["status"], g.STATUS_UNKNOWN_DEVICE)

    def test_messages_never_reveal_method(self):
        for x in [g.generate_imei("35104463"), g.generate_imei("77123456"), "123", "35104463123456"]:
            r = g.inspect_imei(x)
            for text in [r["headline"]] + r["notes"]:
                for word in ("luhn", "checksum", "check digit", "mod 10"):
                    self.assertNotIn(word, text.lower())


class TacDBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = TacDB()

    def test_embedded_db_loads(self):
        self.assertIsNone(self.db.error, self.db.error)
        self.assertGreater(self.db.count(), 10000)
        self.assertIn("Apple", self.db.brands())

    def test_lookup(self):
        row = self.db.lookup("351044630000000")
        self.assertEqual(row["brand"], "Apple")
        self.assertIsNone(self.db.lookup("00000000"))

    def test_esim_models_are_iphones(self):
        models = self.db.esim_models()
        self.assertTrue(models)
        for name, tacs in models:
            self.assertIn("iPhone", name)
            for t in tacs:
                self.assertEqual(self.db.lookup(t)["brand"], "Apple")

    def test_models_search_and_limit(self):
        rows, truncated = self.db.models("Samsung", limit=5)
        self.assertEqual(len(rows), 5)
        self.assertTrue(truncated)
        rows, _ = self.db.models("Apple", "iphone 13")
        self.assertTrue(any("iPhone 13" in m for m, _ in rows))

    def test_fallback_when_missing(self):
        db = TacDB(os.path.join(tempfile.gettempdir(), "does-not-exist.sqlite"))
        self.assertIsNotNone(db.error)
        self.assertEqual(len(db.esim_models()), 3)


if __name__ == "__main__":
    unittest.main()
