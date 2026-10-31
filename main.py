# main.py -- G2 IMEI Generator (Kivy front end).
import csv
import io
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
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.utils import platform

import imei_generator as gen
from tacdb import TacDB

APP_NAME = "G2 IMEI Generator"
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "assets", "fonts")

MODE_ESIM = "esim"
MODE_ALL = "all"
MODE_CUSTOM = "custom"
NO_MODELS = "No models"
MORE = "Refine search to see more"

# Palette (also mirrored in KV below).
GOLD = "D4AF37"
TEXT = "F2EDE3"
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


KV = """
#:import hex kivy.utils.get_color_from_hex
#:import dp kivy.metrics.dp
#:import NoTransition kivy.uix.screenmanager.NoTransition
#:set BG hex('#0B0B0C')
#:set SURFACE hex('#141416')
#:set SURFACE2 hex('#1C1C1F')
#:set BORDER hex('#2A2A2E')
#:set GOLD hex('#D4AF37')
#:set GOLD_DOWN hex('#B08F2A')
#:set GOLD_DIM hex('#D4AF3726')
#:set TEXT hex('#F2EDE3')
#:set MUTED hex('#8C877D')
#:set INK hex('#0B0B0C')

<Label>:
    font_name: "Body"

<Caption@Label>:
    font_size: "11sp"
    bold: True
    color: MUTED
    size_hint_y: None
    height: dp(18)
    text_size: self.size
    halign: "left"
    valign: "middle"

<Hint@Label>:
    font_size: "12sp"
    color: MUTED
    size_hint_y: None
    height: max(self.texture_size[1], dp(16))
    text_size: self.width, None
    halign: "left"

<Card@BoxLayout>:
    orientation: "vertical"
    padding: dp(16)
    spacing: dp(12)
    size_hint_y: None
    height: self.minimum_height
    canvas.before:
        Color:
            rgba: SURFACE
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(18)]
        Color:
            rgba: BORDER
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(18)
            width: 1

<GoldButton@ButtonBehavior+Label>:
    font_name: "Display"
    bold: True
    font_size: "16sp"
    color: INK
    canvas.before:
        Color:
            rgba: GOLD_DOWN if self.state == "down" else GOLD
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

<GhostButton@ButtonBehavior+Label>:
    font_size: "13sp"
    bold: True
    color: GOLD
    canvas.before:
        Color:
            rgba: GOLD_DIM if self.state == "down" else (0, 0, 0, 0)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]
        Color:
            rgba: GOLD[:3] + [0.45]
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(10)
            width: 1

<IconButton@ButtonBehavior+Label>:
    font_name: "Display"
    font_size: "22sp"
    color: GOLD
    size_hint_x: None
    width: dp(44)
    canvas.before:
        Color:
            rgba: GOLD_DIM if self.state == "down" else SURFACE2
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

<Segment@ToggleButtonBehavior+Label>:
    allow_no_selection: False
    font_size: "13sp"
    bold: True
    color: INK if self.state == "down" else MUTED
    canvas.before:
        Color:
            rgba: GOLD if self.state == "down" else (0, 0, 0, 0)
        RoundedRectangle:
            pos: self.x + dp(3), self.y + dp(3)
            size: self.width - dp(6), self.height - dp(6)
            radius: [dp(10)]

<SegmentBar@BoxLayout>:
    size_hint_y: None
    height: dp(46)
    canvas.before:
        Color:
            rgba: SURFACE2
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(13)]

<GField@TextInput>:
    multiline: False
    write_tab: False
    size_hint_y: None
    height: dp(48)
    font_name: "Body"
    font_size: "15sp"
    background_normal: ""
    background_active: ""
    background_color: 0, 0, 0, 0
    foreground_color: TEXT
    hint_text_color: MUTED
    cursor_color: GOLD
    selection_color: GOLD[:3] + [0.35]
    padding: dp(14), (self.height - self.line_height) / 2
    canvas.before:
        Color:
            rgba: SURFACE2
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: GOLD if self.focus else BORDER
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(12)
            width: 1.2 if self.focus else 1
        # TextInput draws its text with the last Color set in canvas.before,
        # so restore the text colour after drawing the border.
        Color:
            rgba: self.disabled_foreground_color if self.disabled else (self.hint_text_color if not self.text else self.foreground_color)

<GOption@SpinnerOption>:
    font_name: "Body"
    font_size: "15sp"
    background_normal: ""
    background_color: SURFACE2 if self.state == "normal" else GOLD_DOWN
    color: TEXT
    height: dp(46)
    padding: dp(14), 0
    text_size: self.size
    halign: "left"
    valign: "middle"
    shorten: True

<GSpinner@Spinner>:
    option_cls: "GOption"
    size_hint_y: None
    height: dp(48)
    font_size: "15sp"
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    color: TEXT
    padding: dp(14), 0, dp(40), 0
    text_size: self.size
    halign: "left"
    valign: "middle"
    shorten: True
    canvas.before:
        Color:
            rgba: SURFACE2
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: GOLD if self.is_open else BORDER
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(12)
            width: 1
    canvas.after:
        Color:
            rgba: GOLD
        Line:
            points: self.right - dp(24), self.center_y + dp(2), self.right - dp(19), self.center_y - dp(3), self.right - dp(14), self.center_y + dp(2)
            width: 1.4
            cap: "round"
            joint: "round"

<FieldGroup@BoxLayout>:
    orientation: "vertical"
    spacing: dp(6)
    size_hint_y: None
    height: dp(72)

<ImeiRow>:
    size_hint_y: None
    height: dp(44)
    padding: dp(4), 0
    canvas.before:
        Color:
            rgba: GOLD_DIM if self.state == "down" else (0, 0, 0, 0)
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: BORDER[:3] + [0.6]
        Rectangle:
            pos: self.x, self.y
            size: self.width, 1
    Label:
        text: root.num
        font_name: "Mono"
        font_size: "12sp"
        color: MUTED
        size_hint_x: None
        width: dp(40)
    Label:
        text: root.markup
        markup: True
        font_name: "Mono"
        font_size: "17sp"
        text_size: self.size
        halign: "left"
        valign: "middle"
    Label:
        text: "COPY"
        font_size: "10sp"
        bold: True
        color: MUTED
        size_hint_x: None
        width: dp(44)

<DetailRow>:
    size_hint_y: None
    height: max(dp(30), val.texture_size[1] + dp(8))
    Label:
        text: root.key
        font_size: "13sp"
        color: MUTED
        size_hint_x: None
        width: dp(104)
        text_size: self.size
        halign: "left"
        valign: "top"
        padding: 0, dp(4)
    Label:
        id: val
        text: root.value
        font_size: "15sp"
        color: TEXT
        text_size: self.width, None
        halign: "left"
        valign: "top"

<Root>:
    canvas.before:
        Color:
            rgba: BG
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: "vertical"
        padding: dp(18), dp(14), dp(18), dp(12)
        spacing: dp(14)

        # ---------------- header ----------------
        BoxLayout:
            size_hint_y: None
            height: dp(52)
            spacing: dp(12)
            Image:
                source: app.logo
                size_hint_x: None
                width: dp(44)
                fit_mode: "contain"
            BoxLayout:
                orientation: "vertical"
                Label:
                    markup: True
                    text: "[color=#D4AF37]G2[/color]  IMEI Generator"
                    font_name: "Display"
                    bold: True
                    font_size: "20sp"
                    color: TEXT
                    text_size: self.size
                    halign: "left"
                    valign: "bottom"
                Label:
                    text: app.db_summary
                    font_size: "12sp"
                    color: MUTED
                    text_size: self.size
                    halign: "left"
                    valign: "top"

        SegmentBar:
            Segment:
                id: tab_generate
                text: "Generate"
                group: "tab"
                state: "down"
                on_state: if self.state == "down": app.switch_tab("generate")
            Segment:
                text: "Check & Lookup"
                group: "tab"
                on_state: if self.state == "down": app.switch_tab("check")

        ScreenManager:
            id: sm
            transition: NoTransition()

            # ================ GENERATE ================
            Screen:
                name: "generate"
                BoxLayout:
                    orientation: "vertical"
                    spacing: dp(14)

                    Card:
                        Caption:
                            text: "SOURCE"
                        SegmentBar:
                            height: dp(42)
                            Segment:
                                id: mode_esim
                                text: "eSIM iPhone"
                                group: "mode"
                                state: "down"
                                on_state: if self.state == "down": app.set_mode("esim")
                            Segment:
                                text: "All brands"
                                group: "mode"
                                on_state: if self.state == "down": app.set_mode("all")
                            Segment:
                                text: "Custom TAC"
                                group: "mode"
                                on_state: if self.state == "down": app.set_mode("custom")

                        BoxLayout:
                            id: brand_row
                            size_hint_y: None
                            height: dp(72)
                            spacing: dp(10)
                            FieldGroup:
                                Caption:
                                    text: "BRAND"
                                GSpinner:
                                    id: brand
                                    on_text: app.refresh_models()
                            FieldGroup:
                                Caption:
                                    text: "SEARCH"
                                GField:
                                    id: search
                                    hint_text: "Model or TAC"
                                    on_text: app.search_trigger()

                        FieldGroup:
                            id: model_group
                            Caption:
                                text: "MODEL"
                            GSpinner:
                                id: model
                                on_text: app.update_tac_info()

                        FieldGroup:
                            id: custom_group
                            Caption:
                                text: "TAC  ·  FIRST 8 DIGITS"
                            GField:
                                id: custom_tac
                                hint_text: "e.g. 35104463"
                                input_filter: "int"
                                font_name: "Mono"
                                on_text: app.update_tac_info()

                        Hint:
                            id: tac_info

                        BoxLayout:
                            size_hint_y: None
                            height: dp(50)
                            spacing: dp(8)
                            IconButton:
                                text: "\u2212"
                                on_release: app.step_qty(-1)
                            GField:
                                id: qty
                                text: "10"
                                input_filter: "int"
                                font_name: "Mono"
                                halign: "center"
                                size_hint_x: None
                                width: dp(64)
                                height: dp(50)
                                padding: dp(6), (self.height - self.line_height) / 2
                            IconButton:
                                text: "+"
                                on_release: app.step_qty(1)
                            Widget:
                                size_hint_x: None
                                width: dp(4)
                            GoldButton:
                                text: "Generate"
                                on_release: app.generate()

                    # ---------------- results ----------------
                    BoxLayout:
                        orientation: "vertical"
                        padding: dp(14), dp(12), dp(14), dp(6)
                        spacing: dp(6)
                        canvas.before:
                            Color:
                                rgba: SURFACE
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [dp(18)]
                            Color:
                                rgba: BORDER
                            Line:
                                rounded_rectangle: self.x, self.y, self.width, self.height, dp(18)
                                width: 1
                        BoxLayout:
                            size_hint_y: None
                            height: dp(40)
                            spacing: dp(8)
                            BoxLayout:
                                orientation: "vertical"
                                Label:
                                    text: app.results_title
                                    font_name: "Display"
                                    bold: True
                                    font_size: "15sp"
                                    color: TEXT
                                    text_size: self.size
                                    halign: "left"
                                    valign: "middle"
                                    shorten: True
                                Label:
                                    text: app.results_subtitle
                                    font_size: "11sp"
                                    color: MUTED
                                    text_size: self.size
                                    halign: "left"
                                    valign: "middle"
                                    shorten: True
                                    shorten_from: "right"
                            GhostButton:
                                text: "Copy all"
                                size_hint_x: None
                                width: dp(76)
                                on_release: app.copy_results()
                            GhostButton:
                                text: app.export_label
                                size_hint_x: None
                                width: dp(70)
                                on_release: app.export_results()
                            GhostButton:
                                text: "Clear"
                                size_hint_x: None
                                width: dp(56)
                                on_release: app.clear_results()
                        FloatLayout:
                            RecycleView:
                                id: rv
                                pos_hint: {"x": 0, "y": 0}
                                size_hint: 1, 1
                                viewclass: "ImeiRow"
                                bar_width: dp(3)
                                bar_color: GOLD[:3] + [0.7]
                                bar_inactive_color: GOLD[:3] + [0.2]
                                scroll_type: ["bars", "content"]
                                RecycleBoxLayout:
                                    default_size: None, dp(44)
                                    default_size_hint: 1, None
                                    size_hint_y: None
                                    height: self.minimum_height
                                    orientation: "vertical"
                            Label:
                                id: empty
                                pos_hint: {"x": 0, "y": 0}
                                size_hint: 1, 1
                                markup: True
                                text: app.empty_text
                                font_size: "14sp"
                                color: MUTED
                                text_size: self.width * 0.8, None
                                halign: "center"
                                valign: "middle"

            # ================ CHECK ================
            Screen:
                name: "check"
                BoxLayout:
                    orientation: "vertical"
                    spacing: dp(14)
                    Card:
                        Caption:
                            text: "IMEI OR TAC"
                        GField:
                            id: check_input
                            hint_text: "15-digit IMEI or 8-digit TAC"
                            input_type: "number"
                            font_name: "Mono"
                            on_text_validate: app.check()
                        GoldButton:
                            text: "Check"
                            size_hint_y: None
                            height: dp(50)
                            on_release: app.check()
                    Card:
                        id: check_card
                        opacity: 0
                        Label:
                            id: check_status
                            markup: True
                            font_name: "Display"
                            bold: True
                            font_size: "17sp"
                            color: TEXT
                            size_hint_y: None
                            height: max(self.texture_size[1], dp(24))
                            text_size: self.width, None
                            halign: "left"
                        BoxLayout:
                            id: details
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                    Widget:
                    Hint:
                        text: app.db_info
                    Hint:
                        text: "For testing only. Do not use generated numbers on a live network or to impersonate a real device."

    # ---------------- snackbar ----------------
    Label:
        id: snack
        opacity: 0
        size_hint: None, None
        size: min(root.width - dp(36), self.texture_size[0] + dp(36)), dp(46)
        pos: (root.width - self.width) / 2, dp(22)
        font_size: "14sp"
        color: TEXT
        shorten: True
        text_size: self.width - dp(24), None
        halign: "center"
        canvas.before:
            Color:
                rgba: SURFACE2
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(14)]
            Color:
                rgba: GOLD[:3] + [0.6]
            Line:
                rounded_rectangle: self.x, self.y, self.width, self.height, dp(14)
                width: 1
"""


