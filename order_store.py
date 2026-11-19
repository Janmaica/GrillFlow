import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from product_store import MAX_SQLITE_INTEGER, normalized_name
from receipt_data import PHILIPPINE_TIME, Receipt, ReceiptItem, ReceiptPayment


PAID = "Paid"
PARTIAL = "Partially Paid"
CREDIT = "Unpaid"
IMMEDIATE = "immediate"
PAY_LATER = "pay_later"
CREDIT_ARRANGEMENT = "credit"
HISTORY_BALANCE_MESSAGE = (
    "Some orders still have unpaid balances. Please settle all outstanding payments before clearing this history."
)
HISTORY_PERIODS = ("Today", "This Week")


def history_bounds(period, now=None):
    if period not in HISTORY_PERIODS:
        raise ValueError("Unknown history filter.")
    local = (now or datetime.now(timezone.utc)).astimezone(PHILIPPINE_TIME)
    first = local.date()
    days = 1
    if period == "This Week":
        first -= timedelta(days=first.weekday())
        days = 7
    start = datetime.combine(first, time.min, tzinfo=PHILIPPINE_TIME).astimezone(timezone.utc)
    end = start + timedelta(days=days)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def report_bounds(period, now=None):
    if period in ("This Day", "This Week"):
        return history_bounds("Today" if period == "This Day" else period, now)
    if period != "This Month":
        raise ValueError("Unknown report period.")
    local = (now or datetime.now(timezone.utc)).astimezone(PHILIPPINE_TIME)
    first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    following = (first + timedelta(days=32)).replace(day=1)
    return tuple(value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                 for value in (first, following))

_PAY_LATER_GUEST = """
    payment_arrangement = 'pay_later'
    AND CAST(substr(customer_name, 8) AS INTEGER) > 0
    AND customer_name = 'Unknown' || CAST(substr(customer_name, 8) AS INTEGER)
"""

_ORDER_BALANCES = """
    WITH order_balances AS (
        SELECT orders.*, COALESCE(ledger.applied, 0) AS recorded_paid
        FROM orders LEFT JOIN (
            SELECT order_id, SUM(amount_centavos) AS applied FROM payments GROUP BY order_id
        ) AS ledger ON ledger.order_id = orders.id
    )
"""
_OUTSTANDING_CREDIT = "payment_arrangement = ? AND total_centavos > recorded_paid"


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


class OutstandingBalanceError(ValueError):
    pass


def can_move_to_credit(arrangement, applied, total):
    return arrangement == IMMEDIATE and 0 < applied < total


def customer_name(text):
    name = text.strip()
    if re.fullmatch(r"unknown\s*\d*", name, re.IGNORECASE):
        return ""
    return name


def format_customer_name(text):
    return " ".join(text.split()).capitalize()


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


def allocate_payment(status, total, tendered, customer, *, arrangement=None):
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
            raise ValueError("An unpaid order must have zero payment at checkout.")
        if arrangement != PAY_LATER and not customer_name(customer):
            raise ValueError("Enter a customer name in New Order before saving an Utang order.")
        return Payment(0, 0, 0, total)
    raise ValueError("Select a payment type.")


