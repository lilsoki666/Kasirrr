import os
import sqlite3
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.graphics import Color, Rectangle

# -----------------------------------------------------------------------------
# DATABASE MANAGEMENT (SQLite)
# -----------------------------------------------------------------------------
class Database:
    def __init__(self, db_name="kasirrr.db"):
        self.conn = sqlite3.connect(db_name)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                image_path TEXT
            )
        ''')
        self.conn.commit()

    def add_product(self, name, price, image_path):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO products (name, price, image_path) VALUES (?, ?, ?)", 
                       (name, price, image_path))
        self.conn.commit()

    def get_all_products(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM products")
        return cursor.fetchall()


# -----------------------------------------------------------------------------
# MAIN APPLICATION LAYOUT (NAVIGASI HP + RESPONSIF)
# -----------------------------------------------------------------------------
class KasirrrApp(App):
    def build(self):
        self.title = "Kasirrr Mobile"
        self.db = Database()
        self.cart = {}
        self.selected_image_path = ""

        # Menggunakan TabbedPanel agar Menu Utama Lainnya Tidak Hilang
        root_panel = TabbedPanel(do_default_tab=False, tab_width=120)

        # Tab 1: Kasir & Produk (Menu Utama POS)
        tab_kasir = TabbedPanelItem(text="Kasir")
        tab_kasir.add_widget(self.build_kasir_screen())
        root_panel.add_widget(tab_kasir)

        # Tab 2: Menu Lain (Tempat Anda memasukkan fitur lain seperti Laporan/Stok)
        tab_menu_lain = TabbedPanelItem(text="Menu Lain")
        tab_menu_lain.add_widget(self.build_other_menu_screen())
        root_panel.add_widget(tab_menu_lain)

        self.load_products()
        return root_panel

    # -------------------------------------------------------------------------
    # LAYOUT KASIR (VERSI PORTRAIT MOBILE)
    # -------------------------------------------------------------------------
    def build_kasir_screen(self):
        # Layout Utama Vertikal (Atas: Katalog, Bawah: Keranjang & Checkout)
        main_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        # 1. Bar Atas: Cari Produk & Tambah Produk
        top_bar = BoxLayout(size_hint_y=None, height=45, spacing=5)
        self.search_input = TextInput(
            hint_text="Cari produk...",
            multiline=False,
            size_hint_x=0.65
        )
        self.search_input.bind(text=self.filter_products)

        btn_add_product = Button(
            text="+ Tambah",
            size_hint_x=0.35,
            background_color=(0.12, 0.16, 0.23, 1),
            color=(1, 1, 1, 1),
            bold=True
        )
        btn_add_product.bind(on_release=self.show_add_product_popup)

        top_bar.add_widget(self.search_input)
        top_bar.add_widget(btn_add_product)
        main_layout.add_widget(top_bar)

        # 2. Grid Katalog Produk (2 Kolom untuk Layar HP)
        scroll_products = ScrollView(size_hint=(1, 0.55))
        self.product_grid = GridLayout(cols=2, spacing=10, size_hint_y=None)
        self.product_grid.bind(minimum_height=self.product_grid.setter('height'))
        scroll_products.add_widget(self.product_grid)
        main_layout.add_widget(scroll_products)

        # 3. Section Keranjang (Bagian Bawah Layar HP)
        cart_box = BoxLayout(orientation='vertical', size_hint_y=0.4, spacing=5, padding=5)
        
        # Background Putih untuk Keranjang
        with cart_box.canvas.before:
            Color(0.92, 0.94, 0.96, 1)
            self.cart_rect = Rectangle(size=cart_box.size, pos=cart_box.pos)
        cart_box.bind(size=self._update_cart_rect, pos=self._update_cart_rect)

        cart_title = Label(
            text="[b]Daftar Pesanan[/b]", 
            markup=True, 
            size_hint_y=None, 
            height=25,
            color=(0,0,0,1)
        )
        cart_box.add_widget(cart_title)

        scroll_cart = ScrollView(size_hint=(1, 1))
        self.cart_container = BoxLayout(orientation='vertical', spacing=5, size_hint_y=None)
        self.cart_container.bind(minimum_height=self.cart_container.setter('height'))
        scroll_cart.add_widget(self.cart_container)
        cart_box.add_widget(scroll_cart)

        # Total & Button Bayar
        footer_cart = BoxLayout(size_hint_y=None, height=45, spacing=10)
        self.total_label = Label(
            text="[b]Total: Rp 0[/b]", 
            markup=True, 
            size_hint_x=0.5,
            color=(0,0,0,1)
        )
        
        btn_checkout = Button(
            text="BAYAR",
            size_hint_x=0.5,
            background_color=(0.06, 0.72, 0.51, 1),
            color=(1, 1, 1, 1),
            bold=True
        )
        btn_checkout.bind(on_release=self.process_checkout)

        footer_cart.add_widget(self.total_label)
        footer_cart.add_widget(btn_checkout)
        cart_box.add_widget(footer_cart)

        main_layout.add_widget(cart_box)
        return main_layout

    def _update_cart_rect(self, instance, value):
        self.cart_rect.pos = instance.pos
        self.cart_rect.size = instance.size

    # -------------------------------------------------------------------------
    # LAYOUT MENU LAIN (PLACEHOLDER MENU LAMA ANDA)
    # -------------------------------------------------------------------------
    def build_other_menu_screen(self):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        layout.add_widget(Label(text="Area Menu Lainnya (Laporan / Pengaturan / Stok)", font_size='14sp'))
        return layout

    # -------------------------------------------------------------------------
    # PEMILIHAN GAMBAR & TAMBAH PRODUK (FIXED PATH & CRASH)
    # -------------------------------------------------------------------------
    def show_add_product_popup(self, instance):
        self.selected_image_path = ""
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        input_name = TextInput(hint_text="Nama Produk", multiline=False)
        input_price = TextInput(hint_text="Harga Produk", multiline=False, input_filter='float')
        
        image_preview = Image(source='', size_hint_y=None, height=80)
        btn_choose_img = Button(text="Pilih Gambar", size_hint_y=None, height=40)

        def open_file_chooser(btn_inst):
            fc_content = BoxLayout(orientation='vertical')
            # Memulai dari directory home / storage user
            start_path = '/sdcard' if os.path.exists('/sdcard') else os.path.expanduser('~')
            file_chooser = FileChooserListView(path=start_path, filters=['*.png', '*.jpg', '*.jpeg'])
            fc_popup = Popup(title="Pilih Gambar", content=fc_content, size_hint=(0.95, 0.95))
            
            def select_file(inst):
                if file_chooser.selection:
                    path = file_chooser.selection[0]
                    if os.path.exists(path):
                        self.selected_image_path = path
                        image_preview.source = path
                        image_preview.reload()
                fc_popup.dismiss()

            btn_select = Button(text="Pilih", size_hint_y=None, height=40)
            btn_select.bind(on_release=select_file)
            fc_content.add_widget(file_chooser)
            fc_content.add_widget(btn_select)
            fc_popup.open()

        btn_choose_img.bind(on_release=open_file_chooser)

        content.add_widget(input_name)
        content.add_widget(input_price)
        content.add_widget(btn_choose_img)
        content.add_widget(image_preview)

        popup = Popup(title="Tambah Produk", content=content, size_hint=(0.85, 0.65))
        
        btn_save = Button(
            text="Simpan", 
            size_hint_y=None, 
            height=40,
            background_color=(0.06, 0.72, 0.51, 1),
            bold=True
        )

        def save_product(save_inst):
            name = input_name.text.strip()
            price_text = input_price.text.strip()
            if name and price_text:
                try:
                    price = float(price_text)
                    self.db.add_product(name, price, self.selected_image_path)
                    self.load_products()
                    popup.dismiss()
                except ValueError:
                    pass

        btn_save.bind(on_release=save_product)
        content.add_widget(btn_save)
        popup.open()

    def load_products(self, filter_text=""):
        self.product_grid.clear_widgets()
        products = self.db.get_all_products()

        for prod in products:
            p_id, p_name, p_price, p_image = prod
            
            if filter_text.lower() not in p_name.lower():
                continue

            card = BoxLayout(orientation='vertical', size_hint_y=None, height=140, padding=5, spacing=3)
            with card.canvas.before:
                Color(1, 1, 1, 1)
                rect = Rectangle(size=card.size, pos=card.pos)
            card.bind(size=lambda inst, val: setattr(rect, 'size', inst.size),
                      pos=lambda inst, val: setattr(rect, 'pos', inst.pos))

            img_source = p_image if p_image and os.path.exists(p_image) else ''
            img_widget = Image(source=img_source, size_hint_y=0.5)

            name_lbl = Label(text=f"[b]{p_name}[/b]", markup=True, size_hint_y=0.2, color=(0,0,0,1), font_size='12sp')
            price_lbl = Label(text=f"Rp {p_price:,.0f}", size_hint_y=0.15, color=(0.3,0.3,0.3,1), font_size='11sp')
            
            btn_add = Button(
                text="+ Tambah", 
                size_hint_y=0.15, 
                background_color=(0.12, 0.16, 0.23, 1),
                color=(1, 1, 1, 1),
                font_size='11sp'
            )
            btn_add.bind(on_release=lambda inst, pid=p_id, name=p_name, price=p_price: self.add_to_cart(pid, name, price))

            card.add_widget(img_widget)
            card.add_widget(name_lbl)
            card.add_widget(price_lbl)
            card.add_widget(btn_add)

            self.product_grid.add_widget(card)

    def filter_products(self, instance, text):
        self.load_products(filter_text=text)

    # -------------------------------------------------------------------------
    # KELOLA KERANJANG
    # -------------------------------------------------------------------------
    def add_to_cart(self, pid, name, price):
        if pid in self.cart:
            self.cart[pid]['qty'] += 1
        else:
            self.cart[pid] = {'name': name, 'price': price, 'qty': 1}
        self.update_cart_ui()

    def update_cart_qty(self, pid, delta):
        if pid in self.cart:
            self.cart[pid]['qty'] += delta
            if self.cart[pid]['qty'] <= 0:
                del self.cart[pid]
        self.update_cart_ui()

    def update_cart_ui(self):
        self.cart_container.clear_widgets()
        grand_total = 0

        for pid, item in self.cart.items():
            subtotal = item['price'] * item['qty']
            grand_total += subtotal

            row = BoxLayout(size_hint_y=None, height=35, spacing=5)
            lbl = Label(
                text=f"{item['name']} ({item['qty']}x)", 
                size_hint_x=0.6, 
                color=(0,0,0,1),
                font_size='11sp'
            )
            
            btn_minus = Button(text="-", size_hint_x=0.2, background_color=(0.8, 0.2, 0.2, 1))
            btn_plus = Button(text="+", size_hint_x=0.2, background_color=(0.2, 0.6, 0.2, 1))

            btn_minus.bind(on_release=lambda inst, p=pid: self.update_cart_qty(p, -1))
            btn_plus.bind(on_release=lambda inst, p=pid: self.update_cart_qty(p, 1))

            row.add_widget(lbl)
            row.add_widget(btn_minus)
            row.add_widget(btn_plus)

            self.cart_container.add_widget(row)

        self.total_label.text = f"[b]Total: Rp {grand_total:,.0f}[/b]"

    def process_checkout(self, instance):
        if not self.cart:
            return

        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        content.add_widget(Label(text="Transaksi Berhasil!", font_size='14sp'))
        
        btn_close = Button(text="OK", size_hint_y=None, height=40, background_color=(0.06, 0.72, 0.51, 1))
        popup = Popup(title="Status", content=content, size_hint=(0.7, 0.3))
        
        def reset_cart(inst):
            self.cart.clear()
            self.update_cart_ui()
            popup.dismiss()

        btn_close.bind(on_release=reset_cart)
        content.add_widget(btn_close)
        popup.open()


if __name__ == '__main__':
    KasirrrApp().run()
