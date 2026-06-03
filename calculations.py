from __future__ import annotations

import pandas as pd


METERS_PER_FOOT = 0.3048
FEET_PER_METER = 1 / METERS_PER_FOOT


def unit_label(display_unit: str) -> str:
    return "ft" if display_unit == "ft" else "m"


def amount_in_display_unit(values, display_unit: str):
    if display_unit == "ft":
        return values * FEET_PER_METER
    return values


def length_in_display_unit(values, display_unit: str):
    if display_unit == "m":
        return values * METERS_PER_FOOT
    return values


def apply_meter_based_repair_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with repair ratios recalculated as meter / meter.

    Excel length columns are in feet; repair amount columns are in meters.
    The dashboard standard is:
      repair amount (m) / repaired spiral length (ft * 0.3048)
    """
    out = df.copy()
    denominator_m = out["repaired_spiral_length"] * METERS_PER_FOOT
    denominator_m = denominator_m.where(denominator_m != 0)
    out["repair_ratio"] = out["total_repair_amount"] / denominator_m
    out["repair_ratio_incl_skelp"] = out["total_repair_amount_incl_skelp"] / denominator_m
    out[["repair_ratio", "repair_ratio_incl_skelp"]] = out[["repair_ratio", "repair_ratio_incl_skelp"]].fillna(0)
    return out


def daily_weighted_repair_ratios(df: pd.DataFrame, baseline_df: pd.DataFrame | None = None) -> pd.DataFrame:
    grouped = (
        df.groupby("date", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
            repaired_spiral_length=("repaired_spiral_length", "sum"),
        )
        .sort_values("date")
    )
    baseline_repair = 0.0
    baseline_repair_incl = 0.0
    baseline_spiral = 0.0
    if baseline_df is not None and not baseline_df.empty:
        baseline_repair = baseline_df["total_repair_amount"].sum()
        baseline_repair_incl = baseline_df["total_repair_amount_incl_skelp"].sum()
        baseline_spiral = baseline_df["repaired_spiral_length"].sum()

    denominator_m = (grouped["repaired_spiral_length"] + baseline_spiral) * METERS_PER_FOOT
    denominator_m = denominator_m.where(denominator_m != 0)
    grouped["weighted_repair_ratio"] = ((grouped["total_repair_amount"] + baseline_repair) / denominator_m).fillna(0)
    grouped["weighted_repair_ratio_incl_skelp"] = (
        (grouped["total_repair_amount_incl_skelp"] + baseline_repair_incl) / denominator_m
    ).fillna(0)
    return grouped
