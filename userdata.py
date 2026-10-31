"""Per-user state kept on the device: settings, favourites and history.

Stored in a small SQLite file in the app's private data directory, separate
from the read-only TAC database.
"""
import json
import os
import sqlite3
import time

HISTORY_LIMIT = 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS favorites (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind    TEXT NOT NULL,            -- 'model' or 'tac'
    brand   TEXT NOT NULL DEFAULT '',
    model   TEXT NOT NULL DEFAULT '',
    tacs    TEXT NOT NULL,            -- JSON list
    created REAL NOT NULL,
    UNIQUE (kind, brand, model, tacs)
);
CREATE TABLE IF NOT EXISTS history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    created REAL NOT NULL,
    label   TEXT NOT NULL,
    count   INTEGER NOT NULL,
    rows    TEXT NOT NULL             -- JSON [[imei, tac], ...]
);
"""


class UserData:
    def __init__(self, directory):
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, "g2user.db")
        try:
            self.con = sqlite3.connect(self.path, check_same_thread=False)
            self.con.executescript(SCHEMA)
        except sqlite3.DatabaseError:  # corrupt file: start fresh rather than crash
            os.replace(self.path, self.path + ".broken")
            self.con = sqlite3.connect(self.path, check_same_thread=False)
            self.con.executescript(SCHEMA)

    # ---- settings -------------------------------------------------------
    def get(self, key, default=None):
        row = self.con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            return default

    def set_many(self, values):
        with self.con:
            self.con.executemany(
                "INSERT OR REPLACE INTO settings VALUES (?, ?)",
                [(k, json.dumps(v)) for k, v in values.items()])

    # ---- favourites -----------------------------------------------------
    def favorites(self):
        return [{"id": i, "kind": k, "brand": b, "model": m, "tacs": json.loads(t)}
                for i, k, b, m, t in self.con.execute(
                    "SELECT id, kind, brand, model, tacs FROM favorites ORDER BY created")]

    def find_favorite(self, kind, brand, model, tacs):
        row = self.con.execute(
            "SELECT id FROM favorites WHERE kind=? AND brand=? AND model=? AND tacs=?",
            (kind, brand, model, json.dumps(list(tacs)))).fetchone()
        return row[0] if row else None

    def add_favorite(self, kind, brand, model, tacs):
        with self.con:
            self.con.execute(
                "INSERT OR IGNORE INTO favorites (kind, brand, model, tacs, created)"
                " VALUES (?,?,?,?,?)", (kind, brand, model, json.dumps(list(tacs)), time.time()))
        return self.find_favorite(kind, brand, model, tacs)

    def remove_favorite(self, fav_id):
        with self.con:
            self.con.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))

    # ---- history --------------------------------------------------------
    def add_history(self, label, rows):
        """rows: [(imei, tac, ...)]"""
        data = json.dumps([[r[0], r[1]] for r in rows], separators=(",", ":"))
        with self.con:
            cur = self.con.execute(
                "INSERT INTO history (created, label, count, rows) VALUES (?,?,?,?)",
                (time.time(), label, len(rows), data))
            self.con.execute(
                "DELETE FROM history WHERE id NOT IN"
                " (SELECT id FROM history ORDER BY id DESC LIMIT ?)", (HISTORY_LIMIT,))
        return cur.lastrowid

    def history(self):
        return [{"id": i, "created": c, "label": l, "count": n}
                for i, c, l, n in self.con.execute(
                    "SELECT id, created, label, count FROM history ORDER BY id DESC")]

    def history_rows(self, hist_id):
        row = self.con.execute("SELECT label, rows FROM history WHERE id = ?", (hist_id,)).fetchone()
        if not row:
            return None, []
        return row[0], [(imei, tac, row[0]) for imei, tac in json.loads(row[1])]

    def delete_history(self, hist_id):
        with self.con:
            self.con.execute("DELETE FROM history WHERE id = ?", (hist_id,))

    def clear_history(self):
        with self.con:
            self.con.execute("DELETE FROM history")