class OrderStore:
    def __init__(self, product_store):
        self.products = product_store

    def initialize(self):
        self.products.initialize()
        with closing(self.products.connect()) as connection, connection:
            connection.executescript("""
                BEGIN IMMEDIATE;
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
                CREATE TABLE IF NOT EXISTS order_arrangement_transfers (
                    order_id INTEGER PRIMARY KEY REFERENCES orders(id),
                    previous_arrangement TEXT NOT NULL CHECK (previous_arrangement = 'immediate'),
                    new_arrangement TEXT NOT NULL CHECK (new_arrangement = 'credit'),
                    remaining_balance_centavos INTEGER NOT NULL CHECK (
                        typeof(remaining_balance_centavos) = 'integer' AND remaining_balance_centavos > 0
                    ),
                    previous_unknown_number INTEGER,
                    transferred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            columns = {column[1] for column in connection.execute("PRAGMA table_info(orders)")}
            if "payment_arrangement" not in columns:
                # NULL preserves the unknown arrangement of existing orders.
                connection.execute("""
                    ALTER TABLE orders ADD COLUMN payment_arrangement TEXT
                    CHECK (payment_arrangement IN ('immediate', 'pay_later', 'credit'))
                """)
            if "archived_at" not in columns:
                connection.execute("ALTER TABLE orders ADD COLUMN archived_at TEXT")
            connection.execute("""
                CREATE INDEX IF NOT EXISTS orders_visible_history ON orders(created_at)
                WHERE archived_at IS NULL
            """)
            connection.execute(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS orders_generated_customer
                ON orders(customer_name)
                WHERE unknown_number IS NOT NULL OR ({_PAY_LATER_GUEST})
            """)

    @staticmethod
    def _next_numbers(connection):
        return connection.execute(f"""
            SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name = 'orders'), 0) + 1,
                   MAX(COALESCE(MAX(CASE
                           WHEN unknown_number IS NOT NULL THEN unknown_number
                           WHEN {_PAY_LATER_GUEST}
                               THEN CAST(substr(customer_name, 8) AS INTEGER)
                       END), 0),
                       COALESCE((SELECT MAX(previous_unknown_number)
                                 FROM order_arrangement_transfers), 0)) + 1
            FROM orders
        """).fetchone()

    def preview(self):
        with closing(self.products.connect()) as connection:
            order_id, unknown = self._next_numbers(connection)
        return f"GF-{order_id:04d}", f"Unknown{unknown}"

    def save(self, draft, customer, status, tendered, remarks, *, arrangement=None):
        return self.save_order(
            draft, customer, status, tendered, remarks, arrangement=arrangement,
        ).order_number

    def save_order(self, draft, customer, status, tendered, remarks, *, arrangement=None):
        if not draft.lines:
            raise ValueError("Add at least one product before saving.")
        if len(remarks) > 100 or "\x00" in remarks:
            raise ValueError("Enter remarks of up to 100 characters.")
        customer = format_customer_name(customer_name(customer))
        if "\x00" in customer:
            raise ValueError("Enter a valid customer name.")
        if arrangement is None:
            arrangement = CREDIT_ARRANGEMENT if status == CREDIT else IMMEDIATE
        allowed = (PAY_LATER, CREDIT_ARRANGEMENT) if status == CREDIT else (IMMEDIATE,)
        if arrangement not in allowed:
            raise ValueError("Select a valid arrangement for this payment status.")
        total = draft.total
        payment = allocate_payment(status, total, tendered, customer, arrangement=arrangement)

        with closing(self.products.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            products = {}
            for product_id in draft.lines:
                row = connection.execute(
                    "SELECT stock, selling_price FROM products WHERE id = ? AND is_active = 1", (product_id,),
                ).fetchone()
                if row is not None:
                    products[product_id] = row
            draft.validate_stock(products)
            order_id, next_unknown = self._next_numbers(connection)
            order_number = f"GF-{order_id:04d}"
            # Legacy unknown_number disallows unpaid guests. Pay Later guests
            # reserve the same generated-name sequence through the unique index.
            connection.execute("""
                INSERT INTO orders (
                    id, order_number, customer_name, unknown_number, total_centavos,
                    amount_paid_centavos, outstanding_balance_centavos, payment_status, remarks,
                    payment_arrangement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (order_id, order_number, customer or f"Unknown{next_unknown}",
                  None if customer or arrangement == PAY_LATER else next_unknown,
                  total, payment.applied, payment.outstanding, status, remarks, arrangement))
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
                    WHERE id = ? AND is_active = 1 AND stock >= ?
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
                SELECT order_number, customer_name, created_at, total_centavos, remarks, payment_arrangement
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
            return Receipt(*order[:5], tuple(ReceiptItem(*item) for item in items),
                           tuple(ReceiptPayment(*payment) for payment in payments),
                           payment_arrangement=order[5])

    def named_customers(self):
        names = {}
        with closing(self.products.connect()) as connection:
            rows = connection.execute(_ORDER_BALANCES + f"""
                SELECT DISTINCT customer_name FROM order_balances
                WHERE archived_at IS NULL OR ({_OUTSTANDING_CREDIT})
                ORDER BY customer_name
            """, (CREDIT_ARRANGEMENT,))
            for (stored_name,) in rows:
                name = format_customer_name(customer_name(stored_name))
                if name:
                    names.setdefault(normalized_name(name), name)
        return [names[key] for key in sorted(names)]

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
        self._record_payment(order_id, tendered, expected_paid=expected_paid, status=status)

    def record_credit_payment(self, order_id, amount, *, expected_paid):
        self._record_payment(order_id, amount, expected_paid=expected_paid, status=None)

    def move_to_credit(self, order_id, *, expected_paid, replacement_customer=""):
        with closing(self.products.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute(_ORDER_BALANCES + """
                SELECT payment_arrangement, recorded_paid, total_centavos, customer_name, unknown_number
                FROM order_balances WHERE id = ?
            """, (order_id,)).fetchone()
            if not order:
                raise ValueError("This order is no longer available.")
            arrangement, paid, total, name, unknown = order
            if not can_move_to_credit(arrangement, paid, total):
                raise ValueError("Only orders created with Partial Payment that still have a balance can be moved.")
            if paid != expected_paid:
                raise ValueError("The balance changed. Reopen Payment Status and review the order.")
            name = customer_name(name) or format_customer_name(customer_name(replacement_customer))
            if not name or "\x00" in name:
                raise ValueError("Enter an identifiable customer name before moving the order to Utang.")
            connection.execute("""
                INSERT INTO order_arrangement_transfers (
                    order_id, previous_arrangement, new_arrangement, remaining_balance_centavos,
                    previous_unknown_number
                ) VALUES (?, ?, ?, ?, ?)
            """, (order_id, arrangement, CREDIT_ARRANGEMENT, total - paid, unknown))
            connection.execute("""
                UPDATE orders SET payment_arrangement = ?, customer_name = ?, unknown_number = NULL
                WHERE id = ?
            """, (CREDIT_ARRANGEMENT, name, order_id))

    def _record_payment(self, order_id, tendered, *, expected_paid, status):
        with closing(self.products.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("""
                SELECT total_centavos, customer_name, payment_arrangement, COALESCE((
                    SELECT SUM(amount_centavos) FROM payments WHERE order_id = orders.id
                ), 0)
                FROM orders WHERE id = ?
            """, (order_id,)).fetchone()
            if row is None:
                raise ValueError("This order is no longer available.")
            total, customer, arrangement, applied = row
            if expected_paid != applied:
                raise ValueError("The balance changed. Close this sheet and reopen Payment Status.")
            if applied >= total:
                raise ValueError("This order is already paid. Refunds and reversals are unavailable.")
            remaining = total - applied
            if status is None and arrangement != CREDIT_ARRANGEMENT:
                raise ValueError("Choose an outstanding credit order.")
            if arrangement == CREDIT_ARRANGEMENT:
                if type(tendered) is not int or not 0 < tendered <= remaining:
                    raise ValueError("Enter a payment greater than zero and no more than the remaining balance.")
                if status is None:
                    status = PAID if tendered == remaining else PARTIAL
            payment = allocate_payment(status, remaining, tendered, customer)
            connection.execute("""
                INSERT INTO payments (order_id, amount_centavos, cash_tendered_centavos, change_centavos)
                VALUES (?, ?, ?, ?)
            """, (order_id, payment.applied, payment.tendered, payment.change))
            connection.execute("""
                UPDATE orders SET amount_paid_centavos = ?, outstanding_balance_centavos = ?,
                                  payment_status = ? WHERE id = ?
            """, (applied + payment.applied, payment.outstanding, status, order_id))

    def credit_payment_history(self, customer_key):
        balances = {}
        history = []
        with closing(self.products.connect()) as connection:
            rows = connection.execute("""
                SELECT o.id, o.order_number, o.total_centavos, p.amount_centavos, p.created_at
                FROM orders AS o JOIN payments AS p ON p.order_id = o.id
                WHERE o.payment_arrangement = ? AND grillflow_name_key(o.customer_name) = ?
                ORDER BY p.created_at, p.id
            """, (CREDIT_ARRANGEMENT, normalized_name(customer_key)))
            for order_id, order_number, total, amount, timestamp in rows:
                balance = max(0, balances.get(order_id, total) - amount)
                balances[order_id] = balance
                history.append((order_number, amount, timestamp, balance))
        return history[::-1]

    def sales_summary(self):
        with closing(self.products.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            summary = connection.execute("""
                SELECT COUNT(CASE WHEN archived_at IS NULL AND preparation_status = 'Pending' THEN 1 END) AS active,
                       COUNT(CASE WHEN archived_at IS NULL AND preparation_status = 'Ready' THEN 1 END) AS ready
                FROM orders
            """).fetchone()
            recent = connection.execute(_ORDER_BALANCES + """
                SELECT order_number AS order_id, customer_name, total_centavos, preparation_status,
                       payment_arrangement, id AS saved_id, CASE
                           WHEN recorded_paid >= total_centavos THEN 'Paid'
                           WHEN recorded_paid > 0 THEN 'Partially Paid'
                           ELSE 'Unpaid'
                       END AS payment_status
                FROM order_balances
                WHERE archived_at IS NULL AND (
                    preparation_status = 'Pending'
                    OR (preparation_status = 'Ready' AND total_centavos > recorded_paid
                        AND (payment_arrangement = ?
                             OR (payment_arrangement = ? AND recorded_paid > 0)))
                )
                ORDER BY id DESC LIMIT 10
            """, (PAY_LATER, IMMEDIATE)).fetchall()
        return dict(summary, customers_with_utang=len(self.credit_customer_groups())), [dict(order) for order in recent]

    def credit_customer_groups(self):
        customers = {}
        for order in self.credit_details():
            key = normalized_name(order["customer_name"])
            customers.setdefault(key, []).append(order)
        return customers

    def history(self, start, end):
        return self._history_rows(
            "archived_at IS NULL AND created_at >= ? AND created_at < ?", (start, end),
        )

    def active_credit(self):
        return self._history_rows(
            _OUTSTANDING_CREDIT, (CREDIT_ARRANGEMENT,),
        )

    def credit_details(self, *, bounds=None, customer_key=None):
        params = [CREDIT_ARRANGEMENT]
        if customer_key is None:
            clauses = [_OUTSTANDING_CREDIT]
        else:
            clauses = ["o.payment_arrangement = ?", "grillflow_name_key(o.customer_name) = ?"]
            params.append(normalized_name(customer_key))
        if bounds:
            clauses.append("o.created_at >= ? AND o.created_at < ?")
            params.extend(bounds)
        groups = {}
        with closing(self.products.connect()) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(_ORDER_BALANCES + f"""
                SELECT o.id, o.order_number, o.customer_name, o.created_at, o.total_centavos,
                       o.preparation_status,
                       CASE WHEN o.recorded_paid >= o.total_centavos THEN 'Paid'
                            WHEN o.recorded_paid > 0 THEN 'Partially Paid'
                            ELSE 'Unpaid' END AS payment_status,
                       MAX(0, o.total_centavos - o.recorded_paid) AS outstanding_balance_centavos,
                       i.product_name_snapshot AS item_name, i.quantity
                FROM order_balances AS o LEFT JOIN order_items AS i ON i.order_id = o.id
                WHERE {' AND '.join(clauses)}
                ORDER BY o.created_at DESC, o.id DESC, i.id
            """, params)
            for row in rows:
                if row["id"] not in groups:
                    order = dict(row)
                    del order["item_name"], order["quantity"]
                    order["items"] = []
                    groups[row["id"]] = order
                if row["item_name"] is not None:
                    groups[row["id"]]["items"].append((row["item_name"], row["quantity"]))
        return list(groups.values())
    def _history_rows(self, condition, args):
        with closing(self.products.connect()) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(_ORDER_BALANCES + f"""
                SELECT id, order_number, customer_name, created_at, total_centavos,
                       payment_arrangement, outstanding_balance_centavos,
                       preparation_status, CASE
                           WHEN recorded_paid >= total_centavos THEN 'Paid'
                           WHEN recorded_paid > 0 THEN 'Partially Paid'
                           ELSE 'Unpaid'
                       END AS payment_status
                FROM order_balances
                WHERE {condition}
                ORDER BY created_at DESC, id DESC
            """, args).fetchall()

    def delete_order(self, order_id):
        with closing(self.products.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(_ORDER_BALANCES + """
                SELECT outstanding_balance_centavos, total_centavos - recorded_paid
                FROM order_balances WHERE id = ?
            """, (order_id,)).fetchone()
            if row is None:
                return False
            if max(row) > 0:
                raise OutstandingBalanceError("This order still has an unpaid balance. Settle it before deleting.")
            self._delete_paid_order(connection, order_id)
            return True

    def delete_history(self, start, end, expected_ids):
        with closing(self.products.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            visible = dict(connection.execute(_ORDER_BALANCES + """
                SELECT id, MAX(outstanding_balance_centavos, total_centavos - recorded_paid)
                FROM order_balances
                WHERE archived_at IS NULL AND created_at >= ? AND created_at < ?
            """, (start, end)))
            if frozenset(visible) != expected_ids:
                raise ValueError("Order history changed. Review the refreshed list before clearing.")
            if any(balance > 0 for balance in visible.values()):
                raise OutstandingBalanceError(HISTORY_BALANCE_MESSAGE)
            for order_id in visible:
                self._delete_paid_order(connection, order_id)
            return len(visible)

    @staticmethod
    def _delete_paid_order(connection, order_id):
        for table in ("order_items", "payments", "order_arrangement_transfers"):
            connection.execute(f"DELETE FROM {table} WHERE order_id = ?", (order_id,))
        result = connection.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        if result.rowcount != 1:
            raise sqlite3.IntegrityError("The selected order could not be deleted.")

    def financial_totals(self, start, end):
        return self.report_summary(start, end)[:3]

    def report_summary(self, start, end):
        with closing(self.products.connect()) as connection:
            return connection.execute(_ORDER_BALANCES + """
                SELECT
                    COALESCE((SELECT SUM(total_centavos) FROM orders WHERE created_at >= ? AND created_at < ?), 0),
                    COALESCE((SELECT SUM(amount_centavos) FROM payments WHERE created_at >= ? AND created_at < ?), 0),
                    COALESCE((SELECT SUM(total_centavos - recorded_paid)
                              FROM order_balances WHERE """ + _OUTSTANDING_CREDIT + """
                              AND created_at >= ? AND created_at < ?), 0),
                    (SELECT COUNT(*) FROM orders WHERE created_at >= ? AND created_at < ?)
            """, (start, end, start, end, CREDIT_ARRANGEMENT, start, end, start, end)).fetchone()

    def sales_trend(self, start, end, *, hourly):
        first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc).astimezone(PHILIPPINE_TIME)
        last = datetime.fromisoformat(end).replace(tzinfo=timezone.utc).astimezone(PHILIPPINE_TIME)
        step = timedelta(hours=1) if hourly else timedelta(days=1)
        totals = [0] * ((last - first) // step)
        with closing(self.products.connect()) as connection:
            for stamp, amount in connection.execute("""
                SELECT created_at, total_centavos FROM orders WHERE created_at >= ? AND created_at < ?
            """, (start, end)):
                local = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc).astimezone(PHILIPPINE_TIME)
                totals[(local - first) // step] += amount
        return [
            ((first + index * step).strftime("%H:%M" if hourly else "%a" if len(totals) == 7 else "%d"),
             amount) for index, amount in enumerate(totals)
        ]

    def ranked_products(self, start, end):
        groups = {}
        with closing(self.products.connect()) as connection:
            for product_id, name, unit, quantity, revenue, photo in connection.execute("""
                SELECT i.product_id, i.product_name_snapshot, i.unit_snapshot, i.quantity,
                       i.line_total_centavos, p.image_path
                FROM orders AS o JOIN order_items AS i ON i.order_id = o.id
                LEFT JOIN products AS p ON p.id = i.product_id
                WHERE o.created_at >= ? AND o.created_at < ?
                ORDER BY o.created_at DESC, i.id DESC
            """, (start, end)):
                # Keep unlike units separate and display the latest name snapshot in the period.
                group = groups.setdefault((product_id, unit), [name, unit, 0, 0, photo])
                group[2] += quantity
                group[3] += revenue
        return sorted(groups.values(), key=lambda row: (-row[2], -row[3], normalized_name(row[0]), row[1]))