class Root(FloatLayout):
    pass


class ImeiRow(ButtonBehavior, BoxLayout):
    num = StringProperty("")
    markup = StringProperty("")
    imei = StringProperty("")

    def on_release(self):
        App.get_running_app().copy_one(self.imei)


class DetailRow(BoxLayout):
    key = StringProperty("")
    value = StringProperty("")


def set_visible(widget, visible):
    """Hide a widget without leaving a gap or letting it receive touches."""
    if not hasattr(widget, "_full_height"):
        widget._full_height = widget.height
    widget.height = widget._full_height if visible else 0
    widget.opacity = 1 if visible else 0
    widget.disabled = not visible


def escape(text):
    return str(text).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def format_imei(imei):
    """TAC in gold, serial in ivory, check digit muted -- shows the structure."""
    return "[color=#%s]%s[/color] %s [color=#%s]%s[/color]" % (
        GOLD, imei[:8], imei[8:14], MUTED, imei[14:])


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


class G2ImeiApp(App):
    db_info = StringProperty("")
    db_summary = StringProperty("")
    results_title = StringProperty("Results")
    results_subtitle = StringProperty("Tap a number to copy it")
    empty_text = StringProperty("")
    export_label = StringProperty("Share" if platform == "android" else "Save")
    logo = StringProperty(os.path.join(HERE, "assets", "logo.png"))
    mode = StringProperty(MODE_ESIM)
    qty_max = NumericProperty(gen.MAX_BATCH)
    busy = BooleanProperty(False)

    def build(self):
        self.title = APP_NAME
        self.icon = os.path.join(HERE, "assets", "icon.png")
        register_fonts()
        Window.clearcolor = (11 / 255, 11 / 255, 12 / 255, 1)
        Window.softinput_mode = "below_target"
        style_android_bars()

        self.db = TacDB()
        self.results = []  # [(imei, tac, label)]
        self.esim = dict(self.db.esim_models())
        self.model_tacs = {}
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

        Builder.load_string(KV)
        root = Root()
        self.root = root
        self.search_trigger = Clock.create_trigger(lambda dt: self.refresh_models(), 0.3)
        ids = root.ids
        ids.brand.values = self.db.brands()
        ids.brand.text = "Apple" if "Apple" in ids.brand.values else (ids.brand.values or [""])[0]
        self.set_mode(MODE_ESIM)
        return root

    # ---- navigation -----------------------------------------------------
    def switch_tab(self, name):
        if self.root:
            self.root.ids.sm.current = name

    # ---- source / model selection --------------------------------------
    def set_mode(self, mode):
        self.mode = mode
        if not self.root:
            return
        ids = self.root.ids
        set_visible(ids.brand_row, mode == MODE_ALL)
        set_visible(ids.model_group, mode != MODE_CUSTOM)
        set_visible(ids.custom_group, mode == MODE_CUSTOM)
        self.refresh_models()

    def refresh_models(self):
        if not self.root:
            return
        ids = self.root.ids
        if self.mode == MODE_ESIM:
            self.model_tacs, truncated = dict(self.esim), False
        elif self.mode == MODE_ALL:
            rows, truncated = self.db.models(ids.brand.text, ids.search.text.strip())
            self.model_tacs = dict(rows)
        else:
            self.update_tac_info()
            return
        names = list(self.model_tacs)
        if truncated:
            names.append(MORE)
        ids.model.values = names
        if ids.model.text not in self.model_tacs:
            ids.model.text = names[0] if self.model_tacs else NO_MODELS
        self.update_tac_info()

    def current_tacs(self):
        """Return (tacs, label) for the current selection or raise ValueError."""
        ids = self.root.ids
        if self.mode == MODE_CUSTOM:
            tac = gen.normalize(ids.custom_tac.text)
            if not gen.is_valid_tac(tac):
                raise ValueError("Enter a valid 8-digit TAC")
            row = self.db.lookup(tac)
            return [tac], ("%s %s" % (row["brand"], row["model"]) if row else "Custom TAC %s" % tac)
        if ids.model.text == MORE:
            raise ValueError("Type in Search to narrow the model list")
        tacs = self.model_tacs.get(ids.model.text)
        if not tacs:
            raise ValueError("Select a model first")
        brand = "Apple" if self.mode == MODE_ESIM else ids.brand.text
        return tacs, "%s %s" % (brand, ids.model.text)

    def update_tac_info(self):
        ids = self.root.ids
        if self.mode == MODE_CUSTOM:
            tac = gen.normalize(ids.custom_tac.text)
            if len(tac) < 8:
                ids.tac_info.text = "Any 8-digit TAC works. Known ones are matched to a device."
                return
            row = self.db.lookup(tac)
            ids.tac_info.text = ("Matches %s %s" % (row["brand"], row["model"]) if row
                                 else "Not in the database. Numbers will still be valid.")
            return
        tacs = self.model_tacs.get(ids.model.text, [])
        if not tacs:
            ids.tac_info.text = "No matching models." if ids.model.text != MORE else \
                "Too many models to list. Type in Search to narrow it down."
            return
        shown = "  ".join(tacs[:4]) + ("  +%d" % (len(tacs) - 4) if len(tacs) > 4 else "")
        ids.tac_info.text = "%s  ·  %s" % (plural(len(tacs), "TAC"), shown)

    def step_qty(self, delta):
        ids = self.root.ids
        try:
            n = int(ids.qty.text or 0)
        except ValueError:
            n = 0
        ids.qty.text = str(max(1, min(gen.MAX_BATCH, n + delta)))

    # ---- generation -----------------------------------------------------
    def generate(self):
        ids = self.root.ids
        try:
            tacs, label = self.current_tacs()
            qty = int(ids.qty.text.strip() or "1")
            batch = gen.generate_batch(tacs, qty)
        except ValueError as e:
            self.snack(str(e), error=True)
            return
        self.results = [(imei, tac, label) for imei, tac in batch]
        width = len(str(qty))
        ids.rv.data = [{"num": str(i).zfill(max(2, width)), "markup": format_imei(imei), "imei": imei}
                       for i, (imei, _, _) in enumerate(self.results, 1)]
        ids.rv.scroll_y = 1
        ids.empty.opacity = 0
        self.results_title = plural(qty, "IMEI")
        self.results_subtitle = label

    def clear_results(self):
        self.results = []
        self.root.ids.rv.data = []
        self.root.ids.empty.opacity = 1
        self.results_title = "Results"
        self.results_subtitle = "Tap a number to copy it"

    def results_text(self):
        return "\n".join(imei for imei, _, _ in self.results)

    def results_csv(self):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["imei", "tac", "model"])
        w.writerows(self.results)
        return buf.getvalue()

    def copy_one(self, imei):
        Clipboard.copy(imei)
        self.snack("Copied %s" % imei)

    def copy_results(self):
        if not self.results:
            self.snack("Nothing to copy yet", error=True)
            return
        Clipboard.copy(self.results_text())
        self.snack("Copied %s" % plural(len(self.results), "IMEI"))

    def export_results(self):
        if not self.results:
            self.snack("Nothing to export yet", error=True)
            return
        if platform == "android":
            try:
                share_text_android(self.results_text(), "Share IMEIs")
                return
            except Exception as e:  # fall back to saving a file
                print("share failed:", e)
        path = os.path.join(self.user_data_dir, "imeis_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(self.results_csv())
        self.snack("Saved to %s" % path)

    def snack(self, msg, error=False):
        s = self.root.ids.snack
        Animation.cancel_all(s)
        s.text = ("[color=#%s]%s[/color]" % (DANGER, escape(msg))) if error else escape(msg)
        s.markup = True
        s.opacity = 0
        anim = Animation(opacity=1, d=0.15) + Animation(d=2.2) + Animation(opacity=0, d=0.3)
        anim.start(s)

    # ---- check / lookup -------------------------------------------------
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
            r = DetailRow(key=k, value=v)
            r.ids.val.markup = True
            details.add_widget(r)
        ids.check_card.opacity = 1


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
