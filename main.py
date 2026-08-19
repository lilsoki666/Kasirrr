__version__ = "4.10.2-kasirqu-branding"

import csv
import os
import platform
from datetime import datetime
import traceback
import time
import textwrap
import shutil

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.scrollview import ScrollView
from database import Database


# ==========================================
# HELPER PRINTER THERMAL BLUETOOTH
# ==========================================
class ThermalPrinterManager:
    """Bluetooth ESC/POS printer helper designed for small Android thermal printers.

    The important reliability rules here are:
    - send only printer-safe ASCII bytes by default;
    - send data in small chunks instead of one large write;
    - pause briefly between chunks so small printer buffers can keep up;
    - always flush and close the socket in finally;
    - wrap long receipt lines before they reach the printer.
    """

    SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"
    LINE_WIDTH = 48  # 80mm ESC/POS paper at normal font size
    CHUNK_SIZE = 96
    CHUNK_DELAY = 0.035

    def __init__(self, mac_address="", line_width=48, auto_cut=False, feed_lines=3):
        self.mac_address = mac_address
        self.line_width = 32 if str(line_width) == "32" else 48
        self.auto_cut = bool(auto_cut)
        try:
            self.feed_lines = max(1, min(8, int(feed_lines)))
        except (ValueError, TypeError):
            self.feed_lines = 3

    @staticmethod
    def _safe_ascii(text):
        # Most low-cost ESC/POS printers do not understand UTF-8 reliably.
        # Keep the receipt deterministic; unsupported characters become '?'.
        return text.encode("ascii", errors="replace")

    def _wrap_receipt(self, text_content):
        """Normalize and wrap every logical line to the printer width."""
        result = []
        for raw in str(text_content).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if not raw:
                result.append("")
                continue
            # Preserve spaces at the beginning of a line, but never allow a
            # physical printer line to exceed LINE_WIDTH.
            leading = len(raw) - len(raw.lstrip(" "))
            prefix = raw[:leading]
            body = raw[leading:]
            width = max(1, self.line_width - len(prefix))
            parts = textwrap.wrap(
                body,
                width=width,
                replace_whitespace=False,
                drop_whitespace=True,
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]
            result.extend(prefix + part for part in parts)
        return "\n".join(result)

    def print_receipt(self, text_content):
        if not self.mac_address or not self.mac_address.strip():
            return False, "MAC Address printer belum diatur di Pengaturan."

        if platform.system() == "Linux" and "ANDROID_ARGUMENT" in os.environ:
            return self._print_android(text_content)

        # PC/Laptop simulation mode.
        safe_text = self._wrap_receipt(text_content)
        print("\n========== SIMULASI CETAK PRINTER ==========")
        print(safe_text)
        print("============================================\n")
        return True, "Mode Laptop/PC: Struk berhasil disimulasikan."

    def _write_chunked(self, output_stream, data):
        """Write small Java byte[] chunks so small Bluetooth buffers keep up."""
        for offset in range(0, len(data), self.CHUNK_SIZE):
            chunk = data[offset:offset + self.CHUNK_SIZE]
            # PyJNIus converts Python bytes to the Java byte[] expected by
            # OutputStream.write(). Avoid jarray entirely for Android builds.
            output_stream.write(bytes(chunk))
            time.sleep(self.CHUNK_DELAY)

    def _print_android(self, text_content):
        socket = None
        output_stream = None
        try:
            from jnius import autoclass

            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            UUID = autoclass('java.util.UUID')

            adapter = BluetoothAdapter.getDefaultAdapter()
            if not adapter or not adapter.isEnabled():
                return False, "Bluetooth HP tidak aktif."

            device = adapter.getRemoteDevice(self.mac_address.strip())
            spp_uuid = UUID.fromString(self.SPP_UUID)

            socket = device.createRfcommSocketToServiceRecord(spp_uuid)
            socket.connect()
            output_stream = socket.getOutputStream()

            safe_text = self._wrap_receipt(text_content)
            payload = self._safe_ascii(safe_text)

            # ESC/POS: initialize, print, feed. Do not send an unconditional
            # cutter command because many inexpensive printers have no cutter;
            # that command can cause an error or stop the print job early.
            self._write_chunked(output_stream, bytes([0x1B, 0x40]))
            time.sleep(0.08)
            self._write_chunked(output_stream, payload)
            self._write_chunked(output_stream, b"\n" * self.feed_lines)
            if self.auto_cut:
                # ESC/POS full cut; only enabled when the user explicitly
                # selects it for a printer that supports a cutter.
                self._write_chunked(output_stream, bytes([0x1D, 0x56, 0x00]))
            output_stream.flush()
            time.sleep(0.30)

            return True, "Struk berhasil dicetak."

        except Exception as e:
            return False, f"Gagal cetak Bluetooth: {str(e)}"
        finally:
            try:
                if output_stream is not None:
                    output_stream.flush()
            except Exception:
                pass
            try:
                if socket is not None:
                    socket.close()
            except Exception:
                pass


# ==========================================
# KIVY INTERFACE (KV LANGUAGE)
# ==========================================
class ToolbarIcon(Widget):
    """Dependency-free vector icon drawn with Kivy Canvas primitives."""
    icon_type = StringProperty("home")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, icon_type=self._redraw)
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2.0, y + h / 2.0
        s = min(w, h) * 0.28
        with self.canvas:
            Color(0.12, 0.20, 0.32, 1)
            if self.icon_type == "home":
                Line(points=[cx-s*1.25, cy, cx, cy+s, cx+s*1.25, cy], width=1.5)
                Line(points=[cx-s, cy, cx-s, cy-s*0.9, cx+s, cy-s*0.9, cx+s, cy], width=1.5)
            elif self.icon_type == "cashier":
                Line(rectangle=(cx-s, cy-s*1.15, 2*s, 2*s*1.3), width=1.5)
                Line(points=[cx-s*0.55, cy+s*0.35, cx+s*0.55, cy+s*0.35], width=1.5)
                for dx, dy in [(-.45,-.35),(0,-.35),(.45,-.35),(-.45,-.72),(0,-.72),(.45,-.72)]:
                    Rectangle(pos=(cx+dx*s-.10*s, cy+dy*s-.10*s), size=(.20*s,.20*s))
            elif self.icon_type == "product":
                Line(points=[cx-s, cy+s*0.45, cx, cy+s, cx+s, cy+s*0.45, cx, cy-s*0.05, cx-s, cy+s*0.45], width=1.5)
                Line(points=[cx-s, cy+s*0.45, cx-s, cy-s*0.8, cx, cy-s*1.2, cx, cy-s*0.05], width=1.5)
                Line(points=[cx+s, cy+s*0.45, cx+s, cy-s*0.8, cx, cy-s*1.2], width=1.5)
            elif self.icon_type == "history":
                Line(circle=(cx, cy, s*1.15, 0, 360), width=1.5)
                Line(points=[cx, cy, cx, cy+s*0.55, cx+s*0.45, cy+s*0.15], width=1.5)
            elif self.icon_type == "report":
                Line(rectangle=(cx-s*0.8, cy-s, s*1.6, s*2), width=1.5)
                Line(points=[cx-s*0.45, cy+s*0.45, cx+s*0.45, cy+s*0.45], width=1.5)
                Line(points=[cx-s*0.45, cy, cx+s*0.45, cy], width=1.5)
                Line(points=[cx-s*0.45, cy-s*0.45, cx+s*0.25, cy-s*0.45], width=1.5)
            else:
                Line(circle=(cx, cy, s*0.48, 0, 360), width=1.5)
                for dx, dy in [(0,1),(1,0),(0,-1),(-1,0),(.7,.7),(.7,-.7),(-.7,.7),(-.7,-.7)]:
                    Line(points=[cx+dx*s*0.45, cy+dy*s*0.45, cx+dx*s*0.95, cy+dy*s*0.95], width=1.5)


class IconNavButton(ButtonBehavior, BoxLayout):
    icon_type = StringProperty("home")
    label_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=0, padding=(0, 2), **kwargs)




class ProductCard(ButtonBehavior, BoxLayout):
    """Compact, minimal POS product card. Keeps existing tap-to-add logic."""
    def __init__(self, product_id=None, image_path="", **kwargs):
        super().__init__(orientation="horizontal", spacing=dp(8), padding=dp(4), **kwargs)
        self.product_id = product_id
        self.size_hint_y = None
        self.height = dp(78)
        self._image_path = image_path or ""
        self.bind(state=self._state_redraw)
        self._build_card()

    def _build_card(self):
        self.clear_widgets()

        thumb_box = BoxLayout(
            orientation="vertical", size_hint_x=None, width=dp(64), padding=dp(1)
        )
        with thumb_box.canvas.before:
            Color(0.94, 0.96, 0.98, 1)
            from kivy.graphics import RoundedRectangle
            thumb_bg = RoundedRectangle(pos=thumb_box.pos, size=thumb_box.size, radius=[dp(7)])
        thumb_box.bind(pos=lambda w, v: setattr(thumb_bg, "pos", v),
                       size=lambda w, v: setattr(thumb_bg, "size", v))

        if self._image_path and os.path.exists(self._image_path):
            thumb = Image(source=self._image_path, allow_stretch=True, keep_ratio=True)
        else:
            thumb = Label(text="FOTO", font_size="8sp", bold=True,
                          color=(.45, .50, .58, 1), halign="center", valign="middle")
            thumb.bind(size=lambda w, v: setattr(w, "text_size", v))
        thumb_box.add_widget(thumb)
        self.add_widget(thumb_box)

        self.info_box = BoxLayout(orientation="vertical", spacing=0, padding=(dp(2), dp(2)))
        self.name_label = Label(
            font_size="11.5sp", bold=True, color=(.08, .10, .14, 1),
            halign="left", valign="middle", text_size=(None, None)
        )
        self.detail_label = Label(
            font_size="9.5sp", color=(.38, .43, .50, 1),
            halign="left", valign="middle", text_size=(None, None)
        )
        self.info_box.add_widget(self.name_label)
        self.info_box.add_widget(self.detail_label)
        self.add_widget(self.info_box)

        add_box = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(46), padding=(0, dp(7)))
        add_label = Label(text="+", font_size="20sp", bold=True,
                          color=(1, 1, 1, 1), halign="center", valign="middle")
        with add_box.canvas.before:
            Color(0.05, 0.60, 0.30, 1)
            from kivy.graphics import RoundedRectangle
            add_bg = RoundedRectangle(pos=add_box.pos, size=add_box.size, radius=[dp(7)])
        add_box.bind(pos=lambda w, v: setattr(add_bg, "pos", v),
                     size=lambda w, v: setattr(add_bg, "size", v))
        add_box.add_widget(add_label)
        self.add_widget(add_box)
        self._state_redraw()

    def set_product_text(self, name, detail):
        self.name_label.text = str(name)
        self.detail_label.text = str(detail)
        self.name_label.text_size = (max(1, self.info_box.width), None)
        self.detail_label.text_size = (max(1, self.info_box.width), None)

    def _state_redraw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.94, 0.97, 0.99, 1) if self.state == "down" else Color(1, 1, 1, 1)
            from kivy.graphics import RoundedRectangle
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])

