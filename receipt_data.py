from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from product_store import format_price


PHILIPPINE_TIME = timezone(timedelta(hours=8), "PHT")


def display_payment_status(status, arrangement):
    if arrangement == "credit":
        if status == "Unpaid":
            return "Credit (Utang)"
        if status == "Partially Paid":
            return "Partially Paid (Credit)"
    return status


def local_timestamp(value):
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(PHILIPPINE_TIME).strftime("%b %d, %Y · %I:%M %p")


@dataclass(frozen=True)
class ReceiptItem:
    name: str
    unit: str
    quantity: int
    unit_price: int
    subtotal: int


@dataclass(frozen=True)
class ReceiptPayment:
    applied: int
    tendered: int
    change: int
    created_at: str


@dataclass(frozen=True)
class Receipt:
    order_number: str
    customer_name: str
    created_at: str
    total: int
    remarks: str
    items: tuple[ReceiptItem, ...]
    payments: tuple[ReceiptPayment, ...]
    payment_arrangement: str | None = None

    @property
    def arrangement_label(self):
        return {"pay_later": "Pay Later", "credit": "Credit (Utang)"}.get(self.payment_arrangement)

    @property
    def payment_label(self):
        return display_payment_status(self.status, self.payment_arrangement)

    @property
    def applied(self):
        return sum(payment.applied for payment in self.payments)

    @property
    def balance(self):
        return max(0, self.total - self.applied)

    @property
    def status(self):
        if self.balance == 0:
            return "Paid"
        return "Partially Paid" if self.applied else "Unpaid"

    def amounts(self):
        rows = [("Total Amount", self.total)]
        if self.status == "Paid":
            rows.extend((
                ("Cash Received / Tendered", sum(payment.tendered for payment in self.payments)),
                ("Change (Sukli)", sum(payment.change for payment in self.payments)),
            ))
            if self.payment_arrangement == "credit":
                rows.extend((("Amount Paid to Date", self.applied), ("Remaining Balance", self.balance)))
        else:
            rows.extend((
                ("Amount Paid to Date" if self.applied else "Amount Paid", self.applied),
                ("Remaining Balance", self.balance),
            ))
        return [(label, format_price(amount)) for label, amount in rows]

    def payment_steps(self):
        balance = self.total
        history = []
        # Payments are loaded in ID order, which breaks timestamp ties.
        for payment in sorted(self.payments, key=lambda entry: entry.created_at):
            balance = max(0, balance - payment.applied)
            history.append((payment, balance))
        return history[::-1]
