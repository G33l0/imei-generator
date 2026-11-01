import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exporters  # noqa: E402
import imei_generator as gen  # noqa: E402
from tacdb import TacDB  # noqa: E402
from userdata import HISTORY_LIMIT, UserData  # noqa: E402

ROWS = [("490154203237518", "49015420", "Test A"), ("356938035643809", "35693803", "Test B")]


class ExportTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(exporters.render(ROWS, "lines"), "490154203237518\n356938035643809")
        self.assertEqual(exporters.render(ROWS, "comma"), "490154203237518,356938035643809")
        self.assertEqual(exporters.render(ROWS, "quoted"), "'490154203237518', '356938035643809'")
        self.assertEqual(json.loads(exporters.render(ROWS, "json")), [r[0] for r in ROWS])
        csv_text = exporters.render(ROWS, "csv").splitlines()
        self.assertEqual(csv_text[0], "imei,tac,model")
        self.assertEqual(csv_text[1], "490154203237518,49015420,Test A")

    def test_every_format_has_label_and_ext(self):
        for key, label, ext in exporters.FORMATS:
            self.assertEqual(exporters.FORMAT_KEYS[label], key)
            self.assertTrue(ext)


class BulkTests(unittest.TestCase):
    def test_parse_mixed_separators(self):
        text = "490154203237518\n35-693803-564380-9; 352099001761481,\n\n['111']"
        self.assertEqual(exporters.parse_bulk(text),
                         ["490154203237518", "35-693803-564380-9", "352099001761481", "111"])

    def test_round_trip_json_and_quoted(self):
        for fmt in ("json", "quoted", "comma", "lines", "csv"):
            rows, summary = exporters.bulk_check(exporters.render(ROWS, fmt))
            valid = [r["imei"] for r in rows if r["ok"]]
            self.assertEqual(valid, [r[0] for r in ROWS], fmt)

    def test_summary_and_device(self):
        db = TacDB()
        good = gen.generate_imei("35104463")
        rows, s = exporters.bulk_check("%s\n490154203237519\nabc" % good, db.lookup)
        self.assertEqual((s["total"], s["valid"], s["unknown"], s["invalid"]), (3, 1, 0, 2))
        self.assertEqual([r["verdict"] for r in rows], ["valid", "invalid", "invalid"])
        self.assertEqual(rows[0]["device"], "Apple iPhone 13")
        report = exporters.bulk_report_csv(rows).splitlines()
        self.assertEqual(report[0], "input,imei,status,device")
        self.assertIn(",valid,", report[1])

    def test_unknown_device_counted_separately(self):
        rows, s = exporters.bulk_check(gen.generate_imei("35999999"), TacDB().lookup)
        self.assertEqual((s["valid"], s["unknown"], s["invalid"]), (0, 1, 0))
        self.assertEqual(rows[0]["verdict"], "unknown")

    def test_limit(self):
        _, s = exporters.bulk_check("\n".join(["1"] * (exporters.MAX_BULK + 5)))
        self.assertEqual(s["total"], exporters.MAX_BULK)
        self.assertTrue(s["truncated"])


class UserDataTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ud = UserData(self.dir)

    def tearDown(self):
        self.ud.con.close()
        shutil.rmtree(self.dir)

    def test_settings_persist(self):
        self.ud.set_many({"mode": "all", "qty": "25", "nested": {"a": 1}})
        ud2 = UserData(self.dir)
        self.assertEqual(ud2.get("mode"), "all")
        self.assertEqual(ud2.get("nested"), {"a": 1})
        self.assertEqual(ud2.get("missing", "x"), "x")

    def test_favorites(self):
        fid = self.ud.add_favorite("model", "Apple", "iPhone 13", ["35104463"])
        self.assertEqual(self.ud.add_favorite("model", "Apple", "iPhone 13", ["35104463"]), fid)
        self.assertEqual(len(self.ud.favorites()), 1)
        self.assertEqual(self.ud.find_favorite("model", "Apple", "iPhone 13", ["35104463"]), fid)
        self.ud.remove_favorite(fid)
        self.assertEqual(self.ud.favorites(), [])

    def test_history(self):
        hid = self.ud.add_history("Test", ROWS)
        label, rows = self.ud.history_rows(hid)
        self.assertEqual(label, "Test")
        self.assertEqual([r[0] for r in rows], [r[0] for r in ROWS])
        self.assertEqual(self.ud.history()[0]["count"], 2)
        self.ud.delete_history(hid)
        self.assertEqual(self.ud.history(), [])

    def test_history_is_capped(self):
        for i in range(HISTORY_LIMIT + 7):
            self.ud.add_history("b%d" % i, ROWS[:1])
        h = self.ud.history()
        self.assertEqual(len(h), HISTORY_LIMIT)
        self.assertEqual(h[0]["label"], "b%d" % (HISTORY_LIMIT + 6))
        self.ud.clear_history()
        self.assertEqual(self.ud.history(), [])

    def test_corrupt_file_recovers(self):
        self.ud.con.close()
        with open(self.ud.path, "wb") as f:
            f.write(b"not a database" * 100)
        ud = UserData(self.dir)
        self.assertEqual(ud.favorites(), [])


class SearchAllTests(unittest.TestCase):
    def test_cross_brand_search(self):
        db = TacDB()
        rows, _ = db.search_all("iphone 13")
        self.assertTrue(any(b == "Apple" and "iPhone 13" in m for b, m, _ in rows))
        rows, _ = db.search_all("galaxy")
        self.assertTrue(rows)
        self.assertTrue(all(b for b, _, _ in rows))
        self.assertEqual(db.search_all("  "), ([], False))
        rows, _ = db.search_all("35104463")
        self.assertEqual(rows[0][:2], ("Apple", "iPhone 13"))


if __name__ == "__main__":
    unittest.main()
