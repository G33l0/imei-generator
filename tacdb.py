"""Read-only access to the embedded TAC database (data/tac.sqlite)."""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "data", "tac.sqlite")
MAX_LIST = 300  # keep Spinner dropdowns responsive on phones

# Used only if data/tac.sqlite is missing or unreadable, so the app still runs.
# These four are the eSIM iPhone TACs present in the Osmocom database.
FALLBACK = [
    ("35104463", "Apple", "iPhone 13", "", 1),
    ("35292511", "Apple", "iPhone 11 (A2221)", "iPhone 11", 1),
    ("35657310", "Apple", "iPhone 11 (A2221)", "iPhone 11", 1),
    ("35727609", "Apple", "iPhone XS Max 256GB", "", 1),
]


class TacDB:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self.error = None
        try:
            if not os.path.exists(path):
                raise FileNotFoundError("%s not found" % path)
            uri = "file:%s?mode=ro&immutable=1" % path.replace("\\", "/")
            self.con = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self.con.execute("SELECT 1 FROM tac LIMIT 1").fetchone()
        except Exception as e:  # missing / corrupt file: degrade gracefully
            self.error = str(e)
            self.con = sqlite3.connect(":memory:", check_same_thread=False)
            self.con.executescript(
                "CREATE TABLE tac (tac TEXT PRIMARY KEY, brand TEXT, model TEXT,"
                " aka TEXT, esim INTEGER, source TEXT);"
                "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);")
            self.con.executemany("INSERT INTO tac VALUES (?,?,?,?,?,'fallback')", FALLBACK)
            self.con.executemany("INSERT INTO meta VALUES (?,?)",
                                 [("count", str(len(FALLBACK))), ("sources", "built-in fallback")])

    # ---- metadata -------------------------------------------------------
    def meta(self):
        return dict(self.con.execute("SELECT key, value FROM meta"))

    def count(self):
        return self.con.execute("SELECT count(*) FROM tac").fetchone()[0]

    # ---- browsing -------------------------------------------------------
    def brands(self):
        """Brands ordered by number of TACs (most common first)."""
        return [r[0] for r in self.con.execute(
            "SELECT brand FROM tac GROUP BY brand ORDER BY count(*) DESC, brand COLLATE NOCASE")]

    def models(self, brand, search="", limit=MAX_LIST):
        """Return (models, truncated) where models is [(model, [tacs])]."""
        sql = "SELECT model, group_concat(tac) FROM tac WHERE brand = ?"
        args = [brand]
        if search:
            sql += " AND (model LIKE ? OR aka LIKE ? OR tac LIKE ?)"
            like = "%" + search.replace("%", "").replace("_", "") + "%"
            args += [like, like, search + "%"]
        sql += " GROUP BY model ORDER BY model COLLATE NOCASE LIMIT ?"
        args.append(limit + 1)
        rows = [(m, t.split(",")) for m, t in self.con.execute(sql, args)]
        return rows[:limit], len(rows) > limit

    def esim_models(self):
        return [(m, t.split(",")) for m, t in self.con.execute(
            "SELECT model, group_concat(tac) FROM tac WHERE esim = 1"
            " GROUP BY model ORDER BY model COLLATE NOCASE")]

    def tacs_for(self, brand, model):
        return [r[0] for r in self.con.execute(
            "SELECT tac FROM tac WHERE brand = ? AND model = ?", (brand, model))]

    # ---- lookup ---------------------------------------------------------
    def lookup(self, tac):
        """Return a dict for an 8-digit TAC (or the TAC part of an IMEI), or None."""
        tac = (tac or "")[:8]
        row = self.con.execute(
            "SELECT tac, brand, model, aka, esim, source FROM tac WHERE tac = ?",
            (tac,)).fetchone()
        if not row:
            return None
        return dict(zip(("tac", "brand", "model", "aka", "esim", "source"), row))
