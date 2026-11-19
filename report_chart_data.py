from datetime import datetime, timedelta, timezone
from decimal import Decimal

from order_store import PHILIPPINE_TIME


CHART_TITLES = {
    "This Day": ("Sales by Hour", "Time"),
    "This Week": ("Daily Sales", "Day"),
    "This Month": ("Sales by Date", "Date"),
}


def chart_buckets(series, period, start):
    first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc).astimezone(PHILIPPINE_TIME)
    hourly = period == "This Day"
    step = timedelta(hours=1) if hourly else timedelta(days=1)
    buckets = []
    for index, (_, amount) in enumerate(series):
        timestamp = first + index * step
        if hourly:
            hour = timestamp.strftime("%I").lstrip("0")
            meridiem = timestamp.strftime("%p")
            short, detail = f"{hour} {meridiem}", f"{hour}:00 {meridiem}"
        else:
            short = timestamp.strftime("%a") if period == "This Week" else f"{timestamp:%b} {timestamp.day}"
            detail = f"{timestamp:%A, %b} {timestamp.day}"
        buckets.append((short, detail, amount))
    return buckets


def axis_ticks(peak):
    if peak <= 0:
        return (0,)
    magnitude = 10 ** (len(str(max(1, peak // 4))) - 1)
    steps = {max(1, base * multiplier // 10)
             for base in (max(1, magnitude // 10), magnitude, magnitude * 10)
             for multiplier in (10, 20, 25, 30, 50)}
    step, count = min(
        ((step, count) for step in steps for count in (3, 4) if step * count >= peak),
        key=lambda pair: (pair[0] * pair[1], -pair[1]),
    )
    return tuple(step * index for index in range(count + 1))


def axis_caption(centavos):
    pesos = Decimal(centavos) / 100
    for scale, suffix in ((10**15, "Q"), (10**12, "T"), (10**9, "B"), (10**6, "M"), (10**3, "K")):
        if pesos >= scale:
            text = f"{pesos / scale:.2f}".rstrip("0").rstrip(".")
            return f"₱{text}{suffix}"
    text = f"{pesos:.2f}".rstrip("0").rstrip(".")
    return f"₱{text}"