KV = """
#:import dp kivy.metrics.dp

# --- Style Komponen Minimalis ---
<IconNavButton>:
    size_hint_y: 1
    padding: dp(0), dp(2)
    spacing: dp(0)
    canvas.before:
        Color:
            rgba: (0.98, 0.98, 0.99, 1) if self.state == "normal" else (0.90, 0.93, 0.98, 1)
        Rectangle:
            pos: self.pos
            size: self.size

<IconLabel@Label>:
    size_hint_y: None
    height: dp(16)
    font_size: "9sp"
    bold: True
    color: (.15, .20, .30, 1)
    halign: "center"
    valign: "middle"
    text_size: self.size

<NavButton@Button>:
    size_hint_y: 1
    background_normal: ""
    background_color: (0.98, 0.98, 0.99, 1) if self.state == 'normal' else (0.90, 0.93, 0.98, 1)
    color: (.15, .20, .30, 1)
    font_size: "11sp"
    bold: True
    halign: "center"
    valign: "middle"

<ModernTextInput@TextInput>:
    size_hint_y: None
    height: dp(44)
    padding: dp(12), dp(11)
    font_size: "13sp"
    background_normal: ""
    background_active: ""
    background_color: .95, .96, .98, 1
    cursor_color: .10, .40, .80, 1
    hint_text_color: .55, .60, .68, 1
    foreground_color: .10, .14, .20, 1

<CardBox@BoxLayout>:
    padding: dp(12)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]

<TitleLabel@Label>:
    font_size: "18sp"
    bold: True
    color: .10, .14, .20, 1
    size_hint_y: None
    height: dp(36)
    halign: "left"
    valign: "middle"
    text_size: self.size

<SectionLabel@Label>:
    font_size: "13sp"
    bold: True
    color: .35, .40, .48, 1
    size_hint_y: None
    height: dp(28)
    halign: "left"
    valign: "middle"
    text_size: self.size

# --- Interactive V4.7 components ---
<InteractiveButton@Button>:
    background_normal: ""
    background_color: (0.10, 0.15, 0.22, 1) if self.state == "normal" else (0.06, 0.10, 0.16, 1)
    color: 1, 1, 1, 1
    bold: True
    font_size: "12sp"

<StatusChip@Label>:
    size_hint_y: None
    height: dp(28)
    padding: dp(8), 0
    halign: "center"
    valign: "middle"
    text_size: self.size
    font_size: "10sp"
    bold: True
    color: .10, .14, .20, 1
    canvas.before:
        Color:
            rgba: .93, .95, .98, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

<QuickCard@Button>:
    background_normal: ""
    background_color: (1, 1, 1, 1) if self.state == "normal" else (.94, .96, .99, 1)
    color: .08, .12, .18, 1
    bold: True
    font_size: "11sp"
    halign: "center"
    valign: "middle"
    text_size: self.size
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]

# --- Style Popup Serba Putih Global ---
<WhitePopup>:
    background_color: 1, 1, 1, 1
    background: ""
    title_color: 0.10, 0.14, 0.20, 1
    title_size: "16sp"
    separator_color: 0.85, 0.88, 0.92, 1

# --- Root Layout Utama ---
<RootLayout>:
    orientation: "vertical"
    canvas.before:
        Color:
            rgba: .94, .95, .97, 1
        Rectangle:
            pos: self.pos
            size: self.size

    # Clean Header Bar
    BoxLayout:
        size_hint_y: None
        height: dp(52)
        padding: dp(16), dp(8)
        canvas.before:
            Color:
                rgba: .08, .12, .18, 1
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            text: app.store_name
            font_size: "16sp"
            bold: True
            color: 1, 1, 1, 1
            halign: "left"
            valign: "middle"
            text_size: self.size

        Label:
            text: "v" + app.version + ("  •  LANDSCAPE" if app.is_landscape else "")
            size_hint_x: None
            width: dp(50)
            font_size: "11sp"
            color: .60, .68, .78, 1
            halign: "right"
            valign: "middle"
            text_size: self.size

    # Area Konten Utama
    ScreenManager:
        id: sm


        Screen:
            name: "dashboard"
            ScrollView:
                do_scroll_x: False
                BoxLayout:
                    orientation: "vertical"
                    padding: dp(14)
                    spacing: dp(10)
                    size_hint_y: None
                    height: self.minimum_height

                    TitleLabel:
                        text: "Dashboard"

                    CardBox:
                        size_hint_y: None
                        height: dp(48)
                        padding: dp(10), dp(6)
                        spacing: dp(6)
                        Label:
                            text: "Kasir aktif: " + app.cashier_name
                            font_size: "10sp"
                            bold: True
                            color: .10, .14, .20, 1
                            halign: "left"
                            valign: "middle"
                            text_size: self.size
                        Label:
                            id: dash_shift_status
                            text: "Memuat status shift..."
                            font_size: "10sp"
                            color: .35, .40, .48, 1
                            halign: "right"
                            valign: "middle"
                            text_size: self.size

                    GridLayout:
                        # Portrait: 2 columns. Landscape/tablet: 4 columns.
                        cols: 4 if self.width >= dp(700) else 2
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(92) if self.width >= dp(700) else dp(170)

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "PENJUALAN HARI INI"
                                font_size: "10sp"
                                bold: True
                                color: .10, .50, .30, 1
                                halign: "left"
                                text_size: self.size
                            Label:
                                id: dash_sales
                                text: "Rp 0"
                                font_size: "16sp"
                                bold: True
                                color: .05, .35, .20, 1
                                halign: "left"
                                valign: "middle"
                                text_size: self.size

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "TRANSAKSI HARI INI"
                                font_size: "10sp"
                                bold: True
                                color: .15, .40, .70, 1
                                halign: "left"
                                text_size: self.size
                            Label:
                                id: dash_trx
                                text: "0"
                                font_size: "18sp"
                                bold: True
                                color: .10, .25, .50, 1
                                halign: "left"
                                valign: "middle"
                                text_size: self.size

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "PRODUK AKTIF"
                                font_size: "10sp"
                                bold: True
                                color: .50, .25, .70, 1
                                halign: "left"
                                text_size: self.size
                            Label:
                                id: dash_products
                                text: "0"
                                font_size: "18sp"
                                bold: True
                                color: .35, .15, .50, 1
                                halign: "left"
                                valign: "middle"
                                text_size: self.size

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "STOK MENIPIS"
                                font_size: "10sp"
                                bold: True
                                color: .80, .40, .10, 1
                                halign: "left"
                                text_size: self.size
                            Label:
                                id: dash_low
                                text: "0"
                                font_size: "18sp"
                                bold: True
                                color: .60, .25, .05, 1
                                halign: "left"
                                valign: "middle"
                                text_size: self.size

                    CardBox:
                        size_hint_y: None
                        height: dp(64)
                        orientation: "vertical"
                        Label:
                            id: dash_profit
                            text: "Laba kotor hari ini: Rp 0"
                            font_size: "12sp"
                            bold: True
                            color: .08, .42, .24, 1
                            halign: "left"
                            valign: "middle"
                            text_size: self.size

                    SectionLabel:
                        text: "Ringkasan Penjualan"

                    GridLayout:
                        cols: 6 if self.width >= dp(700) else 3
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(76)

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "7 HARI"
                                font_size: "9sp"
                                bold: True
                                color: .35, .40, .48, 1
                                text_size: self.size
                            Label:
                                id: dash_7d_sales
                                text: "Rp 0"
                                font_size: "12sp"
                                bold: True
                                color: .10, .14, .20, 1
                                text_size: self.size

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "30 HARI"
                                font_size: "9sp"
                                bold: True
                                color: .35, .40, .48, 1
                                text_size: self.size
                            Label:
                                id: dash_30d_sales
                                text: "Rp 0"
                                font_size: "12sp"
                                bold: True
                                color: .10, .14, .20, 1
                                text_size: self.size

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "ITEM TERJUAL"
                                font_size: "9sp"
                                bold: True
                                color: .35, .40, .48, 1
                                text_size: self.size
                            Label:
                                id: dash_30d_items
                                text: "0"
                                font_size: "12sp"
                                bold: True
                                color: .10, .14, .20, 1
                                text_size: self.size

                    SectionLabel:
                        text: "Produk Terlaris"

                    GridLayout:
                        id: dash_top_products
                        cols: 1
                        spacing: dp(4)
                        size_hint_y: None
                        height: self.minimum_height

                    SectionLabel:
                        text: "Stok Perlu Perhatian"

                    GridLayout:
                        id: dash_low_stock
                        cols: 1
                        spacing: dp(4)
                        size_hint_y: None
                        height: self.minimum_height

                    SectionLabel:
                        text: "Pembayaran Hari Ini"

                    GridLayout:
                        id: dash_payments
                        cols: 1
                        spacing: dp(4)
                        size_hint_y: None
                        height: self.minimum_height

                    SectionLabel:
                        text: "Transaksi Terbaru"

                    GridLayout:
                        id: dash_recent_sales
                        cols: 1
                        spacing: dp(4)
                        size_hint_y: None
                        height: self.minimum_height

                    GridLayout:
                        cols: 2
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(140)

                        Button:
                            text: "BUKA KASIR"
                            background_normal: ""
                            background_color: .04, .58, .30, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.show_screen("pos")

                        Button:
                            text: "KELOLA PRODUK"
                            background_normal: ""
                            background_color: .12, .16, .22, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.show_screen("products")

                        Button:
                            text: "KEUANGAN"
                            background_normal: ""
                            background_color: .12, .42, .72, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.finance_popup()

                        Button:
                            text: "INVENTORY"
                            background_normal: ""
                            background_color: .72, .42, .10, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.inventory_popup()

                    GridLayout:
                        cols: 3
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(88)

                        Button:
                            text: "V4 BUSINESS"
                            background_normal: ""
                            background_color: .10, .15, .22, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.business_center_popup()

                        Button:
                            text: "SHIFT & KAS"
                            background_normal: ""
                            background_color: .45, .25, .70, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.shift_popup()

                        Button:
                            text: "AUDIT"
                            background_normal: ""
                            background_color: .35, .42, .48, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.audit_popup()

                    Button:
                        text: "Refresh Dashboard"
                        size_hint_y: None
                        height: dp(42)
                        background_normal: ""
                        background_color: .88, .91, .95, 1
                        color: .08, .11, .16, 1
                        bold: True
                        on_release: app.refresh_dashboard()
        Screen:
            name: "pos"
            BoxLayout:
                orientation: "vertical"
                padding: dp(12)
                spacing: dp(8)

                TitleLabel:
                    text: "Kasir / POS"

                BoxLayout:
                    size_hint_y: None
                    height: dp(48)
                    spacing: dp(6)
                    ModernTextInput:
                        id: search_pos
                        hint_text: "Cari produk atau scan barcode..."
                        on_text: app.refresh_pos_products(self.text)
                    Button:
                        text: "BARCODE"
                        size_hint_x: None
                        width: dp(100)
                        background_normal: ""
                        background_color: .10, .28, .55, 1
                        color: 1, 1, 1, 1
                        bold: True
                        font_size: "12sp"
                        on_release: app.barcode_popup()

                ScrollView:
                    do_scroll_y: False
                    size_hint_y: None
                    height: dp(44)
                    bar_width: 0
                    BoxLayout:
                        id: pos_category_filter
                        size_hint_x: None
                        width: self.minimum_width
                        spacing: dp(6)
                        padding: 0, dp(1)

                ScrollView:
                    id: pos_product_scroll
                    do_scroll_x: False
                    do_scroll_y: True
                    bar_width: dp(3)
                    scroll_type: ["bars", "content"]
                    GridLayout:
                        id: product_grid
                        cols: 1
                        spacing: dp(5)
                        padding: 0, dp(2)
                        size_hint_x: 1
                        width: self.parent.width
                        size_hint_y: None
                        height: self.minimum_height

                CardBox:
                    size_hint_y: None
                    height: dp(64)
                    padding: dp(10), dp(6)
                    spacing: dp(8)

                    BoxLayout:
                        orientation: "vertical"
                        Label:
                            id: cart_summary_items
                            text: "0 Item"
                            font_size: "10sp"
                            color: .40, .45, .55, 1
                            halign: "left"
                            text_size: self.size
                        Label:
                            id: pos_total
                            text: "Rp 0"
                            font_size: "15sp"
                            bold: True
                            color: .05, .55, .25, 1
                            halign: "left"
                            text_size: self.size

                    Button:
                        text: "Lihat Keranjang"
                        size_hint_x: None
                        width: dp(150)
                        background_normal: ""
                        background_color: .05, .60, .30, 1
                        color: 1, 1, 1, 1
                        bold: True
                        font_size: "12sp"
                        on_release: app.open_cart_popup()

        Screen:
            name: "products"
            BoxLayout:
                orientation: "vertical"
                padding: dp(12)
                spacing: dp(8)

                TitleLabel:
                    text: "Daftar Produk"

                BoxLayout:
                    size_hint_y: None
                    height: dp(44)
                    spacing: dp(6)

                    ModernTextInput:
                        id: search_product
                        hint_text: "Cari nama produk..."
                        on_text: app.refresh_products(self.text)

                    Button:
                        text: "+ Tambah"
                        size_hint_x: None
                        width: dp(95)
                        background_normal: ""
                        background_color: .04, .58, .30, 1
                        color: 1, 1, 1, 1
                        bold: True
                        on_release: app.product_form()

                # Toolbar tindakan produk dibuat horizontal-scroll agar tidak
                # meluber di layar HP yang sempit. Semua tombol tetap satu baris.
                ScrollView:
                    size_hint_y: None
                    height: dp(46)
                    do_scroll_x: True
                    do_scroll_y: False
                    bar_width: dp(3)
                    scroll_type: ["bars", "content"]
                    BoxLayout:
                        size_hint_x: None
                        width: self.minimum_width
                        size_hint_y: None
                        height: dp(42)
                        spacing: dp(6)

                        Button:
                            text: "+ Kategori"
                            size_hint_x: None
                            width: dp(108)
                            background_normal: ""
                            background_color: .88, .91, .95, 1
                            color: .08, .11, .16, 1
                            bold: True
                            on_release: app.category_form()

                        Button:
                            text: "Kelola Kategori"
                            size_hint_x: None
                            width: dp(132)
                            background_normal: ""
                            background_color: .82, .90, 1, 1
                            color: .10, .28, .55, 1
                            bold: True
                            on_release: app.category_manager_popup()

                        Button:
                            text: "Riwayat Stok"
                            size_hint_x: None
                            width: dp(112)
                            background_normal: ""
                            background_color: .10, .14, .20, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.stock_history_popup()

                        Button:
                            text: "Nilai Inventory"
                            size_hint_x: None
                            width: dp(125)
                            background_normal: ""
                            background_color: .72, .42, .10, 1
                            color: 1, 1, 1, 1
                            bold: True
                            on_release: app.inventory_popup()

                Label:
                    text: "Kelola stok mencatat setiap stok masuk, keluar, dan koreksi."
                    color: .35, .40, .48, 1
                    font_size: "10sp"
                    text_size: self.width, None
                    halign: "left"
                    size_hint_y: None
                    height: dp(28)

                ScrollView:
                    do_scroll_x: False
                    GridLayout:
                        id: products_grid
                        cols: 1
                        spacing: dp(6)
                        size_hint_x: 1
                        width: self.parent.width
                        size_hint_y: None
                        height: self.minimum_height

        Screen:
            name: "history"
            BoxLayout:
                orientation: "vertical"
                padding: dp(12)
                spacing: dp(8)

                TitleLabel:
                    text: "Riwayat Transaksi"

                ScrollView:
                    do_scroll_x: False
                    GridLayout:
                        id: history_grid
                        cols: 1
                        spacing: dp(6)
                        size_hint_y: None
                        height: self.minimum_height

        Screen:
            name: "reports"
            BoxLayout:
                orientation: "vertical"
                padding: dp(12)
                spacing: dp(8)

                TitleLabel:
                    text: "Laporan Penjualan"

                ScrollView:
                    do_scroll_x: False
                    GridLayout:
                        id: report_grid
                        cols: 1
                        spacing: dp(6)
                        size_hint_y: None
                        height: self.minimum_height

                SectionLabel:
                    text: "Produk Terlaris (30 Hari)"

                ScrollView:
                    do_scroll_x: False
                    GridLayout:
                        id: top_products_grid
                        cols: 1
                        spacing: dp(5)
                        size_hint_y: None
                        height: self.minimum_height

                Button:
                    text: "Export CSV"
                    size_hint_y: None
                    height: dp(44)
                    background_normal: ""
                    background_color: .04, .58, .30, 1
                    color: 1, 1, 1, 1
                    bold: True
                    on_release: app.export_csv()

        Screen:
            name: "settings"
            ScrollView:
                do_scroll_x: False
                BoxLayout:
                    orientation: "vertical"
                    padding: dp(12)
                    spacing: dp(8)
                    size_hint_y: None
                    height: self.minimum_height

                    TitleLabel:
                        text: "Pengaturan Toko"

                    SectionLabel:
                        text: "Identitas Toko"

                    ModernTextInput:
                        id: setting_store
                        hint_text: "Nama toko"
                        text: app.store_name

                    ModernTextInput:
                        id: setting_address
                        hint_text: "Alamat toko"
                        text: app.store_address

                    ModernTextInput:
                        id: setting_tax
                        hint_text: "Pajak (%)"
                        text: app.tax_percent
                        input_filter: "float"

                    ModernTextInput:
                        id: setting_cashier
                        hint_text: "Nama kasir"
                        text: app.cashier_name

                    SectionLabel:
                        text: "Profil Usaha"

                    Spinner:
                        id: setting_business_type
                        text: app.business_type
                        values: ["Umum", "Toko Pakaian", "Bengkel", "Warung / Retail", "Toko Elektronik", "Toko Bangunan", "Salon / Kecantikan", "Jasa", "Lainnya"]
                        size_hint_y: None
                        height: dp(44)

                    Label:
                        text: "Jenis usaha hanya membantu menyesuaikan istilah aplikasi. Anda tetap bebas membuat kategori sendiri."
                        text_size: self.width, None
                        halign: "left"
                        color: .35, .40, .48, 1
                        font_size: "10sp"
                        size_hint_y: None
                        height: dp(42)

                    SectionLabel:
                        text: "Printer Thermal Bluetooth"

                    ModernTextInput:
                        id: setting_bt_mac
                        hint_text: "MAC Address Printer (cth: 00:11:22:33:AA:BB)"
                        text: app.bt_mac_address

                    Spinner:
                        id: setting_paper_width
                        text: "58 mm" if app.paper_width == "32" else "80 mm"
                        values: ["58 mm", "80 mm"]
                        size_hint_y: None
                        height: dp(44)

                    Spinner:
                        id: setting_auto_cut
                        text: "ON" if app.auto_cut else "OFF"
                        values: ["OFF", "ON"]
                        size_hint_y: None
                        height: dp(44)

                    ModernTextInput:
                        id: setting_feed_lines
                        hint_text: "Feed kertas (1-8)"
                        text: app.feed_lines
                        input_filter: "int"

                    ModernTextInput:
                        id: setting_instagram
                        hint_text: "Instagram toko (opsional)"
                        text: app.store_instagram

                    ModernTextInput:
                        id: setting_whatsapp
                        hint_text: "WhatsApp toko (opsional)"
                        text: app.store_whatsapp

                    ModernTextInput:
                        id: setting_receipt_footer
                        hint_text: "Pesan footer struk"
                        text: app.receipt_footer

                    Button:
                        text: "Tes Cetak Printer"
                        size_hint_y: None
                        height: dp(40)
                        background_normal: ""
                        background_color: .88, .91, .95, 1
                        color: .08, .11, .16, 1
                        bold: True
                        on_release: app.test_print()

                    Button:
                        text: "Simpan Pengaturan"
                        size_hint_y: None
                        height: dp(44)
                        background_normal: ""
                        background_color: .04, .58, .30, 1
                        color: 1, 1, 1, 1
                        bold: True
                        on_release: app.save_settings()

                    SectionLabel:
                        text: "Data & Backup"

                    Button:
                        text: "Buat Backup Database"
                        size_hint_y: None
                        height: dp(44)
                        background_normal: ""
                        background_color: .88, .91, .95, 1
                        color: .08, .11, .16, 1
                        bold: True
                        on_release: app.make_backup()

                    Label:
                        text: "Database SQLite lokal. Aplikasi tetap dapat digunakan tanpa internet."
                        text_size: self.width, None
                        halign: "left"
                        color: .30, .34, .40, 1
                        size_hint_y: None
                        height: dp(36)

    # Bottom Navigation Bar
    BoxLayout:
        size_hint_y: None
        height: dp(54)
        padding: dp(2)
        spacing: dp(2)
        canvas.before:
            Color:
                rgba: 1, 1, 1, 1
            Rectangle:
                pos: self.pos
                size: self.size

        IconNavButton:
            icon_type: "home"
            label_text: "Dashboard"
            on_release: app.show_screen("dashboard")
            ToolbarIcon:
                icon_type: self.parent.icon_type
                size_hint_y: None
                height: dp(28)
            IconLabel:
                text: "Dashboard"
        IconNavButton:
            icon_type: "cashier"
            label_text: "Kasir"
            on_release: app.show_screen("pos")
            ToolbarIcon:
                icon_type: self.parent.icon_type
                size_hint_y: None
                height: dp(28)
            IconLabel:
                text: "Kasir"
        IconNavButton:
            icon_type: "product"
            label_text: "Produk"
            on_release: app.show_screen("products")
            ToolbarIcon:
                icon_type: self.parent.icon_type
                size_hint_y: None
                height: dp(28)
            IconLabel:
                text: "Produk"
        IconNavButton:
            icon_type: "history"
            label_text: "Riwayat"
            on_release: app.show_screen("history")
            ToolbarIcon:
                icon_type: self.parent.icon_type
                size_hint_y: None
                height: dp(28)
            IconLabel:
                text: "Riwayat"
        IconNavButton:
            icon_type: "report"
            label_text: "Laporan"
            on_release: app.show_screen("reports")
            ToolbarIcon:
                icon_type: self.parent.icon_type
                size_hint_y: None
                height: dp(28)
            IconLabel:
                text: "Laporan"
        IconNavButton:
            icon_type: "settings"
            label_text: "Pengaturan"
            on_release: app.show_screen("settings")
            ToolbarIcon:
                icon_type: self.parent.icon_type
                size_hint_y: None
                height: dp(28)
            IconLabel:
                text: "Pengaturan"
"""


class WhitePopup(Popup):
    pass


class RootLayout(BoxLayout):
    pass


