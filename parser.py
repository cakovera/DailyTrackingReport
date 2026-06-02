from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pandas as pd
from openpyxl import load_workbook

from validators import ValidationReport, coerce_number, coerce_report_date, normalize_spaces, normalize_status, validate_dataframe


SHEET_NAME = "Daily Repair Rate"

# Fixed workbook contract:
# - report date is in P1
# - the only accepted source table is A3:P25
# - data rows are 4:25, so lower calculation/chart tables are never read
REPORT_DATE_CELL = "P1"
DATA_START_ROW = 4
DATA_END_ROW = 25

COLUMN_MAP = {
    "project_no": "B",
    "dimensions": "E",
    "qty": "H",
    "project_total_pipe_length": "I",
    "repaired_pipes_total_length": "J",
    "repaired_spiral_length": "K",
    "total_repair_amount": "L",
    "total_repair_amount_incl_skelp": "M",
    "project_status": "N",
    "repair_ratio": "O",
    "repair_ratio_incl_skelp": "P",
}


def parse_daily_repair_rate(file: str | Path | BinaryIO) -> tuple[pd.DataFrame, ValidationReport]:
    report = ValidationReport()

    try:
        wb = load_workbook(file, read_only=True, data_only=True)
    except Exception as exc:
        report.add_check("Sheet bulundu mu?", False)
        report.add_error(f"Excel dosyası açılamadı: {exc}")
        return pd.DataFrame(), report

    if SHEET_NAME not in wb.sheetnames:
        report.add_check("Sheet bulundu mu?", False)
        report.add_error(f"'{SHEET_NAME}' sheet'i bulunamadı.")
        return pd.DataFrame(), report

    report.add_check("Sheet bulundu mu?", True)
    ws = wb[SHEET_NAME]

    report_date = coerce_report_date(ws[REPORT_DATE_CELL].value)
    report.add_check("Tarih bulundu mu?", report_date is not None)
    if report_date is None:
        report.add_error(f"Rapor tarihi boş veya geçersiz: {SHEET_NAME}!{REPORT_DATE_CELL}")
        return pd.DataFrame(), report

    rows: list[dict[str, object]] = []
    for excel_row in range(DATA_START_ROW, DATA_END_ROW + 1):
        project_no = normalize_spaces(ws[f"{COLUMN_MAP['project_no']}{excel_row}"].value)
        dimensions = normalize_spaces(ws[f"{COLUMN_MAP['dimensions']}{excel_row}"].value)

        if not project_no or not dimensions:
            continue

        row = {
            "date": report_date.isoformat(),
            "project_no": project_no,
            "dimensions": dimensions,
            "project_status": normalize_status(ws[f"{COLUMN_MAP['project_status']}{excel_row}"].value),
            "excel_row": excel_row,
        }

        for col_name in [
            "qty",
            "project_total_pipe_length",
            "repaired_pipes_total_length",
            "repaired_spiral_length",
            "total_repair_amount",
            "total_repair_amount_incl_skelp",
            "repair_ratio",
            "repair_ratio_incl_skelp",
        ]:
            row[col_name] = coerce_number(ws[f"{COLUMN_MAP[col_name]}{excel_row}"].value)

        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        ordered = [
            "date",
            "project_no",
            "dimensions",
            "qty",
            "project_total_pipe_length",
            "repaired_pipes_total_length",
            "repaired_spiral_length",
            "total_repair_amount",
            "total_repair_amount_incl_skelp",
            "project_status",
            "repair_ratio",
            "repair_ratio_incl_skelp",
            "excel_row",
        ]
        df = df[ordered]

    return df, validate_dataframe(df, report)
