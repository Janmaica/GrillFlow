import logging
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


UNITS = ("Stick", "Piece", "Pack", "Serving")
MAX_SQLITE_INTEGER = (1 << 63) - 1
DUPLICATE_PRODUCT_MESSAGE = "Product already Exist"


class ProductConflict(ValueError):
    pass


@dataclass(frozen=True)
class ProductFields:
    name: str
    selling_price: int  # Centavos
    stock: int
    unit: str


def format_product_name(name):
    return name.strip().capitalize()


def normalized_name(name):
    return " ".join(name.split()).casefold()


def validate_product(name, price, stock, unit):
    name = format_product_name(name)
    price, stock = price.strip(), stock.strip()
    if not name:
        raise ValueError("Enter a product name.")
    if len(name) > 50 or "\x00" in name:
        raise ValueError("Enter a product name of up to 50 characters.")

    if not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]{1,2})?|\.[0-9]{1,2})", price):
        raise ValueError("Enter a selling price above ₱0 with up to two decimal places.")
    price = price.lstrip("0") or "0"
    if len(price.split(".")[0]) > 17:
        raise ValueError("The selling price is too large.")
    centavos = int(Decimal(price) * 100)
    if not 0 < centavos <= MAX_SQLITE_INTEGER:
        raise ValueError("Enter a selling price above ₱0 within the supported range.")

    if not re.fullmatch(r"[0-9]+", stock):
        raise ValueError("Enter stock as a whole number of 0 or more.")
    stock = stock.lstrip("0") or "0"
    if len(stock) > 19 or int(stock) > MAX_SQLITE_INTEGER:
        raise ValueError("The stock is too large.")
    if unit not in UNITS:
        raise ValueError("Select a valid unit.")
    return ProductFields(name, centavos, int(stock), unit)


def format_price(centavos):
    pesos, remainder = divmod(centavos, 100)
    return f"₱{pesos:,}.{remainder:02d}"


class ProductStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.database_path = self.data_dir / "grillflow.sqlite3"

    def connect(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
            connection.close()
            raise sqlite3.IntegrityError("SQLite foreign-key enforcement could not be enabled.")
        connection.create_function(
            "grillflow_name_key", 1,
            lambda name: normalized_name(name) if isinstance(name, str) else None,
            deterministic=True,
        )
        return connection

    def initialize(self):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL CHECK (
                        typeof(name) = 'text' AND length(name) BETWEEN 1 AND 50
                        AND name = trim(name, char(
                            9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
                            8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201,
                            8202, 8232, 8233, 8239, 8287, 12288
                        )) AND instr(name, char(0)) = 0
                    ),
                    selling_price INTEGER NOT NULL CHECK (
                        typeof(selling_price) = 'integer' AND selling_price > 0
                    ),
                    stock INTEGER NOT NULL CHECK (typeof(stock) = 'integer' AND stock >= 0),
                    unit TEXT NOT NULL CHECK (unit IN ('Stick', 'Piece', 'Pack', 'Serving')),
                    image_path TEXT CHECK (image_path IS NULL OR length(image_path) > 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            columns = {column[1] for column in connection.execute("PRAGMA table_info(products)")}
            if "is_active" not in columns:
                connection.execute("""
                    ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (is_active IN (0, 1))
                """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS product_id_sequence (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    last_id INTEGER NOT NULL
                )
            """)
            connection.execute("""
                INSERT OR IGNORE INTO product_id_sequence
                SELECT 1, COALESCE(MAX(id), 0) FROM products
            """)
            # Replace the catalog-wide rules. Triggers preserve legacy active
            # duplicates for manual review while blocking new collisions.
            connection.execute("DROP TRIGGER IF EXISTS products_unique_name_insert")
            connection.execute("DROP TRIGGER IF EXISTS products_unique_name_update")
            connection.execute(f"""
                CREATE TRIGGER IF NOT EXISTS products_unique_active_name_insert
                BEFORE INSERT ON products
                WHEN NEW.is_active = 1
                 AND EXISTS (SELECT 1 FROM products WHERE is_active = 1
                             AND grillflow_name_key(name) = grillflow_name_key(NEW.name))
                BEGIN SELECT RAISE(ABORT, '{DUPLICATE_PRODUCT_MESSAGE}'); END
            """)
            connection.execute(f"""
                CREATE TRIGGER IF NOT EXISTS products_unique_active_name_update
                BEFORE UPDATE OF name, is_active ON products
                WHEN NEW.is_active = 1
                 AND (OLD.is_active <> 1 OR grillflow_name_key(NEW.name) <> grillflow_name_key(OLD.name))
                 AND EXISTS (SELECT 1 FROM products WHERE is_active = 1 AND id <> OLD.id
                             AND grillflow_name_key(name) = grillflow_name_key(NEW.name))
                BEGIN SELECT RAISE(ABORT, '{DUPLICATE_PRODUCT_MESSAGE}'); END
            """)

    def name_exists(self, name, excluding_id=None):
        with closing(self.connect()) as connection:
            return connection.execute("""
                SELECT 1 FROM products WHERE is_active = 1 AND grillflow_name_key(name) = ?
                    AND (? IS NULL OR id <> ?) LIMIT 1
            """, (normalized_name(name), excluding_id, excluding_id)).fetchone() is not None

    def duplicate_names(self):
        with closing(self.connect()) as connection:
            return connection.execute("""
                SELECT MIN(name), COUNT(*) FROM products
                WHERE is_active = 1
                GROUP BY grillflow_name_key(name) HAVING COUNT(*) > 1
                ORDER BY MIN(name)
            """).fetchall()

    def add(self, fields, image_path=None):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            product_id, = connection.execute("""
                SELECT MAX(last_id, (SELECT COALESCE(MAX(id), 0) FROM products)) + 1
                FROM product_id_sequence WHERE singleton = 1
            """).fetchone()
            connection.execute("""
                INSERT INTO products (id, name, selling_price, stock, unit, image_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (product_id, fields.name, fields.selling_price, fields.stock, fields.unit, image_path))
            connection.execute("UPDATE product_id_sequence SET last_id = ? WHERE singleton = 1", (product_id,))
        return product_id

    def update(self, original, fields, image_path):
        with closing(self.connect()) as connection, connection:
            result = connection.execute("""
                UPDATE products SET name = ?, selling_price = ?, stock = ?, unit = ?,
                    image_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND is_active = 1 AND name = ? AND selling_price = ?
                    AND stock = ? AND unit = ? AND image_path IS ?
            """, (fields.name, fields.selling_price, fields.stock, fields.unit, image_path,
                  original["id"], original["name"], original["selling_price"], original["stock"],
                  original["unit"], original["image_path"]))
            if result.rowcount != 1:
                raise ProductConflict("This product changed. Reopen it to review the current details.")

    def delete(self, product_id):
        removable_photo = None
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            has_orders = connection.execute("""
                SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'order_items'
            """).fetchone()
            referenced = has_orders and connection.execute(
                "SELECT 1 FROM order_items WHERE product_id = ? LIMIT 1", (product_id,),
            ).fetchone()
            if referenced:
                raise ProductConflict("This product is referenced by retained orders and cannot be permanently deleted.")
            row = connection.execute("SELECT image_path FROM products WHERE id = ?", (product_id,)).fetchone()
            result = connection.execute("DELETE FROM products WHERE id = ?", (product_id,))
            if result.rowcount != 1:
                raise ProductConflict("This product no longer exists.")
            if row[0]:
                removable_photo = self._exclusive_photo(connection, row[0])
            connection.execute(
                "UPDATE product_id_sequence SET last_id = MAX(last_id, ?) WHERE singleton = 1",
                (product_id,),
            )
        if removable_photo:
            try:
                removable_photo.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning("Product deleted, but its unused photo could not be removed.")

    def _exclusive_photo(self, connection, image_path):
        if Path(image_path).name != image_path:
            return None
        try:
            folder = self.data_dir / "product_photos"
            if folder.is_symlink():
                return None
            folder = folder.resolve()
            if folder.parent != self.data_dir.resolve():
                return None
            candidate = folder / image_path
            if candidate.is_symlink() or candidate.resolve().parent != folder:
                return None
            retained = connection.execute("SELECT image_path FROM products WHERE image_path IS NOT NULL")
            if any((folder / path).resolve() == candidate.resolve() for (path,) in retained):
                return None
            return candidate
        except (OSError, RuntimeError):
            return None

    def list_products(self):
        with closing(self.connect()) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("""
                SELECT id, name, selling_price, stock, unit, image_path
                FROM products WHERE is_active = 1 ORDER BY id DESC
            """).fetchall()
