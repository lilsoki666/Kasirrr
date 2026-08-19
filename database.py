import sqlite3
from datetime import datetime
from pathlib import Path


class Database:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._seed()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.executescript("""
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE,
            name TEXT NOT NULL,
            category_id INTEGER,
            buy_price REAL NOT NULL DEFAULT 0,
            sell_price REAL NOT NULL DEFAULT 0,
            stock REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'pcs',
            min_stock REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice TEXT NOT NULL UNIQUE,
            subtotal REAL NOT NULL,
            discount REAL NOT NULL DEFAULT 0,
            tax REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL,
            paid REAL NOT NULL,
            change_amount REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'Tunai',
            cashier TEXT NOT NULL DEFAULT 'Admin',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            discount REAL NOT NULL DEFAULT 0,
            line_total REAL NOT NULL,
            cost_price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        # Safe migrations for databases created by earlier versions.
        columns = {row[1] for row in cur.execute("PRAGMA table_info(sale_items)").fetchall()}
        if "cost_price" not in columns:
            cur.execute("ALTER TABLE sale_items ADD COLUMN cost_price REAL NOT NULL DEFAULT 0")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                movement_type TEXT NOT NULL,
                qty REAL NOT NULL,
                stock_before REAL NOT NULL,
                stock_after REAL NOT NULL,
                reference TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );
        """)
        self.conn.commit()

    def _seed(self):
        cur = self.conn.cursor()
        if cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO categories(name) VALUES (?)",
                [("Umum",), ("Makanan",), ("Minuman",), ("Sembako",)]
            )

        if cur.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            umum = cur.execute(
                "SELECT id FROM categories WHERE name='Umum'"
            ).fetchone()[0]
            now = datetime.now().isoformat(timespec="seconds")
            sample = [
                ("899000000001", "Air Mineral 600ml", umum, 2000, 3500, 50, "pcs", 10),
                ("899000000002", "Kopi Sachet", umum, 1500, 2500, 100, "pcs", 20),
                ("899000000003", "Mi Instan", umum, 2200, 3000, 80, "pcs", 15),
            ]
            cur.executemany("""
                INSERT INTO products
                (barcode,name,category_id,buy_price,sell_price,stock,unit,min_stock,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, [x + (now,) for x in sample])

        defaults = {
            "store_name": "TOKO SAYA",
            "store_address": "Alamat toko",
            "tax_percent": "0",
            "cashier_name": "Admin",
        }
        for k, v in defaults.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (k, v)
            )
        self.conn.commit()

    def get_setting(self, key, default=""):
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        self.conn.commit()

    def categories(self):
        return self.conn.execute(
            "SELECT * FROM categories ORDER BY name"
        ).fetchall()

    def add_category(self, name):
        name = name.strip()
        if name:
            self.conn.execute(
                "INSERT OR IGNORE INTO categories(name) VALUES (?)", (name,)
            )
            self.conn.commit()

    def products(self, search=""):
        if search:
            q = f"%{search.strip()}%"
            return self.conn.execute("""
                SELECT p.*, c.name category_name
                FROM products p
                LEFT JOIN categories c ON c.id=p.category_id
                WHERE p.active=1
                  AND (p.name LIKE ? OR COALESCE(p.barcode,'') LIKE ?)
                ORDER BY p.name
            """, (q, q)).fetchall()

        return self.conn.execute("""
            SELECT p.*, c.name category_name
            FROM products p
            LEFT JOIN categories c ON c.id=p.category_id
            WHERE p.active=1
            ORDER BY p.name
        """).fetchall()

    def product_by_id(self, product_id):
        return self.conn.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)
        ).fetchone()

    def save_product(self, data):
        if data.get("id"):
            self.conn.execute("""
                UPDATE products
                SET barcode=?, name=?, category_id=?, buy_price=?,
                    sell_price=?, stock=?, unit=?, min_stock=?
                WHERE id=?
            """, (
                data.get("barcode") or None, data["name"], data.get("category_id"),
                data.get("buy_price", 0), data["sell_price"], data.get("stock", 0),
                data.get("unit", "pcs"), data.get("min_stock", 0), data["id"]
            ))
        else:
            self.conn.execute("""
                INSERT INTO products
                (barcode,name,category_id,buy_price,sell_price,stock,unit,min_stock,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                data.get("barcode") or None, data["name"], data.get("category_id"),
                data.get("buy_price", 0), data["sell_price"], data.get("stock", 0),
                data.get("unit", "pcs"), data.get("min_stock", 0),
                datetime.now().isoformat(timespec="seconds")
            ))
        self.conn.commit()

    def delete_product(self, product_id):
        self.conn.execute(
            "UPDATE products SET active=0 WHERE id=?", (product_id,)
        )
        self.conn.commit()

    def make_invoice(self):
        return datetime.now().strftime("INV%Y%m%d%H%M%S%f")[:-3]

    def save_sale(self, cart, subtotal, discount, tax, total, paid, change, payment):
        """Save a sale atomically and prevent stock from going negative."""
        if not cart:
            raise ValueError("Keranjang kosong.")
        if payment not in {"Tunai", "QRIS", "Transfer", "Debit/Kredit"}:
            raise ValueError("Metode pembayaran tidak valid.")

        invoice = self.make_invoice()
        now = datetime.now().isoformat(timespec="seconds")
        cashier = self.get_setting("cashier_name", "Admin")
        cur = self.conn.cursor()

        try:
            self.conn.execute("BEGIN")
            cur.execute("""
                INSERT INTO sales
                (invoice,subtotal,discount,tax,total,paid,change_amount,
                 payment_method,cashier,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                invoice, subtotal, discount, tax, total, paid, change, payment,
                cashier, now
            ))
            sale_id = cur.lastrowid

            for item in cart:
                product = cur.execute(
                    "SELECT id,name,buy_price,stock,active FROM products WHERE id=?",
                    (item["id"],)
                ).fetchone()
                if not product or not product[4]:
                    raise ValueError(f"Produk tidak tersedia: {item['name']}")

                qty = float(item["qty"])
                if qty <= 0:
                    raise ValueError("Jumlah produk tidak valid.")
                stock_before = float(product[3])
                if stock_before < qty:
                    raise ValueError(
                        f"Stok {product[1]} tidak mencukupi. Tersedia {stock_before:g}."
                    )

                updated = cur.execute(
                    "UPDATE products SET stock=stock-? "
                    "WHERE id=? AND active=1 AND stock>=?",
                    (qty, item["id"], qty)
                )
                if updated.rowcount != 1:
                    raise ValueError(f"Stok {product[1]} berubah. Silakan ulangi transaksi.")

                stock_after = stock_before - qty
                cur.execute("""
                    INSERT INTO sale_items
                    (sale_id,product_id,product_name,qty,price,discount,line_total,cost_price)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    sale_id, item["id"], product[1], qty, float(item["price"]),
                    float(item.get("discount", 0)), float(item["line_total"]),
                    float(product[2])
                ))
                cur.execute("""
                    INSERT INTO stock_movements
                    (product_id,product_name,movement_type,qty,stock_before,stock_after,reference,note,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (
                    item["id"], product[1], "PENJUALAN", -qty, stock_before,
                    stock_after, invoice, "Pengurangan stok dari transaksi", now
                ))

            self.conn.commit()
            return invoice
        except Exception:
            self.conn.rollback()
            raise

    def stock_movements(self, limit=100):
        return self.conn.execute(
            "SELECT * FROM stock_movements ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def stock_adjustment(self, product_id, qty, movement_type="PENYESUAIAN", note=""):
        qty = float(qty)
        cur = self.conn.cursor()
        try:
            self.conn.execute("BEGIN")
            product = cur.execute(
                "SELECT id,name,stock FROM products WHERE id=? AND active=1",
                (product_id,)
            ).fetchone()
            if not product:
                raise ValueError("Produk tidak ditemukan.")
            before = float(product[2])
            after = before + qty
            if after < 0:
                raise ValueError("Stok tidak boleh negatif.")
            cur.execute("UPDATE products SET stock=? WHERE id=?", (after, product_id))
            cur.execute("""
                INSERT INTO stock_movements
                (product_id,product_name,movement_type,qty,stock_before,stock_after,reference,note,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (product_id, product[1], movement_type, qty, before, after, None, note,
                  datetime.now().isoformat(timespec="seconds")))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def top_products(self, days=30, limit=5):
        return self.conn.execute("""
            SELECT si.product_name, SUM(si.qty) qty,
                   SUM(si.line_total) revenue,
                   SUM(CASE WHEN si.cost_price > 0 THEN (si.price - si.cost_price) * si.qty ELSE 0 END) profit
            FROM sale_items si
            JOIN sales s ON s.id=si.sale_id
            WHERE date(s.created_at) >= date('now','localtime',?)
            GROUP BY si.product_id, si.product_name
            ORDER BY qty DESC, revenue DESC
            LIMIT ?
        """, (f"-{days-1} day", limit)).fetchall()

    def sales(self, limit=100):
        return self.conn.execute(
            "SELECT * FROM sales ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def sale_items(self, sale_id):
        return self.conn.execute(
            "SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,)
        ).fetchall()

    def summary_today(self):
        row = self.conn.execute("""
            SELECT COALESCE(SUM(s.total),0) total,
                   COUNT(*) transactions,
                   COALESCE(SUM(s.discount),0) discount,
                   COALESCE((SELECT SUM(CASE WHEN si.cost_price > 0 THEN (si.price - si.cost_price) * si.qty ELSE 0 END)
                             FROM sale_items si JOIN sales sx ON sx.id=si.sale_id
                             WHERE date(sx.created_at)=date('now','localtime')),0) profit
            FROM sales s
            WHERE date(s.created_at)=date('now','localtime')
        """).fetchone()
        product_count = self.conn.execute(
            "SELECT COUNT(*) FROM products WHERE active=1"
        ).fetchone()[0]
        low = self.conn.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE active=1 AND stock<=min_stock"
        ).fetchone()[0]
        return dict(row), product_count, low

    def sales_report(self, days=30):
        return self.conn.execute("""
            SELECT sday.day, sday.transactions, sday.subtotal, sday.discount,
                   sday.tax, sday.total, COALESCE(SUM((si.price-si.cost_price)*si.qty),0) profit
            FROM (
                SELECT date(created_at) day, COUNT(*) transactions,
                       COALESCE(SUM(subtotal),0) subtotal,
                       COALESCE(SUM(discount),0) discount,
                       COALESCE(SUM(tax),0) tax,
                       COALESCE(SUM(total),0) total
                FROM sales
                WHERE date(created_at) >= date('now','localtime',?)
                GROUP BY date(created_at)
            ) sday
            LEFT JOIN sales s ON date(s.created_at)=sday.day
            LEFT JOIN sale_items si ON si.sale_id=s.id
            GROUP BY sday.day, sday.transactions, sday.subtotal, sday.discount, sday.tax, sday.total
            ORDER BY sday.day DESC
        """, (f"-{days-1} day",)).fetchall()

    def backup(self, destination):
        self.conn.commit()
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        backup_conn = sqlite3.connect(str(dest))
        with backup_conn:
            self.conn.backup(backup_conn)
        backup_conn.close()
