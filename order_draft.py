from dataclasses import dataclass
from sqlite3 import Row


@dataclass(frozen=True)
class DraftLine:
    product: Row
    quantity: int

    @property
    def subtotal(self):
        return self.product["selling_price"] * self.quantity


class OrderDraft:
    default_customer = "Unknown1"

    def __init__(self):
        self.lines = {}

    @property
    def total(self):
        return sum(line.subtotal for line in self.lines.values())

    def available(self, product):
        line = self.lines.get(product["id"])
        return max(0, product["stock"] - (line.quantity if line else 0))

    def add(self, product, quantity):
        available = self.available(product)
        if not 1 <= quantity <= available:
            raise ValueError(f"Only {available} more available for {product['name']}.")
        product_id = product["id"]
        line = self.lines.get(product_id)
        if line:
            if line.product["selling_price"] != product["selling_price"]:
                raise ValueError(f"The price of {product['name']} changed. Remove it and add it again.")
            quantity += line.quantity
        self.lines[product_id] = DraftLine(product, quantity)

    def validate_stock(self, products):
        for product_id, line in self.lines.items():
            product = products.get(product_id)
            name = line.product["name"]
            if product is None:
                raise ValueError(f"{name} is no longer available. Remove it from the order.")
            if line.quantity > product["stock"]:
                raise ValueError(f"Only {product['stock']} available for {name}. Remove it and add a smaller quantity.")
            if line.product["selling_price"] != product["selling_price"]:
                raise ValueError(f"The price of {name} changed. Remove it and add it again.")
