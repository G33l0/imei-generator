# main.py -- Kivy front end for the IMEI test-number generator.
import csv
import io
import os
import time

import kivy
kivy.require("2.1.0")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.utils import platform

import imei_generator as gen
from tacdb import TacDB

MODE_ESIM = "eSIM iPhones"
MODE_ALL = "All brands (database)"
MODE_CUSTOM = "Custom TAC"
NO_MODELS = "(no models)"

KV = """
#:import dp kivy.metrics.dp

<Row@BoxLayout>:
    size_hint_y: None
    height: dp(48)
    spacing: dp(8)

<SmallLabel@Label>:
    font_size: "13sp"
    color: 0.75, 0.75, 0.75, 1
    size_hint_y: None
    height: self.texture_size[1] + dp(6)
    text_size: self.width, None
    halign: "left"

<Field@TextInput>:
    multiline: False
    write_tab: False
    size_hint_y: None
    height: dp(48)
    font_size: "16sp"
    padding: dp(10), (self.height - self.line_height) / 2

<Root>:
    do_default_tab: False
    tab_width: self.width / 2
    tab_height: dp(44)

    TabbedPanelItem:
        text: "Generate"
        BoxLayout:
            orientation: "vertical"
            padding: dp(14)
            spacing: dp(8)

            Row:
                Label:
                    text: "Source"
                    size_hint_x: 0.3
                Spinner:
                    id: mode
                    size_hint_x: 0.7
                    values: app.modes
                    text: app.modes[0]
                    on_text: app.on_mode(self.text)
            Row:
                id: brand_row
                Label:
                    text: "Brand"
                    size_hint_x: 0.3
                Spinner:
                    id: brand
                    size_hint_x: 0.7
                    on_text: app.refresh_models()
            Field:
                id: search
                hint_text: "Search model / TAC prefix"
                on_text: app.search_trigger()
            Row:
                id: model_row
                Label:
                    text: "Model"
                    size_hint_x: 0.3
                Spinner:
                    id: model
                    size_hint_x: 0.7
                    shorten: True
                    text_size: self.width - dp(12), None
                    halign: "center"
                    on_text: app.update_tac_info()
            Field:
                id: custom_tac
                hint_text: "Enter 8-digit TAC"
                input_filter: "int"
                on_text: app.update_tac_info()
            SmallLabel:
                id: tac_info
            Row:
                Label:
                    text: "Quantity"
                    size_hint_x: 0.3
                Field:
                    id: qty
                    text: "1"
                    input_filter: "int"
                    size_hint_x: 0.25
                    halign: "center"
                Button:
                    text: "Generate"
                    size_hint_x: 0.45
                    bold: True
                    background_normal: ""
                    background_color: 0.18, 0.62, 0.3, 1
                    on_release: app.generate()
            Row:
                Button:
                    text: "Copy"
                    on_release: app.copy_results()
                Button:
                    text: app.export_label
                    on_release: app.export_results()
                Button:
                    text: "Clear"
                    on_release: app.clear_results()
            ScrollView:
                bar_width: dp(6)
                Label:
                    id: results
                    markup: True
                    font_name: "RobotoMono-Regular"
                    font_size: "16sp"
                    size_hint_y: None
                    height: max(self.texture_size[1], dp(40))
                    text_size: self.width, None
                    halign: "center"
                    valign: "top"
                    text: "Press Generate to create test IMEIs."

    TabbedPanelItem:
        text: "Check / Lookup"
        BoxLayout:
            orientation: "vertical"
            padding: dp(14)
            spacing: dp(10)
            Field:
                id: check_input
                hint_text: "IMEI (15 digits) or TAC (8 digits)"
                input_type: "number"
                on_text_validate: app.check()
            Button:
                text: "Check"
                size_hint_y: None
                height: dp(48)
                on_release: app.check()
            Label:
                id: check_result
                markup: True
                font_size: "16sp"
                size_hint_y: None
                height: self.texture_size[1] + dp(10)
                text_size: self.width, None
                halign: "left"
            Widget:
            SmallLabel:
                text: app.db_info
            SmallLabel:
                text: "Generated numbers are for testing only. Do not use them on a live network or to impersonate a real device."
"""


