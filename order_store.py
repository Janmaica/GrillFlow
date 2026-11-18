import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass

from product_store import MAX_SQLITE_INTEGER
from receipt_data import Receipt, ReceiptItem, ReceiptPayment


PAID = "Paid"
PARTIAL = "Partially Paid"
CREDIT = "Unpaid"

_ORDER_BALANCES = """
    WITH order_balances AS (
        SELECT orders.*, COALESCE(ledger.applied, 0) AS recorded_paid
        FROM orders LEFT JOIN (
            SELECT order_id, SUM(amount_centavos) AS applied FROM payments GROUP BY order_id
        ) AS ledger ON ledger.order_id = orders.id
    )
"""


@dataclass(frozen=True)
class Payment:
    applied: int
    tendered: int
    change: int
    outstanding: int


@dataclass(frozen=True)
class SavedOrder:
    id: int
    order_number: str


def customer_name(text):
    name = text.strip()
    if re.fullmatch(r"unknown\s*\d*", name, re.IGNORECASE):
        return ""
    return name


def parse_payment_amount(text):
    text = text.strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?|\.[0-9]{1,2}", text):
        raise ValueError("Enter a non-negative amount with up to two decimal places.")
    pesos, _, fraction = text.partition(".")
    pesos = pesos.lstrip("0") or "0"
    if len(pesos) > 17:
        raise ValueError("The payment amount is too large.")
    centavos = int(pesos) * 100 + int(fraction.ljust(2, "0"))
    if centavos > MAX_SQLITE_INTEGER:
        raise ValueError("The payment amount is too large.")
    return centavos


def allocate_payment(status, total, tendered, customer):
    if not 0 < total <= MAX_SQLITE_INTEGER:
        raise ValueError("The order total must be positive and within the supported range.")
    if type(tendered) is not int or not 0 <= tendered <= MAX_SQLITE_INTEGER:
        raise ValueError("Enter a valid payment amount.")
    if status == PAID:
        if tendered < total:
            raise ValueError("A paid order needs at least the total amount.")
        return Payment(total, tendered, tendered - total, 0)
    if status == PARTIAL:
        if not 0 < tendered < total:
            raise ValueError("A partial payment must be above zero and below the order total.")
        return Payment(tendered, tendered, 0, total - tendered)
    if status == CREDIT:
        if tendered != 0:
            raise ValueError("An Utang order must have zero payment.")
        if not customer_name(customer):
            raise ValueError("Enter a customer name in New Order before saving an Utang order.")
        return Payment(0, 0, 0, total)
    raise ValueError("Select a payment type.")


