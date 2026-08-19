__version__ = "1.4.1-printer-pro"

import csv
import os
import platform
from datetime import datetime
import traceback
import time
import textwrap

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.label import Label
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
            text: "v" + app.version
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
                    padding: dp(16)
                    spacing: dp(12)
                    size_hint_y: None
                    height: self.minimum_height

                    TitleLabel:
                        text: "Ringkasan Hari Ini"

                    GridLayout:
                        cols: 2
                        spacing: dp(10)
                        size_hint_y: None
                        height: dp(160)

                        CardBox:
                            orientation: "vertical"
                            Label:
                                text: "PENJUALAN"
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
                                text: "TRANSAKSI"
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

                    Label:
                        id: dash_profit
                        text: "Laba kotor hari ini: Rp 0"
                        font_size: "12sp"
                        bold: True
                        color: .08, .42, .24, 1
                        size_hint_y: None
                        height: dp(32)
                        halign: "left"
                        text_size: self.size

                    Button:
                        text: "Refresh Data"
                        size_hint_y: None
                        height: dp(42)
                        background_normal: ""
                        background_color: .12, .16, .22, 1
                        color: 1, 1, 1, 1
                        bold: True
                        on_release: app.refresh_all()

        Screen:
            name: "pos"
            BoxLayout:
                orientation: "vertical"
                padding: dp(12)
                spacing: dp(8)

                TitleLabel:
                    text: "Kasir / POS"

                ModernTextInput:
                    id: search_pos
                    hint_text: "Cari produk atau scan barcode..."
                    on_text: app.refresh_pos_products(self.text)

                ScrollView:
                    do_scroll_x: False
                    GridLayout:
                        id: product_grid
                        cols: 1
                        spacing: dp(6)
                        size_hint_y: None
                        height: self.minimum_height

                CardBox:
                    size_hint_y: None
                    height: dp(54)
                    padding: dp(8), dp(4)
                    spacing: dp(8)

                    BoxLayout:
                        orientation: "vertical"
                        Label:
                            id: cart_summary_items
                            text: "0 Item"
                            font_size: "11sp"
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
                        width: dp(140)
                        background_normal: ""
                        background_color: .05, .60, .30, 1
                        color: 1, 1, 1, 1
                        bold: True
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

                BoxLayout:
                    size_hint_y: None
                    height: dp(42)
                    spacing: dp(6)

                    Button:
                        text: "+ Tambah Kategori"
                        background_normal: ""
                        background_color: .88, .91, .95, 1
                        color: .08, .11, .16, 1
                        bold: True
                        on_release: app.category_form()

                    Button:
                        text: "Riwayat Stok"
                        background_normal: ""
                        background_color: .10, .14, .20, 1
                        color: 1, 1, 1, 1
                        bold: True
                        on_release: app.stock_history_popup()

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
    store_address = StringProperty("")
    tax_percent = StringProperty("0")
    cashier_name = StringProperty("Admin")
    bt_mac_address = StringProperty("")

    def build(self):
        self.title = "POS Kasir"
        self.db = Database(os.path.join(self.user_data_dir, "pos.db"))
        self.load_settings()
        self.cart = []
        self.cart_popup = None
        self.cart_popup_grid = None
        self.popup_total_label = None
        self.popup_change_label = None
        self.paid_input = None
        Builder.load_string(KV)
        return RootLayout()

    def on_start(self):
        try:
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
        self.refresh_pos_products("")
        self.update_cart_summary()
        self.refresh_products("")
        self.refresh_history()
        self.refresh_reports()

    @staticmethod
    def money(value):
        return "Rp {:,.0f}".format(float(value)).replace(",", ".")

    def refresh_dashboard(self):
        s, product_count, low = self.db.summary_today()
        self.root.ids.dash_sales.text = f"{self.money(s['total'])}"
        self.root.ids.dash_trx.text = f"{s['transactions']}"
        self.root.ids.dash_products.text = f"{product_count}"
        self.root.ids.dash_low.text = f"{low}"
        self.root.ids.dash_profit.text = f"Laba kotor hari ini: {self.money(s['profit'])}"

    def refresh_pos_products(self, search):
        grid = self.root.ids.product_grid
        grid.clear_widgets()
        for p in self.db.products(search)[:100]:
            btn = Button(
                text=f"{p['name']}\n{self.money(p['sell_price'])}  |  Stok {p['stock']:g} {p['unit']}",
                size_hint_y=None, height=dp(56),
                background_normal="",
                background_color=(1, 1, 1, 1),
                color=(.08, .10, .14, 1),
                font_size="13sp",
                bold=True,
                halign="left",
                valign="middle",
                padding=(dp(12), dp(6))
            )
            btn.bind(size=lambda instance, value: setattr(instance, 'text_size', (value[0] - dp(24), None)))
            btn.bind(on_release=lambda b, pid=p["id"]: self.add_to_cart(pid))
            grid.add_widget(btn)

    def add_to_cart(self, product_id):
        p = self.db.product_by_id(product_id)
        if not p or p["stock"] <= 0:
            self.info("Stok produk habis.")
            return
        for item in self.cart:
            if item["id"] == product_id:
                if item["qty"] + 1 > p["stock"]:
                    self.info("Jumlah melebihi stok.")
                    return
                item["qty"] += 1
                item["line_total"] = item["qty"] * item["price"]
                self.update_cart_summary()
                return
        self.cart.append({
            "id": p["id"], "name": p["name"], "qty": 1,
            "price": float(p["sell_price"]), "discount": 0,
            "line_total": float(p["sell_price"])
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

        checkout_box.height = dp(214)
        checkout_box.add_widget(self.popup_total_label)
        checkout_box.add_widget(discount_row)
        checkout_box.add_widget(payment_row)
        checkout_box.add_widget(pay_row)
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
                p = self.db.product_by_id(product_id)
                item["qty"] += delta
                if item["qty"] <= 0:
                    self.remove_cart(product_id)
                    return
                if item["qty"] > p["stock"]:
                    item["qty"] = p["stock"]
                item["line_total"] = item["qty"] * item["price"]
                break
        self.update_cart_summary()
        self.refresh_cart_popup_grid()

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

    def checkout(self):
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

        try:
            invoice = self.db.save_sale(
                self.cart, subtotal, discount, tax, total, paid_val, change_val, payment
            )
        except ValueError as exc:
            self.info(str(exc), "Transaksi Ditolak")
            self.refresh_all()
            return
        except Exception:
            self.log_startup_error()
            self.info("Transaksi gagal disimpan. Tidak ada stok yang dikurangi.", "Kesalahan")
            return

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

    def refresh_products(self, search):
        grid = self.root.ids.products_grid
        grid.clear_widgets()
        for p in self.db.products(search):
            row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(4))
            row.add_widget(Label(
                text=f"{p['name']} | {p['barcode'] or '-'}\n"
                     f"Jual {self.money(p['sell_price'])} | Stok {p['stock']:g} {p['unit']}",
                halign="left",
                valign="middle",
                color=(.08,.10,.14,1),
                font_size="11sp"
            ))
            stock = Button(text="Stok", size_hint_x=None, width=dp(58),
                           background_normal="", background_color=(.88,.97,.91,1),
                           color=(.05,.45,.22,1), bold=True)
            edit = Button(text="Edit", size_hint_x=None, width=dp(60),
                           background_normal="", background_color=(.88,.94,1,1),
                           color=(.10,.28,.55,1), bold=True)
            delete = Button(text="Hapus", size_hint_x=None, width=dp(60),
                            background_normal="", background_color=(.98,.90,.90,1),
                            color=(.72,.12,.12,1), bold=True)
            stock.bind(on_release=lambda btn, pid=p["id"]: self.stock_form(pid))
            edit.bind(on_release=lambda btn, pid=p["id"]: self.product_form(pid))
            delete.bind(on_release=lambda btn, pid=p["id"]: self.delete_product(pid))
            row.add_widget(stock)
            row.add_widget(edit)
            row.add_widget(delete)
            grid.add_widget(row)

    def product_form(self, product_id=None):
        p = self.db.product_by_id(product_id) if product_id else None
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        fields = {}
        for key, hint in [
            ("barcode", "Barcode (opsional)"),
            ("name", "Nama produk"),
            ("buy_price", "Harga beli"),
            ("sell_price", "Harga jual"),
            ("stock", "Stok"),
            ("unit", "Satuan"),
            ("min_stock", "Batas stok minimum"),
        ]:
            t = TextInput(
                hint_text=hint, multiline=False,
                size_hint_y=None, height=dp(40),
                text="" if not p else str(p[key] if p[key] is not None else "")
            )
            fields[key] = t
            box.add_widget(t)

        categories = self.db.categories()
        cat_names = [c["name"] for c in categories]
        current_cat = "Umum"
        if p and p["category_id"]:
            for c in categories:
                if c["id"] == p["category_id"]:
                    current_cat = c["name"]
                    break

        cat_spinner = Spinner(
            text=current_cat, values=cat_names,
            size_hint_y=None, height=dp(40)
        )
        box.add_widget(cat_spinner)

        save = Button(text="Simpan", size_hint_y=None, height=dp(44))
        box.add_widget(save)
        popup = WhitePopup(title="Produk", content=box, size_hint=(.90, None), height=dp(500))

        def save_it(*_):
            try:
                cat = next(c for c in categories if c["name"] == cat_spinner.text)
                data = {
                    "id": product_id,
                    "barcode": fields["barcode"].text.strip(),
                    "name": fields["name"].text.strip(),
                    "category_id": cat["id"],
                    "buy_price": float(fields["buy_price"].text or 0),
                    "sell_price": float(fields["sell_price"].text or 0),
                    "stock": float(fields["stock"].text or 0),
                    "unit": fields["unit"].text.strip() or "pcs",
                    "min_stock": float(fields["min_stock"].text or 0),
                }
                if not data["name"] or data["sell_price"] < 0:
                    raise ValueError
                self.db.save_product(data)
                popup.dismiss()
                self.refresh_all()
            except Exception:
                self.info("Data tidak valid atau barcode sudah digunakan.")

        save.bind(on_release=save_it)
        popup.open()

    def delete_product(self, product_id):
        self.db.delete_product(product_id)
        self.refresh_all()

    def stock_form(self, product_id):
        p = self.db.product_by_id(product_id)
        if not p:
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

    def category_form(self):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        t = TextInput(
            hint_text="Nama kategori", multiline=False,
            size_hint_y=None, height=dp(42)
        )
        b = Button(text="Simpan", size_hint_y=None, height=dp(44))
        box.add_widget(t)
        box.add_widget(b)
        popup = WhitePopup(title="Kategori", content=box, size_hint=(.82, None), height=dp(180))

        def save_cat(*_):
            self.db.add_category(t.text)
            popup.dismiss()
            self.refresh_all()

        b.bind(on_release=save_cat)
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
