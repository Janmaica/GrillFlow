from dataclasses import dataclass
from datetime import datetime, timezone

from product_store import format_price


def local_timestamp(value):
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone().strftime("%b %d, %Y · %I:%M %p")


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
        else:
            rows.extend((
                ("Amount Paid to Date" if self.applied else "Amount Paid", self.applied),
                ("Remaining Balance", self.balance),
            ))
        return [(label, format_price(amount)) for label, amount in rows]