class Root(TabbedPanel):
    pass


def set_visible(widget, visible):
    """Hide a widget without leaving a gap or letting it receive touches."""
    if not hasattr(widget, "_full_height"):
        widget._full_height = widget.height
    widget.height = widget._full_height if visible else 0
    widget.opacity = 1 if visible else 0
    widget.disabled = not visible


class IMEIGeneratorApp(App):
    db_info = StringProperty("")
    export_label = StringProperty("Share" if platform == "android" else "Save CSV")
    modes = [MODE_ESIM, MODE_ALL, MODE_CUSTOM]

    def build(self):
        self.title = "eSIM IMEI Generator"
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        Window.softinput_mode = "below_target"  # keep inputs above the keyboard
        self.db = TacDB()
        self.results = []  # [(imei, tac, label)]
        self.esim = dict(self.db.esim_models())
        self.model_tacs = {}

        meta = self.db.meta()
        info = "TAC database: %d TACs, %d eSIM iPhone TACs. Sources: %s." % (
            self.db.count(), sum(len(t) for t in self.esim.values()), meta.get("sources", "?"))
        if meta.get("built"):
            info += " Built %s." % meta["built"]
        if meta.get("license"):
            info += "\n" + meta["license"] + "."
        if self.db.error:
            info += "\n[database not loaded: %s]" % self.db.error
        self.db_info = info

        self.root = Builder.load_string(KV) or Root()
        self.search_trigger = Clock.create_trigger(lambda dt: self.refresh_models(), 0.35)
        ids = self.root.ids
        ids.brand.values = self.db.brands()
        ids.brand.text = "Apple" if "Apple" in ids.brand.values else (ids.brand.values or [""])[0]
        self.on_mode(ids.mode.text)
        return self.root

    # ---- source / model selection --------------------------------------
    def on_mode(self, mode):
        ids = self.root.ids
        set_visible(ids.brand_row, mode == MODE_ALL)
        set_visible(ids.search, mode == MODE_ALL)
        set_visible(ids.model_row, mode != MODE_CUSTOM)
        set_visible(ids.custom_tac, mode == MODE_CUSTOM)
        self.refresh_models()

    def refresh_models(self):
        ids = self.root.ids
        mode = ids.mode.text
        if mode == MODE_ESIM:
            self.model_tacs = dict(self.esim)
            truncated = False
        elif mode == MODE_ALL:
            rows, truncated = self.db.models(ids.brand.text, ids.search.text.strip())
            self.model_tacs = dict(rows)
        else:
            self.update_tac_info()
            return
        names = list(self.model_tacs)
        if truncated:
            names.append("... refine search to see more")
        ids.model.values = names
        if ids.model.text not in self.model_tacs:
            ids.model.text = names[0] if self.model_tacs else NO_MODELS
        self.update_tac_info()

    def current_tacs(self):
        """Return (tacs, label) for the current selection or raise ValueError."""
        ids = self.root.ids
        if ids.mode.text == MODE_CUSTOM:
            tac = gen.normalize(ids.custom_tac.text)
            if not gen.is_valid_tac(tac):
                raise ValueError("Enter a valid 8-digit TAC")
            row = self.db.lookup(tac)
            return [tac], ("%s %s" % (row["brand"], row["model"]) if row else "Custom TAC")
        tacs = self.model_tacs.get(ids.model.text)
        if not tacs:
            raise ValueError("Select a model first")
        brand = "Apple" if ids.mode.text == MODE_ESIM else ids.brand.text
        return tacs, "%s %s" % (brand, ids.model.text)

    def update_tac_info(self):
        ids = self.root.ids
        if ids.mode.text == MODE_CUSTOM:
            tac = gen.normalize(ids.custom_tac.text)
            if len(tac) < 8:
                ids.tac_info.text = "Any 8-digit TAC. Known TACs are labelled from the database."
                return
            row = self.db.lookup(tac)
            ids.tac_info.text = ("Known: %s %s" % (row["brand"], row["model"]) if row
                                 else "TAC not in database (will still generate)")
            return
        tacs = self.model_tacs.get(ids.model.text, [])
        if not tacs:
            ids.tac_info.text = "No matching models."
        else:
            shown = ", ".join(tacs[:6]) + (" ..." if len(tacs) > 6 else "")
            ids.tac_info.text = "%d TAC%s: %s" % (len(tacs), "" if len(tacs) == 1 else "s", shown)

    # ---- generation -----------------------------------------------------
    def show_error(self, msg):
        self.root.ids.results.text = "[color=ff5555]%s[/color]" % escape(msg)

    def generate(self):
        try:
            tacs, label = self.current_tacs()
            qty_text = self.root.ids.qty.text.strip() or "1"
            qty = int(qty_text)
            batch = gen.generate_batch(tacs, qty)
        except ValueError as e:
            self.show_error(str(e))
            return
        self.results = [(imei, tac, label) for imei, tac in batch]
        header = "[color=55dd77]%d IMEI%s - %s[/color]\n\n" % (
            qty, "" if qty == 1 else "s", escape(label))
        body = "\n".join(imei for imei, _, _ in self.results[:500])
        if qty > 500:
            body += "\n\n(+%d more - use Copy or %s)" % (qty - 500, self.export_label)
        self.root.ids.results.text = header + "[b]" + body + "[/b]"

    def clear_results(self):
        self.results = []
        self.root.ids.results.text = "Press Generate to create test IMEIs."

    def results_text(self):
        return "\n".join(imei for imei, _, _ in self.results)

    def results_csv(self):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["imei", "tac", "model"])
        w.writerows(self.results)
        return buf.getvalue()

    def copy_results(self):
        if not self.results:
            self.show_error("Nothing to copy - generate first")
            return
        Clipboard.copy(self.results_text())
        self.toast("Copied %d IMEI%s" % (len(self.results), "" if len(self.results) == 1 else "s"))

    def export_results(self):
        if not self.results:
            self.show_error("Nothing to export - generate first")
            return
        if platform == "android":
            try:
                share_text_android(self.results_text(), "Generated test IMEIs")
                return
            except Exception as e:  # fall back to saving a file
                print("share failed:", e)
        path = os.path.join(self.user_data_dir, "imeis_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(self.results_csv())
        self.toast("Saved %s" % path)

    def toast(self, msg):
        if platform == "android":
            try:
                toast_android(msg)
                return
            except Exception:
                pass
        ids = self.root.ids
        ids.tac_info.text = msg
        Clock.schedule_once(lambda dt: self.update_tac_info(), 3)

    # ---- check / lookup -------------------------------------------------
    def check(self):
        ids = self.root.ids
        text = gen.normalize(ids.check_input.text)
        lines = []
        if len(text) == 8 and text.isdigit():
            lines.append("TAC %s" % text)
        elif text:
            ok, msg = gen.validate_imei(text)
            lines.append("[color=%s]%s[/color]" % ("55dd77" if ok else "ff5555", escape(msg)))
        else:
            ids.check_result.text = "[color=ff5555]Enter an IMEI or TAC[/color]"
            return
        if len(text) >= 8 and text[:8].isdigit():
            row = self.db.lookup(text[:8])
            if row:
                lines.append("Device: [b]%s %s[/b]" % (escape(row["brand"]), escape(row["model"])))
                if row["aka"]:
                    lines.append("Also known as: %s" % escape(row["aka"].replace(",", ", ")))
                if row["esim"]:
                    lines.append("eSIM-capable iPhone")
            else:
                lines.append("TAC %s is not in the embedded database" % text[:8])
        ids.check_result.text = "\n".join(lines)


def escape(text):
    return str(text).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


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


def toast_android(msg):
    from android.runnable import run_on_ui_thread
    from jnius import autoclass, cast

    @run_on_ui_thread
    def _show():
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Toast = autoclass("android.widget.Toast")
        String = autoclass("java.lang.String")
        Toast.makeText(PythonActivity.mActivity,
                       cast("java.lang.CharSequence", String(msg)),
                       Toast.LENGTH_SHORT).show()

    _show()


if __name__ == "__main__":
    IMEIGeneratorApp().run()
