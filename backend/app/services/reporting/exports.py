from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _metadata_rows(report_metadata: dict) -> list[tuple[str, object]]:
    return [
        ("project_name", report_metadata.get("project_name", "Project Vigyan")),
        ("academic_year_id", report_metadata.get("academic_year_id")),
        ("report_type", report_metadata.get("report_type")),
        ("reporting_period", report_metadata.get("reporting_period")),
        ("generated_at", report_metadata.get("generated_at")),
        ("generated_by", report_metadata.get("generated_by")),
        ("applied_filters", report_metadata.get("applied_filters", {})),
    ]


def csv_bytes(report_type: str, rows: list[dict], metadata: dict) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Project Vigyan"])
    for key, value in _metadata_rows(metadata):
        writer.writerow([
            key,
            json.dumps(value, sort_keys=True, default=str)
            if isinstance(value, (dict, list))
            else value,
        ])
    writer.writerow([])
    if not rows:
        writer.writerow(["No data"])
        return output.getvalue().encode("utf-8")
    columns = list(rows[0])
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column) for column in columns])
    return output.getvalue().encode("utf-8")


def metadata(
    report_type: str,
    generated_by: str,
    filters: dict,
) -> dict:
    return {
        "project_name": "Project Vigyan",
        "academic_year_id": filters.get("academic_year_id"),
        "report_type": report_type,
        "reporting_period": (
            filters.get("reporting_period") or filters.get("assessment")
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "applied_filters": filters,
    }


def xlsx_bytes(report_type: str, rows: list[dict], report_metadata: dict) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = report_type[:31]
    sheet.append(["Project Vigyan"])
    for key, value in _metadata_rows(report_metadata):
        sheet.append([
            key,
            json.dumps(value, sort_keys=True, default=str)
            if isinstance(value, (dict, list))
            else value,
        ])
    sheet.append([])
    columns = list(rows[0]) if rows else ["No data"]
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(column) for column in columns])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def pdf_bytes(
    report_type: str,
    rows: list[dict],
    report_metadata: dict,
) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Project Vigyan", styles["Title"]),
        Paragraph(f"{report_type.title()} Report", styles["Heading2"]),
    ]
    for key, value in _metadata_rows(report_metadata):
        display_value = json.dumps(value, sort_keys=True, default=str)
        story.append(
            Paragraph(
                escape(f"{key}: {display_value}"),
                styles["BodyText"],
            )
        )
    story.append(Spacer(1, 12))
    if rows:
        columns = list(rows[0])
        table_rows = [columns] + [
            [str(row.get(column, "")) for column in columns]
            for row in rows
        ]
    else:
        table_rows = [["No data"]]
    table = Table(table_rows, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ])
    )
    story.append(table)
    document.build(story)
    return output.getvalue()


def report_bytes(
    report_type: str,
    rows: list[dict],
    report_metadata: dict,
    file_format: str,
) -> tuple[bytes, str, str]:
    if file_format == "csv":
        return csv_bytes(report_type, rows, report_metadata), "text/csv", "csv"
    if file_format == "xlsx":
        return (
            xlsx_bytes(report_type, rows, report_metadata),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    if file_format == "pdf":
        return pdf_bytes(report_type, rows, report_metadata), "application/pdf", "pdf"
    raise ValueError("Unsupported export format.")
