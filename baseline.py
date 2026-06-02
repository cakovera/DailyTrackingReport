from __future__ import annotations

from typing import BinaryIO

import pandas as pd

from calculations import METERS_PER_FOOT


BASELINE_COLUMNS = [
    "project_no",
    "repaired_spiral_length",
    "total_repair_amount",
    "total_repair_amount_incl_skelp",
]


def parse_historical_baseline_csv(file: BinaryIO) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(file)
    df.columns = [str(col).strip().lower() for col in df.columns]
    missing = [col for col in BASELINE_COLUMNS if col not in df.columns]
    if missing:
        return pd.DataFrame(), [f"Historical baseline CSV eksik kolon iceriyor: {', '.join(missing)}"]

    if "dimensions" not in df.columns:
        df["dimensions"] = "Historical Baseline"
    if "project_status" not in df.columns:
        df["project_status"] = "Completed"

    df = df[
        [
            "project_no",
            "dimensions",
            "repaired_spiral_length",
            "total_repair_amount",
            "total_repair_amount_incl_skelp",
            "project_status",
        ]
    ].copy()
    df["project_no"] = df["project_no"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    df["dimensions"] = df["dimensions"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    df["project_status"] = df["project_status"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)

    for col in ["repaired_spiral_length", "total_repair_amount", "total_repair_amount_incl_skelp"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[df["project_no"] != ""]
    errors: list[str] = []
    for idx, row in df.iterrows():
        row_no = idx + 2
        if pd.isna(row["repaired_spiral_length"]) or row["repaired_spiral_length"] <= 0:
            errors.append(f"CSV satir {row_no}: repaired_spiral_length pozitif numeric olmali.")
        if pd.isna(row["total_repair_amount"]) or row["total_repair_amount"] < 0:
            errors.append(f"CSV satir {row_no}: total_repair_amount numeric ve negatif olmayan deger olmali.")
        if pd.isna(row["total_repair_amount_incl_skelp"]) or row["total_repair_amount_incl_skelp"] < 0:
            errors.append(f"CSV satir {row_no}: total_repair_amount_incl_skelp numeric ve negatif olmayan deger olmali.")
        if (
            pd.notna(row["total_repair_amount"])
            and pd.notna(row["total_repair_amount_incl_skelp"])
            and row["total_repair_amount_incl_skelp"] < row["total_repair_amount"]
        ):
            errors.append(f"CSV satir {row_no}: incl. skelp amount normal amount degerinden kucuk.")

    if errors:
        return df, errors

    denominator_m = df["repaired_spiral_length"] * METERS_PER_FOOT
    df["repair_ratio"] = df["total_repair_amount"] / denominator_m
    df["repair_ratio_incl_skelp"] = df["total_repair_amount_incl_skelp"] / denominator_m
    return df, []


def baseline_template_csv() -> str:
    return (
        "project_no,dimensions,repaired_spiral_length,total_repair_amount,total_repair_amount_incl_skelp,project_status\n"
        "05-092,Historical Baseline,26035.18,332.55,965.55,Completed\n"
    )
