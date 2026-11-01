# main.py -- G2 IMEI Generator (Kivy front end). Layout lives in g2.kv.
import math
import os
import threading
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
from kivy.factory import Factory
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import platform

import dbupdate
import exporters
import imei_generator as gen
from tacdb import DEFAULT_PATH as BUNDLED_DB, TacDB
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
AMBER = "E0A33A"


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
    verdict = StringProperty("invalid")

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


class Splash(FloatLayout):
    """Boot intro overlay; blocks touches until it is removed."""

    def on_touch_down(self, touch):
        return True

    def on_touch_move(self, touch):
        return True

    def on_touch_up(self, touch):
        return True


class CheckMark(Widget):
    """Gold tick that draws itself as ``progress`` goes 0 -> 1."""
    progress = NumericProperty(0)
    points = ListProperty([])

    def on_progress(self, *_):
        self._build()

    def on_size(self, *_):
        self._build()

    def on_pos(self, *_):
        self._build()

    def _build(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        a = (x + w * 0.28, y + h * 0.52)
        b = (x + w * 0.44, y + h * 0.36)
        c = (x + w * 0.73, y + h * 0.66)
        p = max(0.0, min(1.0, self.progress))
        if p <= 0:
            self.points = []
        elif p < 0.4:  # first stroke (short leg)
            t = p / 0.4
            self.points = [a[0], a[1], a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
        else:          # second stroke (long leg)
            t = (p - 0.4) / 0.6
            self.points = [a[0], a[1], b[0], b[1],
                           b[0] + (c[0] - b[0]) * t, b[1] + (c[1] - b[1]) * t]


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
class Collapsible(BoxLayout):
    """A row that can be hidden without leaving a gap.

    Hidden rows collapse to zero height, but their children keep their own
    fixed heights and overflow onto the widgets above. They must therefore
    ignore touches entirely: a *disabled* widget would swallow every tap that
    lands on it, which is what blocked the source buttons after choosing
    Custom TAC.
    """
    hidden = BooleanProperty(False)

    def on_touch_down(self, touch):
        return False if self.hidden else super().on_touch_down(touch)

    def on_touch_move(self, touch):
        return False if self.hidden else super().on_touch_move(touch)

    def on_touch_up(self, touch):
        return False if self.hidden else super().on_touch_up(touch)


def set_visible(widget, visible):
    """Show/hide a Collapsible row without leaving a gap."""
    if not hasattr(widget, "_full_height"):
        widget._full_height = widget.height
    widget.hidden = not visible
    widget.height = widget._full_height if visible else 0
    widget.opacity = 1 if visible else 0
    if not visible:
        for w in widget.walk(restrict=True):
            if getattr(w, "focus", False):
                w.focus = False  # close the keyboard of a hidden field


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
    net_state = StringProperty("offline")   # checking | updating | online | offline
    update_status = StringProperty("")

    # Animation state (driven by kivy.animation.Animation)
    content_opacity = NumericProperty(0)
    content_shift = NumericProperty(dp(28))
    splash_angle = NumericProperty(0)
    splash_logo_scale = NumericProperty(1)
    splash_text_opacity = NumericProperty(0)
    splash_status = StringProperty("Loading TAC database")
    bar_opacity = NumericProperty(0)
    update_progress = NumericProperty(-1)    # -1 = indeterminate
    shimmer = NumericProperty(0)
    dot_alpha = NumericProperty(1)
    shown_count = NumericProperty(0)
    banner_offset = NumericProperty(dp(24))
    banner_opacity = NumericProperty(0)
    banner_check = NumericProperty(0)
    banner_title = StringProperty("")
    banner_sub = StringProperty("")

    # ---- lifecycle ------------------------------------------------------
    def build(self):
        self.title = APP_NAME
        self.icon = os.path.join(HERE, "assets", "icon.png")
        register_fonts()
        Window.clearcolor = (11 / 255, 11 / 255, 12 / 255, 1)
        # Default mode: the keyboard overlays the bottom of the screen. Every
        # text field sits in the top half, and unlike Kivy's "pan" /
        # "below_target" modes nothing is shifted, so taps always land where
        # they look like they land.
        Window.softinput_mode = ""
        Window.bind(on_keyboard=self.on_key)
        style_android_bars()

        self.user = UserData(self.user_data_dir)
        path, _ = dbupdate.choose_database(BUNDLED_DB, self.user_data_dir)
        self.db = TacDB(path)
        if self.db.error and path != BUNDLED_DB:  # saved copy unusable: fall back
            self.db = TacDB(BUNDLED_DB)
        self.results = []        # [(imei, tac, label)]
        self.bulk_rows = []
        self.esim = dict(self.db.esim_models())
        self.model_tacs = {}     # display label -> [tacs]
        self.model_meta = {}     # display label -> (brand, model)
        self._restoring = True
        self.empty_text = "No numbers yet.\nPick a source and tap [color=#%s]Generate[/color]." % GOLD

        self.shown_count = self.db.count()
        self.refresh_db_labels()

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
        Clock.schedule_once(lambda dt: self.play_intro(), 0)
        return root

    # ---- boot intro -------------------------------------------------------
    def play_intro(self):
        """Gold ring draws around the logo, title rises in, then the screen
        glides up into place. ~1.6 s; the database is already open."""
        count = self.db.count()
        ring = Animation(splash_angle=360, d=0.95, t="in_out_cubic")
        breathe = (Animation(splash_logo_scale=1.06, d=0.45, t="out_quad")
                   + Animation(splash_logo_scale=1.0, d=0.5, t="in_out_quad"))
        text_in = Animation(d=0.15) + Animation(splash_text_opacity=1, d=0.5, t="out_cubic")

        def ready(*_):
            self.splash_status = "{:,} devices ready".format(count)
            Clock.schedule_once(self._reveal, 0.35)

        ring.bind(on_complete=ready)
        ring.start(self)
        breathe.start(self)
        text_in.start(self)
        # Safety net: the intro blocks touches, so never let it outlive 4 s.
        Clock.schedule_once(self._force_reveal, 4.0)

    def _force_reveal(self, *_):
        splash = self.root.ids.splash
        if splash.parent:
            Animation.cancel_all(self)
            splash.parent.remove_widget(splash)
            self.content_opacity, self.content_shift = 1, 0
            self.start_db_update()

    def _reveal(self, *_):
        splash = self.root.ids.splash
        Animation(opacity=0, d=0.38, t="out_quad").start(splash)
        reveal = Animation(content_opacity=1, content_shift=0, d=0.55, t="out_cubic")

        def done(*_):
            if splash.parent:
                splash.parent.remove_widget(splash)
                self.start_db_update()

        reveal.bind(on_complete=done)
        reveal.start(self)

    # ---- update animations --------------------------------------------------
    def _busy_animations(self, on):
        Animation.cancel_all(self, "shimmer", "dot_alpha", "bar_opacity")
        if on:
            self.update_progress = -1
            self.shimmer = 0
            sweep = Animation(shimmer=1, d=1.05, t="in_out_sine") + Animation(shimmer=0, d=0)
            sweep.repeat = True
            sweep.start(self)
            pulse = Animation(dot_alpha=0.25, d=0.55, t="in_out_sine") + \
                Animation(dot_alpha=1, d=0.55, t="in_out_sine")
            pulse.repeat = True
            pulse.start(self)
            Animation(bar_opacity=1, d=0.2).start(self)
        else:
            self.dot_alpha = 1
            Animation(bar_opacity=0, d=0.35, t="out_quad").start(self)

    def _set_download_progress(self, frac):
        if self.net_state != "updating":
            self.net_state = "updating"
            self.update_status = "Downloading the new database…"
            Animation.cancel_all(self, "shimmer")
            self.refresh_db_labels()
        Animation.cancel_all(self, "update_progress")
        Animation(update_progress=frac, d=0.18, t="out_quad").start(self)

    def show_banner(self, title, sub):
        Animation.cancel_all(self, "banner_offset", "banner_opacity", "banner_check")
        self.banner_title, self.banner_sub = title, sub
        self.banner_offset, self.banner_opacity, self.banner_check = dp(24), 0, 0
        slide_in = Animation(banner_offset=0, banner_opacity=1, d=0.45, t="out_back")
        tick = Animation(d=0.2) + Animation(banner_check=1, d=0.5, t="out_cubic")
        slide_out = (Animation(d=3.2)
                     + Animation(banner_offset=dp(24), banner_opacity=0, d=0.35, t="in_quad"))
        slide_in.start(self)
        tick.start(self)
        slide_out.start(self)

    def on_shown_count(self, *_):
        if getattr(self, "db", None) is not None and self.root:
            self.refresh_db_labels()

    def on_pause(self):
        self.save_settings()
        return True

    def on_resume(self):
        # Phones keep apps alive for days: re-check if the last check is old.
        last = self.user.get("last_update_check", 0) or 0
        if time.time() - last > 6 * 3600:
            self.start_db_update()

    def on_stop(self):
        self.save_settings()

    # ---- exit / back key -------------------------------------------------
    def confirm_exit(self):
        Factory.ExitDialog().open()

    def exit_app(self):
        self.save_settings()
        self.stop()

    def on_key(self, window, key, *args):
        """Android back button (Esc on desktop): step back, then ask to exit."""
        if key != 27:
            return False
        for w in list(window.children):
            if isinstance(w, Factory.ModalView):  # close an open dialog first
                w.dismiss()
                return True
        ids = self.root.ids
        if ids.brand.is_open or ids.model.is_open or ids.fmt.is_open:
            return False  # let the dropdown close itself
        if ids.sm.current != "generate":
            select_segment(ids.tab_generate)
        else:
            self.confirm_exit()
        return True  # never let Kivy close the app without asking

    # ---- TAC database: labels and online updates ------------------------
    def refresh_db_labels(self):
        meta = self._db_meta = getattr(self, "_db_meta", None) or self.db.meta()
        count = self.db.count()
        built = meta.get("built", "")
        state = {"online": "Online", "checking": "Checking for updates",
                 "updating": "Updating"}.get(self.net_state, "Offline")
        self.db_summary = "{}  ·  {:,} devices{}".format(
            state, int(round(self.shown_count)) or count, ("  ·  " + built) if built else "")
        info = "Database: {:,} TACs, {} eSIM iPhone TACs. Source: {}.".format(
            count, sum(len(t) for t in self.esim.values()), meta.get("sources", "?"))
        if built:
            info += " Built %s." % built
        info += " " + ("Downloaded update." if self.db.path != BUNDLED_DB else "Bundled with the app.")
        if meta.get("license"):
            info += "\n" + meta["license"] + "."
        if self.db.error:
            info += "\nDatabase not loaded (%s), using built-in list." % self.db.error
        self.db_info = info

    def start_db_update(self, manual=False):
        if self.net_state in ("checking", "updating"):
            return
        self.net_state = "checking"
        self.update_status = "Checking for database updates…"
        self.refresh_db_labels()
        self._busy_animations(True)
        current = dbupdate.read_meta(self.db.path) or {}
        user_dir = self.user_data_dir

        def progress(frac):  # called from the worker thread
            Clock.schedule_once(lambda dt: self._set_download_progress(frac))

        def work():
            result = dbupdate.check_and_update(current, user_dir, progress=progress)
            Clock.schedule_once(lambda dt: self.finish_db_update(result, manual))

        threading.Thread(target=work, name="tac-db-update", daemon=True).start()

    def finish_db_update(self, result, manual):
        self._busy_animations(False)
        old_count = self.db.count()
        if result.status == "updated":
            new_db = TacDB(result.path)
            if new_db.error:
                result = dbupdate.UpdateResult("error", "Update could not be opened")
            else:
                self.db = new_db
                self._db_meta = None
                self.esim = dict(self.db.esim_models())
                self.root.ids.brand.values = [ANY_BRAND] + self.db.brands()
                self.refresh_models()
        self.net_state = "online" if result.status in ("updated", "current", "unavailable") else "offline"
        built = self.db.meta().get("built", "?")
        self.update_status = {
            "updated": "Updated to the %s database." % built,
            "current": "Up to date (database from %s)." % built,
            "offline": "Offline: using saved database from %s." % built,
            "unavailable": "Online, no update published: using database from %s." % built,
        }.get(result.status, "Update failed: using saved database from %s." % built)
        self.refresh_db_labels()
        self.user.set_many({"last_update_check": time.time(), "last_update_status": result.status})
        if result.status == "updated":
            new_count = self.db.count()
            Animation.cancel_all(self, "shown_count")
            self.shown_count = old_count
            Animation(shown_count=new_count, d=1.4, t="out_cubic").start(self)
            diff = new_count - old_count
            change = ("{:+,} device{}".format(diff, "" if abs(diff) == 1 else "s") if diff
                      else "Corrections to existing devices")
            self.show_banner("Database updated",
                             "{}  ·  {:,} total  ·  {}".format(change, new_count, built))
        elif manual:
            self.snack(self.update_status, error=result.status == "error")

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
                if row:
                    ids.tac_info.text = "Matches %s %s" % (row["brand"], row["model"])
                elif tac[:2] not in gen.REPORTING_BODIES:
                    ids.tac_info.text = ("Not in the database, and %s is not a known allocation "
                                         "prefix. Numbers will be well-formed but unrealistic." % tac[:2])
                else:
                    ids.tac_info.text = "Not in the database. Numbers will still be well-formed."
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
            row = self.db.lookup(text)
            status = ("TAC lookup" if row else
                      "[color=#%s]TAC not in the database[/color]" % AMBER)
            info = {"device": row, "issuer": gen.REPORTING_BODIES.get(text[:2], ""), "notes": []}
        else:
            info = gen.inspect_imei(text, self.db.lookup)
            colour = {gen.STATUS_KNOWN_DEVICE: GOLD, gen.STATUS_UNKNOWN_DEVICE: AMBER,
                      gen.STATUS_TEST: AMBER}.get(info["status"], DANGER)
            status = "[color=#%s]%s[/color]" % (colour, escape(info["headline"]))
            if len(text) == 15 and text.isdigit():
                rows.append(("IMEI", format_imei(text)))
        if len(text) >= 8 and text[:8].isdigit():
            rows.append(("TAC", "[font=Mono]%s[/font]" % text[:8]))
            rows.append(("Allocated by", escape(info["issuer"]) if info["issuer"] else
                         "[color=#%s]Unrecognised prefix %s[/color]" % (AMBER, text[:2])))
            row = info["device"]
            if row:
                rows.append(("Brand", escape(row["brand"])))
                rows.append(("Model", "[b]%s[/b]" % escape(row["model"])))
                if row["aka"]:
                    rows.append(("Also known as", escape(row["aka"].replace(",", ", "))))
                rows.append(("eSIM iPhone", "Yes" if row["esim"] else "No"))
            else:
                rows.append(("Device", "[color=#%s]Not in the database[/color]" % MUTED))
        for note in info.get("notes", []):
            rows.append(("Note", "[color=#%s]%s[/color]" % (AMBER, escape(note))))
        if len(text) == 15 and info.get("ok"):
            rows.append(("Good to know", "[color=#%s]A valid number is well-formed. Only the network "
                         "operator can confirm it belongs to a real phone.[/color]" % MUTED))
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
            "device": r["device"] or r["message"],
            "imei": r["imei"],
            "verdict": r["verdict"],
        } for r in rows]
        ids.bulk_rv.scroll_y = 1
        ids.bulk_empty.opacity = 0
        summary = ("[color=#%s]%s valid[/color]  [color=#%s]%s unknown[/color]  "
                   "[color=#%s]%s invalid[/color]  [color=#%s]of %s[/color]") % (
            GOLD, "{:,}".format(s["valid"]), AMBER, "{:,}".format(s["unknown"]),
            DANGER, "{:,}".format(s["invalid"]), MUTED, "{:,}".format(s["total"]))
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
