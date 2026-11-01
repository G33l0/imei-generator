"""Core IMEI maths: Luhn check digit, validation and test-IMEI generation.

Pure Python, no Kivy dependency, so it can be unit-tested and reused from the
command line:  python imei_generator.py 35104463 5
"""
import secrets

IMEI_LENGTH = 15
TAC_LENGTH = 8
SNR_LENGTH = 6
MAX_BATCH = 1000

_rng = secrets.SystemRandom()


def luhn_check_digit(payload):
    """Return the Luhn check digit (0-9) for a string of digits."""
    if not payload or not payload.isdigit():
        raise ValueError("Luhn payload must be a non-empty string of digits")
    total = 0
    # Walk from the right; the digit next to the (future) check digit is doubled.
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def normalize(text):
    """Strip spaces, dashes and slashes users commonly paste with an IMEI."""
    return "".join(ch for ch in (text or "") if ch not in " -/.\t\r\n")


def is_valid_tac(tac):
    return isinstance(tac, str) and len(tac) == TAC_LENGTH and tac.isdigit()


def validate_imei(imei):
    """Return (ok, message) for an IMEI.

    Messages are deliberately neutral: they are shown in the app and must not
    reveal how numbers are verified (no algorithm name, no expected digit).
    """
    imei = normalize(imei)
    if not imei.isdigit():
        return False, "Digits only, please"
    if len(imei) != IMEI_LENGTH:
        return False, "An IMEI has 15 digits (this has %d)" % len(imei)
    if int(imei[-1]) != luhn_check_digit(imei[:-1]):
        return False, "Invalid IMEI"
    return True, "Valid IMEI"


# Reporting Body Identifiers: the first two digits of a TAC name the body that
# allocated it. 00 is reserved for test equipment.
REPORTING_BODIES = {
    "00": "Test IMEI",
    "01": "PTCRB (USA)", "10": "PTCRB (USA)",
    "30": "Iridium",
    "33": "DGPT (France)",
    "35": "BABT (UK)",
    "44": "BABT (UK)",
    "45": "NTA (Denmark)",
    "49": "BZT/BAPT (Germany)",
    "50": "BZT ETS (Germany)",
    "51": "Cetecom ICT (Germany)",
    "52": "Cetecom (Germany)",
    "53": "TUV (Germany)",
    "54": "Phoenix Test Lab (Germany)",
    "86": "TAF (China)",
    "91": "MSAI (India)",
    "98": "BABT (UK)",
    "99": "GHA (multi-standard)",
}

STATUS_INVALID = "invalid"
STATUS_TEST = "test"
STATUS_UNKNOWN_DEVICE = "valid_unknown"
STATUS_KNOWN_DEVICE = "valid_known"


def inspect_imei(imei, lookup=None):
    """Full verdict for one IMEI, for display.

    Returns a dict with:
      status   one of STATUS_* above
      ok       True when the number itself is well-formed and consistent
      headline short neutral text for the UI
      imei     normalised digits
      issuer   reporting-body name, or "" if unrecognised
      device   lookup row for the TAC (dict) or None
      notes    list of extra neutral observations

    A consistent number only proves it is well-formed. Whether it is assigned
    to a real handset can only be confirmed by the operator/GSMA, so an
    unknown TAC or issuer is reported rather than hidden.
    """
    num = normalize(imei)
    ok, msg = validate_imei(num)
    result = {"status": STATUS_INVALID, "ok": ok, "headline": msg, "imei": num,
              "issuer": "", "device": None, "notes": []}
    if len(num) >= 8 and num[:8].isdigit():
        result["issuer"] = REPORTING_BODIES.get(num[:2], "")
        if lookup:
            result["device"] = lookup(num[:8])
    if not ok:
        return result
    notes = result["notes"]
    if len(set(num[:14])) == 1:
        notes.append("Repeated single digit: placeholder, not a real device")
    elif num[8:14] in ("000000", "123456", "999999"):
        notes.append("Serial looks like a placeholder")
    if num[:2] == "00":
        result["status"] = STATUS_TEST
        result["headline"] = "Valid test IMEI (not issued to a phone)"
    elif result["device"]:
        result["status"] = STATUS_KNOWN_DEVICE
        result["headline"] = "Valid IMEI"
    else:
        result["status"] = STATUS_UNKNOWN_DEVICE
        result["headline"] = "Valid format, unknown device type"
    return result


def generate_imei(tac):
    """Generate one 15-digit Luhn-valid IMEI starting with an 8-digit TAC."""
    tac = normalize(tac)
    if not is_valid_tac(tac):
        raise ValueError("TAC must be exactly 8 digits")
    snr = "".join(str(_rng.randrange(10)) for _ in range(SNR_LENGTH))
    base = tac + snr
    return base + str(luhn_check_digit(base))


def generate_batch(tacs, count):
    """Generate `count` unique IMEIs, picking a random TAC from `tacs` for each.

    Returns a list of (imei, tac) tuples.
    """
    tacs = [normalize(t) for t in (tacs if isinstance(tacs, (list, tuple)) else [tacs])]
    if not tacs:
        raise ValueError("No TAC available")
    for t in tacs:
        if not is_valid_tac(t):
            raise ValueError("Invalid TAC %r: must be exactly 8 digits" % t)
    if not 1 <= count <= MAX_BATCH:
        raise ValueError("Quantity must be between 1 and %d" % MAX_BATCH)
    seen, out = set(), []
    while len(out) < count:
        tac = _rng.choice(tacs)
        imei = generate_imei(tac)
        if imei not in seen:
            seen.add(imei)
            out.append((imei, tac))
    return out


# Backwards-compatible name used by the original version of the app.
generate_imei_with_tac = generate_imei


if __name__ == "__main__":
    import sys

    tac_arg = sys.argv[1] if len(sys.argv) > 1 else "35104463"  # iPhone 13 (Osmocom)
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for imei, _ in generate_batch([tac_arg], n):
        print(imei)
