# eSIM iPhone IMEI Generator

A minimal Android application that generates checksum-valid IMEI numbers for eSIM-capable iPhone models. Built with Kivy and packaged as an APK using Buildozer.

**Built by [IamG2](https://github.com/IamG2).**

---

## Overview

This tool is a **number generator**, not an IMEI flasher. It produces 15-digit strings that pass the Luhn checksum and carry a TAC (Type Allocation Code) prefix associated with eSIM iPhone models. It does **not** write to device hardware, activate eSIM profiles, or bypass carrier restrictions.

It exists for QA testing, educational purposes, and development work where simulated device identities are required. Using a generated IMEI on a live cellular network is illegal in most jurisdictions and will result in permanent blacklisting.

---

## Features

- Generates Luhn-valid 15-digit IMEIs
- Uses a configurable TAC database (`tac_db.json`)
- Supports custom TAC input
- Minimal Kivy UI, single-screen
- Buildable from Termux (experimental) or Linux (recommended)

---

## Limitations

- **Cannot write IMEIs to hardware.** Android’s security model prevents third-party apps from modifying the protected IMEI partition.
- **TAC list is incomplete.** The bundled database is a starter set. You are responsible for expanding it from public sources.
- **Not a network tool.** Generated numbers are for local testing only.

---


---

## TAC Database

The app reads `tac_db.json` at startup. The bundled file contains a small set of known eSIM-compatible iPhone TACs. To expand it:

1. Download the **OSMOCOM TAC database** CSV from [tacdb.osmocom.org](http://tacdb.osmocom.org). It is free and community-maintained.
2. Filter rows where the manufacturer is `Apple` and the model matches an eSIM-capable iPhone (XR, XS, 11 series onward, SE 2nd/3rd gen).
3. Extract the first 8 digits of each IMEI as the TAC.
4. Add them to the corresponding arrays in `tac_db.json`.

The GSMA IMEI database (`imeidb.gsma.com`) is the official source but requires manufacturer registration and payment. Do not scrape it.

---

## Building the APK

### Option A: Linux / WSL2 (Recommended)

This is the supported path. Buildozer works reliably on Ubuntu and WSL2.

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git zip unzip openjdk-17-jdk -y

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install buildozer cython==0.29.33 kivy

buildozer init
# Edit buildozer.spec (see below)
buildozer -v android debug

