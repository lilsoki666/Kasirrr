import os
import sqlite3
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, db
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalpopup import ModalPopup
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput


def get_db():
    conn = sqlite3.connect("pos_kasir.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS menu (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 nama TEXT NOT NULL,
                 kategori TEXT NOT NULL,
                 harga INTEGER NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS transaksi (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 faktur TEXT NOT NULL,
                 tanggal TEXT NOT NULL,
                 total INTEGER NOT NULL,
                 bayar INTEGER NOT NULL,
                 kembali INTEGER NOT NULL,
                 pembayaran TEXT DEFAULT 'TUNAI',
                 catatan TEXT DEFAULT '')"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS detail_transaksi (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 faktur TEXT NOT NULL,
                 menu_id INTEGER NOT NULL,
                 nama TEXT NOT NULL,
                 harga INTEGER NOT NULL,
                 jumlah INTEGER NOT NULL,
                 subtotal INTEGER NOT NULL)"""
    )

    c.execute("PRAGMA table_info(transaksi)")
    columns = [column[1] for column in c.fetchall()]
    if "pembayaran" not in columns:
        c.execute(
            "ALTER TABLE transaksi ADD COLUMN pembayaran TEXT DEFAULT 'TUNAI'"
        )
    if "catatan" not in columns:
        c.execute("ALTER TABLE transaksi ADD COLUMN catatan TEXT DEFAULT ''")

    c.execute("SELECT COUNT(*) FROM menu")
    if c.fetchone()[0] == 0:
        sample_menu = [
            ("Kopi Hitam", "Minuman", 10000),
            ("Es Teh Manis", "Minuman", 5000),
            ("Nasi Goreng", "Makanan", 15000),
            ("Mie Goreng", "Makanan", 12000),
            ("Roti Bakar", "Snack", 10000),
            ("Kentang Goreng", "Snack", 12000),
        ]
        c.executemany(
            "INSERT INTO menu (nama, kategori, harga) VALUES (?, ?, ?)",
            sample_menu,
        )

    conn.commit()
    conn.close()


def format_rupiah(angka):
    return f"Rp {angka:,}".replace(",", ".")


class RoundedButton(Button):

    def __init__(self, bg_color=(0.15, 0.65, 0.6, 1), radius=10, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.radius = radius
        self.background_color = (0, 0, 0, 0)
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg_color)
            RoundedRectangle(
                pos=self.pos, size=self.size, radius=[dp(self.radius)]
            )


class RoundedBox(BoxLayout):

    def __init__(
        self, bg_color=(1, 1, 1, 1), radius=10, border_color=None, **kwargs
    ):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.radius = radius
        self.border_color = border_color
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg_color)
            RoundedRectangle(
                pos=self.pos, size=self.size, radius=[dp(self.radius)]
            )


class CustomPopup(Popup):

    def __init__(self, title_text, content_widget, size_hint=(0.85, 0.8)):
        super().__init__()
        self.title = ""
        self.separator_height = 0
        self.size_hint = size_hint
        self.background = ""
        self.background_color = (0, 0, 0, 0)

        main_box = RoundedBox(
            orientation="vertical",
            bg_color=(0.95, 0.96, 0.98, 1),
            radius=15,
            padding=dp(15),
            spacing=dp(10),
        )

        header = RoundedBox(
            size_hint_y=None,
            height=dp(45),
            bg_color=(0.15, 0.65, 0.6, 1),
            radius=10,
            padding=[dp(15), 0],
        )
        title_label = Label(
            text=title_text,
            font_size=dp(16),
            bold=True,
            color=(1, 1, 1, 1),
            halign="left",
            valign="middle",
        )
        title_label.bind(size=title_label.setter("text_size"))
        header.add_widget(title_label)

        close_btn = Button(
            text="X",
            size_hint=(None, None),
            size=(dp(30), dp(30)),
            background_color=(0, 0, 0, 0),
            color=(1, 1, 1, 1),
            bold=True,
            pos_hint={"center_y": 0.5},
        )
        close_btn.bind(on_release=self.dismiss)
        header.add_widget(close_btn)

        main_box.add_widget(header)
        main_box.add_widget(content_widget)

        self.content = main_box


class MenuManagementWidget(BoxLayout):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(10)

        form = RoundedBox(
            orientation="vertical",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(190),
            bg_color=(1, 1, 1, 1),
            padding=dp(10),
        )

        self.txt_nama = TextInput(
            hint_text="Nama Menu",
            multiline=False,
            size_hint_y=None,
            height=dp(38),
        )

        kat_box = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(5))
        self.selected_kategori = "Makanan"
        self.btn_dropdown = RoundedButton(
            text=f"Kategori: {self.selected_kategori}",
            bg_color=(0.85, 0.87, 0.9, 1),
            color=(0.2, 0.2, 0.2, 1),
            radius=5,
        )

        self.dropdown = DropDown()
        for kat in ["Makanan", "Minuman", "Snack"]:
            btn = Button(
                text=kat,
                size_hint_y=None,
                height=dp(35),
                background_normal="",
                background_color=(0.9, 0.92, 0.95, 1),
                color=(0.2, 0.2, 0.2, 1),
            )
            btn.bind(
                on_release=lambda btn: self.select_kategori(
                    btn.text, self.dropdown
                )
            )
            self.dropdown.add_widget(btn)

        self.btn_dropdown.bind(on_release=self.dropdown.open)
        kat_box.add_widget(self.btn_dropdown)

        self.txt_harga = TextInput(
            hint_text="Harga (Rp)",
            multiline=False,
            input_filter="int",
            size_hint_y=None,
            height=dp(38),
        )

        btn_simpan = RoundedButton(
            text="Tambah Menu",
            size_hint_y=None,
            height=dp(40),
            bg_color=(0.15, 0.65, 0.6, 1),
            color=(1, 1, 1, 1),
            bold=True,
        )
        btn_simpan.bind(on_release=self.tambah_menu)

        form.add_widget(self.txt_nama)
        form.add_widget(kat_box)
        form.add_widget(self.txt_harga)
        form.add_widget(btn_simpan)

        self.add_widget(form)

        scroll = ScrollView()
        self.grid_menu = GridLayout(
            cols=1, spacing=dp(5), size_hint_y=None, padding=[0, dp(5)]
        )
        self.grid_menu.bind(
            minimum_height=self.grid_menu.setter("height")
        )
        scroll.add_widget(self.grid_menu)
        self.add_widget(scroll)

        self.load_menu_list()

    def select_kategori(self, text, dropdown):
        self.selected_kategori = text
        self.btn_dropdown.text = f"Kategori: {text}"
        dropdown.dismiss()

    def tambah_menu(self, instance):
        nama = self.txt_nama.text.strip()
        harga_str = self.txt_harga.text.strip()

        if not nama or not harga_str:
            return

        try:
            harga = int(harga_str)
        except ValueError:
            return

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO menu (nama, kategori, harga) VALUES (?, ?, ?)",
            (nama, self.selected_kategori, harga),
        )
        conn.commit()
        conn.close()

        self.txt_nama.text = ""
        self.txt_harga.text = ""
        self.load_menu_list()

        app = App.get_running_app()
        if hasattr(app, "kasir_screen"):
            app.kasir_screen.load_menu()

    def load_menu_list(self):
        self.grid_menu.clear_widgets()
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM menu ORDER BY id DESC")
        menus = c.fetchall()
        conn.close()

        for m in menus:
            row = RoundedBox(
                size_hint_y=None,
                height=dp(50),
                bg_color=(1, 1, 1, 1),
                padding=dp(8),
                spacing=dp(5),
            )

            info_box = BoxLayout(orientation="vertical")
            lbl_nama = Label(
                text=f"[b]{m['nama']}[/b]",
                markup=True,
                font_size=dp(13),
                color=(0.2, 0.2, 0.2, 1),
                halign="left",
                valign="middle",
            )
            lbl_nama.bind(size=lbl_nama.setter("text_size"))
            lbl_sub = Label(
                text=f"{m['kategori']} • {format_rupiah(m['harga'])}",
                font_size=dp(11),
                color=(0.5, 0.5, 0.5, 1),
                halign="left",
                valign="middle",
            )
            lbl_sub.bind(size=lbl_sub.setter("text_size"))
            info_box.add_widget(lbl_nama)
            info_box.add_widget(lbl_sub)

            btn_hapus = RoundedButton(
                text="Hapus",
                size_hint=(None, None),
                size=(dp(60), dp(34)),
                bg_color=(0.9, 0.3, 0.3, 1),
                color=(1, 1, 1, 1),
                font_size=dp(11),
                pos_hint={"center_y": 0.5},
            )
            btn_hapus.bind(
                on_release=lambda btn, menu_id=m["id"]: self.hapus_menu(
                    menu_id
                )
            )

            row.add_widget(info_box)
            row.add_widget(btn_hapus)
            self.grid_menu.add_widget(row)

    def hapus_menu(self, menu_id):
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM menu WHERE id = ?", (menu_id,))
        conn.commit()
        conn.close()

        self.load_menu_list()

        app = App.get_running_app()
        if hasattr(app, "kasir_screen"):
            app.kasir_screen.load_menu()


class RiwayatWidget(BoxLayout):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(10)

        scroll = ScrollView()
        self.grid_riwayat = GridLayout(
            cols=1, spacing=dp(8), size_hint_y=None, padding=[0, dp(5)]
        )
        self.grid_riwayat.bind(
            minimum_height=self.grid_riwayat.setter("height")
        )
        scroll.add_widget(self.grid_riwayat)
        self.add_widget(scroll)

        self.load_riwayat()

    def load_riwayat(self):
        self.grid_riwayat.clear_widgets()
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM transaksi ORDER BY id DESC")
        transaksi_list = c.fetchall()
        conn.close()

        for t in transaksi_list:
            row = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(70),
                bg_color=(1, 1, 1, 1),
                padding=dp(10),
                spacing=dp(3),
            )

            top_box = BoxLayout()
            lbl_faktur = Label(
                text=f"[b]{t['faktur']}[/b]",
                markup=True,
                font_size=dp(13),
                color=(0.2, 0.2, 0.2, 1),
                halign="left",
                valign="middle",
            )
            lbl_faktur.bind(size=lbl_faktur.setter("text_size"))

            lbl_total = Label(
                text=format_rupiah(t["total"]),
                font_size=dp(13),
                bold=True,
                color=(0.15, 0.65, 0.6, 1),
                halign="right",
                valign="middle",
            )
            lbl_total.bind(size=lbl_total.setter("text_size"))

            top_box.add_widget(lbl_faktur)
            top_box.add_widget(lbl_total)

            bottom_box = BoxLayout()
            metode = t["pembayaran"] if "pembayaran" in t.keys() else "TUNAI"
            lbl_detail = Label(
                text=f"{t['tanggal']} • {metode}",
                font_size=dp(11),
                color=(0.5, 0.5, 0.5, 1),
                halign="left",
                valign="middle",
            )
            lbl_detail.bind(size=lbl_detail.setter("text_size"))

            btn_detail = RoundedButton(
                text="Detail",
                size_hint=(None, None),
                size=(dp(55), dp(25)),
                bg_color=(0.85, 0.87, 0.9, 1),
                color=(0.2, 0.2, 0.2, 1),
                font_size=dp(10),
            )
            btn_detail.bind(
                on_release=lambda btn, faktur=t["faktur"]: self.show_detail(
                    faktur
                )
            )

            bottom_box.add_widget(lbl_detail)
            bottom_box.add_widget(btn_detail)

            row.add_widget(top_box)
            row.add_widget(bottom_box)
            self.grid_riwayat.add_widget(row)

    def show_detail(self, faktur):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM transaksi WHERE faktur = ?", (faktur,))
        trans = c.fetchone()

        c.execute(
            "SELECT * FROM detail_transaksi WHERE faktur = ?", (faktur,)
        )
        details = c.fetchall()
        conn.close()

        if not trans:
            return

        detail_box = BoxLayout(orientation="vertical", spacing=dp(8))

        info_str = (
            f"Faktur: {trans['faktur']}\n"
            f"Tanggal: {trans['tanggal']}\n"
            f"Metode: {trans['pembayaran']}\n"
        )
        if trans["catatan"]:
            info_str += f"Catatan: {trans['catatan']}\n"

        lbl_info = Label(
            text=info_str,
            font_size=dp(12),
            color=(0.3, 0.3, 0.3, 1),
            size_hint_y=None,
            height=dp(60),
            halign="left",
        )
        lbl_info.bind(size=lbl_info.setter("text_size"))
        detail_box.add_widget(lbl_info)

        scroll_item = ScrollView()
        grid_item = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        grid_item.bind(minimum_height=grid_item.setter("height"))

        for d in details:
            item_row = BoxLayout(size_hint_y=None, height=dp(25))
            l1 = Label(
                text=f"{d['nama']} x{d['jumlah']}",
                font_size=dp(12),
                color=(0.2, 0.2, 0.2, 1),
                halign="left",
            )
            l1.bind(size=l1.setter("text_size"))
            l2 = Label(
                text=format_rupiah(d["subtotal"]),
                font_size=dp(12),
                color=(0.2, 0.2, 0.2, 1),
                halign="right",
            )
            l2.bind(size=l2.setter("text_size"))
            item_row.add_widget(l1)
            item_row.add_widget(l2)
            grid_item.add_widget(item_row)

        scroll_item.add_widget(grid_item)
        detail_box.add_widget(scroll_item)

        tot_str = (
            f"Total: {format_rupiah(trans['total'])}\n"
            f"Bayar: {format_rupiah(trans['bayar'])}\n"
            f"Kembali: {format_rupiah(trans['kembali'])}"
        )
        lbl_tot = Label(
            text=tot_str,
            font_size=dp(12),
            bold=True,
            color=(0.15, 0.65, 0.6, 1),
            size_hint_y=None,
            height=dp(55),
            halign="right",
        )
        lbl_tot.bind(size=lbl_tot.setter("text_size"))
        detail_box.add_widget(lbl_tot)

        popup = CustomPopup(f"Detail {faktur}", detail_box)
        popup.open()


class LaporanWidget(BoxLayout):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(10)

        self.lbl_ringkasan = Label(
            text="Memuat laporan...",
            markup=True,
            font_size=dp(13),
            color=(0.2, 0.2, 0.2, 1),
            size_hint_y=None,
            height=dp(100),
            halign="left",
            valign="top",
        )
        self.lbl_ringkasan.bind(size=self.lbl_ringkasan.setter("text_size"))

        ringkasan_box = RoundedBox(
            orientation="vertical",
            bg_color=(1, 1, 1, 1),
            padding=dp(12),
            size_hint_y=None,
            height=dp(120),
        )
        ringkasan_box.add_widget(self.lbl_ringkasan)
        self.add_widget(ringkasan_box)

        lbl_top = Label(
            text="[b]Menu Terlaris[/b]",
            markup=True,
            font_size=dp(14),
            color=(0.2, 0.2, 0.2, 1),
            size_hint_y=None,
            height=dp(25),
            halign="left",
        )
        lbl_top.bind(size=lbl_top.setter("text_size"))
        self.add_widget(lbl_top)

        scroll = ScrollView()
        self.grid_laris = GridLayout(
            cols=1, spacing=dp(5), size_hint_y=None, padding=[0, dp(5)]
        )
        self.grid_laris.bind(minimum_height=self.grid_laris.setter("height"))
        scroll.add_widget(self.grid_laris)
        self.add_widget(scroll)

        self.load_laporan()

    def load_laporan(self):
        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT COUNT(*), SUM(total) FROM transaksi")
        res = c.fetchone()
        tot_trans = res[0] or 0
        tot_omset = res[1] or 0

        today_str = datetime.now().strftime("%Y-%m-%d")
        c.execute(
            "SELECT COUNT(*), SUM(total) FROM transaksi WHERE tanggal LIKE ?",
            (f"{today_str}%",),
        )
        res_today = c.fetchone()
        today_trans = res_today[0] or 0
        today_omset = res_today[1] or 0

        self.lbl_ringkasan.text = (
            f"[b]Hari Ini ({today_str}):[/b]\n"
            f"• Transaksi: {today_trans}\n"
            f"• Omset: {format_rupiah(today_omset)}\n\n"
            f"[b]Total Keseluruhan:[/b]\n"
            f"• Transaksi: {tot_trans}\n"
            f"• Omset: {format_rupiah(tot_omset)}"
        )

        self.grid_laris.clear_widgets()
        c.execute(
            """SELECT nama, SUM(jumlah) as total_qty, SUM(subtotal) as total_rp
                     FROM detail_transaksi
                     GROUP BY nama
                     ORDER BY total_qty DESC
                     LIMIT 10"""
        )
        laris_list = c.fetchall()
        conn.close()

        for idx, item in enumerate(laris_list, start=1):
            row = RoundedBox(
                size_hint_y=None,
                height=dp(40),
                bg_color=(1, 1, 1, 1),
                padding=[dp(10), 0],
            )
            l1 = Label(
                text=f"{idx}. {item['nama']}",
                font_size=dp(12),
                color=(0.2, 0.2, 0.2, 1),
                halign="left",
                valign="middle",
            )
            l1.bind(size=l1.setter("text_size"))

            l2 = Label(
                text=f"{item['total_qty']} porsi ({format_rupiah(item['total_rp'])})",
                font_size=dp(12),
                bold=True,
                color=(0.15, 0.65, 0.6, 1),
                halign="right",
                valign="middle",
            )
            l2.bind(size=l2.setter("text_size"))

            row.add_widget(l1)
            row.add_widget(l2)
            self.grid_laris.add_widget(row)


class KasirScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.cart = {}
        self.kategori_aktif = "Semua"

        main_layout = BoxLayout(orientation="vertical", spacing=0)

        header = RoundedBox(
            size_hint_y=None,
            height=dp(55),
            bg_color=(0.15, 0.65, 0.6, 1),
            radius=0,
            padding=[dp(15), 0],
        )
        lbl_title = Label(
            text="UT Kasirrr",
            font_size=dp(18),
            bold=True,
            color=(1, 1, 1, 1),
            halign="left",
            valign="middle",
        )
        lbl_title.bind(size=lbl_title.setter("text_size"))

        btn_menu_mgm = RoundedButton(
            text="Kelola Menu",
            size_hint=(None, None),
            size=(dp(90), dp(32)),
            bg_color=(0.2, 0.75, 0.7, 1),
            color=(1, 1, 1, 1),
            font_size=dp(11),
            pos_hint={"center_y": 0.5},
        )
        btn_menu_mgm.bind(on_release=self.open_menu_management)

        btn_riwayat = RoundedButton(
            text="Riwayat",
            size_hint=(None, None),
            size=(dp(70), dp(32)),
            bg_color=(0.2, 0.75, 0.7, 1),
            color=(1, 1, 1, 1),
            font_size=dp(11),
            pos_hint={"center_y": 0.5},
        )
        btn_riwayat.bind(on_release=self.open_riwayat)

        btn_laporan = RoundedButton(
            text="Laporan",
            size_hint=(None, None),
            size=(dp(70), dp(32)),
            bg_color=(0.2, 0.75, 0.7, 1),
            color=(1, 1, 1, 1),
            font_size=dp(11),
            pos_hint={"center_y": 0.5},
        )
        btn_laporan.bind(on_release=self.open_laporan)

        header.add_widget(lbl_title)
        header.add_widget(btn_menu_mgm)
        header.add_widget(
            BoxLayout(size_hint_x=None, width=dp(5))
        )  # spacer
        header.add_widget(btn_riwayat)
        header.add_widget(
            BoxLayout(size_hint_x=None, width=dp(5))
        )  # spacer
        header.add_widget(btn_laporan)

        main_layout.add_widget(header)

        content = BoxLayout(
            orientation="horizontal", padding=dp(10), spacing=dp(10)
        )

        left_side = BoxLayout(orientation="vertical", spacing=dp(10))

        kat_bar = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(5))
        self.kat_buttons = {}
        for kat in ["Semua", "Makanan", "Minuman", "Snack"]:
            btn = RoundedButton(
                text=kat,
                bg_color=(
                    (0.15, 0.65, 0.6, 1)
                    if kat == "Semua"
                    else (0.85, 0.87, 0.9, 1)
                ),
                color=(
                    (1, 1, 1, 1) if kat == "Semua" else (0.3, 0.3, 0.3, 1)
                ),
                font_size=dp(12),
                radius=8,
            )
            btn.bind(
                on_release=lambda instance, k=kat: self.filter_kategori(k)
            )
            self.kat_buttons[kat] = btn
            kat_bar.add_widget(btn)

        left_side.add_widget(kat_bar)

        scroll_menu = ScrollView()
        self.grid_menu = GridLayout(
            cols=2, spacing=dp(8), size_hint_y=None, padding=[0, dp(2)]
        )
        self.grid_menu.bind(minimum_height=self.grid_menu.setter("height"))
        scroll_menu.add_widget(self.grid_menu)

        left_side.add_widget(scroll_menu)

        right_side = RoundedBox(
            orientation="vertical",
            bg_color=(1, 1, 1, 1),
            radius=12,
            padding=dp(10),
            spacing=dp(8),
            size_hint_x=0.45,
        )

        lbl_cart_title = Label(
            text="[b]Pesanan[/b]",
            markup=True,
            font_size=dp(14),
            color=(0.2, 0.2, 0.2, 1),
            size_hint_y=None,
            height=dp(25),
            halign="left",
        )
        lbl_cart_title.bind(size=lbl_cart_title.setter("text_size"))
        right_side.add_widget(lbl_cart_title)

        scroll_cart = ScrollView()
        self.grid_cart = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.grid_cart.bind(minimum_height=self.grid_cart.setter("height"))
        scroll_cart.add_widget(self.grid_cart)
        right_side.add_widget(scroll_cart)

        total_box = BoxLayout(size_hint_y=None, height=dp(30))
        lbl_tot_text = Label(
            text="Total:",
            font_size=dp(13),
            bold=True,
            color=(0.2, 0.2, 0.2, 1),
            halign="left",
        )
        lbl_tot_text.bind(size=lbl_tot_text.setter("text_size"))
        self.lbl_total_val = Label(
            text="Rp 0",
            font_size=dp(15),
            bold=True,
            color=(0.15, 0.65, 0.6, 1),
            halign="right",
        )
        self.lbl_total_val.bind(
            size=self.lbl_total_val.setter("text_size")
        )
        total_box.add_widget(lbl_tot_text)
        total_box.add_widget(self.lbl_total_val)
        right_side.add_widget(total_box)

        btn_bayar = RoundedButton(
            text="BAYAR",
            size_hint_y=None,
            height=dp(42),
            bg_color=(0.15, 0.65, 0.6, 1),
            color=(1, 1, 1, 1),
            font_size=dp(14),
            bold=True,
        )
        btn_bayar.bind(on_release=self.open_bayar_popup)
        right_side.add_widget(btn_bayar)

        content.add_widget(left_side)
        content.add_widget(right_side)

        main_layout.add_widget(content)
        self.add_widget(main_layout)

        self.load_menu()

    def filter_kategori(self, kategori):
        self.kategori_aktif = kategori
        for k, btn in self.kat_buttons.items():
            if k == kategori:
                btn.bg_color = (0.15, 0.65, 0.6, 1)
                btn.color = (1, 1, 1, 1)
            else:
                btn.bg_color = (0.85, 0.87, 0.9, 1)
                btn.color = (0.3, 0.3, 0.3, 1)
            btn.update_canvas()
        self.load_menu()

    def load_menu(self):
        self.grid_menu.clear_widgets()
        conn = get_db()
        c = conn.cursor()

        if self.kategori_aktif == "Semua":
            c.execute("SELECT * FROM menu")
        else:
            c.execute(
                "SELECT * FROM menu WHERE kategori = ?",
                (self.kategori_aktif,),
            )

        menus = c.fetchall()
        conn.close()

        for m in menus:
            btn_item = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(65),
                bg_color=(1, 1, 1, 1),
                padding=dp(8),
                spacing=dp(2),
            )

            lbl_nama = Label(
                text=f"[b]{m['nama']}[/b]",
                markup=True,
                font_size=dp(12),
                color=(0.2, 0.2, 0.2, 1),
                halign="left",
                valign="top",
            )
            lbl_nama.bind(size=lbl_nama.setter("text_size"))

            lbl_harga = Label(
                text=format_rupiah(m["harga"]),
                font_size=dp(11),
                color=(0.15, 0.65, 0.6, 1),
                bold=True,
                halign="left",
                valign="bottom",
            )
            lbl_harga.bind(size=lbl_harga.setter("text_size"))

            btn_item.add_widget(lbl_nama)
            btn_item.add_widget(lbl_harga)

            btn_item.bind(
                on_touch_down=lambda instance, touch, item=m: self.on_menu_touch(
                    instance, touch, item
                )
            )

            self.grid_menu.add_widget(btn_item)

    def on_menu_touch(self, instance, touch, item):
        if instance.collide_point(*touch.pos):
            self.add_to_cart(item)
            return True
        return False

    def add_to_cart(self, item):
        item_id = item["id"]
        if item_id in self.cart:
            self.cart[item_id]["jumlah"] += 1
        else:
            self.cart[item_id] = {
                "nama": item["nama"],
                "harga": item["harga"],
                "jumlah": 1,
            }
        self.update_cart_ui()

    def update_cart_ui(self):
        self.grid_cart.clear_widgets()
        grand_total = 0

        for item_id, item in self.cart.items():
            subtotal = item["harga"] * item["jumlah"]
            grand_total += subtotal

            row = BoxLayout(
                size_hint_y=None, height=dp(35), spacing=dp(4)
            )

            info_box = BoxLayout(orientation="vertical")
            lbl_nama = Label(
                text=item["nama"],
                font_size=dp(11),
                color=(0.2, 0.2, 0.2, 1),
                halign="left",
            )
            lbl_nama.bind(size=lbl_nama.setter("text_size"))
            lbl_sub = Label(
                text=format_rupiah(subtotal),
                font_size=dp(10),
                color=(0.5, 0.5, 0.5, 1),
                halign="left",
            )
            lbl_sub.bind(size=lbl_sub.setter("text_size"))
            info_box.add_widget(lbl_nama)
            info_box.add_widget(lbl_sub)

            qty_box = BoxLayout(
                size_hint_x=None, width=dp(70), spacing=dp(2)
            )
            btn_min = RoundedButton(
                text="-",
                bg_color=(0.85, 0.87, 0.9, 1),
                color=(0.2, 0.2, 0.2, 1),
                radius=4,
            )
            btn_min.bind(
                on_release=lambda instance, i_id=item_id: self.change_qty(
                    i_id, -1
                )
            )

            lbl_qty = Label(
                text=str(item["jumlah"]),
                font_size=dp(11),
                color=(0.2, 0.2, 0.2, 1),
            )

            btn_plus = RoundedButton(
                text="+",
                bg_color=(0.85, 0.87, 0.9, 1),
                color=(0.2, 0.2, 0.2, 1),
                radius=4,
            )
            btn_plus.bind(
                on_release=lambda instance, i_id=item_id: self.change_qty(
                    i_id, 1
                )
            )

            qty_box.add_widget(btn_min)
            qty_box.add_widget(lbl_qty)
            qty_box.add_widget(btn_plus)

            row.add_widget(info_box)
            row.add_widget(qty_box)

            self.grid_cart.add_widget(row)

        self.lbl_total_val.text = format_rupiah(grand_total)

    def change_qty(self, item_id, delta):
        if item_id in self.cart:
            self.cart[item_id]["jumlah"] += delta
            if self.cart[item_id]["jumlah"] <= 0:
                del self.cart[item_id]
            self.update_cart_ui()

    def get_grand_total(self):
        return sum(
            item["harga"] * item["jumlah"] for item in self.cart.values()
        )

    def open_bayar_popup(self, instance):
        if not self.cart:
            return

        total = self.get_grand_total()

        content = BoxLayout(orientation="vertical", spacing=dp(10))

        lbl_tot = Label(
            text=f"Total: [b]{format_rupiah(total)}[/b]",
            markup=True,
            font_size=dp(16),
            color=(0.15, 0.65, 0.6, 1),
            size_hint_y=None,
            height=dp(30),
        )
        content.add_widget(lbl_tot)

        lbl_metode = Label(
            text="Metode Pembayaran:",
            font_size=dp(12),
            color=(0.3, 0.3, 0.3, 1),
            size_hint_y=None,
            height=dp(20),
            halign="left",
        )
        lbl_metode.bind(size=lbl_metode.setter("text_size"))
        content.add_widget(lbl_metode)

        self.selected_metode = "TUNAI"
        metode_box = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(5))
        self.btn_metode_tunai = RoundedButton(
            text="TUNAI",
            bg_color=(0.15, 0.65, 0.6, 1),
            color=(1, 1, 1, 1),
            radius=6,
        )
        self.btn_metode_qris = RoundedButton(
            text="QRIS / DEBIT",
            bg_color=(0.85, 0.87, 0.9, 1),
            color=(0.3, 0.3, 0.3, 1),
            radius=6,
        )

        self.btn_metode_tunai.bind(
            on_release=lambda x: self.select_metode("TUNAI")
        )
        self.btn_metode_qris.bind(
            on_release=lambda x: self.select_metode("QRIS / DEBIT")
        )

        metode_box.add_widget(self.btn_metode_tunai)
        metode_box.add_widget(self.btn_metode_qris)
        content.add_widget(metode_box)

        self.txt_bayar = TextInput(
            hint_text="Nominal Bayar (Rp)",
            multiline=False,
            input_filter="int",
            size_hint_y=None,
            height=dp(40),
            font_size=dp(14),
        )
        content.add_widget(self.txt_bayar)

        quick_box = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(5))
        btn_pas = RoundedButton(
            text="Uang Pas",
            bg_color=(0.85, 0.87, 0.9, 1),
            color=(0.2, 0.2, 0.2, 1),
            font_size=dp(10),
            radius=5,
        )
        btn_pas.bind(on_release=lambda x: self.set_bayar_quick(total))

        btn_50 = RoundedButton(
            text="50.000",
            bg_color=(0.85, 0.87, 0.9, 1),
            color=(0.2, 0.2, 0.2, 1),
            font_size=dp(10),
            radius=5,
        )
        btn_50.bind(on_release=lambda x: self.set_bayar_quick(50000))

        btn_100 = RoundedButton(
            text="100.000",
            bg_color=(0.85, 0.87, 0.9, 1),
            color=(0.2, 0.2, 0.2, 1),
            font_size=dp(10),
            radius=5,
        )
        btn_100.bind(on_release=lambda x: self.set_bayar_quick(100000))

        quick_box.add_widget(btn_pas)
        quick_box.add_widget(btn_50)
        quick_box.add_widget(btn_100)
        content.add_widget(quick_box)

        self.txt_catatan = TextInput(
            hint_text="Catatan (opsional)",
            multiline=False,
            size_hint_y=None,
            height=dp(35),
            font_size=dp(12),
        )
        content.add_widget(self.txt_catatan)

        btn_proses = RoundedButton(
            text="PROSES TRANSAKSI",
            size_hint_y=None,
            height=dp(42),
            bg_color=(0.15, 0.65, 0.6, 1),
            color=(1, 1, 1, 1),
            bold=True,
        )
        btn_proses.bind(on_release=self.proses_transaksi)
        content.add_widget(btn_proses)

        self.popup_bayar = CustomPopup(
            "Pembayaran", content, size_hint=(0.8, 0.75)
        )
        self.popup_bayar.open()

    def select_metode(self, metode):
        self.selected_metode = metode
        if metode == "TUNAI":
            self.btn_metode_tunai.bg_color = (0.15, 0.65, 0.6, 1)
            self.btn_metode_tunai.color = (1, 1, 1, 1)
            self.btn_metode_qris.bg_color = (0.85, 0.87, 0.9, 1)
            self.btn_metode_qris.color = (0.3, 0.3, 0.3, 1)
        else:
            self.btn_metode_qris.bg_color = (0.15, 0.65, 0.6, 1)
            self.btn_metode_qris.color = (1, 1, 1, 1)
            self.btn_metode_tunai.bg_color = (0.85, 0.87, 0.9, 1)
            self.btn_metode_tunai.color = (0.3, 0.3, 0.3, 1)
        self.btn_metode_tunai.update_canvas()
        self.btn_metode_qris.update_canvas()

    def set_bayar_quick(self, nominal):
        self.txt_bayar.text = str(nominal)

    def proses_transaksi(self, instance):
        total = self.get_grand_total()
        bayar_str = self.txt_bayar.text.strip()

        if not bayar_str:
            return

        try:
            bayar = int(bayar_str)
        except ValueError:
            return

        if bayar < total:
            return

        kembali = bayar - total
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        faktur = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        catatan = self.txt_catatan.text.strip()

        conn = get_db()
        c = conn.cursor()
        c.execute(
            """INSERT INTO transaksi (faktur, tanggal, total, bayar, kembali, pembayaran, catatan)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                faktur,
                now_str,
                total,
                bayar,
                kembali,
                self.selected_metode,
                catatan,
            ),
        )

        for item_id, item in self.cart.items():
            subtotal = item["harga"] * item["jumlah"]
            c.execute(
                """INSERT INTO detail_transaksi (faktur, menu_id, nama, harga, jumlah, subtotal)
                         VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    faktur,
                    item_id,
                    item["nama"],
                    item["harga"],
                    item["jumlah"],
                    subtotal,
                ),
            )

        conn.commit()
        conn.close()

        self.popup_bayar.dismiss()
        self.show_struk(faktur, now_str, total, bayar, kembali, catatan)

        self.cart.clear()
        self.update_cart_ui()

    def show_struk(self, faktur, tanggal, total, bayar, kembali, catatan):
        content = BoxLayout(orientation="vertical", spacing=dp(8))

        struk_text = (
            f"[b]UT KASIRRR[/b]\n"
            f"Faktur: {faktur}\n"
            f"Tgl: {tanggal}\n"
            f"Metode: {self.selected_metode}\n"
            f"-----------------------------------\n"
        )

        for item in self.cart.values():
            subtotal = item["harga"] * item["jumlah"]
            struk_text += f"{item['nama']} x{item['jumlah']} = {format_rupiah(subtotal)}\n"

        struk_text += (
            f"-----------------------------------\n"
            f"Total: {format_rupiah(total)}\n"
            f"Bayar: {format_rupiah(bayar)}\n"
            f"Kembali: {format_rupiah(kembali)}\n"
        )

        if catatan:
            struk_text += f"Catatan: {catatan}\n"

        struk_text += "\nTerima kasih telah berbelanja!"

        scroll = ScrollView()
        lbl_struk = Label(
            text=struk_text,
            markup=True,
            font_size=dp(11),
            color=(0.2, 0.2, 0.2, 1),
            size_hint_y=None,
            halign="center",
        )
        lbl_struk.bind(
            texture_size=lambda instance, value: setattr(
                instance, "height", value[1]
            )
        )
        scroll.add_widget(lbl_struk)
        content.add_widget(scroll)

        popup = CustomPopup("Struk Transaksi", content, size_hint=(0.8, 0.8))
        popup.open()

    def open_menu_management(self, instance):
        widget = MenuManagementWidget()
        popup = CustomPopup("Kelola Menu", widget, size_hint=(0.85, 0.85))
        popup.open()

    def open_riwayat(self, instance):
        widget = RiwayatWidget()
        popup = CustomPopup(
            "Riwayat Transaksi", widget, size_hint=(0.85, 0.85)
        )
        popup.open()

    def open_laporan(self, instance):
        widget = LaporanWidget()
        popup = CustomPopup("Laporan Penjualan", widget, size_hint=(0.85, 0.85))
        popup.open()


class KasirApp(App):

    def build(self):
        init_db()
        sm = ScreenManager()
        self.kasir_screen = KasirScreen(name="kasir")
        sm.add_widget(self.kasir_screen)
        return sm


if __name__ == "__main__":
    KasirApp().run()
