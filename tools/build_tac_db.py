#!/usr/bin/env python3
"""Build data/tac.sqlite -- the TAC database embedded in the APK.

Sources (merged in this order, later wins):
  1. Osmocom TAC database CSV (CC-BY-SA 3.0, (c) Harald Welte and contributors)
  2. data/tac_extra.csv -- your own verified TACs (tac,brand,model,aka,esim)

Usage:
  python tools/build_tac_db.py                    # download Osmocom CSV, build
  python tools/build_tac_db.py --csv tacdb.csv    # build from a local copy (offline)
  python tools/build_tac_db.py --no-osmocom       # only data/tac_extra.csv

Run it again whenever you add TACs, then rebuild the APK.
"""
import argparse
import collections
import csv
import datetime
import io
import os
import re
import sqlite3
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "data", "tac.sqlite")
DEFAULT_EXTRA = os.path.join(ROOT, "data", "tac_extra.csv")
# The https endpoint serves a mismatched certificate, so plain http is used.
OSMOCOM_URL = "http://tacdb.osmocom.org/export/tacdb.csv"
OSMOCOM_LICENSE = "Osmocom TAC database, CC-BY-SA 3.0, (c) Harald Welte and contributors"

# iPhones that support eSIM: XR, XS/XS Max, 11 and later, SE 2nd/3rd gen, Air.
ESIM_IPHONE = re.compile(
    r"\biPhone\s*(XR|XS|1[1-9]|2\d|Air|SE\s*\(?\s*(2nd|3rd|20(20|22)))", re.I)
APPLE_MODEL_NUMBER = re.compile(r"^A\d{4}$")

SCHEMA = """
CREATE TABLE tac (
    tac    TEXT PRIMARY KEY CHECK (length(tac) = 8),
    brand  TEXT NOT NULL,
    model  TEXT NOT NULL,
    aka    TEXT NOT NULL DEFAULT '',
    esim   INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL
);
CREATE INDEX idx_tac_brand_model ON tac (brand COLLATE NOCASE, model COLLATE NOCASE);
CREATE INDEX idx_tac_esim ON tac (esim) WHERE esim = 1;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def clean(s):
    return " ".join((s or "").split())


def display_model(brand, model, aka):
    """Apple rows are often filed under a model number (A2221); show the name."""
    first_aka = clean(aka.split(",")[0]) if aka else ""
    if brand.lower() == "apple" and APPLE_MODEL_NUMBER.match(model) and first_aka:
        return "%s (%s)" % (first_aka, model)
    return model


def is_esim(brand, model, aka):
    if brand.lower() != "apple":
        return False
    text = "%s %s" % (model, aka)
    return bool(ESIM_IPHONE.search(text)) and "ipad" not in text.lower()


def read_osmocom(text):
    """Yield dicts from the Osmocom export.

    Columns: tac, brand, model, contributor, comment, gsmarena, gsmarena, aka.
    The first line is a licence banner, the second a header.
    """
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 3:
            continue
        tac = row[0].strip()
        if not (len(tac) == 8 and tac.isdigit()):
            continue  # header / malformed
        brand, model = clean(row[1]), clean(row[2])
        if not brand or not model:
            continue
        aka = clean(row[7]) if len(row) > 7 else ""
        yield {"tac": tac, "brand": brand, "model": model, "aka": aka, "esim": None,
               "source": "osmocom"}


def read_extra(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", newline="") as f:
        lines = [l for l in f if l.strip() and not l.lstrip().startswith("#")]
    for n, row in enumerate(csv.DictReader(lines), start=2):
        tac = (row.get("tac") or "").strip()
        brand, model = clean(row.get("brand")), clean(row.get("model"))
        if not (len(tac) == 8 and tac.isdigit()) or not brand or not model:
            print("tac_extra.csv: skipping invalid row %d: %r" % (n, row), file=sys.stderr)
            continue
        esim = (row.get("esim") or "").strip().lower()
        yield {"tac": tac, "brand": brand, "model": model, "aka": clean(row.get("aka")),
               "esim": None if esim == "" else esim in ("1", "true", "yes", "y"),
               "source": "extra"}


def fetch(url):
    print("Downloading %s ..." % url, file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def build(rows, out_path, sources):
    records = {}
    for r in rows:
        records[r["tac"]] = r  # later sources override earlier ones

    # Normalise brand spelling ("OPPO" vs "Oppo") to the most common variant.
    spellings = collections.defaultdict(collections.Counter)
    for r in records.values():
        spellings[r["brand"].lower()][r["brand"]] += 1
    canonical = {k: c.most_common(1)[0][0] for k, c in spellings.items()}

    tmp = out_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    for tac in sorted(records):
        r = records[tac]
        brand = canonical[r["brand"].lower()]
        model = display_model(brand, r["model"], r["aka"])
        esim = r["esim"] if r["esim"] is not None else is_esim(brand, model, r["aka"])
        con.execute("INSERT INTO tac VALUES (?,?,?,?,?,?)",
                    (tac, brand, model, r["aka"], int(bool(esim)), r["source"]))
    meta = {
        "built": datetime.date.today().isoformat(),
        "sources": ", ".join(sources),
        "license": OSMOCOM_LICENSE if "osmocom" in sources else "",
        "count": str(len(records)),
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    con.commit()
    con.execute("VACUUM")
    con.close()
    os.replace(tmp, out_path)
    return meta


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", help="local Osmocom CSV instead of downloading")
    p.add_argument("--url", default=OSMOCOM_URL)
    p.add_argument("--no-osmocom", action="store_true", help="only use the extra CSV")
    p.add_argument("--extra", default=DEFAULT_EXTRA)
    p.add_argument("--out", default=DEFAULT_OUT)
    a = p.parse_args(argv)

    rows, sources = [], []
    if not a.no_osmocom:
        if a.csv:
            with open(a.csv, encoding="utf-8", errors="replace", newline="") as f:
                text = f.read()
        else:
            text = fetch(a.url)
        osmo = list(read_osmocom(text))
        if len(osmo) < 1000:
            sys.exit("Osmocom CSV looks wrong (%d rows) -- refusing to build" % len(osmo))
        rows += osmo
        sources.append("osmocom")
    extra = list(read_extra(a.extra))
    if extra:
        rows += extra
        sources.append("extra")
    if not rows:
        sys.exit("No TAC rows found")

    meta = build(rows, a.out, sources)
    con = sqlite3.connect(a.out)
    brands = con.execute("SELECT count(DISTINCT brand) FROM tac").fetchone()[0]
    esim = con.execute("SELECT count(*) FROM tac WHERE esim = 1").fetchone()[0]
    con.close()
    print("Wrote %s: %s TACs, %d brands, %d eSIM iPhone TACs (%s)"
          % (os.path.relpath(a.out), meta["count"], brands, esim, meta["sources"]))


if __name__ == "__main__":
    main()
