[app]
title = G2 IMEI Generator
package.name = g2imeigen
# Change to a domain you control before publishing; changing it later
# produces a different app id (it installs side-by-side with the old one).
package.domain = io.github.g33l0
source.dir = .
# "sqlite" is required so data/tac.sqlite (the embedded TAC database) is packaged.
source.include_exts = py,png,jpg,kv,atlas,ttf,otf,sqlite
source.include_patterns = data/tac.sqlite
source.exclude_dirs = tests, tools, docs, bin, .buildozer, .github, .venv, venv, __pycache__
version = 1.3.0
# sqlite3 recipe is needed for Python's sqlite3 module on Android.
requirements = python3,kivy==2.3.1,sqlite3
orientation = portrait
# 0 keeps the Android status bar visible (1 hid it and could cover the keyboard).
fullscreen = 0

# Branding (regenerate with: python tools/make_logo.py)
icon.filename = %(source.dir)s/assets/icon.png
icon.adaptive_foreground.filename = %(source.dir)s/assets/icon_fg.png
icon.adaptive_background.filename = %(source.dir)s/assets/icon_bg.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #0B0B0C

# No permissions needed: export uses the Android share sheet.
android.permissions =
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = False
android.release_artifact = apk
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
