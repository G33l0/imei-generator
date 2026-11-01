"""Keep the TAC database current without ever blocking the app.

Flow (run in a background thread by the app):

1. The app opens whichever is newer: the database bundled in the APK or the
   one saved by a previous update (``choose_database``). Works offline.
2. ``check_and_update`` fetches a tiny manifest (data/tac_manifest.json in the
   repository). If its ``data_hash`` differs from the open database and it is
   not older, the new database is downloaded to a temp file, verified
   (size, SHA-256, opens as SQLite, row count and data hash match) and only
   then atomically moved into place. Any failure leaves the current file alone.
3. No connection -> ``UpdateResult(status="offline")``; the app keeps using the
   database it already has.
"""
import hashlib
import json
import os
import sqlite3
import ssl
import tempfile
import urllib.error
import urllib.request

REPO_RAW = "https://raw.githubusercontent.com/G33l0/imei-generator/main/"
MANIFEST_URL = REPO_RAW + "data/tac_manifest.json"
SCHEMA = 1
SAVED_NAME = "tac.sqlite"
MANIFEST_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 60
MAX_DB_BYTES = 64 * 1024 * 1024
USER_AGENT = "G2-IMEI-Generator/1.4 (+https://github.com/G33l0/imei-generator)"


class UpdateResult:
    """status: 'updated', 'current', 'unavailable' (online, but the server has
    no usable update), 'offline' or 'error' (download rejected)."""

    def __init__(self, status, message="", path=None, meta=None):
        self.status = status
        self.message = message
        self.path = path
        self.meta = meta or {}

    def __repr__(self):
        return "UpdateResult(%r, %r)" % (self.status, self.message)


# ---------------------------------------------------------------------------
#  Local database inspection
# ---------------------------------------------------------------------------
def read_meta(path):
    """Return the meta table of a TAC database as a dict, or None if unusable."""
    if not path or not os.path.exists(path):
        return None
    try:
        uri = "file:%s?mode=ro" % path.replace("\\", "/")
        con = sqlite3.connect(uri, uri=True)
        try:
            meta = dict(con.execute("SELECT key, value FROM meta"))
            meta["_rows"] = con.execute("SELECT count(*) FROM tac").fetchone()[0]
        finally:
            con.close()
        return meta
    except sqlite3.Error:
        return None


def _newer_or_equal(a, b):
    """Compare ISO dates stored in meta['built'] (missing counts as oldest)."""
    return (a or "") >= (b or "")


def choose_database(bundled_path, user_dir):
    """Pick the database to open: saved update if valid and not older."""
    saved = os.path.join(user_dir, SAVED_NAME)
    saved_meta = read_meta(saved)
    bundled_meta = read_meta(bundled_path)
    if saved_meta and saved_meta.get("_rows", 0) > 0 and (
            not bundled_meta
            or _newer_or_equal(saved_meta.get("built"), bundled_meta.get("built"))):
        return saved, saved_meta
    return bundled_path, bundled_meta


def needs_update(local_meta, manifest):
    if not manifest or manifest.get("schema") != SCHEMA:
        return False
    local_meta = local_meta or {}
    if manifest.get("data_hash") and manifest.get("data_hash") == local_meta.get("data_hash"):
        return False
    return _newer_or_equal(manifest.get("built"), local_meta.get("built"))


# ---------------------------------------------------------------------------
#  Network
# ---------------------------------------------------------------------------
def _ssl_context():
    # Android's Python has no system CA store; certifi ships one.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Cache-Control": "no-cache"})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def fetch_manifest(url=None, timeout=MANIFEST_TIMEOUT):
    with _open(url or MANIFEST_URL, timeout) as r:
        data = r.read(64 * 1024)
    manifest = json.loads(data.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest is not an object")
    return manifest


def _download(url, dest, expected_size, timeout=DOWNLOAD_TIMEOUT, progress=None):
    h = hashlib.sha256()
    total = 0
    with _open(url, timeout) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DB_BYTES or (expected_size and total > expected_size):
                raise ValueError("download larger than expected")
            h.update(chunk)
            f.write(chunk)
            if progress and expected_size:
                progress(min(1.0, total / expected_size))
    if expected_size and total != expected_size:
        raise ValueError("download size mismatch (%d != %d)" % (total, expected_size))
    return h.hexdigest()


def verify_database(path, manifest):
    meta = read_meta(path)
    if not meta:
        raise ValueError("downloaded file is not a TAC database")
    if manifest.get("count") and meta["_rows"] != int(manifest["count"]):
        raise ValueError("row count mismatch")
    if manifest.get("data_hash") and meta.get("data_hash") != manifest["data_hash"]:
        raise ValueError("data hash mismatch")
    return meta


def check_and_update(current_meta, user_dir, manifest_url=None, progress=None):
    """Check online for a newer database and install it into ``user_dir``.

    ``progress(fraction)`` is called during the download (from this thread).
    Never raises: returns an UpdateResult.
    """
    try:
        manifest = fetch_manifest(manifest_url or MANIFEST_URL)
    except urllib.error.HTTPError as e:  # reached the server: we are online
        return UpdateResult("unavailable", "Update server returned HTTP %s" % e.code)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return UpdateResult("offline", "No connection (%s)" % getattr(e, "reason", e))
    except Exception as e:  # bad JSON etc.
        return UpdateResult("unavailable", "Update check failed: %s" % e)

    if not needs_update(current_meta, manifest):
        return UpdateResult("current", "Database is up to date", meta=current_meta)

    url = manifest.get("url") or (REPO_RAW + "data/tac.sqlite")
    os.makedirs(user_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="tac_", suffix=".download", dir=user_dir)
    os.close(fd)
    try:
        if progress:
            progress(0.0)
        digest = _download(url, tmp, int(manifest.get("size") or 0), progress=progress)
        if manifest.get("sha256") and digest != manifest["sha256"]:
            raise ValueError("checksum mismatch")
        meta = verify_database(tmp, manifest)
        final = os.path.join(user_dir, SAVED_NAME)
        os.replace(tmp, final)
        return UpdateResult("updated", "Database updated: {:,} devices".format(meta["_rows"]),
                            path=final, meta=meta)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return UpdateResult("offline", "Download interrupted (%s)" % getattr(e, "reason", e))
    except Exception as e:
        return UpdateResult("error", "Update rejected: %s" % e)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
