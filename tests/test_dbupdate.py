import contextlib
import hashlib
import http.server
import json
import os
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_tac_db  # noqa: E402
import dbupdate  # noqa: E402

ROWS_A = [{"tac": "35104463", "brand": "Apple", "model": "iPhone 13", "aka": "", "esim": None, "source": "extra"}]
ROWS_B = ROWS_A + [{"tac": "35332510", "brand": "Samsung", "model": "SM-G960F", "aka": "", "esim": None, "source": "extra"}]


def make_db(directory, rows, built):
    path = os.path.join(directory, "tac.sqlite")
    meta = build_tac_db.build(rows, path, ["extra"])
    # force the build date for ordering tests
    import sqlite3
    con = sqlite3.connect(path)
    con.execute("UPDATE meta SET value = ? WHERE key = 'built'", (built,))
    con.commit(); con.execute("VACUUM"); con.close()
    meta["built"] = built
    manifest = build_tac_db.write_manifest(path, meta, os.path.join(directory, "tac_manifest.json"))
    return path, manifest


@contextlib.contextmanager
def serve(directory):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=directory, **kw)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield "http://127.0.0.1:%d/" % httpd.server_address[1]
        finally:
            httpd.shutdown()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.remote = os.path.join(self.tmp, "remote"); os.makedirs(self.remote)
        self.local = os.path.join(self.tmp, "local"); os.makedirs(self.local)
        self.user = os.path.join(self.tmp, "user")
        self.local_db, _ = make_db(self.local, ROWS_A, "2026-01-01")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def publish(self, rows, built, **tamper):
        path, manifest = make_db(self.remote, rows, built)
        manifest.update(tamper)
        with open(os.path.join(self.remote, "tac_manifest.json"), "w") as f:
            json.dump(manifest, f)
        return manifest

    def run_update(self, base, local_db=None, progress=None):
        manifest_url = base + "tac_manifest.json"
        m = json.load(open(os.path.join(self.remote, "tac_manifest.json")))
        m["url"] = base + "tac.sqlite"
        with open(os.path.join(self.remote, "tac_manifest.json"), "w") as f:
            json.dump(m, f)
        return dbupdate.check_and_update(dbupdate.read_meta(local_db or self.local_db),
                                         self.user, manifest_url, progress=progress)

    def test_downloads_newer_data_and_app_prefers_it(self):
        self.publish(ROWS_B, "2026-06-01")
        with serve(self.remote) as base:
            r = self.run_update(base)
        self.assertEqual(r.status, "updated", r.message)
        self.assertEqual(r.meta["_rows"], 2)
        path, meta = dbupdate.choose_database(self.local_db, self.user)
        self.assertEqual(path, os.path.join(self.user, "tac.sqlite"))
        # Second run: nothing new
        with serve(self.remote) as base:
            r2 = self.run_update(base, local_db=path)
        self.assertEqual(r2.status, "current")

    def test_progress_reported_during_download(self):
        self.publish(ROWS_B, "2026-06-01")
        seen = []
        with serve(self.remote) as base:
            r = self.run_update(base, progress=seen.append)
        self.assertEqual(r.status, "updated")
        self.assertEqual(seen[0], 0.0)
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(seen, sorted(seen))

    def test_same_data_is_current(self):
        self.publish(ROWS_A, "2026-01-01")
        with serve(self.remote) as base:
            self.assertEqual(self.run_update(base).status, "current")

    def test_older_remote_is_ignored(self):
        self.publish(ROWS_B, "2025-01-01")
        with serve(self.remote) as base:
            self.assertEqual(self.run_update(base).status, "current")

    def test_bad_checksum_rejected_and_nothing_installed(self):
        self.publish(ROWS_B, "2026-06-01", sha256="0" * 64)
        with serve(self.remote) as base:
            r = self.run_update(base)
        self.assertEqual(r.status, "error")
        self.assertFalse(os.path.exists(os.path.join(self.user, "tac.sqlite")))
        self.assertEqual([f for f in os.listdir(self.user) if f.endswith(".download")], [])

    def test_row_count_mismatch_rejected(self):
        self.publish(ROWS_B, "2026-06-01", count=999)
        with serve(self.remote) as base:
            self.assertEqual(self.run_update(base).status, "error")

    def test_offline(self):
        r = dbupdate.check_and_update(dbupdate.read_meta(self.local_db), self.user,
                                      "http://127.0.0.1:9/tac_manifest.json")
        self.assertEqual(r.status, "offline")

    def test_missing_manifest_is_online_but_unavailable(self):
        with serve(self.remote) as base:  # nothing published -> 404
            r = dbupdate.check_and_update(dbupdate.read_meta(self.local_db), self.user,
                                          base + "missing.json")
        self.assertEqual(r.status, "unavailable")

    def test_corrupt_saved_copy_falls_back_to_bundled(self):
        os.makedirs(self.user)
        with open(os.path.join(self.user, "tac.sqlite"), "wb") as f:
            f.write(b"garbage" * 1000)
        path, _ = dbupdate.choose_database(self.local_db, self.user)
        self.assertEqual(path, self.local_db)

    def test_newer_bundled_db_wins_over_old_saved_copy(self):
        os.makedirs(self.user)
        old, _ = make_db(self.user, ROWS_A, "2025-01-01")
        path, _ = dbupdate.choose_database(self.local_db, self.user)
        self.assertEqual(path, self.local_db)


class ManifestTests(unittest.TestCase):
    def test_committed_manifest_matches_committed_db(self):
        m = json.load(open(os.path.join(ROOT, "data", "tac_manifest.json")))
        db = os.path.join(ROOT, "data", "tac.sqlite")
        with open(db, "rb") as f:
            blob = f.read()
        self.assertEqual(m["schema"], dbupdate.SCHEMA)
        self.assertEqual(m["size"], len(blob))
        self.assertEqual(m["sha256"], hashlib.sha256(blob).hexdigest())
        meta = dbupdate.read_meta(db)
        self.assertEqual(m["data_hash"], meta["data_hash"])
        self.assertEqual(m["count"], meta["_rows"])
        self.assertTrue(m["url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
