import webbrowser
from base64 import b64encode
from html import escape
from pathlib import Path
from shutil import copyfile
from uuid import uuid4

from product_store import format_price
from receipt_data import local_timestamp


RECEIPT_LOGO = Path(__file__).resolve().parent / "assets" / "images" / "grillflow_logo.png"
RECEIPT_HEADING = "SALES RECEIPT"
RECEIPT_FOOTER = "Salamat sa inyong suporta! — GrillFlow —"


class ReceiptOutputError(Exception):
    pass


def printable_html(receipt):
    logo = b64encode(RECEIPT_LOGO.read_bytes()).decode("ascii")
    items = "".join(
        f"<tr><td>{escape(item.name)}<br><small>{escape(item.unit)}</small></td>"
        f"<td>{item.quantity}</td><td>{format_price(item.unit_price)}</td>"
        f"<td>{format_price(item.subtotal)}</td></tr>"
        for item in receipt.items
    )
    totals = "".join(
        f"<dt>{escape(caption)}</dt><dd>{escape(amount)}</dd>"
        for caption, amount in receipt.amounts()
    )
    arrangement = (
        f"<dt>Payment Arrangement</dt><dd>{escape(receipt.arrangement_label)}</dd>"
        if receipt.arrangement_label else ""
    )
    history = ""
    if receipt.payment_arrangement == "credit" and receipt.payments:
        history = "<h2>Payment History</h2><ul>" + "".join(
            f"<li>{escape(local_timestamp(payment.created_at))} · {format_price(payment.applied)} applied"
            f" · Balance: {format_price(balance)}</li>" for payment, balance in receipt.payment_steps()
        ) + "</ul>"
    elif len(receipt.payments) > 1:
        history = "<h2>Payment History</h2><ul>" + "".join(
            f"<li>{escape(local_timestamp(payment.created_at))} · "
            f"{format_price(payment.applied)} applied</li>"
            for payment in receipt.payments
        ) + "</ul>"
    remarks = f"<p>Remarks: {escape(receipt.remarks)}</p>" if receipt.remarks.strip() else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>GrillFlow · {escape(receipt.order_number)}</title>
<style>
  body {{ font: 14px/1.45 Arial, sans-serif; color: #211916; margin: 24px auto;
          max-width: 390px; padding: 0 14px; overflow-wrap: anywhere; }}
  header, footer {{ text-align: center; }}
  header img {{ height: 52px; object-fit: contain; }}
  h1 {{ font-size: 19px; }} h2 {{ font-size: 15px; }}
  p {{ white-space: pre-line; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 5px 3px; text-align: right; vertical-align: top; }}
  th:first-child, td:first-child {{ text-align: left; width: 39%; }}
  table, dl, footer {{ border-top: 1px dashed #999; }}
  thead {{ display: table-header-group; }}
  tr {{ break-inside: avoid; }}
  dl {{ display: grid; grid-template-columns: auto auto; gap: 4px 10px; padding-top: 8px; }}
  dd {{ margin: 0; text-align: right; font-weight: bold; }}
  footer {{ margin-top: 14px; padding-top: 8px; }}
  .tools {{ margin-bottom: 12px; }}
  @media print {{ .tools {{ display: none; }} body {{ margin: 0 auto; }} }}
</style></head>
<body><div class="tools"><button type="button" onclick="window.print()">Print / Save as PDF</button></div>
<header><img alt="" src="data:image/png;base64,{logo}"><br><strong>GrillFlow</strong><br>
BBQ Business Manager<h1>{RECEIPT_HEADING}</h1></header>
<p>Order No.: {escape(receipt.order_number)}<br>
Customer: {escape(receipt.customer_name)}<br>
{escape(local_timestamp(receipt.created_at))}</p>
<table><thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
<tbody>{items}</tbody></table>
<dl>{totals}<dt>Payment Status</dt><dd>{escape(receipt.payment_label)}</dd>{arrangement}</dl>
{history}{remarks}<footer>{RECEIPT_FOOTER}</footer></body></html>"""


class DesktopReceiptOutput:
    def __init__(self, data_dir):
        self.directory = Path(data_dir) / "receipts"

    def _path(self, receipt, extension):
        self.directory.mkdir(parents=True, exist_ok=True)
        return self.directory / f"{receipt.order_number}-{uuid4().hex[:12]}.{extension}"

    def print_receipt(self, receipt):
        output = self._path(receipt, "html")
        output.write_text(printable_html(receipt), encoding="utf-8")
        if not webbrowser.open(output.resolve().as_uri()):
            raise ReceiptOutputError("Could not open a browser. Open the print-ready file at " + str(output))
        return "Use Print / Save as PDF in the browser."

    def share_receipt(self, receipt, export_png):
        output = self._path(receipt, "png")
        try:
            export_png(output)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        try:
            import tkinter
            from tkinter import filedialog
        except ImportError:
            return f"Receipt image saved to {output}"
        try:
            root = tkinter.Tk()
            try:
                root.withdraw()
                root.attributes("-topmost", True)
                selected = filedialog.asksaveasfilename(
                    parent=root, title="Export receipt", defaultextension=".png",
                    initialfile=f"{receipt.order_number}.png",
                    filetypes=(("PNG image", "*.png"),),
                )
            finally:
                root.destroy()
        except (OSError, tkinter.TclError):
            return f"Receipt image saved to {output}"
        if selected:
            target = Path(selected)
            if target.resolve() != output.resolve():
                try:
                    copyfile(output, target)
                except OSError:
                    return f"Could not export to that location. The receipt image is at {output}"
            return f"Receipt image exported to {target}"
        return f"Receipt image kept in {output}"


class AndroidReceiptOutput:
    # Native integration needs PrintManager and an ACTION_SEND content URI
    # from an app-scoped FileProvider. No raw file URIs are sent to other apps.
    def print_receipt(self, receipt):
        raise ReceiptOutputError("Android printing is not available yet.")

    def share_receipt(self, receipt, export_png):
        raise ReceiptOutputError("Android receipt sharing is not available yet.")


def receipt_output(data_dir, platform):
    if platform == "android":
        return AndroidReceiptOutput()
    return DesktopReceiptOutput(data_dir)
