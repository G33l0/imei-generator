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


VERDICT = {
    gen.STATUS_KNOWN_DEVICE: "valid",
    gen.STATUS_UNKNOWN_DEVICE: "unknown",
    gen.STATUS_TEST: "test",
    gen.STATUS_INVALID: "invalid",
}
VERDICT_LABEL = {"valid": "valid", "unknown": "valid format, unknown device",
                 "test": "test IMEI", "invalid": "invalid"}


def bulk_check(text, lookup=None):
    """Check every entry. Returns (rows, summary).

    rows: [{"input", "imei", "ok", "verdict", "message", "device"}]
      ok      the number itself is well-formed and consistent
      verdict valid | unknown | test | invalid (see imei_generator.inspect_imei)
    summary: {"total", "valid", "unknown", "invalid", "truncated"}
      ("unknown" counts both unknown-device and test IMEIs)
    """
    entries = parse_bulk(text)
    truncated = len(entries) > MAX_BULK
    entries = entries[:MAX_BULK]
    rows = []
    counts = {"valid": 0, "unknown": 0, "invalid": 0}
    for raw in entries:
        info = gen.inspect_imei(raw, lookup)
        verdict = VERDICT[info["status"]]
        device = ""
        if info["device"]:
            device = "%s %s" % (info["device"]["brand"], info["device"]["model"])
        counts["valid" if verdict == "valid" else "invalid" if verdict == "invalid" else "unknown"] += 1
        rows.append({"input": raw, "imei": info["imei"], "ok": info["ok"], "verdict": verdict,
                     "message": info["headline"], "device": device})
    summary = dict(counts, total=len(rows), truncated=truncated)
    return rows, summary


def bulk_report_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["input", "imei", "status", "device"])
    for r in rows:
        w.writerow([r["input"], r["imei"], VERDICT_LABEL[r["verdict"]], r["device"]])
    return buf.getvalue()
