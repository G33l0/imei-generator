# main.py -- G2 IMEI Generator (Kivy front end). Layout lives in g2.kv.
import math
import os
import time

import kivy
kivy.require("2.1.0")

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import platform

import exporters
import imei_generator as gen
from tacdb import TacDB
from userdata import UserData

APP_NAME = "G2 IMEI Generator"
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "assets", "fonts")

MODE_ESIM = "esim"
MODE_ALL = "all"
MODE_CUSTOM = "custom"
ANY_BRAND = "Any brand"
NO_MODELS = "No models"
MORE = "Refine search to see more"
TYPE_TO_SEARCH = "Type to search all brands"
QTY_PRESETS = (1, 10, 50, 100)

GOLD = "D4AF37"
MUTED = "8C877D"
DANGER = "E5484D"


def register_fonts():
    def f(name):
        return os.path.join(FONTS, name)
    try:
        LabelBase.register("Body", f("Manrope-Medium.ttf"), fn_bold=f("Manrope-Bold.ttf"))
        LabelBase.register("Display", f("SpaceGrotesk-SemiBold.ttf"), fn_bold=f("SpaceGrotesk-Bold.ttf"))
        LabelBase.register("Mono", f("JetBrainsMono-Medium.ttf"))
    except Exception as e:  # fonts missing: fall back to Kivy's Roboto
        print("font registration failed:", e)
        LabelBase.register("Body", "Roboto")
        LabelBase.register("Display", "Roboto")
        LabelBase.register("Mono", "RobotoMono-Regular")


# ---------------------------------------------------------------------------
#  Widgets
# ---------------------------------------------------------------------------
class Root(FloatLayout):
    pass


class ImeiRow(ButtonBehavior, BoxLayout):
    num = StringProperty("")
    markup = StringProperty("")
    imei = StringProperty("")

    def on_release(self):
        App.get_running_app().copy_one(self.imei)


class BulkRow(ButtonBehavior, BoxLayout):
    markup = StringProperty("")
    device = StringProperty("")
    imei = StringProperty("")
    ok = BooleanProperty(False)

    def on_release(self):
        App.get_running_app().copy_one(self.imei)


class HistoryRow(ButtonBehavior, BoxLayout):
    hid = NumericProperty(0)
    title = StringProperty("")
    meta = StringProperty("")

    def on_release(self):
        App.get_running_app().open_history(self.hid)


class DetailRow(BoxLayout):
    key = StringProperty("")
    value = StringProperty("")


class Chip(ButtonBehavior, Label):
    active = BooleanProperty(False)


