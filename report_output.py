import csv
import webbrowser
from html import escape
from uuid import uuid4


def write_report(directory, rows, *, print_report=False):
    directory = directory / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    extension = "html" if print_report else "csv"
    output = directory / f"grillflow-report-{uuid4().hex[:12]}.{extension}"
    if not print_report:
        with output.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerows(tuple(
                "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
                else value for value in row
            ) for row in rows)
        return f"Report exported to {output}"

    table = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>" for row in rows)
    output.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>GrillFlow Report</title>'
        '<style>body{font:14px Arial;margin:24px}td{padding:5px;border-bottom:1px solid #ddd}'
        '@media print{button{display:none}}</style><h1>GrillFlow Report</h1>'
        '<button onclick="window.print()">Print / Save as PDF</button>'
        f"<table>{table}</table></html>", encoding="utf-8",
    )
    if not webbrowser.open(output.resolve().as_uri()):
        return f"Open the print-ready report at {output}"
    return "Use Print / Save as PDF in the browser."
