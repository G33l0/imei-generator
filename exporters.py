"""Turn IMEI lists into text for copying/sharing, and run bulk checks."""
import csv
import io
import json
import re

import imei_generator as gen

# (key, label shown in the UI, file extension)
FORMATS = [
    ("lines", "One per line", "txt"),
    ("csv", "CSV", "csv"),
    ("json", "JSON", "json"),
    ("quoted", "Quoted list", "txt"),
    ("comma", "Comma list", "txt"),
]
FORMAT_LABELS = {k: label for k, label, _ in FORMATS}
FORMAT_KEYS = {label: k for k, label, _ in FORMATS}
FORMAT_EXT = {k: ext for k, _, ext in FORMATS}

MAX_BULK = 5000


def render(rows, fmt="lines"):
    """rows: [(imei, tac, label)] -> text in the requested format."""
    imeis = [r[0] for r in rows]
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["imei", "tac", "model"])
        for r in rows:
            w.writerow([r[0], r[1] if len(r) > 1 else r[0][:8], r[2] if len(r) > 2 else ""])
        return buf.getvalue()
    if fmt == "json":
        return json.dumps(imeis, indent=2)
    if fmt == "quoted":
        return ", ".join("'%s'" % i for i in imeis)
    if fmt == "comma":
        return ",".join(imeis)
    return "\n".join(imeis)


_SPLIT = re.compile(r"[\n,;|\t]+")


def parse_bulk(text):
    """Split pasted text into candidate numbers.

    Separators are new lines, commas, semicolons, pipes and tabs. Spaces and
    dashes inside an entry are kept as part of the number ("35 104463 ...").
    Quotes and brackets (from JSON / quoted lists) are stripped.
    """
    out = []
    for part in _SPLIT.split(text or ""):
        part = part.strip().strip("'\"[]() ")
        if part:
            out.append(part)
    return out


def bulk_check(text, lookup=None):
    """Check every entry. Returns (rows, summary).

    rows: [{"input", "imei", "ok", "message", "device"}]
    summary: {"total", "valid", "invalid", "truncated"}
    """
    entries = parse_bulk(text)
    truncated = len(entries) > MAX_BULK
    entries = entries[:MAX_BULK]
    rows, valid = [], 0
    for raw in entries:
        num = gen.normalize(raw)
        ok, msg = gen.validate_imei(num)
        device = ""
        if lookup and len(num) >= 8 and num[:8].isdigit():
            row = lookup(num[:8])
            if row:
                device = "%s %s" % (row["brand"], row["model"])
        valid += ok
        rows.append({"input": raw, "imei": num, "ok": ok, "message": msg, "device": device})
    return rows, {"total": len(rows), "valid": valid, "invalid": len(rows) - valid,
                  "truncated": truncated}


def bulk_report_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["input", "imei", "status", "device"])
    for r in rows:
        w.writerow([r["input"], r["imei"], "valid" if r["ok"] else "invalid", r["device"]])
    return buf.getvalue()
