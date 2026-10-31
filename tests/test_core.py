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
        self.assertIn("8", msg)

    def test_accepts_formatted_input(self):
        self.assertTrue(g.validate_imei("49-015420-323751-8")[0])
        self.assertTrue(g.validate_imei(" 49 015420 323751 8 ")[0])

    def test_14_digit_hint(self):
        ok, msg = g.validate_imei("49015420323751")
        self.assertFalse(ok)
        self.assertIn("should be 8", msg)

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