class POSApp(App):
    version = __version__
    store_name = StringProperty("TOKO SAYA")
    is_landscape = False

    def _set_android_orientation_to_system(self):
        """Let Android choose orientation according to its current setting."""
        if platform.system() == "Linux" and "ANDROID_ARGUMENT" in os.environ:
            try:
                from jnius import autoclass
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                ActivityInfo = autoclass("android.content.pm.ActivityInfo")
                PythonActivity.mActivity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
                )
            except Exception as exc:
                print("Adaptive orientation Android gagal:", exc)

    def _on_window_resize(self, _window, size):
        try:
            self.is_landscape = float(size[0]) > float(size[1])
        except Exception:
            self.is_landscape = False
        # Android can resize the window before the ScreenManager/ScrollView
        # has completed its next layout pass. Rebuild the two product lists
        # after that pass so their children receive the new width/height.
        if hasattr(self, "_adaptive_refresh_trigger"):
            self._adaptive_refresh_trigger()

    def _adaptive_refresh_lists(self, *_):
        try:
            if not getattr(self, "root", None):
                return
            # Force the list containers to use the current viewport width.
            try:
                product_grid = self.root.ids["product_grid"]
                available = max(1, self.root.ids.sm.width - dp(24))
                product_grid.width = available
                product_grid.cols = 2 if self.is_landscape and available >= dp(520) else 1
            except Exception:
                pass
            try:
                grid = self.root.ids["products_grid"]
                grid.width = max(1, self.root.ids.sm.width - dp(24))
            except Exception:
                pass
            self.refresh_pos_categories()
            self.refresh_pos_products(self.root.ids.search_pos.text if "search_pos" in self.root.ids else "")
            self.refresh_products(self.root.ids.search_product.text if "search_product" in self.root.ids else "")
        except Exception as exc:
            print("Adaptive list refresh gagal:", exc)

    def _schedule_adaptive_refresh(self):
        # Triggered/debounced refresh prevents multiple rebuilds during one
        # Android rotation animation.
        if not hasattr(self, "_adaptive_refresh_event"):
            self._adaptive_refresh_event = None

        def trigger(*_):
            if self._adaptive_refresh_event is not None:
                self._adaptive_refresh_event.cancel()
            self._adaptive_refresh_event = Clock.schedule_once(self._adaptive_refresh_lists, 0.12)

        self._adaptive_refresh_trigger = trigger
        trigger()

    store_address = StringProperty("")
    tax_percent = StringProperty("0")
    cashier_name = StringProperty("Admin")
    bt_mac_address = StringProperty("")

    def build(self):
        self.title = "KasirQu"
        self.db = Database(os.path.join(self.user_data_dir, "pos.db"))
        self.init_v46_schema()
        self.init_product_image_schema()
        self.load_settings()
        self.cart = []
        self.pos_category = "Semua"
        self.cart_popup = None
        self.cart_popup_grid = None
        self.popup_total_label = None
        self.popup_change_label = None
        self.paid_input = None
        Builder.load_string(KV)
        return RootLayout()

    def on_start(self):
        try:
            Window.bind(size=self._on_window_resize)
            self._schedule_adaptive_refresh()
            self._on_window_resize(Window, Window.size)
            Clock.schedule_once(lambda dt: self._set_android_orientation_to_system(), 0.35)
            # AUTO REQUEST PERMISSION SAAT APLIKASI PERTAMA DI BUKA
            self.request_android_permissions()
            self.refresh_all()
        except Exception:
            self.log_startup_error()
            self.show_startup_error()

    def request_android_permissions(self):
        # Mengecek apakah aplikasi sedang berjalan di HP Android
        if platform.system() == "Linux" and "ANDROID_ARGUMENT" in os.environ:
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.BLUETOOTH,
                    Permission.BLUETOOTH_ADMIN,
                    Permission.BLUETOOTH_CONNECT,
                    Permission.BLUETOOTH_SCAN,
                    Permission.ACCESS_FINE_LOCATION
                ])
            except Exception as e:
                print("Gagal meminta izin Android:", e)

    def log_startup_error(self):
        try:
            path = os.path.join(self.user_data_dir, "startup_error.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n=== POS KASIR STARTUP ERROR ===\n")
                f.write(traceback.format_exc())
        except Exception:
            pass

    def show_startup_error(self):
        message = (
            "Aplikasi berhasil dibuka, tetapi terjadi kesalahan saat "
            "memuat data awal.\n\n"
            "Silakan periksa file startup_error.log di folder data aplikasi."
        )
        Clock.schedule_once(lambda dt: self.info(message, "Kesalahan Startup"), 0)

    def load_settings(self):
        self.store_name = self.db.get_setting("store_name", "TOKO SAYA")
        self.store_address = self.db.get_setting("store_address", "")
        self.tax_percent = self.db.get_setting("tax_percent", "0")
        self.cashier_name = self.db.get_setting("cashier_name", "Admin")
        self.bt_mac_address = self.db.get_setting("bt_mac_address", "")
        self.paper_width = self.db.get_setting("paper_width", "48")
        self.auto_cut = self.db.get_setting("auto_cut", "0") == "1"
        self.feed_lines = self.db.get_setting("feed_lines", "3")
        self.store_instagram = self.db.get_setting("store_instagram", "")
        self.store_whatsapp = self.db.get_setting("store_whatsapp", "")
        self.receipt_footer = self.db.get_setting("receipt_footer", "Terima Kasih Atas Kunjungan Anda!")
        self.business_type = self.db.get_setting("business_type", "Umum")

    def show_screen(self, name):
        """Navigate between top-level screens with directional horizontal sliding.

        The direction follows the toolbar order: moving to a screen on the
        right slides the new screen in from the right (content moves left);
        moving to a screen on the left slides it in from the left (content
        moves right). The existing vertical ScrollViews remain untouched.
        """
        sm = self.root.ids.sm
        order = ["dashboard", "pos", "products", "history", "reports", "settings"]
        current = sm.current
        if name == current:
            return

        try:
            old_index = order.index(current)
            new_index = order.index(name)
        except ValueError:
            old_index = new_index = 0

        if new_index > old_index:
            sm.transition = SlideTransition(direction="left", duration=0.20)
        else:
            sm.transition = SlideTransition(direction="right", duration=0.20)

        sm.current = name
        if name == "dashboard":
            self.refresh_dashboard()
        elif name == "pos":
            self.refresh_pos_categories()
            self.refresh_pos_products("")
            self.update_cart_summary()
        elif name == "products":
            self.refresh_products("")
        elif name == "history":
            self.refresh_history()
        elif name == "reports":
            self.refresh_reports()

    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_pos_categories()
        self.refresh_pos_products("")
        self.update_cart_summary()
        self.refresh_products("")
        self.refresh_history()
        self.refresh_reports()

    @staticmethod
    def money(value):
        return "Rp {:,.0f}".format(float(value)).replace(",", ".")

    def _v48_products(self, search=""):
        """Read products directly so V4.8 fields work even if database.py uses a fixed SELECT list."""
        q = str(search or "").strip()
        if q:
            like = f"%{q}%"
            return self.db.conn.execute(
                "SELECT p.*, c.name AS category_name FROM products p "
                "LEFT JOIN categories c ON c.id=p.category_id "
                "WHERE p.active=1 AND (p.name LIKE ? OR COALESCE(p.barcode,'') LIKE ?) "
                "ORDER BY p.name", (like, like)
            ).fetchall()
        return self.db.conn.execute(
            "SELECT p.*, c.name AS category_name FROM products p "
            "LEFT JOIN categories c ON c.id=p.category_id "
            "WHERE p.active=1 ORDER BY p.name"
        ).fetchall()

    def _v48_product_by_id(self, product_id):
        return self.db.conn.execute(
            "SELECT p.*, c.name AS category_name FROM products p "
            "LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=?",
            (product_id,)
        ).fetchone()

    @staticmethod
    def _is_service_product(p):
        """Works with sqlite3.Row and normal dicts."""
        try:
            item_type = p["item_type"] if "item_type" in p.keys() else "BARANG"
            track_stock = p["track_stock"] if "track_stock" in p.keys() else 1
        except AttributeError:
            item_type = p.get("item_type", "BARANG")
            track_stock = p.get("track_stock", 1)
        return str(item_type or "BARANG").upper() == "JASA" or not int(track_stock or 0)


    def refresh_dashboard(self):
        """Refresh the V2 dashboard using only the existing SQLite schema."""
        try:
            s, product_count, low = self.db.summary_today()
            # V4.8: services/non-stock items must never appear as low-stock products.
            low = self.db.conn.execute("""
                SELECT COUNT(*) FROM products
                WHERE active=1 AND COALESCE(item_type,'BARANG')='BARANG'
                  AND COALESCE(track_stock,1)=1 AND stock <= min_stock
            """).fetchone()[0]
            self.root.ids.dash_sales.text = self.money(s["total"])
            self.root.ids.dash_trx.text = f"{s['transactions']}"
            self.root.ids.dash_products.text = f"{product_count}"
            self.root.ids.dash_low.text = f"{low}"
            self.root.ids.dash_profit.text = f"Laba kotor hari ini: {self.money(s['profit'])}"
            try:
                sh = self._active_shift()
                if sh:
                    opening, sales, cin, cout = self._cash_summary(sh['id'])
                    expected = opening + sales + cin - cout
                    self.root.ids.dash_shift_status.text = f"Shift aktif • Kas {self.money(expected)}"
                    self.root.ids.dash_shift_status.color = (.05, .45, .25, 1)
                else:
                    self.root.ids.dash_shift_status.text = "Shift belum dibuka"
                    self.root.ids.dash_shift_status.color = (.65, .35, .05, 1)
            except Exception:
                pass

            conn = self.db.conn

            period = conn.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN date(created_at) >= date('now','localtime','-6 day')
                                      THEN total ELSE 0 END),0) AS sales_7d,
                    COALESCE(SUM(total),0) AS sales_30d
                FROM sales
                WHERE date(created_at) >= date('now','localtime','-29 day')
            """).fetchone()
            self.root.ids.dash_7d_sales.text = self.money(period["sales_7d"])
            self.root.ids.dash_30d_sales.text = self.money(period["sales_30d"])

            items = conn.execute("""
                SELECT COALESCE(SUM(si.qty),0) qty
                FROM sale_items si
                JOIN sales s ON s.id=si.sale_id
                WHERE date(s.created_at) >= date('now','localtime','-29 day')
            """).fetchone()["qty"]
            self.root.ids.dash_30d_items.text = f"{float(items):g}"

            # Top products
            top_box = self.root.ids.dash_top_products
            top_box.clear_widgets()
            top = self.db.top_products(30, 5)
            if not top:
                top_box.add_widget(Label(
                    text="Belum ada produk terjual dalam 30 hari.",
                    size_hint_y=None, height=dp(34),
                    color=(.35,.40,.48,1), font_size="11sp",
                    halign="left", text_size=(None, None)
                ))
            else:
                for i, row in enumerate(top, 1):
                    top_box.add_widget(Label(
                        text=f"{i}. {row['product_name']}  |  {row['qty']:g} terjual  |  {self.money(row['revenue'])}",
                        size_hint_y=None, height=dp(34),
                        color=(.10,.14,.20,1), font_size="11sp",
                        halign="left", valign="middle",
                        text_size=(None, None)
                    ))

            # Low stock list
            low_box = self.root.ids.dash_low_stock
            low_box.clear_widgets()
            low_rows = conn.execute("""
                SELECT name, stock, min_stock, unit
                FROM products
                WHERE active=1 AND COALESCE(item_type,'BARANG')='BARANG'
                  AND COALESCE(track_stock,1)=1 AND stock <= min_stock
                ORDER BY stock ASC, name
                LIMIT 8
            """).fetchall()
            if not low_rows:
                low_box.add_widget(Label(
                    text="Semua stok berada di atas batas minimum.",
                    size_hint_y=None, height=dp(34),
                    color=(.08,.42,.24,1), font_size="11sp",
                    halign="left"
                ))
            else:
                for row in low_rows:
                    low_box.add_widget(Label(
                        text=f"[!] {row['name']}  |  Stok {row['stock']:g} {row['unit']}  |  Minimum {row['min_stock']:g}",
                        size_hint_y=None, height=dp(34),
                        color=(.60,.25,.05,1), font_size="11sp",
                        halign="left", valign="middle"
                    ))

            # Payment summary
            pay_box = self.root.ids.dash_payments
            pay_box.clear_widgets()
            payments = conn.execute("""
                SELECT payment_method, COUNT(*) transactions,
                       COALESCE(SUM(total),0) total
                FROM sales
                WHERE date(created_at)=date('now','localtime')
                GROUP BY payment_method
                ORDER BY total DESC
            """).fetchall()
            if not payments:
                pay_box.add_widget(Label(
                    text="Belum ada pembayaran hari ini.",
                    size_hint_y=None, height=dp(34),
                    color=(.35,.40,.48,1), font_size="11sp",
                    halign="left"
                ))
            else:
                for row in payments:
                    pay_box.add_widget(Label(
                        text=f"{row['payment_method']}  |  {row['transactions']} transaksi  |  {self.money(row['total'])}",
                        size_hint_y=None, height=dp(34),
                        color=(.10,.14,.20,1), font_size="11sp",
                        halign="left", valign="middle"
                    ))

            # Recent transactions
            recent_box = self.root.ids.dash_recent_sales
            recent_box.clear_widgets()
            recent = self.db.sales(5)
            if not recent:
                recent_box.add_widget(Label(
                    text="Belum ada transaksi.",
                    size_hint_y=None, height=dp(34),
                    color=(.35,.40,.48,1), font_size="11sp",
                    halign="left"
                ))
            else:
                for row in recent:
                    when = str(row["created_at"]).replace("T", " ")[:16]
                    recent_box.add_widget(Label(
                        text=f"{when}  |  {row['invoice']}  |  {row['payment_method']}  |  {self.money(row['total'])}",
                        size_hint_y=None, height=dp(36),
                        color=(.10,.14,.20,1), font_size="10sp",
                        halign="left", valign="middle"
                    ))
        except Exception:
            # Keep the existing app usable even if an optional dashboard query fails.
            self.log_startup_error()
    def refresh_pos_categories(self):
        if not hasattr(self, "root") or not self.root:
            return
        box = self.root.ids.get("pos_category_filter")
        if not box:
            return
        box.clear_widgets()
        current = getattr(self, "pos_category", "Semua")
        categories = ["Semua"] + [str(c["name"]) for c in self.db.categories()]
        for name in categories:
            active = name == current
            btn = Button(
                text=name, size_hint_x=None,
                width=max(dp(72), dp(18) + len(name) * dp(7)),
                background_normal="",
                background_color=(0.05, 0.60, 0.30, 1) if active else (0.92, 0.94, 0.97, 1),
                color=(1, 1, 1, 1) if active else (0.12, 0.16, 0.22, 1),
                font_size="12sp", bold=True
            )
            btn.bind(on_release=lambda b, cat=name: self.select_pos_category(cat))
            box.add_widget(btn)

    def select_pos_category(self, category):
        self.pos_category = category
        self.refresh_pos_categories()
        search = self.root.ids.search_pos.text if self.root and "search_pos" in self.root.ids else ""
        self.refresh_pos_products(search)

    def refresh_pos_products(self, search):
        grid = self.root.ids.product_grid
        grid.clear_widgets()
        products = self._v48_products(search)
        category = getattr(self, "pos_category", "Semua")
        if category != "Semua":
            products = [p for p in products if str(p["category_name"] or "") == category]
        for p in products[:100]:
            is_service = self._is_service_product(p)
            stock_text = "JASA" if is_service else f"Stok {float(p['stock']):g} {p['unit']}"
            card = ProductCard(product_id=p["id"], image_path=(p["image_path"] if "image_path" in p.keys() else ""))
            card.set_product_text(p["name"], f"{self.money(p['sell_price'])}  |  {stock_text}")
            cols = max(1, int(getattr(grid, "cols", 1)))
            gap = dp(8) * max(0, cols - 1)
            card_width = max(dp(240), (grid.width - gap) / cols)
            card.width = card_width
            card.bind(size=lambda instance, value: None)
            card.bind(on_release=lambda b, pid=p["id"]: self.add_to_cart(pid))
            grid.add_widget(card)

    def add_to_cart(self, product_id):
        p = self._v48_product_by_id(product_id)
        if not p:
            return
        is_service = self._is_service_product(p)
        if not is_service and float(p["stock"]) <= 0:
            self.info("Stok produk habis.")
            return
        for item in self.cart:
            if item["id"] == product_id:
                if not is_service and item["qty"] + 1 > float(p["stock"]):
                    self.info("Jumlah melebihi stok.")
                    return
                item["qty"] += 1
                item["line_total"] = item["qty"] * item["price"]
                self.update_cart_summary()
                return
        self.cart.append({
            "id": p["id"], "name": p["name"], "qty": 1,
            "price": float(p["sell_price"]), "discount": 0,
            "line_total": float(p["sell_price"]),
            "item_type": "JASA" if is_service else "BARANG",
        })
        self.update_cart_summary()

    def update_cart_summary(self):
        if not hasattr(self, "root") or not self.root:
            return
        subtotal, discount, tax, total, paid, change = self.recalculate_pos()
        total_items = sum(item["qty"] for item in self.cart)
        self.root.ids.cart_summary_items.text = f"{total_items:g} Item"
        self.root.ids.pos_total.text = self.money(total)

    def open_cart_popup(self):
        if not self.cart:
            self.info("Keranjang belanja masih kosong.")
            return

        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
        
        scroll = ScrollView(do_scroll_x=False)
        self.cart_popup_grid = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        self.cart_popup_grid.bind(minimum_height=self.cart_popup_grid.setter('height'))
        
        scroll.add_widget(self.cart_popup_grid)
        content.add_widget(scroll)

        checkout_box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(130), spacing=dp(6))

        total_val = sum(x["line_total"] for x in self.cart)
        self.popup_total_label = Label(
            text="Total Tagihan: " + self.money(total_val),
            bold=True, font_size="15sp", color=(0.05, 0.55, 0.25, 1),
            halign="left", valign="middle", size_hint_y=None, height=dp(26)
        )
        self.popup_total_label.bind(size=lambda instance, value: setattr(instance, 'text_size', value))

        discount_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        discount_lbl = Label(
            text="Diskon:", font_size="12sp", bold=True,
            color=(0.10, 0.14, 0.20, 1), size_hint_x=None, width=dp(100),
            halign="left", valign="middle"
        )
        discount_lbl.bind(size=lambda instance, value: setattr(instance, 'text_size', value))
        self.discount_input = TextInput(
            text="0", hint_text="Nominal diskon", multiline=False,
            input_filter="float", font_size="13sp", size_hint_y=1,
            background_normal="", background_color=(0.95, 0.96, 0.98, 1),
            foreground_color=(0.10, 0.14, 0.20, 1), cursor_color=(0.10, 0.40, 0.80, 1)
        )
        self.discount_input.bind(text=self._on_checkout_input_changed)
        discount_row.add_widget(discount_lbl)
        discount_row.add_widget(self.discount_input)

        payment_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        payment_lbl = Label(
            text="Pembayaran:", font_size="12sp", bold=True,
            color=(0.10, 0.14, 0.20, 1), size_hint_x=None, width=dp(100),
            halign="left", valign="middle"
        )
        payment_lbl.bind(size=lambda instance, value: setattr(instance, 'text_size', value))
        self.payment_spinner = Spinner(
            text="Tunai", values=("Tunai", "QRIS", "Transfer", "Debit/Kredit"),
            font_size="12sp"
        )
        self.payment_spinner.bind(text=self._on_payment_changed)
        payment_row.add_widget(payment_lbl)
        payment_row.add_widget(self.payment_spinner)

        pay_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        pay_lbl = Label(
            text="Uang Diterima:", font_size="12sp", bold=True,
            color=(0.10, 0.14, 0.20, 1), size_hint_x=None, width=dp(100),
            halign="left", valign="middle"
        )
        pay_lbl.bind(size=lambda instance, value: setattr(instance, 'text_size', value))

        self.paid_input = TextInput(
            hint_text="Masukkan uang pas/tunai", multiline=False,
            input_filter="float", font_size="13sp", size_hint_y=1,
            background_normal="", background_color=(0.95, 0.96, 0.98, 1),
            foreground_color=(0.10, 0.14, 0.20, 1), cursor_color=(0.10, 0.40, 0.80, 1)
        )
        self.paid_input.bind(text=self.calculate_change)

        pay_row.add_widget(pay_lbl)
        pay_row.add_widget(self.paid_input)

        # Nominal cepat dibuat responsif agar tidak keluar dari lebar popup
        # pada HP kecil. Tombol disusun 2x2, bukan 4 tombol dengan lebar tetap.
        quick_row = BoxLayout(size_hint_y=None, height=dp(74), spacing=dp(6))
        quick_label = Label(
            text="Cepat:", size_hint_x=None, width=dp(48), font_size="11sp",
            color=(0.30, 0.34, 0.40, 1), halign="left", valign="middle"
        )
        quick_label.bind(size=lambda instance, value: setattr(instance, 'text_size', value))
        quick_row.add_widget(quick_label)

        quick_grid = GridLayout(cols=2, rows=2, spacing=dp(5), size_hint_x=1)
        for amount in (10000, 20000, 50000, 100000):
            qb = Button(
                text=self.money(amount), font_size="10sp", size_hint_x=1, size_hint_y=1,
                background_normal="", background_color=(0.92,0.94,0.97,1),
                color=(0.08,0.12,0.18,1), bold=True
            )
            qb.bind(on_release=lambda btn, val=amount: self.set_quick_payment(val))
            quick_grid.add_widget(qb)
        quick_row.add_widget(quick_grid)

        self.popup_change_label = Label(
            text="Kembalian: Rp 0",
            bold=True, font_size="14sp", color=(0.10, 0.40, 0.80, 1),
            halign="left", valign="middle", size_hint_y=None, height=dp(26)
        )
        self.popup_change_label.bind(size=lambda instance, value: setattr(instance, 'text_size', value))

        btn_pay = Button(
            text="PROSES BAYAR", size_hint_y=None, height=dp(40),
            background_normal="", background_color=(0.05, 0.60, 0.30, 1),
            color=(1, 1, 1, 1), bold=True
        )
        btn_pay.bind(on_release=lambda instance: self.checkout())

        checkout_box.height = dp(294)
        checkout_box.add_widget(self.popup_total_label)
        checkout_box.add_widget(discount_row)
        checkout_box.add_widget(payment_row)
        checkout_box.add_widget(pay_row)
        checkout_box.add_widget(quick_row)
        checkout_box.add_widget(self.popup_change_label)
        checkout_box.add_widget(btn_pay)

        content.add_widget(checkout_box)

        self.cart_popup = WhitePopup(
            title="Keranjang Belanja",
            content=content,
            size_hint=(0.92, 0.88)
        )
        self.discount_input.text = "0"
        self.payment_spinner.text = "Tunai"
        self.refresh_cart_popup_grid()
        self.cart_popup.open()

    def _on_checkout_input_changed(self, *_):
        self.recalculate_pos()
        self._refresh_payment_display()

    def _on_payment_changed(self, *_):
        if not self.payment_spinner:
            return
        is_cash = self.payment_spinner.text == "Tunai"
        if self.paid_input:
            self.paid_input.disabled = not is_cash
            if not is_cash:
                _, _, _, total, _, _ = self.recalculate_pos()
                self.paid_input.text = str(int(total))
        self._refresh_payment_display()

    def _refresh_payment_display(self):
        if not self.popup_change_label:
            return
        _, _, _, total, _, _ = self.recalculate_pos()
        if self.payment_spinner and self.payment_spinner.text != "Tunai":
            self.popup_change_label.text = "Pembayaran non-tunai: lunas"
            self.popup_change_label.color = (0.10, 0.40, 0.80, 1)
            return
        text = self.paid_input.text if self.paid_input else ""
        try:
            paid_amount = float(text) if text else 0
        except ValueError:
            paid_amount = 0
        diff = paid_amount - total
        if diff >= 0:
            self.popup_change_label.text = f"Kembalian: {self.money(diff)}"
            self.popup_change_label.color = (0.10, 0.40, 0.80, 1)
        else:
            self.popup_change_label.text = f"Kurang: {self.money(abs(diff))}"
            self.popup_change_label.color = (0.80, 0.20, 0.20, 1)

    def set_quick_payment(self, amount):
        if getattr(self, "payment_spinner", None) and self.payment_spinner.text != "Tunai":
            self.payment_spinner.text = "Tunai"
        if getattr(self, "paid_input", None):
            self.paid_input.text = str(int(amount))
        self._refresh_payment_display()

    def calculate_change(self, instance, text):
        self._refresh_payment_display()

    def refresh_cart_popup_grid(self):
        if not self.cart_popup_grid:
            return
        
        self.cart_popup_grid.clear_widgets()
        for item in self.cart:
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))

            lbl = Label(
                text=f"{item['name']}\n{self.money(item['price'])} x {item['qty']:g} = {self.money(item['line_total'])}",
                halign="left", valign="middle", 
                color=(0.10, 0.14, 0.20, 1),
                font_size="12sp", bold=True
            )
            lbl.bind(size=lambda instance, value: setattr(instance, 'text_size', value))

            minus = Button(text="-", size_hint_x=None, width=dp(36),
                           background_normal="", background_color=(0.90, 0.92, 0.95, 1),
                           color=(0.08, 0.10, 0.14, 1), font_size="14sp", bold=True)
            plus = Button(text="+", size_hint_x=None, width=dp(36),
                          background_normal="", background_color=(0.88, 0.95, 0.91, 1),
                          color=(0.04, 0.48, 0.25, 1), font_size="14sp", bold=True)
            delete = Button(text="x", size_hint_x=None, width=dp(36),
                            background_normal="", background_color=(0.98, 0.90, 0.90, 1),
                            color=(0.72, 0.12, 0.12, 1), font_size="12sp", bold=True)
            
            minus.bind(on_release=lambda btn, iid=item["id"]: self.change_qty(iid, -1))
            plus.bind(on_release=lambda btn, iid=item["id"]: self.change_qty(iid, 1))
            delete.bind(on_release=lambda btn, iid=item["id"]: self.remove_cart(iid))
            
            row.add_widget(lbl)
            row.add_widget(minus)
            row.add_widget(plus)
            row.add_widget(delete)
            self.cart_popup_grid.add_widget(row)

        subtotal, discount, tax, total, paid, change = self.recalculate_pos()
        if self.popup_total_label:
            self.popup_total_label.text = "Total Tagihan: " + self.money(total)
        self._refresh_payment_display()

    def change_qty(self, product_id, delta):
        for item in self.cart:
            if item["id"] == product_id:
                p = self._v48_product_by_id(product_id)
                is_service = self._is_service_product(p)
                item["qty"] += delta
                if item["qty"] <= 0:
                    self.remove_cart(product_id)
                    return
                if not is_service and item["qty"] > float(p["stock"]):
                    item["qty"] = float(p["stock"])
                item["line_total"] = item["qty"] * item["price"]
                break
        self.refresh_cart_popup_grid() if self.cart_popup else None
        self.update_cart_summary()

    def remove_cart(self, product_id):
        self.cart = [x for x in self.cart if x["id"] != product_id]
        self.update_cart_summary()
        if not self.cart and self.cart_popup:
            self.cart_popup.dismiss()
        else:
            self.refresh_cart_popup_grid()

    def recalculate_pos(self, *_):
        subtotal = sum(float(x["line_total"]) for x in self.cart)
        discount = 0
        try:
            raw_discount = self.discount_input.text if getattr(self, "discount_input", None) else "0"
            discount = min(max(0, float(raw_discount or 0)), subtotal)
        except (ValueError, TypeError):
            discount = 0
        try:
            tax = max(0, float(self.tax_percent)) / 100 * max(0, subtotal - discount)
        except (ValueError, TypeError):
            tax = 0
        total = max(0, subtotal - discount + tax)
        if hasattr(self, "root") and self.root:
            if "pos_total" in self.root.ids:
                self.root.ids.pos_total.text = self.money(total)
        paid = total
        change = 0
        if getattr(self, "paid_input", None):
            try:
                paid = max(0, float(self.paid_input.text or 0))
            except (ValueError, TypeError):
                paid = 0
            change = max(0, paid - total)
        return subtotal, discount, tax, total, paid, change

    def generate_receipt_text(self, invoice, cart_items, total, paid, change, payment="Tunai", subtotal=None, discount=0, tax=0, cashier=None, created_at=None):
        width = 32 if str(self.paper_width) == "32" else 48
        lines = []

        def add_wrapped(value, align="left"):
            text = str(value or "").strip()
            if not text:
                return
            wrapped = textwrap.wrap(text, width=width, replace_whitespace=True,
                                    drop_whitespace=True, break_long_words=True) or [""]
            for part in wrapped:
                if align == "center":
                    lines.append(part.center(width))
                else:
                    lines.append(part[:width])

        add_wrapped(self.store_name, "center")
        add_wrapped(self.store_address, "center")
        if self.store_instagram:
            add_wrapped("Instagram: " + self.store_instagram, "center")
        if self.store_whatsapp:
            add_wrapped("WhatsApp: " + self.store_whatsapp, "center")

        lines.append("-" * width)
        add_wrapped("No  : " + invoice)
        add_wrapped("Tgl : " + (created_at or datetime.now().strftime("%Y-%m-%d %H:%M")))
        add_wrapped("Ksr : " + (cashier or self.cashier_name))
        add_wrapped("Pay : " + payment)
        lines.append("-" * width)

        for item in cart_items:
            add_wrapped(item["name"])
            qty_price = f"  {item['qty']:g} x {item['price']:,.0f}".replace(",", ".")
            item_total = f"{item['line_total']:,.0f}".replace(",", ".")
            spaces = width - len(qty_price) - len(item_total)
            if spaces >= 1:
                lines.append(qty_price + (" " * spaces) + item_total)
            else:
                lines.append(qty_price[:width])
                lines.append(item_total.rjust(width))

        lines.append("-" * width)
        subtotal_value = sum(float(x["line_total"]) for x in cart_items) if subtotal is None else float(subtotal)
        for label, value in (("Subtotal:", subtotal_value), ("Diskon  :", discount),
                             ("Pajak   :", tax), ("Total   :", total),
                             ("Bayar   :", paid), ("Kembali :", change)):
            val = self.money(value)
            prefix = label.ljust(12)
            lines.append(prefix + val.rjust(max(1, width - len(prefix))))

        lines.append("-" * width)
        add_wrapped(self.receipt_footer, "center")
        return "\n".join(lines)

    def print_receipt(self, receipt_text):
        printer = ThermalPrinterManager(
            self.bt_mac_address,
            line_width=self.paper_width,
            auto_cut=self.auto_cut,
            feed_lines=self.feed_lines,
        )
        return printer.print_receipt(receipt_text)

    def test_print(self):
        sample = (
            f"{self.store_name}\n"
            "--------------------------------\n"
            "TES CETAK PRINTER THERMAL\n"
            "Koneksi Bluetooth Berhasil!\n"
            f"Kertas: {'58mm' if str(self.paper_width) == '32' else '80mm'}\n"
            "--------------------------------"
        )
        success, msg = self.print_receipt(sample)
        self.info(msg, "Tes Cetak")

    def _checkout_v3(self):
        if not self.cart:
            self.info("Keranjang masih kosong.")
            return

        subtotal, discount, tax, total, _, _ = self.recalculate_pos()
        payment = self.payment_spinner.text if getattr(self, "payment_spinner", None) else "Tunai"

        if payment == "Tunai":
            try:
                paid_val = float(self.paid_input.text or 0) if self.paid_input else 0
            except (ValueError, TypeError):
                paid_val = 0
            if paid_val < total:
                self.info("Uang yang diterima kurang dari total belanja!")
                return
            change_val = paid_val - total
        else:
            paid_val = total
            change_val = 0

        # Database V4.x already owns the sale transaction and stock decrement.
        # For non-stock services, temporarily expose a safe virtual stock value
        # only during save_sale, then restore the original value immediately.
        virtualized = []
        try:
            for item in self.cart:
                p = self._v48_product_by_id(item["id"])
                if p and (self._is_service_product(p)):
                    original = float(p["stock"])
                    virtualized.append((item["id"], original))
                    self.db.conn.execute("UPDATE products SET stock=? WHERE id=?", (999999999.0, item["id"]))
            self.db.conn.commit()

            invoice = self.db.save_sale(
                self.cart, subtotal, discount, tax, total, paid_val, change_val, payment
            )
        except ValueError as exc:
            for pid, original in virtualized:
                self.db.conn.execute("UPDATE products SET stock=? WHERE id=?", (original, pid))
            self.db.conn.commit()
            self.info(str(exc), "Transaksi Ditolak")
            self.refresh_all()
            return
        except Exception:
            for pid, original in virtualized:
                self.db.conn.execute("UPDATE products SET stock=? WHERE id=?", (original, pid))
            self.db.conn.commit()
            self.log_startup_error()
            self.info("Transaksi gagal disimpan. Tidak ada stok yang dikurangi.", "Kesalahan")
            return

        # Restore service/non-stock items to their previous quantity (normally 0).
        try:
            for pid, original in virtualized:
                self.db.conn.execute("UPDATE products SET stock=? WHERE id=?", (original, pid))
            self.db.conn.commit()
        except Exception:
            self.log_startup_error()

        receipt_text = self.generate_receipt_text(
            invoice, self.cart, total, paid_val, change_val, payment=payment,
            subtotal=subtotal, discount=discount, tax=tax, cashier=self.cashier_name
        )
        print_ok, print_msg = self.print_receipt(receipt_text)

        self.cart = []
        if self.cart_popup:
            self.cart_popup.dismiss()
        self.refresh_all()

        self.info(
            f"Transaksi Berhasil!\n\n"
            f"Nota: {invoice}\n"
            f"Metode: {payment}\n"
            f"Total: {self.money(total)}\n"
            f"Bayar: {self.money(paid_val)}\n"
            f"Kembali: {self.money(change_val)}\n\n"
            f"Status Printer: {print_msg}"
        )


    # ==========================================
    # V4.6 PROFESSIONAL BUSINESS LAYER
    # ==========================================
    def init_v46_schema(self):
        """Create V4.6 business tables without changing the existing schema."""
        c = self.db.conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            pin TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Kasir',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            opening_cash REAL NOT NULL DEFAULT 0,
            opened_at TEXT NOT NULL,
            closing_cash REAL,
            expected_cash REAL,
            difference REAL,
            closed_at TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS cash_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id INTEGER,
            user_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(shift_id) REFERENCES shifts(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER,
            invoice TEXT NOT NULL UNIQUE,
            total REAL NOT NULL DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            user_id INTEGER,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS purchase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty REAL NOT NULL,
            cost_price REAL NOT NULL,
            line_total REAL NOT NULL,
            FOREIGN KEY(purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            invoice TEXT NOT NULL,
            amount REAL NOT NULL,
            reason TEXT DEFAULT '',
            user_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(sale_id),
            FOREIGN KEY(sale_id) REFERENCES sales(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)
        now = datetime.now().isoformat(timespec="seconds")
        if not c.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
            c.execute("INSERT INTO users(username,pin,role,created_at) VALUES (?,?,?,?)",
                      ('admin', '1234', 'Admin', now))
        self.db.conn.commit()
        row = c.execute("SELECT id,username,role FROM users WHERE username=? AND active=1",
                         (self.db.get_setting('active_username', 'admin'),)).fetchone()
        if not row:
            row = c.execute("SELECT id,username,role FROM users WHERE username='admin'").fetchone()
        self.active_user = dict(row) if row else {'id': 1, 'username': 'admin', 'role': 'Admin'}

        # V4.8: universal product/service fields. Existing databases are kept intact.
        product_columns = {r[1] for r in c.execute("PRAGMA table_info(products)").fetchall()}
        if "item_type" not in product_columns:
            c.execute("ALTER TABLE products ADD COLUMN item_type TEXT NOT NULL DEFAULT 'BARANG'")
        if "track_stock" not in product_columns:
            c.execute("ALTER TABLE products ADD COLUMN track_stock INTEGER NOT NULL DEFAULT 1")
        c.execute("UPDATE products SET item_type='BARANG' WHERE item_type IS NULL OR item_type=''")
        c.execute("UPDATE products SET track_stock=1 WHERE track_stock IS NULL")
        self.db.conn.commit()

    def _audit(self, action, detail=''):
        try:
            u = getattr(self, 'active_user', {'id': None, 'username': self.cashier_name})
            self.db.conn.execute(
                "INSERT INTO audit_logs(user_id,username,action,detail,created_at) VALUES (?,?,?,?,?)",
                (u.get('id'), u.get('username', self.cashier_name), str(action), str(detail),
                 datetime.now().isoformat(timespec='seconds'))
            )
            self.db.conn.commit()
        except Exception:
            pass

    def _active_shift(self):
        try:
            return self.db.conn.execute(
                "SELECT * FROM shifts WHERE status='OPEN' AND user_id=? ORDER BY id DESC LIMIT 1",
                (getattr(self, 'active_user', {}).get('id', 1),)
            ).fetchone()
        except Exception:
            return None

    def _cash_summary(self, shift_id):
        sh = self.db.conn.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
        if not sh:
            return 0, 0, 0, 0
        cash_sales = self.db.conn.execute("""
            SELECT COALESCE(SUM(total),0) total FROM sales
            WHERE payment_method='Tunai' AND created_at>=?
              AND created_at<=COALESCE(?, datetime('now','localtime'))
        """, (sh['opened_at'], sh['closed_at'])).fetchone()['total']
        movements = self.db.conn.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN movement_type='IN' THEN amount ELSE 0 END),0) cash_in,
              COALESCE(SUM(CASE WHEN movement_type='OUT' THEN amount ELSE 0 END),0) cash_out
            FROM cash_movements WHERE shift_id=?
        """, (shift_id,)).fetchone()
        expected = float(sh['opening_cash']) + float(cash_sales) + float(movements['cash_in']) - float(movements['cash_out'])
        return float(sh['opening_cash']), float(cash_sales), float(movements['cash_in']), float(movements['cash_out'])

    def checkout(self):
        before = len(self.db.sales(1)) if hasattr(self.db, 'sales') else 0
        self._checkout_v3()
        try:
            if len(self.cart) == 0:
                # _checkout_v3 clears cart only after a successful save.
                # Find the newest sale and audit it without changing V3 behavior.
                sale = self.db.sales(1)[0] if self.db.sales(1) else None
                if sale:
                    self._audit('SALE', f"{sale['invoice']} | {self.money(sale['total'])} | {sale['payment_method']}")
        except Exception:
            pass

    def business_center_popup(self):
        """V4.7 interactive business center using the existing V4.6 functions."""
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        user = getattr(self, 'active_user', {'username': self.cashier_name, 'role': 'Kasir'})
        sh = self._active_shift()
        header = CardBox(orientation='vertical', size_hint_y=None, height=dp(82), padding=dp(12), spacing=dp(3))
        header.add_widget(Label(text='Pusat Operasional Toko', size_hint_y=None, height=dp(28),
                                font_size='16sp', bold=True, color=(.08,.12,.18,1), halign='left'))
        header.add_widget(Label(text=f"{user.get('username', self.cashier_name)}  •  {user.get('role', 'Kasir')}",
                                size_hint_y=None, height=dp(20), font_size='11sp', color=(.35,.40,.48,1), halign='left'))
        if sh:
            opening, sales, cin, cout = self._cash_summary(sh['id'])
            expected = opening + sales + cin - cout
            chip_text = f"SHIFT AKTIF  •  Kas {self.money(expected)}"
        else:
            chip_text = "SHIFT BELUM DIBUKA  •  Buka shift sebelum transaksi tunai"
        chip = StatusChip(text=chip_text)
        chip.color = (.05,.45,.25,1) if sh else (.65,.35,.05,1)
        header.add_widget(chip)
        content.add_widget(header)

        scroll = ScrollView(do_scroll_x=False, bar_width=0)
        body = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_y=None)
        body.bind(minimum_height=body.setter('height'))
        body.add_widget(Label(text='AKSES CEPAT', size_hint_y=None, height=dp(22), font_size='11sp',
                              bold=True, color=(.35,.40,.48,1), halign='left'))
        grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(240))
        actions = [
            ('LOGIN KASIR', self.login_popup),
            ('SHIFT & KAS', self.shift_popup),
            ('KAS MASUK / KELUAR', self.cash_movement_popup),
            ('SUPPLIER & PEMBELIAN', self.supplier_popup),
            ('MANAJEMEN USER', self.user_management_popup),
            ('RETUR TRANSAKSI', self.return_popup),
            ('AUDIT LOG', self.audit_popup),
            ('INVENTORY', self.inventory_popup),
        ]
        for text, fn in actions:
            b = QuickCard(text=text, size_hint_y=None, height=dp(54))
            b.bind(on_release=lambda _b, f=fn: (self._close_popup(), f()))
            grid.add_widget(b)
        body.add_widget(grid)
        body.add_widget(Label(text='RINGKASAN SHIFT', size_hint_y=None, height=dp(22), font_size='11sp',
                              bold=True, color=(.35,.40,.48,1), halign='left'))
        status_card = CardBox(orientation='vertical', size_hint_y=None, height=dp(88), spacing=dp(2))
        if sh:
            opening, sales, cin, cout = self._cash_summary(sh['id'])
            expected = opening + sales + cin - cout
            lines = [f"Kas awal     {self.money(opening)}", f"Tunai        {self.money(sales)}",
                     f"Masuk/Keluar {self.money(cin - cout)}", f"Seharusnya   {self.money(expected)}"]
        else:
            lines = ['Belum ada shift aktif.', 'Tekan SHIFT & KAS untuk membuka shift.']
        for line in lines:
            status_card.add_widget(Label(text=line, size_hint_y=None, height=dp(20), font_size='10sp',
                                         color=(.10,.14,.20,1), halign='left'))
        body.add_widget(status_card)
        scroll.add_widget(body)
        content.add_widget(scroll)
        close = Button(text='TUTUP', size_hint_y=None, height=dp(42), background_normal='',
                       background_color=(.88,.91,.95,1), color=(.08,.11,.16,1), bold=True)
        content.add_widget(close)
        self._business_popup = WhitePopup(title='V4.7 BUSINESS CENTER', content=content,
                                          size_hint=(.94, .86), auto_dismiss=True)
        close.bind(on_release=self._business_popup.dismiss)
        self._business_popup.open()

    def _close_popup(self):
        p = getattr(self, '_business_popup', None)
        if p:
            try: p.dismiss()
            except Exception: pass

    def login_popup(self):
        box = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        user = TextInput(hint_text='Username', multiline=False, size_hint_y=None, height=dp(44))
        pin = TextInput(hint_text='PIN', password=True, multiline=False, input_filter='int', size_hint_y=None, height=dp(44))
        status = Label(text='Masuk dengan akun kasir.', size_hint_y=None, height=dp(32), font_size='11sp')
        box.add_widget(user); box.add_widget(pin); box.add_widget(status)
        btn = Button(text='MASUK', size_hint_y=None, height=dp(46), background_normal='', background_color=(.04,.58,.30,1), color=(1,1,1,1), bold=True)
        box.add_widget(btn)
        pop = WhitePopup(title='LOGIN KASIR', content=box, size_hint=(.88,.48))
        def do_login(*_):
            row = self.db.conn.execute("SELECT * FROM users WHERE username=? AND pin=? AND active=1", (user.text.strip(), pin.text.strip())).fetchone()
            if not row:
                status.text = 'Username atau PIN salah.'
                return
            self.active_user = dict(row)
            self.cashier_name = row['username']
            self.db.set_setting('cashier_name', row['username'])
            self.db.set_setting('active_username', row['username'])
            self._audit('LOGIN', f"Role={row['role']}")
            pop.dismiss()
            self.info(f"Login berhasil.\nKasir: {row['username']}\nRole: {row['role']}", 'Login')
            self.refresh_dashboard()
        btn.bind(on_release=do_login)
        pop.open()

    def shift_popup(self):
        sh = self._active_shift()
        if sh:
            opening, sales, cin, cout = self._cash_summary(sh['id'])
            expected = opening + sales + cin - cout
            box = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(7))
            for t in [f"Kasir: {self.active_user['username']}", f"Buka: {sh['opened_at']}", f"Kas awal: {self.money(opening)}", f"Penjualan tunai: {self.money(sales)}", f"Kas masuk: {self.money(cin)}", f"Kas keluar: {self.money(cout)}", f"Kas seharusnya: {self.money(expected)}"]:
                box.add_widget(Label(text=t, size_hint_y=None, height=dp(28), halign='left'))
            close_input = TextInput(hint_text='Kas aktual saat tutup', input_filter='float', multiline=False, size_hint_y=None, height=dp(44))
            box.add_widget(close_input)
            b = Button(text='TUTUP SHIFT', size_hint_y=None, height=dp(46), background_normal='', background_color=(.75,.25,.12,1), color=(1,1,1,1), bold=True)
            box.add_widget(b)
            pop = WhitePopup(title='SHIFT AKTIF', content=box, size_hint=(.90,.72))
            def close_shift(*_):
                try: actual = float(close_input.text or 0)
                except ValueError: actual = -1
                if actual < 0: self.info('Masukkan kas aktual yang valid.'); return
                diff = actual - expected
                self.db.conn.execute("UPDATE shifts SET closing_cash=?,expected_cash=?,difference=?,closed_at=?,status='CLOSED' WHERE id=?", (actual,expected,diff,datetime.now().isoformat(timespec='seconds'),sh['id']))
                self.db.conn.commit(); self._audit('CLOSE_SHIFT', f"Shift {sh['id']} | Selisih {self.money(diff)}")
                pop.dismiss(); self.info(f"Shift ditutup.\nSeharusnya: {self.money(expected)}\nAktual: {self.money(actual)}\nSelisih: {self.money(diff)}", 'Tutup Shift'); self.refresh_dashboard()
            b.bind(on_release=close_shift); pop.open(); return
        box = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        box.add_widget(Label(text=f"Kasir: {self.active_user['username']}", size_hint_y=None, height=dp(30)))
        opening = TextInput(hint_text='Modal awal kas', input_filter='float', multiline=False, size_hint_y=None, height=dp(44))
        box.add_widget(opening)
        b = Button(text='BUKA SHIFT', size_hint_y=None, height=dp(46), background_normal='', background_color=(.04,.58,.30,1), color=(1,1,1,1), bold=True)
        box.add_widget(b)
        pop = WhitePopup(title='BUKA SHIFT', content=box, size_hint=(.88,.42))
        def open_shift(*_):
            try: amount=float(opening.text or 0)
            except ValueError: amount=-1
            if amount < 0: self.info('Modal awal tidak valid.'); return
            now=datetime.now().isoformat(timespec='seconds')
            cur=self.db.conn.execute("INSERT INTO shifts(user_id,opening_cash,opened_at,status) VALUES (?,?,?,'OPEN')",(self.active_user['id'],amount,now))
            self.db.conn.commit(); self._audit('OPEN_SHIFT', f"Shift {cur.lastrowid} | Modal {self.money(amount)}")
            pop.dismiss(); self.info(f"Shift dibuka dengan modal {self.money(amount)}.",'Shift'); self.refresh_dashboard()
        b.bind(on_release=open_shift); pop.open()

    def cash_movement_popup(self):
        sh=self._active_shift()
        if not sh:
            self.info('Buka shift terlebih dahulu.','Kas'); return
        box=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8))
        sp=Spinner(text='Kas Masuk',values=('Kas Masuk','Kas Keluar'),size_hint_y=None,height=dp(44))
        amount=TextInput(hint_text='Nominal',input_filter='float',multiline=False,size_hint_y=None,height=dp(44))
        note=TextInput(hint_text='Keterangan',multiline=False,size_hint_y=None,height=dp(44))
        save=Button(text='SIMPAN',size_hint_y=None,height=dp(46),background_normal='',background_color=(.10,.42,.72,1),color=(1,1,1,1),bold=True)
        for w in (sp,amount,note,save): box.add_widget(w)
        pop=WhitePopup(title='KAS MASUK / KAS KELUAR',content=box,size_hint=(.90,.55))
        def save_move(*_):
            try: val=float(amount.text or 0)
            except ValueError: val=0
            if val<=0: self.info('Nominal harus lebih dari 0.'); return
            typ='IN' if sp.text=='Kas Masuk' else 'OUT'
            self.db.conn.execute("INSERT INTO cash_movements(shift_id,user_id,movement_type,amount,note,created_at) VALUES (?,?,?,?,?,?)",(sh['id'],self.active_user['id'],typ,val,note.text.strip(),datetime.now().isoformat(timespec='seconds')))
            self.db.conn.commit(); self._audit('CASH_'+typ, f"{self.money(val)} | {note.text.strip()}")
            pop.dismiss(); self.info('Pergerakan kas berhasil disimpan.','Kas'); self.refresh_dashboard()
        save.bind(on_release=save_move); pop.open()

    def user_management_popup(self):
        if getattr(self, 'active_user', {}).get('role') != 'Admin':
            self.info('Hanya Admin yang dapat mengelola user.', 'Akses Ditolak')
            return
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(6))
        rows=self.db.conn.execute("SELECT * FROM users ORDER BY active DESC, username").fetchall()
        grid=GridLayout(cols=1,spacing=dp(4),size_hint_y=None); grid.bind(minimum_height=grid.setter('height'))
        for r in rows:
            grid.add_widget(Label(text=f"{r['username']} | {r['role']} | {'AKTIF' if r['active'] else 'NONAKTIF'}",size_hint_y=None,height=dp(34),halign='left'))
        scroll=ScrollView(do_scroll_x=False); scroll.add_widget(grid); box.add_widget(scroll)
        add=Button(text='TAMBAH USER',size_hint_y=None,height=dp(44),background_normal='',background_color=(.04,.58,.30,1),color=(1,1,1,1),bold=True); box.add_widget(add)
        pop=WhitePopup(title='MANAJEMEN USER',content=box,size_hint=(.92,.72))
        def add_user(*_):
            form=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(7))
            username=TextInput(hint_text='Username',multiline=False,size_hint_y=None,height=dp(42))
            pin=TextInput(hint_text='PIN 4-8 digit',password=True,input_filter='int',multiline=False,size_hint_y=None,height=dp(42))
            role=Spinner(text='Kasir',values=('Kasir','Admin'),size_hint_y=None,height=dp(42))
            save=Button(text='SIMPAN USER',size_hint_y=None,height=dp(44),background_normal='',background_color=(.04,.58,.30,1),color=(1,1,1,1))
            for w in (username,pin,role,save): form.add_widget(w)
            pp=WhitePopup(title='TAMBAH USER',content=form,size_hint=(.90,.58))
            def save_u(*_):
                u=username.text.strip(); p=pin.text.strip()
                if len(u)<3 or not p.isdigit() or not (4<=len(p)<=8): self.info('Username minimal 3 karakter dan PIN 4-8 digit.'); return
                try:
                    self.db.conn.execute("INSERT INTO users(username,pin,role,created_at) VALUES (?,?,?,?)",(u,p,role.text,datetime.now().isoformat(timespec='seconds')))
                    self.db.conn.commit()
                except Exception:
                    self.info('Username sudah digunakan.'); return
                self._audit('ADD_USER',f"{u} | {role.text}"); pp.dismiss(); pop.dismiss(); self.user_management_popup()
            save.bind(on_release=save_u); pp.open()
        add.bind(on_release=add_user); pop.open()

    def supplier_popup(self):
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(6))
        rows=self.db.conn.execute("SELECT * FROM suppliers WHERE active=1 ORDER BY name").fetchall()
        scroll=ScrollView(do_scroll_x=False); grid=GridLayout(cols=1,spacing=dp(4),size_hint_y=None); grid.bind(minimum_height=grid.setter('height'))
        if not rows: grid.add_widget(Label(text='Belum ada supplier.',size_hint_y=None,height=dp(34)))
        for r in rows: grid.add_widget(Label(text=f"{r['name']} | {r['phone'] or '-'}\n{r['address'] or '-'}",size_hint_y=None,height=dp(52),halign='left'))
        scroll.add_widget(grid); box.add_widget(scroll)
        button_row=BoxLayout(size_hint_y=None,height=dp(44),spacing=dp(6))
        add=Button(text='TAMBAH SUPPLIER',background_normal='',background_color=(.04,.58,.30,1),color=(1,1,1,1),bold=True)
        buy=Button(text='CATAT PEMBELIAN',background_normal='',background_color=(.10,.42,.72,1),color=(1,1,1,1),bold=True)
        button_row.add_widget(add); button_row.add_widget(buy); box.add_widget(button_row)
        pop=WhitePopup(title='SUPPLIER',content=box,size_hint=(.92,.72))
        def add_supplier(*_):
            form=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(7))
            name=TextInput(hint_text='Nama supplier',multiline=False,size_hint_y=None,height=dp(42)); phone=TextInput(hint_text='Telepon',multiline=False,size_hint_y=None,height=dp(42)); addr=TextInput(hint_text='Alamat',multiline=False,size_hint_y=None,height=dp(42)); save=Button(text='SIMPAN',size_hint_y=None,height=dp(44),background_normal='',background_color=(.04,.58,.30,1),color=(1,1,1,1))
            for w in (name,phone,addr,save): form.add_widget(w)
            pp=WhitePopup(title='TAMBAH SUPPLIER',content=form,size_hint=(.90,.55))
            def save_s(*_):
                if not name.text.strip(): self.info('Nama supplier wajib diisi.'); return
                self.db.conn.execute("INSERT INTO suppliers(name,phone,address,created_at) VALUES (?,?,?,?)",(name.text.strip(),phone.text.strip(),addr.text.strip(),datetime.now().isoformat(timespec='seconds'))); self.db.conn.commit(); self._audit('ADD_SUPPLIER',name.text.strip()); pp.dismiss(); pop.dismiss(); self.supplier_popup()
            save.bind(on_release=save_s); pp.open()
        add.bind(on_release=add_supplier)
        def purchase_form(*_):
            suppliers=self.db.conn.execute("SELECT * FROM suppliers WHERE active=1 ORDER BY name").fetchall()
            products=self._v48_products("")
            if not suppliers or not products:
                self.info('Supplier dan produk harus tersedia terlebih dahulu.'); return
            form=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(6))
            svals=[f"{r['id']}|{r['name']}" for r in suppliers]
            pvals=[f"{r['id']}|{r['name']}" for r in products]
            sp=Spinner(text=svals[0],values=svals,size_hint_y=None,height=dp(42))
            pr=Spinner(text=pvals[0],values=pvals,size_hint_y=None,height=dp(42))
            qty=TextInput(hint_text='Jumlah stok masuk',input_filter='float',multiline=False,size_hint_y=None,height=dp(42))
            cost=TextInput(hint_text='Harga modal per unit',input_filter='float',multiline=False,size_hint_y=None,height=dp(42))
            note=TextInput(hint_text='Catatan pembelian',multiline=False,size_hint_y=None,height=dp(42))
            save=Button(text='SIMPAN PEMBELIAN',size_hint_y=None,height=dp(44),background_normal='',background_color=(.04,.58,.30,1),color=(1,1,1,1),bold=True)
            for w in (sp,pr,qty,cost,note,save): form.add_widget(w)
            pp=WhitePopup(title='CATAT PEMBELIAN',content=form,size_hint=(.92,.76))
            def save_purchase(*_):
                try:
                    sid=int(sp.text.split('|',1)[0]); pid=int(pr.text.split('|',1)[0]); q=float(qty.text or 0); cp=float(cost.text or 0)
                except Exception: self.info('Data pembelian tidak valid.'); return
                if q<=0 or cp<0: self.info('Jumlah atau harga modal tidak valid.'); return
                prod=self._v48_product_by_id(pid);
                if self._is_service_product(prod):
                    self.info("Item jasa tidak dapat dicatat sebagai pembelian stok.", "Pembelian"); return
                before=float(prod['stock'])
                total=q*cp; inv='PUR'+datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]; now=datetime.now().isoformat(timespec='seconds')
                try:
                    self.db.conn.execute('BEGIN')
                    self.db.conn.execute("INSERT INTO purchases(supplier_id,invoice,total,note,created_at,user_id) VALUES (?,?,?,?,?,?)",(sid,inv,total,note.text.strip(),now,self.active_user['id']))
                    pur_id=self.db.conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                    self.db.conn.execute("INSERT INTO purchase_items(purchase_id,product_id,qty,cost_price,line_total) VALUES (?,?,?,?,?)",(pur_id,pid,q,cp,total))
                    self.db.conn.execute("UPDATE products SET stock=stock+?, buy_price=? WHERE id=?",(q,cp,pid))
                    self.db.conn.execute("INSERT INTO stock_movements(product_id,product_name,movement_type,qty,stock_before,stock_after,reference,note,created_at) VALUES (?,?,?,?,?,?,?,?,?)",(pid,prod['name'],'PEMBELIAN',q,before,before+q,inv,note.text.strip(),now))
                    self.db.conn.commit()
                except Exception as e:
                    self.db.conn.rollback(); self.info(f'Pembelian gagal: {e}','Pembelian'); return
                self._audit('PURCHASE',f"{inv} | {prod['name']} | {q:g} | {self.money(total)}")
                pp.dismiss(); pop.dismiss(); self.refresh_all(); self.info(
                    f"Pembelian tersimpan.\nNo: {inv}\nStok bertambah: {q:g} {prod['unit']}",
                    'Pembelian'
                )
            save.bind(on_release=save_purchase); pp.open()
        buy.bind(on_release=purchase_form); pop.open()

    def return_popup(self):
        box=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8))
        inv=TextInput(hint_text='Nomor invoice',multiline=False,size_hint_y=None,height=dp(44)); reason=TextInput(hint_text='Alasan retur',multiline=False,size_hint_y=None,height=dp(44)); info=Label(text='Retur penuh: seluruh item invoice dikembalikan ke stok.',size_hint_y=None,height=dp(42),font_size='11sp'); btn=Button(text='PROSES RETUR',size_hint_y=None,height=dp(46),background_normal='',background_color=(.75,.25,.12,1),color=(1,1,1,1),bold=True)
        for w in (inv,reason,info,btn): box.add_widget(w)
        pop=WhitePopup(title='RETUR TRANSAKSI',content=box,size_hint=(.90,.52))
        def process(*_):
            row=self.db.conn.execute("SELECT * FROM sales WHERE invoice=?",(inv.text.strip(),)).fetchone()
            if not row: self.info('Invoice tidak ditemukan.'); return
            if self.db.conn.execute('SELECT 1 FROM returns WHERE sale_id=?',(row['id'],)).fetchone(): self.info('Invoice ini sudah pernah diretur.'); return
            items=self.db.conn.execute('SELECT * FROM sale_items WHERE sale_id=?',(row['id'],)).fetchall()
            try:
                self.db.conn.execute('BEGIN')
                for it in items:
                    prod = self._v48_product_by_id(it['product_id'])
                    if self._is_service_product(prod):
                        continue
                    self.db.conn.execute('UPDATE products SET stock=stock+? WHERE id=?',(it['qty'],it['product_id']))
                    p=self.db.conn.execute('SELECT name,stock FROM products WHERE id=?',(it['product_id'],)).fetchone()
                    self.db.conn.execute("INSERT INTO stock_movements(product_id,product_name,movement_type,qty,stock_before,stock_after,reference,note,created_at) VALUES (?,?,?,?,?,?,?,?,?)",(it['product_id'],it['product_name'],'RETUR',it['qty'],float(p['stock'])-float(it['qty']),float(p['stock']),row['invoice'],reason.text.strip(),datetime.now().isoformat(timespec='seconds')))
                self.db.conn.execute("INSERT INTO returns(sale_id,invoice,amount,reason,user_id,created_at) VALUES (?,?,?,?,?,?)",(row['id'],row['invoice'],row['total'],reason.text.strip(),self.active_user['id'],datetime.now().isoformat(timespec='seconds')))
                self.db.conn.commit()
            except Exception as e:
                self.db.conn.rollback(); self.info(f'Retur gagal: {e}','Retur'); return
            self._audit('RETURN',f"{row['invoice']} | {self.money(row['total'])}"); pop.dismiss(); self.refresh_all(); self.info(f"Retur berhasil.\nStok dikembalikan untuk invoice {row['invoice']}.",'Retur')
        btn.bind(on_release=process); pop.open()

    def audit_popup(self):
        rows=self.db.conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 60").fetchall()
        grid=GridLayout(cols=1,spacing=dp(3),size_hint_y=None); grid.bind(minimum_height=grid.setter('height'))
        if not rows: grid.add_widget(Label(text='Belum ada aktivitas.',size_hint_y=None,height=dp(34)))
        for r in rows:
            grid.add_widget(Label(text=f"{r['created_at']} | {r['username']}\n{r['action']} — {r['detail']}",size_hint_y=None,height=dp(52),halign='left',valign='middle',text_size=(None,None),font_size='10sp'))
        scroll=ScrollView(do_scroll_x=False); scroll.add_widget(grid)
        box=BoxLayout(orientation='vertical',padding=dp(8)); box.add_widget(scroll)
        WhitePopup(title='AUDIT LOG',content=box,size_hint=(.94,.82)).open()

    def init_product_image_schema(self):
        """Add the optional product image path without changing existing data."""
        try:
            cols = [r[1] for r in self.db.conn.execute("PRAGMA table_info(products)").fetchall()]
            if "image_path" not in cols:
                self.db.conn.execute("ALTER TABLE products ADD COLUMN image_path TEXT DEFAULT ''")
                self.db.conn.commit()
        except Exception as exc:
            print("Product image schema migration skipped:", exc)

    def _product_image_dir(self):
        path = os.path.join(self.user_data_dir, "product_images")
        os.makedirs(path, exist_ok=True)
        return path

    def _copy_image_file(self, source_path, preferred_ext=".jpg"):
        if not source_path or not os.path.isfile(source_path):
            return ""
        ext = os.path.splitext(source_path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = preferred_ext
        dest = os.path.join(self._product_image_dir(),
                            "img_" + datetime.now().strftime("%Y%m%d%H%M%S%f") + ext)
        shutil.copy2(source_path, dest)
        return dest

    def _copy_android_uri_to_file(self, uri):
        """Copy an Android content:// URI into app-private storage."""
        try:
            from jnius import autoclass, jarray
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            resolver = PythonActivity.mActivity.getContentResolver()
            mime = resolver.getType(uri) or "image/jpeg"
            mime_text = str(mime).lower()
            if "png" in mime_text:
                ext = ".png"
            elif "webp" in mime_text:
                ext = ".webp"
            elif "jpeg" in mime_text or "jpg" in mime_text:
                ext = ".jpg"
            else:
                ext = ".jpg"
            dest = os.path.join(self._product_image_dir(),
                                "img_" + datetime.now().strftime("%Y%m%d%H%M%S%f") + ext)
            stream = resolver.openInputStream(uri)
            if stream is None:
                return ""
            FileOutputStream = autoclass("java.io.FileOutputStream")
            out = FileOutputStream(dest)
            buf = jarray.zeros(8192, 'b')
            try:
                while True:
                    n = stream.read(buf)
                    if n is None or int(n) < 0:
                        break
                    if int(n) > 0:
                        out.write(buf, 0, int(n))
            finally:
                try:
                    stream.close()
                except Exception:
                    pass
                try:
                    out.close()
                except Exception:
                    pass
            return dest if os.path.exists(dest) else ""
        except Exception as exc:
            print("Gagal menyalin foto Android:", exc)
            return ""

    def _pick_product_image(self, preview=None, status_label=None):
        """Open Android's system image picker without changing POS/database logic.

        Uses the Android Photo Picker on API 33+ and falls back to
        ACTION_OPEN_DOCUMENT / ACTION_GET_CONTENT on older Android versions.
        The picker is launched directly (no chooser) to avoid OEM chooser
        failures seen on some phones.
        """
        self._product_image_preview = preview
        self._product_image_status = status_label
        self._image_picker_request = 49104

        try:
            from android import activity
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
        except Exception as exc:
            print("Android photo picker import gagal:", repr(exc))
            self._set_product_image_status("Pemilih foto Android tidak tersedia pada APK ini.")
            return

        # Avoid duplicate callbacks if the button is pressed twice.
        try:
            if getattr(self, "_image_picker_bound", False):
                activity.unbind(on_activity_result=self._on_product_image_result)
        except Exception:
            pass
        self._image_picker_bound = False

        try:
            activity.bind(on_activity_result=self._on_product_image_result)
            self._image_picker_bound = True
        except Exception as exc:
            print("Bind activity result gagal:", repr(exc))
            self._set_product_image_status("Pemilih foto gagal disiapkan.")
            return

        try:
            android_activity = PythonActivity.mActivity
            if android_activity is None:
                raise RuntimeError("PythonActivity.mActivity kosong")

            # Android 13+ system Photo Picker. No storage permission is needed.
            picker_intent = None
            try:
                Build = autoclass("android.os.Build")
                if int(Build.VERSION.SDK_INT) >= 33:
                    picker_intent = Intent("android.provider.action.PICK_IMAGES")
                    picker_intent.setType("image/*")
            except Exception as exc:
                print("Photo Picker API tidak tersedia:", repr(exc))

            # Android 4.4+ document provider fallback.
            if picker_intent is None:
                try:
                    picker_intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
                    picker_intent.addCategory(Intent.CATEGORY_OPENABLE)
                    picker_intent.setType("image/*")
                    picker_intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                except Exception as exc:
                    print("ACTION_OPEN_DOCUMENT gagal dibuat:", repr(exc))
                    picker_intent = Intent(Intent.ACTION_GET_CONTENT)
                    picker_intent.addCategory(Intent.CATEGORY_OPENABLE)
                    picker_intent.setType("image/*")
                    picker_intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

            # Launch the actual Activity directly. Do NOT wrap it in a chooser
            # and do NOT request persistable permission for GET_CONTENT.
            android_activity.startActivityForResult(
                picker_intent, self._image_picker_request
            )
            self._set_product_image_status("Memilih foto...")
            return

        except Exception as exc:
            print("Android photo picker launch gagal:", repr(exc))
            traceback.print_exc()

        try:
            if self._image_picker_bound:
                activity.unbind(on_activity_result=self._on_product_image_result)
        except Exception:
            pass
        self._image_picker_bound = False
        self._set_product_image_status(
            "Galeri tidak dapat dibuka. Tekan + Foto Produk lagi."
        )

    def _on_product_image_result(self, request_code, result_code, intent):
        if request_code != getattr(self, "_image_picker_request", -1):
            return
        try:
            from android import activity
            if getattr(self, "_image_picker_bound", False):
                activity.unbind(on_activity_result=self._on_product_image_result)
        except Exception:
            pass
        self._image_picker_bound = False

        if result_code != -1 or intent is None:
            self._set_product_image_status("Pemilihan foto dibatalkan.")
            return

        try:
            uri = intent.getData()
            if uri is None:
                self._set_product_image_status("Foto tidak ditemukan.")
                return

            # Some Android document providers require the temporary read grant
            # to remain attached while the URI is copied.  Copy immediately.
            path = self._copy_android_uri_to_file(uri)
            if path:
                self._product_image_path = path
                self._update_product_image_preview(path)
                self._set_product_image_status("Foto berhasil dipilih.")
            else:
                self._set_product_image_status("Foto gagal dibaca dari Gallery Android.")
        except Exception as exc:
            self._set_product_image_status("Foto tidak dapat digunakan.")
            print("Hasil Android photo picker gagal:", exc)

    def _open_desktop_image_picker(self):
        chooser = FileChooserListView(path=os.path.expanduser("~"), filters=["*.png", "*.jpg", "*.jpeg", "*.webp"])
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        box.add_widget(chooser)
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        cancel = Button(text="Batal")
        choose = Button(text="Pilih Foto", background_normal="", background_color=(.04,.58,.30,1), color=(1,1,1,1), bold=True)
        actions.add_widget(cancel); actions.add_widget(choose); box.add_widget(actions)
        pop = WhitePopup(title="Pilih Foto Produk", content=box, size_hint=(.94,.86))
        cancel.bind(on_release=pop.dismiss)
        def use_file(*_):
            if not chooser.selection:
                self._set_product_image_status("Pilih file gambar terlebih dahulu.")
                return
            path = self._copy_image_file(chooser.selection[0])
            if path:
                self._product_image_path = path
                self._update_product_image_preview(path)
                pop.dismiss()
        choose.bind(on_release=use_file)
        pop.open()

    def _update_product_image_preview(self, path):
        if self._product_image_preview is not None:
            try:
                self._product_image_preview.clear_widgets()
                self._product_image_preview.add_widget(Image(source=path, allow_stretch=True, keep_ratio=True))
            except Exception:
                pass
        self._set_product_image_status("Foto produk siap disimpan.")

    def _set_product_image_status(self, text):
        if self._product_image_status is not None:
            self._product_image_status.text = str(text)

    def _remove_product_image(self):
        self._product_image_path = ""
        self._update_product_image_preview("")
        if self._product_image_preview is not None:
            self._product_image_preview.clear_widgets()
            placeholder = Label(text="FOTO", font_size="11sp", bold=True,
                                color=(.45,.50,.58,1), halign="center", valign="middle")
            placeholder.bind(size=lambda w,v: setattr(w,"text_size",v))
            self._product_image_preview.add_widget(placeholder)
        self._set_product_image_status("Foto akan dihapus saat disimpan.")

    def refresh_products(self, search):
        grid = self.root.ids.products_grid
        grid.clear_widgets()
        for p in self._v48_products(search):
            is_service = self._is_service_product(p)
            stock_text = "JASA | tanpa stok" if is_service else f"Stok {float(p['stock']):g} {p['unit']}"
            row = BoxLayout(
                orientation="horizontal", size_hint_x=1, size_hint_y=None,
                height=dp(78), spacing=dp(6), padding=(dp(4), dp(3))
            )
            thumb_box = BoxLayout(size_hint_x=None, width=dp(64), padding=dp(1))
            with thumb_box.canvas.before:
                Color(0.94, 0.96, 0.98, 1)
                from kivy.graphics import RoundedRectangle
                thumb_bg = RoundedRectangle(pos=thumb_box.pos, size=thumb_box.size, radius=[dp(7)])
            thumb_box.bind(pos=lambda w, v: setattr(thumb_bg, "pos", v),
                           size=lambda w, v: setattr(thumb_bg, "size", v))
            image_path = p["image_path"] if "image_path" in p.keys() else ""
            if image_path and os.path.exists(image_path):
                thumb_box.add_widget(Image(source=image_path, allow_stretch=True, keep_ratio=True))
            else:
                placeholder = Label(text="FOTO", font_size="8sp", bold=True,
                                     color=(.45,.50,.58,1), halign="center", valign="middle")
                placeholder.bind(size=lambda w,v: setattr(w,"text_size",v))
                thumb_box.add_widget(placeholder)
            row.add_widget(thumb_box)

            info_box = BoxLayout(orientation="vertical", spacing=0, padding=(dp(2), dp(1)))
            name_lbl = Label(text=str(p['name']), font_size="11sp", bold=True,
                             color=(.08,.10,.14,1), halign="left", valign="middle")
            detail_lbl = Label(
                text=f"{self.money(p['sell_price'])} | {stock_text}",
                font_size="9sp", color=(.38,.43,.50,1), halign="left", valign="middle"
            )
            name_lbl.bind(size=lambda w,v: setattr(w,"text_size",(max(1,v[0]),None)))
            detail_lbl.bind(size=lambda w,v: setattr(w,"text_size",(max(1,v[0]),None)))
            info_box.add_widget(name_lbl)
            info_box.add_widget(detail_lbl)
            row.add_widget(info_box)

            action_box = BoxLayout(orientation="horizontal", size_hint_x=None, width=dp(132), spacing=dp(4))
            stock = Button(text="Stok" if not is_service else "Info", size_hint_x=None, width=dp(42),
                           background_normal="", background_color=(.88,.97,.91,1),
                           color=(.05,.45,.22,1), bold=True, font_size="9sp")
            edit = Button(text="Edit", size_hint_x=None, width=dp(42),
                          background_normal="", background_color=(.88,.94,1,1),
                          color=(.10,.28,.55,1), bold=True, font_size="9sp")
            delete = Button(text="Hapus", size_hint_x=None, width=dp(42),
                            background_normal="", background_color=(.98,.90,.90,1),
                            color=(.72,.12,.12,1), bold=True, font_size="9sp")
            if is_service:
                stock.bind(on_release=lambda btn, pid=p["id"]: self.info("Item jasa tidak menggunakan stok.", "Jasa"))
            else:
                stock.bind(on_release=lambda btn, pid=p["id"]: self.stock_form(pid))
            edit.bind(on_release=lambda btn, pid=p["id"]: self.product_form(pid))
            delete.bind(on_release=lambda btn, pid=p["id"]: self.delete_product(pid))
            action_box.add_widget(stock); action_box.add_widget(edit); action_box.add_widget(delete)
            row.add_widget(action_box)
            grid.add_widget(row)

    def product_form(self, product_id=None):
        p = self._v48_product_by_id(product_id) if product_id else None
        self._product_image_path = (p["image_path"] if p and "image_path" in p.keys() else "") or ""
        self._product_image_preview = None
        self._product_image_status = None
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        scroll = ScrollView(do_scroll_x=False)
        inner = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        inner.bind(minimum_height=inner.setter("height"))

        # Foto produk
        photo_wrap = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(126), spacing=dp(5))
        preview = BoxLayout(size_hint_y=None, height=dp(82), padding=dp(4))
        self._product_image_preview = preview
        if self._product_image_path and os.path.exists(self._product_image_path):
            preview.add_widget(Image(source=self._product_image_path, allow_stretch=True, keep_ratio=True))
        else:
            placeholder = Label(text="FOTO PRODUK\nBelum ada foto", font_size="10sp", color=(.45,.50,.58,1), halign="center", valign="middle")
            placeholder.bind(size=lambda w,v: setattr(w,"text_size",v)); preview.add_widget(placeholder)
        photo_wrap.add_widget(preview)
        photo_actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(5))
        pick_btn = Button(text="+ Foto Produk", background_normal="", background_color=(.10,.28,.55,1), color=(1,1,1,1), bold=True)
        remove_btn = Button(text="Hapus Foto", background_normal="", background_color=(.96,.90,.90,1), color=(.72,.12,.12,1), bold=True)
        photo_actions.add_widget(pick_btn); photo_actions.add_widget(remove_btn)
        photo_wrap.add_widget(photo_actions)
        status = Label(text="Foto tersimpan di perangkat." if self._product_image_path else "Opsional — tambahkan foto produk.",
                       size_hint_y=None, height=dp(18), font_size="9sp", color=(.35,.40,.48,1), halign="left", valign="middle")
        status.bind(size=lambda w,v: setattr(w,"text_size",v))
        photo_wrap.add_widget(status)
        inner.add_widget(photo_wrap)
        self._product_image_status = status
        pick_btn.bind(on_release=lambda *_: self._pick_product_image(preview, status))
        remove_btn.bind(on_release=lambda *_: self._remove_product_image())

        fields = {}
        for key, hint in [
            ("barcode", "Barcode / SKU (opsional)"),
            ("name", "Nama barang atau jasa"),
            ("buy_price", "Harga modal / biaya"),
            ("sell_price", "Harga jual"),
            ("stock", "Stok"),
            ("unit", "Satuan (pcs, kg, jam, paket, dll.)"),
            ("min_stock", "Batas stok minimum"),
        ]:
            t = TextInput(hint_text=hint, multiline=False, size_hint_y=None, height=dp(40),
                          text="" if not p else str(p[key] if p[key] is not None else ""))
            fields[key] = t; inner.add_widget(t)

        item_type = ((p["item_type"] if "item_type" in p.keys() else "BARANG") if p else "BARANG").upper()
        type_spinner = Spinner(text="Jasa" if item_type == "JASA" else "Barang", values=("Barang", "Jasa"), size_hint_y=None, height=dp(40))
        inner.add_widget(Label(text="Tipe item", size_hint_y=None, height=dp(22), halign="left", color=(.20,.24,.30,1), bold=True, font_size="11sp"))
        inner.add_widget(type_spinner)
        categories = self.db.categories(); cat_names = [str(c["name"]) for c in categories]
        current_cat = cat_names[0] if cat_names else ""
        if p and p["category_id"]:
            for c in categories:
                if c["id"] == p["category_id"]: current_cat = c["name"]; break
        inner.add_widget(Label(text="Kategori", size_hint_y=None, height=dp(22), halign="left", color=(.20,.24,.30,1), bold=True, font_size="11sp"))
        cat_spinner = Spinner(text=current_cat or "Belum ada kategori", values=cat_names or ["Belum ada kategori"], size_hint_y=None, height=dp(40))
        inner.add_widget(cat_spinner)
        hint = Label(text="Barang memakai stok. Jasa tidak mengurangi stok saat terjual.", size_hint_y=None, height=dp(38), font_size="10sp", color=(.35,.40,.48,1), halign="left", valign="middle")
        hint.bind(size=lambda w,v: setattr(w,"text_size",v)); inner.add_widget(hint)
        scroll.add_widget(inner); box.add_widget(scroll)
        save = Button(text="Simpan", size_hint_y=None, height=dp(44), background_normal="", background_color=(.04,.58,.30,1), color=(1,1,1,1), bold=True)
        box.add_widget(save)
        popup = WhitePopup(title="Barang / Jasa", content=box, size_hint=(.92,.90))

        def sync_type(*_):
            is_service = type_spinner.text == "Jasa"
            fields["stock"].disabled = is_service; fields["min_stock"].disabled = is_service
            if is_service:
                fields["stock"].text = "0"; fields["min_stock"].text = "0"; fields["unit"].text = fields["unit"].text or "jasa"
            elif fields["unit"].text == "jasa": fields["unit"].text = "pcs"
        type_spinner.bind(text=sync_type); sync_type()

        def save_it(*_):
            try:
                if not categories: raise ValueError("Buat kategori terlebih dahulu.")
                cat = next(c for c in categories if c["name"] == cat_spinner.text)
                is_service = type_spinner.text == "Jasa"
                data = {"id": product_id, "barcode": fields["barcode"].text.strip(), "name": fields["name"].text.strip(), "category_id": cat["id"],
                        "buy_price": float(fields["buy_price"].text or 0), "sell_price": float(fields["sell_price"].text or 0),
                        "stock": 0.0 if is_service else float(fields["stock"].text or 0), "unit": fields["unit"].text.strip() or ("jasa" if is_service else "pcs"),
                        "min_stock": 0.0 if is_service else float(fields["min_stock"].text or 0)}
                if not data["name"] or data["sell_price"] < 0: raise ValueError("Nama produk dan harga jual harus valid.")
                self.db.save_product(data)
                row = self.db.conn.execute("SELECT id FROM products WHERE barcode=? ORDER BY id DESC LIMIT 1", (data["barcode"],)).fetchone() if data["barcode"] else None
                if not row:
                    row = self.db.conn.execute("SELECT id FROM products WHERE name=? AND category_id=? ORDER BY id DESC LIMIT 1", (data["name"], data["category_id"])).fetchone()
                saved_id = product_id or (row["id"] if row else None)
                if saved_id:
                    self.db.conn.execute("UPDATE products SET item_type=?, track_stock=?, image_path=? WHERE id=?",
                                         ("JASA" if is_service else "BARANG", 0 if is_service else 1, self._product_image_path or "", saved_id))
                    self.db.conn.commit()
                self._audit("SAVE_ITEM", f"{data['name']} | {'JASA' if is_service else 'BARANG'}")
                popup.dismiss(); self.refresh_all()
            except Exception as exc:
                self.info(str(exc) or "Data tidak valid atau barcode sudah digunakan.", "Barang / Jasa")
        save.bind(on_release=save_it); popup.open()

    def delete_product(self, product_id):
        self.db.delete_product(product_id)
        self.refresh_all()

    def stock_form(self, product_id):
        p = self._v48_product_by_id(product_id)
        if not p:
            return
        if self._is_service_product(p):
            self.info("Item jasa tidak memiliki stok untuk dikelola.", "Jasa")
            return

        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        box.add_widget(Label(
            text=f"{p['name']}\nStok saat ini: {p['stock']:g} {p['unit']}",
            size_hint_y=None, height=dp(58), halign="left", valign="middle"
        ))
        mode = Spinner(text="STOK MASUK", values=("STOK MASUK", "STOK KELUAR", "KOREKSI"),
                       size_hint_y=None, height=dp(44))
        qty = TextInput(hint_text="Jumlah / stok akhir", multiline=False, input_filter="float",
                        size_hint_y=None, height=dp(44))
        note = TextInput(hint_text="Catatan / alasan", multiline=False,
                         size_hint_y=None, height=dp(44))
        box.add_widget(mode); box.add_widget(qty); box.add_widget(note)
        save = Button(text="SIMPAN PERUBAHAN STOK", size_hint_y=None, height=dp(46),
                      background_normal="", background_color=(.04,.58,.30,1),
                      color=(1,1,1,1), bold=True)
        box.add_widget(save)
        popup = WhitePopup(title="Kelola Stok", content=box, size_hint=(.90, None), height=dp(350))

        def save_stock(*_):
            try:
                amount = float(qty.text or 0)
                if amount <= 0:
                    raise ValueError("Jumlah stok harus lebih dari 0.")
                if mode.text == "STOK MASUK":
                    delta, kind = amount, "STOK MASUK"
                elif mode.text == "STOK KELUAR":
                    delta, kind = -amount, "STOK KELUAR"
                else:
                    delta, kind = amount - float(p["stock"]), "KOREKSI"
                self.db.stock_adjustment(product_id, delta, kind, note.text.strip())
                popup.dismiss(); self.refresh_all()
                self.info("Perubahan stok berhasil disimpan.")
            except Exception as exc:
                self.info(str(exc), "Stok")
        save.bind(on_release=save_stock)
        popup.open()

    def stock_history_popup(self):
        rows = self.db.stock_movements(150)
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        scroll = ScrollView(do_scroll_x=False)
        grid = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        if not rows:
            grid.add_widget(Label(text="Belum ada pergerakan stok.", size_hint_y=None, height=dp(42)))
        else:
            for r in rows:
                sign = "+" if float(r["qty"]) >= 0 else ""
                text = f"{r['created_at'].replace('T',' ')} | {r['movement_type']}\n{r['product_name']}  {sign}{r['qty']:g}  -> stok {r['stock_after']:g}"
                if r["note"]:
                    text += f"\nCatatan: {r['note']}"
                grid.add_widget(Label(text=text, size_hint_y=None, height=dp(62), halign="left"))
        scroll.add_widget(grid); box.add_widget(scroll)
        close = Button(text="Tutup", size_hint_y=None, height=dp(44)); box.add_widget(close)
        popup = WhitePopup(title="Riwayat Pergerakan Stok", content=box, size_hint=(.94, None), height=dp(500))
        close.bind(on_release=popup.dismiss); popup.open()

    def barcode_popup(self):
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        box.add_widget(Label(
            text="Masukkan atau scan barcode produk.",
            size_hint_y=None, height=dp(34), halign="left"
        ))
        code = TextInput(
            hint_text="Barcode", multiline=False,
            size_hint_y=None, height=dp(46)
        )
        box.add_widget(code)
        result = Label(
            text="", size_hint_y=None, height=dp(44),
            halign="left", valign="middle"
        )
        result.text_size = (None, None)
        box.add_widget(result)
        buttons = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        add_btn = Button(text="TAMBAH KE KERANJANG")
        close_btn = Button(text="Tutup")
        buttons.add_widget(add_btn); buttons.add_widget(close_btn)
        box.add_widget(buttons)
        popup = WhitePopup(title="Barcode", content=box,
                           size_hint=(.90, None), height=dp(270))

        def add_barcode(*_):
            value = code.text.strip()
            if not value:
                result.text = "Barcode belum diisi."
                return
            row = self.db.conn.execute(
                "SELECT id,name,stock,sell_price,unit FROM products "
                "WHERE barcode=? AND active=1", (value,)
            ).fetchone()
            if not row:
                result.text = "Produk dengan barcode tersebut tidak ditemukan."
                return
            if float(row[2]) <= 0:
                result.text = f"{row[1]}: stok habis."
                return
            self.add_to_cart(row[0])
            result.text = f"Ditambahkan: {row[1]}"
            self.refresh_pos_products("")

        add_btn.bind(on_release=add_barcode)
        close_btn.bind(on_release=popup.dismiss)
        popup.open()
        Clock.schedule_once(lambda dt: setattr(code, "focus", True), .15)

    def finance_popup(self):
        conn = self.db.conn
        today = conn.execute("""
            SELECT COUNT(*) transactions,
                   COALESCE(SUM(total),0) sales,
                   COALESCE(SUM(discount),0) discount,
                   COALESCE(SUM(tax),0) tax
            FROM sales
            WHERE date(created_at)=date('now','localtime')
        """).fetchone()
        profit = conn.execute("""
            SELECT COALESCE(SUM((si.price-si.cost_price)*si.qty),0) profit,
                   COALESCE(SUM(si.cost_price*si.qty),0) cost
            FROM sale_items si JOIN sales s ON s.id=si.sale_id
            WHERE date(s.created_at)=date('now','localtime')
        """).fetchone()
        month = conn.execute("""
            SELECT COALESCE(SUM(s.total),0) sales,
                   COALESCE(SUM((si.price-si.cost_price)*si.qty),0) profit
            FROM sales s JOIN sale_items si ON si.sale_id=s.id
            WHERE date(s.created_at)>=date('now','localtime','-29 day')
        """).fetchone()
        payments = conn.execute("""
            SELECT payment_method, COUNT(*) transactions, COALESCE(SUM(total),0) total
            FROM sales WHERE date(created_at)=date('now','localtime')
            GROUP BY payment_method ORDER BY total DESC
        """).fetchall()

        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        box.add_widget(Label(
            text=f"Hari ini\nPenjualan: {self.money(today['sales'])}\n"
                 f"Transaksi: {today['transactions']}\n"
                 f"Modal terjual: {self.money(profit['cost'])}\n"
                 f"Laba kotor: {self.money(profit['profit'])}\n"
                 f"Diskon: {self.money(today['discount'])}   Pajak: {self.money(today['tax'])}",
            size_hint_y=None, height=dp(145), halign="left", valign="middle"
        ))
        box.add_widget(Label(
            text=f"30 hari\nPenjualan: {self.money(month['sales'])}\n"
                 f"Laba kotor: {self.money(month['profit'])}",
            size_hint_y=None, height=dp(75), halign="left", valign="middle"
        ))
        box.add_widget(Label(text="Metode Pembayaran", size_hint_y=None,
                             height=dp(28), bold=True, halign="left"))
        scroll = ScrollView(do_scroll_x=False)
        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        if payments:
            for r in payments:
                grid.add_widget(Label(
                    text=f"{r['payment_method']} | {r['transactions']} transaksi | {self.money(r['total'])}",
                    size_hint_y=None, height=dp(30), halign="left"
                ))
        else:
            grid.add_widget(Label(text="Belum ada transaksi hari ini.",
                                  size_hint_y=None, height=dp(30), halign="left"))
        scroll.add_widget(grid); box.add_widget(scroll)
        close = Button(text="Tutup", size_hint_y=None, height=dp(44))
        box.add_widget(close)
        popup = WhitePopup(title="Ringkasan Keuangan", content=box,
                           size_hint=(.94, None), height=dp(430))
        close.bind(on_release=popup.dismiss)
        popup.open()

    def inventory_popup(self):
        conn = self.db.conn
        totals = conn.execute("""
            SELECT COUNT(*) products,
                   COALESCE(SUM(stock*buy_price),0) cost_value,
                   COALESCE(SUM(stock*sell_price),0) retail_value,
                   COALESCE(SUM(CASE WHEN stock<=min_stock THEN 1 ELSE 0 END),0) low,
                   COALESCE(SUM(CASE WHEN stock<=0 THEN 1 ELSE 0 END),0) out_count
            FROM products WHERE active=1 AND COALESCE(item_type,'BARANG')='BARANG' AND COALESCE(track_stock,1)=1
        """).fetchone()
        rows = conn.execute("""
            SELECT name, barcode, stock, min_stock, unit, buy_price, sell_price
            FROM products WHERE active=1 AND COALESCE(item_type,'BARANG')='BARANG' AND COALESCE(track_stock,1)=1 AND stock<=min_stock
            ORDER BY stock ASC, name LIMIT 30
        """).fetchall()
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        box.add_widget(Label(
            text=f"Produk aktif: {totals['products']}\n"
                 f"Nilai modal stok: {self.money(totals['cost_value'])}\n"
                 f"Nilai jual stok: {self.money(totals['retail_value'])}\n"
                 f"Potensi margin: {self.money(totals['retail_value']-totals['cost_value'])}\n"
                 f"Stok menipis: {totals['low']} | Habis: {totals['out_count']}",
            size_hint_y=None, height=dp(125), halign="left", valign="middle"
        ))
        box.add_widget(Label(text="Stok Perlu Perhatian", size_hint_y=None,
                             height=dp(28), bold=True, halign="left"))
        scroll = ScrollView(do_scroll_x=False)
        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        if rows:
            for r in rows:
                status = "HABIS" if float(r['stock']) <= 0 else "MENIPIS"
                grid.add_widget(Label(
                    text=f"[{status}] {r['name']} | {r['stock']:g} {r['unit']} / min {r['min_stock']:g}\n"
                         f"Barcode: {r['barcode'] or '-'} | Modal {self.money(r['buy_price'])} | Jual {self.money(r['sell_price'])}",
                    size_hint_y=None, height=dp(54), halign="left", valign="middle"
                ))
        else:
            grid.add_widget(Label(text="Tidak ada stok yang perlu perhatian.",
                                  size_hint_y=None, height=dp(32), halign="left"))
        scroll.add_widget(grid); box.add_widget(scroll)
        close = Button(text="Tutup", size_hint_y=None, height=dp(44))
        box.add_widget(close)
        popup = WhitePopup(title="Smart Inventory", content=box,
                           size_hint=(.95, None), height=dp(470))
        close.bind(on_release=popup.dismiss)
        popup.open()

    def category_form(self):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        Label(
            text="Buat kategori sesuai jenis usaha Anda.",
            size_hint_y=None, height=dp(30),
            halign="left", color=(.35, .40, .48, 1), font_size="11sp"
        )
        t = TextInput(
            hint_text="Contoh: Pakaian, Sparepart, Jasa Servis, Elektronik...",
            multiline=False, size_hint_y=None, height=dp(42)
        )
        b = Button(text="Simpan Kategori", size_hint_y=None, height=dp(44))
        box.add_widget(t)
        box.add_widget(b)
        popup = WhitePopup(title="Tambah Kategori", content=box, size_hint=(.90, None), height=dp(190))

        def save_cat(*_):
            name = t.text.strip()
            if not name or name.lower() == "semua":
                self.info("Nama kategori tidak boleh kosong atau menggunakan 'Semua'.", "Kategori")
                return
            try:
                before = len(self.db.categories())
                self.db.add_category(name)
                after = len(self.db.categories())
                if after == before:
                    self.info("Kategori sudah ada.", "Kategori")
                    return
                if hasattr(self, "_audit"):
                    self._audit("ADD_CATEGORY", name)
                popup.dismiss()
                self.refresh_all()
            except Exception:
                self.info("Kategori gagal ditambahkan.", "Kategori")

        b.bind(on_release=save_cat)
        popup.open()

    def category_manager_popup(self):
        """Manage category names so the POS stays universal for any UMKM type."""
        outer = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        outer.add_widget(Label(
            text="Kategori di bawah ini dipakai sebagai filter POS dan saat membuat produk.",
            size_hint_y=None, height=dp(34), text_size=(dp(330), None),
            halign="left", valign="middle", color=(.35, .40, .48, 1), font_size="10sp"
        ))

        scroll = ScrollView(do_scroll_x=False)
        grid = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        scroll.add_widget(grid)
        outer.add_widget(scroll)

        close = Button(text="Tutup", size_hint_y=None, height=dp(42))
        outer.add_widget(close)
        popup = WhitePopup(title="Kelola Kategori Usaha", content=outer,
                           size_hint=(.94, None), height=dp(440))
        close.bind(on_release=popup.dismiss)

        def rebuild(*_):
            grid.clear_widgets()
            categories = self.db.categories()
            if not categories:
                grid.add_widget(Label(text="Belum ada kategori.", size_hint_y=None, height=dp(36)))
                return
            for cat in categories:
                row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
                name = Label(text=str(cat["name"]), halign="left", valign="middle",
                             color=(.08,.10,.14,1), font_size="11sp")
                name.bind(size=lambda w, v: setattr(w, "text_size", v))
                edit = Button(text="Ubah", size_hint_x=None, width=dp(72),
                               background_normal="", background_color=(.82,.90,1,1),
                               color=(.10,.28,.55,1), bold=True)
                row.add_widget(name)
                row.add_widget(edit)
                grid.add_widget(row)
                edit.bind(on_release=lambda btn, cid=cat["id"], old=str(cat["name"]):
                          self.rename_category(cid, old, popup, rebuild))

        rebuild()
        popup.open()

    def rename_category(self, category_id, old_name, manager_popup=None, rebuild_callback=None):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        t = TextInput(text=str(old_name), multiline=False, size_hint_y=None, height=dp(42))
        save = Button(text="Simpan Perubahan", size_hint_y=None, height=dp(44))
        box.add_widget(t)
        box.add_widget(save)
        popup = WhitePopup(title="Ubah Nama Kategori", content=box, size_hint=(.88, None), height=dp(170))

        def do_save(*_):
            new_name = t.text.strip()
            if not new_name or new_name.lower() == "semua":
                self.info("Nama kategori tidak valid.", "Kategori")
                return
            if new_name == old_name:
                popup.dismiss()
                return
            try:
                exists = self.db.conn.execute(
                    "SELECT id FROM categories WHERE lower(name)=lower(?) AND id<>?",
                    (new_name, category_id)
                ).fetchone()
                if exists:
                    self.info("Nama kategori tersebut sudah digunakan.", "Kategori")
                    return
                self.db.conn.execute(
                    "UPDATE categories SET name=? WHERE id=?",
                    (new_name, category_id)
                )
                self.db.conn.commit()
                if hasattr(self, "_audit"):
                    self._audit("RENAME_CATEGORY", f"{old_name} -> {new_name}")
                popup.dismiss()
                if rebuild_callback:
                    rebuild_callback()
                self.refresh_all()
            except Exception as e:
                self.info(f"Gagal mengubah kategori: {e}", "Kategori")

        save.bind(on_release=do_save)
        popup.open()

    def refresh_history(self):
        grid = self.root.ids.history_grid
        grid.clear_widgets()
        for s in self.db.sales(100):
            row = BoxLayout(size_hint_y=None, height=dp(54))
            row.add_widget(Label(
                text=f"{s['invoice']} | {s['created_at'].replace('T',' ')}\n"
                     f"{s['payment_method']} | {self.money(s['total'])}",
                halign="left",
                valign="middle",
                color=(.08,.10,.14,1),
                font_size="11sp"
            ))
            b = Button(text="Detail", size_hint_x=None, width=dp(68),
                       background_normal="", background_color=(.88,.94,1,1),
                       color=(.10,.28,.55,1), bold=True)
            b.bind(on_release=lambda btn, sid=s["id"]: self.show_sale(sid))
            row.add_widget(b)
            grid.add_widget(row)

    def show_sale(self, sale_id):
        sale = None
        for x in self.db.sales(200):
            if x["id"] == sale_id:
                sale = x
                break
        if not sale:
            return

        items = self.db.sale_items(sale_id)
        
        cart_repr = []
        for it in items:
            cart_repr.append({
                "name": it['product_name'],
                "qty": it['qty'],
                "price": it['price'],
                "line_total": it['line_total']
            })
            
        receipt_text = self.generate_receipt_text(
            sale['invoice'], cart_repr, sale['total'], sale['paid'], sale['change_amount'],
            payment=sale['payment_method'], subtotal=sale['subtotal'],
            discount=sale['discount'], tax=sale['tax'], cashier=sale['cashier'],
            created_at=sale['created_at'][:16].replace('T', ' ')
        )

        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        scroll = ScrollView(do_scroll_x=False)
        
        lbl = Label(
            text=receipt_text, font_size="12sp", color=(0.10, 0.14, 0.20, 1),
            size_hint_y=None, halign="left", valign="top"
        )
        lbl.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        lbl.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        
        scroll.add_widget(lbl)
        content.add_widget(scroll)

        btn_reprint = Button(
            text="Cetak Ulang Struk", size_hint_y=None, height=dp(40),
            background_normal="", background_color=(0.05, 0.60, 0.30, 1),
            color=(1, 1, 1, 1), bold=True
        )
        
        popup = WhitePopup(title="Detail Transaksi", content=content, size_hint=(0.88, None), height=dp(500))
        
        def do_reprint(*_):
            ok, msg = self.print_receipt(receipt_text)
            self.info(msg, "Status Cetak")

        btn_reprint.bind(on_release=do_reprint)
        content.add_widget(btn_reprint)
        popup.open()

    def refresh_reports(self):
        grid = self.root.ids.report_grid
        grid.clear_widgets()
        rows = self.db.sales_report(30)
        if not rows:
            grid.add_widget(Label(
                text="Belum ada transaksi.",
                size_hint_y=None, height=dp(40), color=(0.2, 0.2, 0.2, 1)
            ))
            return
        for r in rows:
            grid.add_widget(Label(
                text=f"{r['day']} | {r['transactions']} transaksi | "
                     f"Total {self.money(r['total'])} | Laba {self.money(r['profit'])}",
                size_hint_y=None, height=dp(40), halign="left", color=(0.1, 0.14, 0.2, 1)
            ))

        top_grid = self.root.ids.top_products_grid
        top_grid.clear_widgets()
        top = self.db.top_products(30, 5)
        if not top:
            top_grid.add_widget(Label(text="Belum ada produk terjual.", size_hint_y=None, height=dp(40)))
        else:
            for i, r in enumerate(top, 1):
                top_grid.add_widget(Label(
                    text=f"{i}. {r['product_name']} | {r['qty']:g} terjual | "
                         f"Omzet {self.money(r['revenue'])} | Laba {self.money(r['profit'])}",
                    size_hint_y=None, height=dp(40), halign="left", color=(0.1,0.14,0.2,1)
                ))

    def export_csv(self):
        path = os.path.join(self.user_data_dir, "laporan_30_hari.csv")
        rows = self.db.sales_report(30)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Tanggal", "Transaksi", "Subtotal",
                "Diskon", "Pajak", "Total", "Laba Kotor"
            ])
            for r in rows:
                writer.writerow([
                    r["day"], r["transactions"], r["subtotal"],
                    r["discount"], r["tax"], r["total"], r["profit"]
                ])
        self.info(f"CSV tersimpan di:\n{path}")

    def save_settings(self):
        ids = self.root.ids
        self.db.set_setting(
            "store_name", ids.setting_store.text.strip() or "TOKO SAYA"
        )
        self.db.set_setting("store_address", ids.setting_address.text.strip())
        self.db.set_setting("tax_percent", ids.setting_tax.text.strip() or "0")
        self.db.set_setting(
            "cashier_name", ids.setting_cashier.text.strip() or "Admin"
        )
        self.db.set_setting(
            "bt_mac_address", ids.setting_bt_mac.text.strip()
        )
        self.db.set_setting("paper_width", "32" if ids.setting_paper_width.text == "58 mm" else "48")
        self.db.set_setting("auto_cut", "1" if ids.setting_auto_cut.text == "ON" else "0")
        self.db.set_setting("feed_lines", ids.setting_feed_lines.text.strip() or "3")
        self.db.set_setting("store_instagram", ids.setting_instagram.text.strip())
        self.db.set_setting("store_whatsapp", ids.setting_whatsapp.text.strip())
        self.db.set_setting("receipt_footer", ids.setting_receipt_footer.text.strip() or "Terima Kasih Atas Kunjungan Anda!")
        self.db.set_setting("business_type", ids.setting_business_type.text.strip() or "Umum")
        self.load_settings()
        self.refresh_all()
        self.info("Pengaturan berhasil disimpan.")

    def make_backup(self):
        filename = f"backup_pos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path = os.path.join(self.user_data_dir, filename)
        self.db.backup(path)
        self.info(f"Backup dibuat di:\n{path}")

    def info(self, message, title="Informasi"):
        # Compact and Android-safe: determine a reasonable height before opening.
        # No runtime binding to Popup height is used, avoiding startup/render issues.
        text = str(message)
        approx_lines = 0
        for paragraph in text.split("\n") or [""]:
            approx_lines += max(1, (len(paragraph) + 43) // 44)
        popup_height = min(dp(520), max(dp(150), dp(74 + approx_lines * 22)))

        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        scroll = ScrollView(do_scroll_x=False)
        lbl = Label(
            text=text,
            font_size="13sp",
            color=(0.10, 0.14, 0.20, 1),
            size_hint_y=None,
            halign="left",
            valign="top",
            text_size=(None, None),
        )
        # Fixed content width makes wrapping predictable on Android.
        def update_label_width(instance, width):
            instance.text_size = (max(dp(100), width - dp(4)), None)
            instance.texture_update()
            instance.height = max(dp(42), instance.texture_size[1])

        lbl.bind(width=update_label_width)
        scroll.add_widget(lbl)
        content.add_widget(scroll)

        popup = WhitePopup(
            title=title,
            content=content,
            size_hint=(0.88, None),
            height=popup_height
        )
        popup.open()


if __name__ == "__main__":
    POSApp().run()