class OrderStore:
    def __init__(self, product_store):
        self.products = product_store

    def initialize(self):
        self.products.initialize()
        with closing(self.products.connect()) as connection:
            connection.executescript("""
                BEGIN;
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE CHECK (order_number = printf('GF-%04d', id)),
                    customer_name TEXT NOT NULL CHECK (length(trim(customer_name)) > 0),
                    unknown_number INTEGER UNIQUE CHECK (
                        unknown_number IS NULL OR
                        (typeof(unknown_number) = 'integer' AND unknown_number > 0
                         AND customer_name = 'Unknown' || unknown_number AND payment_status <> 'Unpaid')
                    ),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    total_centavos INTEGER NOT NULL CHECK (
                        typeof(total_centavos) = 'integer' AND total_centavos > 0
                    ),
                    amount_paid_centavos INTEGER NOT NULL CHECK (
                        typeof(amount_paid_centavos) = 'integer'
                        AND amount_paid_centavos BETWEEN 0 AND total_centavos
                    ),
                    outstanding_balance_centavos INTEGER NOT NULL CHECK (
                        typeof(outstanding_balance_centavos) = 'integer'
                        AND outstanding_balance_centavos = total_centavos - amount_paid_centavos
                    ),
                    payment_status TEXT NOT NULL CHECK (
                        (payment_status = 'Paid' AND amount_paid_centavos = total_centavos) OR
                        (payment_status = 'Partially Paid' AND amount_paid_centavos > 0
                         AND outstanding_balance_centavos > 0) OR
                        (payment_status = 'Unpaid' AND amount_paid_centavos = 0)
                    ),
                    preparation_status TEXT NOT NULL DEFAULT 'Pending' CHECK (
                        preparation_status IN ('Pending', 'Cooking', 'Ready', 'Received')
                    ),
                    remarks TEXT NOT NULL DEFAULT '' CHECK (length(remarks) <= 100)
                );
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    product_name_snapshot TEXT NOT NULL CHECK (length(product_name_snapshot) > 0),
                    unit_snapshot TEXT NOT NULL CHECK (length(unit_snapshot) > 0),
                    unit_price_centavos INTEGER NOT NULL CHECK (
                        typeof(unit_price_centavos) = 'integer' AND unit_price_centavos > 0
                    ),
                    quantity INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity > 0),
                    line_total_centavos INTEGER NOT NULL CHECK (
                        typeof(line_total_centavos) = 'integer'
                        AND line_total_centavos = unit_price_centavos * quantity
                    ),
                    UNIQUE (order_id, product_id)
                );
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id),
                    amount_centavos INTEGER NOT NULL CHECK (
                        typeof(amount_centavos) = 'integer' AND amount_centavos > 0
                    ),
                    cash_tendered_centavos INTEGER NOT NULL CHECK (
                        typeof(cash_tendered_centavos) = 'integer' AND cash_tendered_centavos > 0
                    ),
                    change_centavos INTEGER NOT NULL CHECK (
                        typeof(change_centavos) = 'integer' AND change_centavos >= 0
                        AND cash_tendered_centavos - change_centavos = amount_centavos
                    ),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS payments_order_id ON payments(order_id);
                COMMIT;
            """)

    @staticmethod
    def _next_numbers(connection):
        return connection.execute("""
            SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name = 'orders'), 0) + 1,
                   COALESCE(MAX(unknown_number), 0) + 1
            FROM orders
        """).fetchone()

    def preview(self):
        with closing(self.products.connect()) as connection:
            order_id, unknown = self._next_numbers(connection)
        return f"GF-{order_id:04d}", f"Unknown{unknown}"

    def save(self, draft, customer, status, tendered, remarks):
        return self.save_order(draft, customer, status, tendered, remarks).order_number

    def save_order(self, draft, customer, status, tendered, remarks):
        if not draft.lines:
            raise ValueError("Add at least one product before saving.")
        if len(remarks) > 100 or "\x00" in remarks:
            raise ValueError("Enter remarks of up to 100 characters.")
        customer = customer_name(customer)
        if "\x00" in customer:
            raise ValueError("Enter a valid customer name.")
        total = draft.total
        payment = allocate_payment(status, total, tendered, customer)

        with closing(self.products.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            products = {}
            for product_id in draft.lines:
                row = connection.execute(
                    "SELECT stock, selling_price FROM products WHERE id = ?", (product_id,),
                ).fetchone()
                if row is not None:
                    products[product_id] = row
            draft.validate_stock(products)
            order_id, next_unknown = self._next_numbers(connection)
            order_number = f"GF-{order_id:04d}"
            connection.execute("""
                INSERT INTO orders (
                    id, order_number, customer_name, unknown_number, total_centavos,
                    amount_paid_centavos, outstanding_balance_centavos, payment_status, remarks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (order_id, order_number, customer or f"Unknown{next_unknown}",
                  None if customer else next_unknown, total, payment.applied,
                  payment.outstanding, status, remarks))
            for product_id, line in draft.lines.items():
                product = line.product
                connection.execute("""
                    INSERT INTO order_items (
                        order_id, product_id, product_name_snapshot, unit_snapshot,
                        unit_price_centavos, quantity, line_total_centavos
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (order_id, product_id, product["name"], product["unit"],
                      product["selling_price"], line.quantity, line.subtotal))
                update = connection.execute("""
                    UPDATE products SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND stock >= ?
                """, (line.quantity, product_id, line.quantity))
                if update.rowcount != 1:
                    raise ValueError(f"Could not deduct stock for {product['name']}. Review the order and try again.")
            if payment.applied:
                connection.execute("""
                    INSERT INTO payments (order_id, amount_centavos, cash_tendered_centavos, change_centavos)
                    VALUES (?, ?, ?, ?)
                """, (order_id, payment.applied, payment.tendered, payment.change))
        return SavedOrder(order_id, order_number)

    def get_receipt(self, order_id):
        with closing(self.products.connect()) as connection, connection:
            connection.execute("BEGIN")
            order = connection.execute("""
                SELECT order_number, customer_name, created_at, total_centavos, remarks
                FROM orders WHERE id = ?
            """, (order_id,)).fetchone()
            if order is None:
                return None
            items = connection.execute("""
                SELECT product_name_snapshot, unit_snapshot, quantity,
                       unit_price_centavos, line_total_centavos
                FROM order_items WHERE order_id = ? ORDER BY id
            """, (order_id,))
            payments = connection.execute("""
                SELECT amount_centavos, cash_tendered_centavos, change_centavos, created_at
                FROM payments WHERE order_id = ? ORDER BY id
            """, (order_id,))
            return Receipt(*order, tuple(ReceiptItem(*item) for item in items),
                           tuple(ReceiptPayment(*payment) for payment in payments))

    def set_preparation(self, order_id, status):
        statuses = {"Pending": "Pending", "Done": "Ready"}
        if status not in statuses:
            raise ValueError("Choose Pending or Done.")
        with closing(self.products.connect()) as connection, connection:
            result = connection.execute("""
                UPDATE orders SET preparation_status = ?
                WHERE id = ? AND preparation_status <> 'Received'
            """, (statuses[status], order_id))
            if result.rowcount != 1:
                raise ValueError("This order is unavailable or has already been received.")

    def record_payment(self, order_id, status, tendered, *, expected_paid):
        if status not in (PAID, PARTIAL):
            raise ValueError("Payments already recorded cannot be reversed here.")
        with closing(self.products.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("""
                SELECT total_centavos, customer_name, COALESCE((
                    SELECT SUM(amount_centavos) FROM payments WHERE order_id = orders.id
                ), 0)
                FROM orders WHERE id = ?
            """, (order_id,)).fetchone()
            if row is None:
                raise ValueError("This order is no longer available.")
            total, customer, applied = row
            if expected_paid != applied:
                raise ValueError("The balance changed. Close this sheet and reopen Payment Status.")
            if applied >= total:
                raise ValueError("This order is already paid. Refunds and reversals are unavailable.")
            payment = allocate_payment(status, total - applied, tendered, customer)
            connection.execute("""
                INSERT INTO payments (order_id, amount_centavos, cash_tendered_centavos, change_centavos)
                VALUES (?, ?, ?, ?)
            """, (order_id, payment.applied, payment.tendered, payment.change))
            connection.execute("""
                UPDATE orders SET amount_paid_centavos = ?, outstanding_balance_centavos = ?,
                                  payment_status = ? WHERE id = ?
            """, (applied + payment.applied, payment.outstanding, status, order_id))

    def sales_summary(self):
        with closing(self.products.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            summary = connection.execute(_ORDER_BALANCES + """
                SELECT COUNT(CASE WHEN preparation_status = 'Pending' THEN 1 END) AS active,
                       COUNT(CASE WHEN preparation_status = 'Ready' THEN 1 END) AS ready,
                       COUNT(CASE WHEN total_centavos > recorded_paid THEN 1 END) AS unpaid
                FROM order_balances
            """).fetchone()
            recent = connection.execute(_ORDER_BALANCES + """
                SELECT order_number AS order_id, customer_name, total_centavos, preparation_status,
                       id AS saved_id, CASE
                           WHEN recorded_paid >= total_centavos THEN 'Paid'
                           WHEN recorded_paid > 0 THEN 'Partially Paid'
                           ELSE 'Unpaid'
                       END AS payment_status
                FROM order_balances ORDER BY id DESC LIMIT 10
            """).fetchall()
        return dict(summary), [dict(order) for order in recent]
