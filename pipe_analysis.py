from __future__ import annotations

import pandas as pd


PIPE_PROJECT_RECONCILIATION_TOLERANCE_M = 0.01


def reconcile_pipe_projects(
    daily_df: pd.DataFrame,
    pipe_df: pd.DataFrame,
    tolerance_m: float = PIPE_PROJECT_RECONCILIATION_TOLERANCE_M,
) -> pd.DataFrame:
    """Return only pipe sheets that uniquely reconcile to one daily project row."""
    columns = [
        "project_sheet",
        "project_no",
        "dimensions",
        "expected_repair_amount",
        "pipe_repair_amount",
        "difference_m",
        "pipe_rows",
        "joint_count_coverage",
    ]
    if daily_df.empty or pipe_df.empty:
        return pd.DataFrame(columns=columns)

    sheet_totals = (
        pipe_df.groupby("project_sheet", as_index=False)
        .agg(
            pipe_repair_amount=("repair_amount", "sum"),
            pipe_rows=("pipe_no", "size"),
            joint_count_rows=("repair_count", "count"),
        )
    )
    reconciled: list[dict[str, object]] = []
    for _, sheet in sheet_totals.iterrows():
        candidates = daily_df[
            (daily_df["total_repair_amount"] - sheet["pipe_repair_amount"]).abs() <= tolerance_m
        ]
        if len(candidates) != 1:
            continue

        project = candidates.iloc[0]
        reconciled.append(
            {
                "project_sheet": sheet["project_sheet"],
                "project_no": project["project_no"],
                "dimensions": project["dimensions"],
                "expected_repair_amount": float(project["total_repair_amount"]),
                "pipe_repair_amount": float(sheet["pipe_repair_amount"]),
                "difference_m": float(sheet["pipe_repair_amount"] - project["total_repair_amount"]),
                "pipe_rows": int(sheet["pipe_rows"]),
                "joint_count_coverage": (
                    float(sheet["joint_count_rows"]) / float(sheet["pipe_rows"])
                    if sheet["pipe_rows"]
                    else 0.0
                ),
            }
        )
    return pd.DataFrame(reconciled, columns=columns).sort_values(
        ["project_no", "dimensions", "project_sheet"]
    )
