import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from product_store import MAX_SQLITE_INTEGER, normalized_name
from receipt_data import PHILIPPINE_TIME


EXPENSE_CATEGORIES = ("Ingredients", "Charcoal", "Supplies", "Others")


class ExpenseStore:
    def __init__(self, products):
        self.products = products

    @staticmethod
    def ensure_schema(connection):
        connection.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                category TEXT NOT NULL CHECK (category IN ('Ingredients', 'Charcoal', 'Supplies', 'Others')),
                amount_centavos INTEGER NOT NULL CHECK (
                    typeof(amount_centavos) = 'integer' AND amount_centavos > 0
                ),
                incurred_at TEXT NOT NULL,
                remarks TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                archived_at TEXT
            )
        """)
        columns = {column[1] for column in connection.execute("PRAGMA table_info(expenses)")}
        if "archived_at" not in columns:
            connection.execute("ALTER TABLE expenses ADD COLUMN archived_at TEXT")
        connection.execute("CREATE INDEX IF NOT EXISTS expenses_by_date ON expenses(incurred_at)")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS expense_corrections (
                id INTEGER PRIMARY KEY,
                expense_id INTEGER NOT NULL REFERENCES expenses(id),
                previous_amount_centavos INTEGER NOT NULL,
                previous_category TEXT NOT NULL,
                previous_incurred_at TEXT NOT NULL,
                corrected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE TRIGGER IF NOT EXISTS audit_expense_correction
            AFTER UPDATE OF amount_centavos, category, incurred_at ON expenses
            WHEN OLD.amount_centavos <> NEW.amount_centavos OR OLD.category <> NEW.category
                 OR OLD.incurred_at <> NEW.incurred_at
            BEGIN
                INSERT INTO expense_corrections (
                    expense_id, previous_amount_centavos, previous_category, previous_incurred_at
                ) VALUES (OLD.id, OLD.amount_centavos, OLD.category, OLD.incurred_at);
            END
        """)

    def save(self, name, category, amount, local_date, remarks, expense_id=None):
        name = name.strip()
        if not name or "\x00" in name:
            raise ValueError("Enter an expense name.")
        if category not in EXPENSE_CATEGORIES:
            raise ValueError("Choose an expense category.")
        if type(amount) is not int or not 0 < amount <= MAX_SQLITE_INTEGER:
            raise ValueError("Enter an amount greater than ₱0.00.")
        try:
            stamp = datetime.fromisoformat(local_date.strip())
            if stamp.tzinfo or len(local_date.strip()) not in (16, 19):
                raise ValueError
            utc = stamp.replace(tzinfo=PHILIPPINE_TIME).astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError("Enter Philippine date and time as YYYY-MM-DD HH:MM.") from None
        incurred_at = utc.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
        values = (name, category, amount, incurred_at, remarks.strip())
        with closing(self.products.connect()) as connection, connection:
            if expense_id is None:
                return connection.execute("""
                    INSERT INTO expenses (name, category, amount_centavos, incurred_at, remarks)
                    VALUES (?, ?, ?, ?, ?)
                """, values).lastrowid
            cursor = connection.execute("""
                UPDATE expenses SET name = ?, category = ?, amount_centavos = ?, incurred_at = ?,
                                    remarks = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND archived_at IS NULL
            """, (*values, expense_id))
            if cursor.rowcount != 1:
                raise ValueError("This expense no longer exists.")
            return expense_id

    def delete(self, expense_id):
        with closing(self.products.connect()) as connection, connection:
            if connection.execute("""
                UPDATE expenses SET archived_at = CURRENT_TIMESTAMP WHERE id = ? AND archived_at IS NULL
            """, (expense_id,)).rowcount != 1:
                raise ValueError("This expense no longer exists.")

    def total(self, start, end):
        with closing(self.products.connect()) as connection:
            return self._total(connection, start, end)

    @staticmethod
    def _total(connection, start, end):
        return sum(row[0] for row in connection.execute("""
            SELECT amount_centavos FROM expenses WHERE incurred_at >= ? AND incurred_at < ?
        """, (start, end)))

    def period_view(self, start, end, *, category=None, search=""):
        with closing(self.products.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            total = self._total(connection, start, end)
            any_expenses = connection.execute(
                "SELECT 1 FROM expenses WHERE archived_at IS NULL LIMIT 1"
            ).fetchone() is not None
            rows = connection.execute("""
                SELECT id, name, category, amount_centavos, incurred_at, remarks FROM expenses
                WHERE incurred_at >= ? AND incurred_at < ?
                  AND archived_at IS NULL
                  AND (? IS NULL OR category = ?)
                  AND instr(grillflow_name_key(name), ?) > 0
                ORDER BY incurred_at DESC, id DESC
            """, (start, end, category, category, normalized_name(search))).fetchall()
            return total, any_expenses, rows
