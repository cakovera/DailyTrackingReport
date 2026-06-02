from __future__ import annotations

import pandas as pd


METERS_PER_FOOT = 0.3048


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


def daily_weighted_repair_ratios(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("date", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
            repaired_spiral_length=("repaired_spiral_length", "sum"),
        )
        .sort_values("date")
    )
    denominator_m = grouped["repaired_spiral_length"] * METERS_PER_FOOT
    denominator_m = denominator_m.where(denominator_m != 0)
    grouped["weighted_repair_ratio"] = (grouped["total_repair_amount"] / denominator_m).fillna(0)
    grouped["weighted_repair_ratio_incl_skelp"] = (
        grouped["total_repair_amount_incl_skelp"] / denominator_m
    ).fillna(0)
    return grouped