class StarButton(ButtonBehavior, Widget):
    """Favourite toggle; the star is drawn as vector geometry (no icon font)."""
    active = BooleanProperty(False)
    star_points = ListProperty([])
    mesh_vertices = ListProperty([])
    mesh_indices = ListProperty([])

    def on_size(self, *_):
        self._build()

    def on_pos(self, *_):
        self._build()

    def _build(self):
        cx, cy = self.center
        outer, inner = dp(9.5), dp(4.2)
        pts = []
        for i in range(10):
            r = outer if i % 2 == 0 else inner
            a = math.pi / 2 + i * math.pi / 5
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        self.star_points = pts
        verts = [cx, cy, 0, 0]
        for i in range(0, len(pts), 2):
            verts += [pts[i], pts[i + 1], 0, 0]
        verts += [pts[0], pts[1], 0, 0]
        self.mesh_vertices = verts
        self.mesh_indices = list(range(len(verts) // 4))


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
def set_visible(widget, visible):
    """Hide a widget without leaving a gap or letting it receive touches."""
    if not hasattr(widget, "_full_height"):
        widget._full_height = widget.height
    widget.height = widget._full_height if visible else 0
    widget.opacity = 1 if visible else 0
    widget.disabled = not visible


def select_segment(widget):
    """Programmatically select a segment and release the rest of its group."""
    for w in ToggleButtonBehavior.get_widgets(widget.group):
        if w is not widget:
            w.state = "normal"
    widget.state = "down"


def escape(text):
    return str(text).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def format_imei(imei):
    """TAC (device type) in gold, the rest in ivory."""
    return "[color=#%s]%s[/color] %s" % (GOLD, imei[:8], escape(imei[8:]))


def plural(n, word):
    return "{:,} {}{}".format(n, word, "" if n == 1 else "s")


def when(ts):
    t = time.localtime(ts)
    if time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d"):
        return "Today " + time.strftime("%H:%M", t)
    return time.strftime("%d %b %Y, %H:%M", t)


# ---------------------------------------------------------------------------
#  App
# ---------------------------------------------------------------------------
class G2ImeiApp(App):
    db_info = StringProperty("")
    db_summary = StringProperty("")
    results_title = StringProperty("Results")
    results_subtitle = StringProperty("Tap a number to copy it")
    empty_text = StringProperty("")
    bulk_summary = StringProperty("Results")
    history_title = StringProperty("History")
    export_label = StringProperty("Share" if platform == "android" else "Save")
    logo = StringProperty(os.path.join(HERE, "assets", "logo.png"))
    format_labels = ListProperty([label for _, label, _ in exporters.FORMATS])
    mode = StringProperty(MODE_ESIM)

    # ---- lifecycle ------------------------------------------------------
    def build(self):
        self.title = APP_NAME
        self.icon = os.path.join(HERE, "assets", "icon.png")
        register_fonts()
        Window.clearcolor = (11 / 255, 11 / 255, 12 / 255, 1)
        Window.softinput_mode = "below_target"
        style_android_bars()

        self.db = TacDB()
        self.user = UserData(self.user_data_dir)
        self.results = []        # [(imei, tac, label)]
        self.bulk_rows = []
        self.esim = dict(self.db.esim_models())
        self.model_tacs = {}     # display label -> [tacs]
        self.model_meta = {}     # display label -> (brand, model)
        self._restoring = True
        self.empty_text = "No numbers yet.\nPick a source and tap [color=#%s]Generate[/color]." % GOLD

        meta = self.db.meta()
        count = self.db.count()
        self.db_summary = "Offline TAC database  ·  {:,} devices".format(count)
        info = "Database: {:,} TACs, {} eSIM iPhone TACs. Source: {}.".format(
            count, sum(len(t) for t in self.esim.values()), meta.get("sources", "?"))
        if meta.get("built"):
            info += " Built %s." % meta["built"]
        if meta.get("license"):
            info += "\n" + meta["license"] + "."
        if self.db.error:
            info += "\nDatabase not loaded (%s), using built-in list." % self.db.error
        self.db_info = info

        Builder.load_file(os.path.join(HERE, "g2.kv"))
        root = Root()
        self.root = root
        ids = root.ids
        self.search_trigger = Clock.create_trigger(lambda dt: self.refresh_models(), 0.3)

        for n in QTY_PRESETS:
            chip = Chip(text=str(n))
            chip.bind(on_release=lambda c: self.set_qty(int(c.text)))
            ids.qty_chips.add_widget(chip)

        ids.brand.values = [ANY_BRAND] + self.db.brands()
        self.restore_settings()
        self.refresh_favorites()
        self.refresh_history()
        self._restoring = False
        return root

    def on_pause(self):
        self.save_settings()
        return True

    def on_stop(self):
        self.save_settings()

    # ---- settings (feature: remember your setup) -----------------------
    def save_settings(self, *_):
        if getattr(self, "_restoring", True) or not self.root:
            return
        ids = self.root.ids
        self.user.set_many({
            "mode": self.mode,
            "brand": ids.brand.text,
            "search": ids.search.text,
            "model": ids.model.text,
            "custom_tac": ids.custom_tac.text,
            "qty": ids.qty.text,
            "fmt": ids.fmt.text,
            "tab": ids.sm.current,
            "check_mode": ids.check_sm.current,
        })

    def restore_settings(self):
        ids = self.root.ids
        u = self.user
        brand = u.get("brand", "Apple")
        ids.brand.text = brand if brand in ids.brand.values else "Apple"
        ids.search.text = u.get("search", "") or ""
        ids.custom_tac.text = u.get("custom_tac", "") or ""
        ids.qty.text = str(u.get("qty", "10") or "10")
        fmt = u.get("fmt")
        if fmt in self.format_labels:
            ids.fmt.text = fmt
        mode = u.get("mode", MODE_ESIM)
        target = {MODE_ESIM: ids.mode_esim, MODE_ALL: ids.mode_all,
                  MODE_CUSTOM: ids.mode_custom}.get(mode, ids.mode_esim)
        select_segment(target)
        self.set_mode(mode if mode in (MODE_ESIM, MODE_ALL, MODE_CUSTOM) else MODE_ESIM)
        model = u.get("model")
        if model in self.model_tacs:
            ids.model.text = model
        if u.get("check_mode") == "bulk":
            select_segment(ids.check_bulk)
        tab = u.get("tab", "generate")
        select_segment({"check": ids.tab_check, "history": ids.tab_history}.get(tab, ids.tab_generate))
        self.update_qty_chips()
        self.update_tac_info()

    # ---- navigation -----------------------------------------------------
    def switch_tab(self, name):
        if not self.root:
            return
        self.root.ids.sm.current = name
        if name == "history":
            self.refresh_history()
        self.save_settings()

    def set_check_mode(self, name):
        if self.root:
            self.root.ids.check_sm.current = name
            self.save_settings()

    # ---- source / model selection --------------------------------------
    def set_mode(self, mode):
        self.mode = mode
        if not self.root:
            return
        ids = self.root.ids
        set_visible(ids.brand_row, mode == MODE_ALL)
        set_visible(ids.model_row, mode != MODE_CUSTOM)
        set_visible(ids.custom_row, mode == MODE_CUSTOM)
        self.refresh_models()
        self.save_settings()

    def refresh_models(self):
        if not self.root:
            return
        ids = self.root.ids
        truncated = False
        self.model_meta = {}
        if self.mode == MODE_ESIM:
            self.model_tacs = dict(self.esim)
            self.model_meta = {m: ("Apple", m) for m in self.esim}
        elif self.mode == MODE_ALL:
            query = ids.search.text.strip()
            if ids.brand.text == ANY_BRAND:
                rows, truncated = self.db.search_all(query)
                self.model_tacs = {}
                for brand, model, tacs in rows:
                    label = "%s · %s" % (brand, model)
                    self.model_tacs[label] = tacs
                    self.model_meta[label] = (brand, model)
            else:
                rows, truncated = self.db.models(ids.brand.text, query)
                self.model_tacs = dict(rows)
                self.model_meta = {m: (ids.brand.text, m) for m, _ in rows}
        else:
            self.update_tac_info()
            return
        names = list(self.model_tacs)
        if truncated:
            names.append(MORE)
        ids.model.values = names
        if ids.model.text not in self.model_tacs:
            if self.model_tacs:
                ids.model.text = names[0]
            elif self.mode == MODE_ALL and ids.brand.text == ANY_BRAND and not ids.search.text.strip():
                ids.model.text = TYPE_TO_SEARCH
            else:
                ids.model.text = NO_MODELS
        self.update_tac_info()

    def current_selection(self):
        """Return (kind, brand, model, tacs) or raise ValueError."""
        ids = self.root.ids
        if self.mode == MODE_CUSTOM:
            tac = gen.normalize(ids.custom_tac.text)
            if not gen.is_valid_tac(tac):
                raise ValueError("Enter a valid 8-digit TAC")
            return "tac", "", "", [tac]
        if ids.model.text == MORE:
            raise ValueError("Type in Search to narrow the model list")
        if ids.model.text == TYPE_TO_SEARCH:
            raise ValueError("Type a model name in Search")
        tacs = self.model_tacs.get(ids.model.text)
        if not tacs:
            raise ValueError("Select a model first")
        brand, model = self.model_meta.get(ids.model.text, ("", ids.model.text))
        return "model", brand, model, tacs

    def selection_label(self, kind, brand, model, tacs):
        if kind == "tac":
            row = self.db.lookup(tacs[0])
            return "%s %s" % (row["brand"], row["model"]) if row else "Custom TAC %s" % tacs[0]
        return ("%s %s" % (brand, model)).strip()

    def update_tac_info(self):
        if not self.root:
            return
        ids = self.root.ids
        self.update_star()
        if self.mode == MODE_CUSTOM:
            tac = gen.normalize(ids.custom_tac.text)
            if len(tac) < 8:
                ids.tac_info.text = "Any 8-digit TAC works. Known ones are matched to a device."
            else:
                row = self.db.lookup(tac)
                ids.tac_info.text = ("Matches %s %s" % (row["brand"], row["model"]) if row
                                     else "Not in the database. Numbers will still be valid.")
        else:
            tacs = self.model_tacs.get(ids.model.text, [])
            if tacs:
                shown = "  ".join(tacs[:4]) + ("  +%d" % (len(tacs) - 4) if len(tacs) > 4 else "")
                ids.tac_info.text = "%s  ·  %s" % (plural(len(tacs), "TAC"), shown)
            elif ids.model.text == MORE:
                ids.tac_info.text = "Too many models to list. Type in Search to narrow it down."
            elif ids.model.text == TYPE_TO_SEARCH:
                ids.tac_info.text = "Search every brand at once, e.g. \"galaxy s9\" or \"iphone\"."
            else:
                ids.tac_info.text = "No matching models."
        self.save_settings()

    # ---- quantity (feature: shortcuts) ---------------------------------
    def set_qty(self, n):
        self.root.ids.qty.text = str(max(1, min(gen.MAX_BATCH, n)))

    def step_qty(self, delta):
        try:
            n = int(self.root.ids.qty.text or 0)
        except ValueError:
            n = 0
        self.set_qty(n + delta)

    def update_qty_chips(self):
        if not self.root:
            return
        qty = self.root.ids.qty.text.strip()
        for chip in self.root.ids.qty_chips.children:
            chip.active = chip.text == qty

    # ---- favourites -----------------------------------------------------
    def _selection_or_none(self):
        try:
            return self.current_selection()
        except ValueError:
            return None

    def update_star(self):
        sel = self._selection_or_none()
        active = bool(sel and self.user.find_favorite(*sel))
        ids = self.root.ids
        ids.star_model.active = active
        ids.star_custom.active = active

    def toggle_favorite(self):
        sel = self._selection_or_none()
        if not sel:
            self.snack("Choose a model or enter a TAC first", error=True)
            return
        fav = self.user.find_favorite(*sel)
        if fav:
            self.user.remove_favorite(fav)
            self.snack("Removed from favourites")
        else:
            self.user.add_favorite(*sel)
            self.snack("Added to favourites")
        self.refresh_favorites()
        self.update_star()

    def refresh_favorites(self):
        ids = self.root.ids
        box = ids.fav_box
        box.clear_widgets()
        favs = self.user.favorites()
        for fav in favs:
            text = fav["model"] if fav["kind"] == "model" else "TAC " + fav["tacs"][0]
            if len(text) > 26:
                text = text[:25] + "…"
            chip = Chip(text=text)
            chip.bind(on_release=lambda c, f=fav: self.apply_favorite(f))
            box.add_widget(chip)
        set_visible(ids.fav_strip, bool(favs))

    def apply_favorite(self, fav):
        ids = self.root.ids
        if fav["kind"] == "tac":
            select_segment(ids.mode_custom)
            ids.custom_tac.text = fav["tacs"][0]
        elif fav["brand"] == "Apple" and fav["model"] in self.esim:
            select_segment(ids.mode_esim)
            ids.model.text = fav["model"]
        else:
            select_segment(ids.mode_all)
            if fav["brand"] in ids.brand.values:
                ids.brand.text = fav["brand"]
            ids.search.text = fav["model"]
            self.search_trigger.cancel()
            self.refresh_models()
            label = fav["model"] if ids.brand.text != ANY_BRAND else "%s · %s" % (fav["brand"], fav["model"])
            if label in self.model_tacs:
                ids.model.text = label
            else:  # model no longer in the database: use the stored TACs
                self.model_tacs[label] = fav["tacs"]
                self.model_meta[label] = (fav["brand"], fav["model"])
                ids.model.text = label
        self.update_tac_info()

    # ---- generation -----------------------------------------------------
    def generate(self):
        ids = self.root.ids
        try:
            sel = self.current_selection()
            qty = int(ids.qty.text.strip() or "1")
            batch = gen.generate_batch(sel[3], qty)
        except ValueError as e:
            self.snack(str(e), error=True)
            return
        label = self.selection_label(*sel)
        rows = [(imei, tac, label) for imei, tac in batch]
        self.show_results(rows, label)
        self.user.add_history(label, rows)
        self.refresh_history()
        self.save_settings()

    def show_results(self, rows, subtitle):
        ids = self.root.ids
        self.results = rows
        width = max(2, len(str(len(rows))))
        ids.rv.data = [{"num": str(i).zfill(width), "markup": format_imei(imei), "imei": imei}
                       for i, (imei, _, _) in enumerate(rows, 1)]
        ids.rv.scroll_y = 1
        ids.empty.opacity = 0 if rows else 1
        self.results_title = plural(len(rows), "IMEI") if rows else "Results"
        self.results_subtitle = subtitle

    def clear_results(self):
        self.show_results([], "Tap a number to copy it")

    # ---- copy / export (feature: copy formats) -------------------------
    def current_format(self):
        return exporters.FORMAT_KEYS.get(self.root.ids.fmt.text, "lines")

    def copy_one(self, imei):
        Clipboard.copy(imei)
        self.snack("Copied %s" % imei)

    def copy_rows(self, rows):
        fmt = self.current_format()
        Clipboard.copy(exporters.render(rows, fmt))
        self.snack("Copied %s  ·  %s" % (plural(len(rows), "IMEI"), exporters.FORMAT_LABELS[fmt]))

    def copy_results(self):
        if not self.results:
            self.snack("Nothing to copy yet", error=True)
            return
        self.copy_rows(self.results)

    def export_text(self, text, ext, title):
        if platform == "android":
            try:
                share_text_android(text, title)
                return
            except Exception as e:  # fall back to saving a file
                print("share failed:", e)
        path = os.path.join(self.user_data_dir, "g2_%s.%s" % (time.strftime("%Y%m%d_%H%M%S"), ext))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self.snack("Saved to %s" % path)

    def export_results(self):
        if not self.results:
            self.snack("Nothing to export yet", error=True)
            return
        fmt = self.current_format()
        self.export_text(exporters.render(self.results, fmt), exporters.FORMAT_EXT[fmt], "Share IMEIs")

    # ---- history --------------------------------------------------------
    def refresh_history(self):
        if not self.root:
            return
        ids = self.root.ids
        items = self.user.history()
        ids.history_rv.data = [{
            "hid": h["id"],
            "title": "%s  ·  %s" % (plural(h["count"], "IMEI"), h["label"]),
            "meta": when(h["created"]),
        } for h in items]
        ids.history_empty.opacity = 0 if items else 1
        self.history_title = "History  ·  %d" % len(items) if items else "History"

    def open_history(self, hid):
        label, rows = self.user.history_rows(hid)
        if not rows:
            return
        self.show_results(rows, "%s  ·  from history" % label)
        select_segment(self.root.ids.tab_generate)

    def copy_history(self, hid):
        _, rows = self.user.history_rows(hid)
        if rows:
            self.copy_rows(rows)

    def delete_history(self, hid):
        self.user.delete_history(hid)
        self.refresh_history()
        self.snack("Batch deleted")

    def clear_history(self):
        if not self.user.history():
            return
        self.user.clear_history()
        self.refresh_history()
        self.snack("History cleared")

    # ---- check / lookup -------------------------------------------------
    def paste_into(self, field, single=False):
        text = Clipboard.paste() or ""
        if not text.strip():
            self.snack("Clipboard is empty", error=True)
            return
        field.text = text.strip() if single else text
        if single:
            self.check()

    def check(self):
        ids = self.root.ids
        text = gen.normalize(ids.check_input.text)
        details = ids.details
        details.clear_widgets()
        if not text:
            self.snack("Enter an IMEI or a TAC", error=True)
            return
        rows = []
        if len(text) == 8 and text.isdigit():
            status = "TAC lookup"
        else:
            ok, msg = gen.validate_imei(text)
            status = "[color=#%s]%s[/color]" % (GOLD if ok else DANGER, escape(msg))
            if len(text) == 15 and text.isdigit():
                rows.append(("IMEI", format_imei(text)))
        if len(text) >= 8 and text[:8].isdigit():
            rows.append(("TAC", "[font=Mono]%s[/font]" % text[:8]))
            row = self.db.lookup(text[:8])
            if row:
                rows.append(("Brand", escape(row["brand"])))
                rows.append(("Model", "[b]%s[/b]" % escape(row["model"])))
                if row["aka"]:
                    rows.append(("Also known as", escape(row["aka"].replace(",", ", "))))
                rows.append(("eSIM iPhone", "Yes" if row["esim"] else "No"))
            else:
                rows.append(("Device", "[color=#%s]Not in the database[/color]" % MUTED))
        ids.check_status.text = status
        for k, v in rows:
            details.add_widget(DetailRow(key=k, value=v))
        ids.check_card.opacity = 1

    # ---- bulk check -----------------------------------------------------
    def bulk_check(self):
        ids = self.root.ids
        rows, s = exporters.bulk_check(ids.bulk_input.text, self.db.lookup)
        self.bulk_rows = rows
        if not rows:
            self.snack("Paste some numbers first", error=True)
            return
        ids.bulk_rv.data = [{
            "markup": format_imei(r["imei"]) if r["ok"] else escape(r["input"]),
            "device": r["device"] or ("" if r["ok"] else r["message"]),
            "imei": r["imei"],
            "ok": r["ok"],
        } for r in rows]
        ids.bulk_rv.scroll_y = 1
        ids.bulk_empty.opacity = 0
        summary = "[color=#%s]%s valid[/color]   [color=#%s]%s invalid[/color]   [color=#%s]of %s[/color]" % (
            GOLD, "{:,}".format(s["valid"]), DANGER, "{:,}".format(s["invalid"]),
            MUTED, "{:,}".format(s["total"]))
        if s["truncated"]:
            summary += "  [color=#%s](first %s only)[/color]" % (MUTED, "{:,}".format(exporters.MAX_BULK))
        self.bulk_summary = summary

    def clear_bulk(self):
        ids = self.root.ids
        ids.bulk_input.text = ""
        ids.bulk_rv.data = []
        ids.bulk_empty.opacity = 1
        self.bulk_rows = []
        self.bulk_summary = "Results"

    def _copy_bulk(self, want_ok):
        picked = [(r["imei"] if want_ok else r["input"], r["imei"][:8], r["device"])
                  for r in self.bulk_rows if r["ok"] == want_ok]
        if not picked:
            self.snack("No %s numbers" % ("valid" if want_ok else "invalid"), error=True)
            return
        self.copy_rows(picked)

    def copy_bulk_valid(self):
        self._copy_bulk(True)

    def copy_bulk_invalid(self):
        self._copy_bulk(False)

    def export_bulk_report(self):
        if not self.bulk_rows:
            self.snack("Run a bulk check first", error=True)
            return
        self.export_text(exporters.bulk_report_csv(self.bulk_rows), "csv", "Share check report")

    # ---- feedback -------------------------------------------------------
    def snack(self, msg, error=False):
        s = self.root.ids.snack
        Animation.cancel_all(s)
        s.text = ("[color=#%s]%s[/color]" % (DANGER, escape(msg))) if error else escape(msg)
        s.opacity = 0
        (Animation(opacity=1, d=0.15) + Animation(d=2.2) + Animation(opacity=0, d=0.3)).start(s)


# ---- Android helpers (pyjnius ships with python-for-android) -------------
def share_text_android(text, title):
    from jnius import autoclass, cast
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    String = autoclass("java.lang.String")
    intent = Intent()
    intent.setAction(Intent.ACTION_SEND)
    intent.setType("text/plain")
    intent.putExtra(Intent.EXTRA_TEXT, cast("java.lang.CharSequence", String(text)))
    chooser = Intent.createChooser(intent, cast("java.lang.CharSequence", String(title)))
    PythonActivity.mActivity.startActivity(chooser)


def style_android_bars():
    """Paint the status and navigation bars black to match the app."""
    if platform != "android":
        return
    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        @run_on_ui_thread
        def _apply():
            Color = autoclass("android.graphics.Color")
            window = autoclass("org.kivy.android.PythonActivity").mActivity.getWindow()
            window.setStatusBarColor(Color.parseColor("#0B0B0C"))
            window.setNavigationBarColor(Color.parseColor("#0B0B0C"))

        _apply()
    except Exception as e:
        print("could not style system bars:", e)


# Kept for backwards compatibility with the previous class name.
IMEIGeneratorApp = G2ImeiApp

if __name__ == "__main__":
    G2ImeiApp().run()
