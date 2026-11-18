import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


UNITS = ("Stick", "Piece", "Pack", "Serving")
MAX_SQLITE_INTEGER = (1 << 63) - 1


@dataclass(frozen=True)
class ProductFields:
    name: str
    selling_price: int  # Centavos
    stock: int
    unit: str


def format_product_name(name):
    return name.strip().capitalize()


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
        raise ValueError("Enter initial stock as a whole number of 0 or more.")
    stock = stock.lstrip("0") or "0"
    if len(stock) > 19 or int(stock) > MAX_SQLITE_INTEGER:
        raise ValueError("The initial stock is too large.")
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
        return connection

    def initialize(self):
        with closing(self.connect()) as connection, connection:
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

    def add(self, fields, image_path=None):
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO products (name, selling_price, stock, unit, image_path) "
                "VALUES (?, ?, ?, ?, ?)",
                (fields.name, fields.selling_price, fields.stock, fields.unit, image_path),
            )

    def list_products(self):
        with closing(self.connect()) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("""
                SELECT id, name, selling_price, stock, unit, image_path
                FROM products ORDER BY id DESC
            """).fetchall()
