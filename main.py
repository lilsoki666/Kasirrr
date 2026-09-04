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
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle

# Set Resolusi Window Awal (Ideal untuk Layar Tablet/Desktop POS)
Window.size = (1100, 700)

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
# MAIN APPLICATION LAYOUT (UI/UX MODERN)
# -----------------------------------------------------------------------------
class KasirrrApp(App):
    def build(self):
        self.title = "Kasirrr - Point of Sale Professional"
        self.db = Database()
        self.cart = {}  # Format: {product_id: {'name': str, 'price': float, 'qty': int}}
        self.selected_image_path = ""

        # Root Layout Horizontal (Kiri: Produk 70%, Kanan: Keranjang 30%)
        root = BoxLayout(orientation='horizontal', spacing=10, padding=10)
        
        # Set Background Warna Dasar Soft Light Gray (#F8FAFC)
        with root.canvas.before:
            Color(0.97, 0.98, 0.98, 1)
            self.rect = Rectangle(size=Window.size, pos=root.pos)
        root.bind(size=self._update_rect, pos=self._update_rect)

        # Build Komponen Utama
        left_panel = self.build_left_panel()
        right_panel = self.build_right_panel()

        root.add_widget(left_panel)
        root.add_widget(right_panel)

        self.load_products()
        return root

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    # -------------------------------------------------------------------------
    # LAYOUT KIRI: KATALOG PRODUK & SEARCH BAR (70% WIDTH)
    # -------------------------------------------------------------------------
    def build_left_panel(self):
        panel = BoxLayout(orientation='vertical', size_hint_x=0.7, spacing=10)

        # Header Bar & Tombol Tambah Produk
        top_bar = BoxLayout(size_hint_y=None, height=50, spacing=10)
        
        self.search_input = TextInput(
            hint_text="Cari produk...",
            multiline=False,
            size_hint_x=0.8,
            padding=[10, 12, 10, 10],
            background_color=(1, 1, 1, 1)
        )
        self.search_input.bind(text=self.filter_products)

        btn_add_product = Button(
            text="+ Tambah Produk",
            size_hint_x=0.2,
            background_color=(0.12, 0.16, 0.23, 1), # Deep Slate Blue
            color=(1, 1, 1, 1),
            bold=True
        )
        btn_add_product.bind(on_release=self.show_add_product_popup)

        top_bar.add_widget(self.search_input)
        top_bar.add_widget(btn_add_product)
        panel.add_widget(top_bar)

        # Grid Katalog Produk (Scrollable)
        scroll = ScrollView(size_hint=(1, 1))
        self.product_grid = GridLayout(cols=3, spacing=15, size_hint_y=None)
        self.product_grid.bind(minimum_height=self.product_grid.setter('height'))
        scroll.add_widget(self.product_grid)

        panel.add_widget(scroll)
        return panel

    # -------------------------------------------------------------------------
    # LAYOUT KANAN: PANEL KERANJANG & CHECKOUT (30% WIDTH)
    # -------------------------------------------------------------------------
    def build_right_panel(self):
        panel = BoxLayout(orientation='vertical', size_hint_x=0.3, spacing=10, padding=10)
        
        # Background Panel Keranjang (Card White Background)
        with panel.canvas.before:
            Color(1, 1, 1, 1)
            self.right_rect = Rectangle(size=panel.size, pos=panel.pos)
        panel.bind(size=self._update_right_rect, pos=self._update_right_rect)

        # Header Keranjang
        cart_title = Label(
            text="[b]Daftar Pesanan[/b]", 
            markup=True, 
            font_size='18sp', 
            size_hint_y=None, 
            height=40,
            color=(0.06, 0.09, 0.16, 1)
        )
        panel.add_widget(cart_title)

        # List Item Keranjang (Scrollable)
        scroll_cart = ScrollView(size_hint=(1, 1))
        self.cart_container = BoxLayout(orientation='vertical', spacing=5, size_hint_y=None)
        self.cart_container.bind(minimum_height=self.cart_container.setter('height'))
        scroll_cart.add_widget(self.cart_container)
        panel.add_widget(scroll_cart)

        # Total & Tombol Bayar
        footer_cart = BoxLayout(orientation='vertical', size_hint_y=None, height=120, spacing=10)
        
        self.total_label = Label(
            text="[b]Total: Rp 0[/b]", 
            markup=True, 
            font_size='20sp',
            color=(0.06, 0.09, 0.16, 1)
        )
        
        btn_checkout = Button(
            text="BAYAR / CHECKOUT",
            size_hint_y=None,
            height=50,
            background_color=(0.06, 0.72, 0.51, 1), # Emerald Green (#10B981)
            color=(1, 1, 1, 1),
            bold=True
        )
        btn_checkout.bind(on_release=self.process_checkout)

        footer_cart.add_widget(self.total_label)
        footer_cart.add_widget(btn_checkout)
        panel.add_widget(footer_cart)

        return panel

    def _update_right_rect(self, instance, value):
        self.right_rect.pos = instance.pos
        self.right_rect.size = instance.size

    # -------------------------------------------------------------------------
    # MANAGEMENT PRODUK & LOGIKA INPUT GAMBAR (PERBAIKAN ERROR GAMBAR)
    # -------------------------------------------------------------------------
    def show_add_product_popup(self, instance):
        self.selected_image_path = ""
        
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        input_name = TextInput(hint_text="Nama Produk", multiline=False)
        input_price = TextInput(hint_text="Harga (contoh: 15000)", multiline=False, input_filter='float')
        
        # Section Gambar
        image_preview = Image(source='', size_hint_y=None, height=100)
        btn_choose_img = Button(text="Pilih Gambar Produk", size_hint_y=None, height=40)

        # Modal FileChooser agar tidak Crash Path
        def open_file_chooser(btn_inst):
            fc_content = BoxLayout(orientation='vertical')
            file_chooser = FileChooserListView(filters=['*.png', '*.jpg', '*.jpeg'])
            fc_popup = Popup(title="Pilih File Gambar", content=fc_content, size_hint=(0.9, 0.9))
            
            def select_file(instance):
                if file_chooser.selection:
                    path = file_chooser.selection[0]
                    # Validasi File Exists untuk Mencegah Crash Path
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

        popup = Popup(title="Tambah Produk Baru", content=content, size_hint=(0.6, 0.7))
        
        btn_save = Button(
            text="Simpan Produk", 
            size_hint_y=None, 
            height=45,
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
            
            # Filter Pencarian
            if filter_text.lower() not in p_name.lower():
                continue

            # Card Widget Produk
            card = BoxLayout(orientation='vertical', size_hint_y=None, height=180, padding=8, spacing=5)
            with card.canvas.before:
                Color(1, 1, 1, 1)
                rect = Rectangle(size=card.size, pos=card.pos)
            card.bind(size=lambda inst, val: setattr(rect, 'size', inst.size),
                      pos=lambda inst, val: setattr(rect, 'pos', inst.pos))

            # Handling Fallback Gambar (Mencegah Crash jika Gambar Hilang)
            img_source = p_image if p_image and os.path.exists(p_image) else ''
            img_widget = Image(source=img_source, size_hint_y=0.55)

            name_lbl = Label(text=f"[b]{p_name}[/b]", markup=True, size_hint_y=0.15, color=(0,0,0,1))
            price_lbl = Label(text=f"Rp {p_price:,.0f}", size_hint_y=0.15, color=(0.3,0.3,0.3,1))
            
            btn_add = Button(
                text="+ Tambah", 
                size_hint_y=0.15, 
                background_color=(0.12, 0.16, 0.23, 1),
                color=(1, 1, 1, 1)
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
    # LOGIKA KERANJANG & CHECKOUT
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

            row = BoxLayout(size_hint_y=None, height=40, spacing=5)
            lbl = Label(
                text=f"{item['name']}\n{item['qty']}x @ Rp {item['price']:,.0f}", 
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
        content.add_widget(Label(text="Transaksi Berhasil Disimpan!", font_size='16sp'))
        
        btn_close = Button(text="OK", size_hint_y=None, height=40, background_color=(0.06, 0.72, 0.51, 1))
        popup = Popup(title="Status Pembayaran", content=content, size_hint=(0.4, 0.3))
        
        def reset_cart(inst):
            self.cart.clear()
            self.update_cart_ui()
            popup.dismiss()

        btn_close.bind(on_release=reset_cart)
        content.add_widget(btn_close)
        popup.open()


if __name__ == '__main__':
    KasirrrApp().run()
