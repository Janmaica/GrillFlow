import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from product_store import MAX_SQLITE_INTEGER, normalized_name
from receipt_data import PHILIPPINE_TIME


class ConsumptionStore:
    def __init__(self, products):
        self.products = products

    @staticmethod
    def ensure_schema(connection):
        connection.execute("""
            CREATE TABLE IF NOT EXISTS family_consumption (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id),
                product_name_snapshot TEXT NOT NULL,
                unit_snapshot TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity > 0),
                selling_price_centavos INTEGER NOT NULL CHECK (
                    typeof(selling_price_centavos) = 'integer' AND selling_price_centavos > 0
                ),
                retail_value_centavos INTEGER NOT NULL CHECK (
                    typeof(retail_value_centavos) = 'integer'
                    AND retail_value_centavos = quantity * selling_price_centavos
                ),
                consumed_at TEXT NOT NULL,
                remarks TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                archived_at TEXT
            )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS consumption_by_date ON family_consumption(consumed_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS consumption_by_product ON family_consumption(product_id)")

    def save(self, product_id, quantity, local_date, remarks="", *, expected_price=None):
        if type(quantity) is not int or not 0 < quantity <= MAX_SQLITE_INTEGER:
            raise ValueError("Enter a positive whole quantity.")
        try:
            value = local_date.strip()
            stamp = datetime.fromisoformat(value)
            if len(value) not in (16, 19) or stamp.tzinfo is not None:
                raise ValueError
            consumed_at = stamp.replace(tzinfo=PHILIPPINE_TIME).astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError("Enter Philippine date and time as YYYY-MM-DD HH:MM.") from None
        with closing(self.products.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            product = connection.execute("""
                SELECT name, unit, selling_price, stock FROM products WHERE id = ? AND is_active = 1
            """, (product_id,)).fetchone()
            if not product:
                raise ValueError("Choose an active product.")
            name, unit, price, stock = product
            if quantity > stock:
                raise ValueError(f"Only {stock} in stock.")
            if expected_price is not None and price != expected_price:
                raise ValueError("The selling price changed. Reopen the form to review the current price.")
            retail_value = quantity * price
            if retail_value > MAX_SQLITE_INTEGER:
                raise ValueError("The estimated retail value is too large.")
            connection.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
            return connection.execute("""
                INSERT INTO family_consumption (
                    product_id, product_name_snapshot, unit_snapshot, quantity, selling_price_centavos,
                    retail_value_centavos, consumed_at, remarks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (product_id, name, unit, quantity, price, retail_value,
                  consumed_at.strftime("%Y-%m-%d %H:%M:%S"), remarks.strip())).lastrowid

    def archive(self, record_id):
        with closing(self.products.connect()) as connection, connection:
            result = connection.execute("""
                UPDATE family_consumption SET archived_at = CURRENT_TIMESTAMP
                WHERE id = ? AND archived_at IS NULL
            """, (record_id,))
            if result.rowcount != 1:
                raise ValueError("This record is no longer available.")

    @staticmethod
    def _total(connection, start, end):
        return sum(row[0] for row in connection.execute("""
            SELECT retail_value_centavos FROM family_consumption WHERE consumed_at >= ? AND consumed_at < ?
        """, (start, end)))

    def total(self, start, end):
        with closing(self.products.connect()) as connection:
            return self._total(connection, start, end)

    def period_view(self, start, end, search=""):
        with closing(self.products.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            total = self._total(connection, start, end)
            records = connection.execute("""
                SELECT * FROM family_consumption
                WHERE archived_at IS NULL AND consumed_at >= ? AND consumed_at < ?
                  AND instr(grillflow_name_key(product_name_snapshot), ?) > 0
                ORDER BY consumed_at DESC, id DESC
            """, (start, end, normalized_name(search))).fetchall()
            return total, records
