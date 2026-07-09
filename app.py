from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import charts
import database as db
from calculations import METERS_PER_FOOT, amount_in_display_unit, apply_meter_based_repair_ratios, length_in_display_unit, unit_label
from parser import parse_daily_repair_rate
from pdf_report import build_a3_pdf_report
from validators import mark_duplicate_counts

DB_PATH = db.DB_PATH
get_backend_name = db.get_backend_name
get_existing_keys = db.get_existing_keys
load_historical_baselines = db.load_historical_baselines
load_master_data = db.load_master_data
upsert_historical_baselines = db.upsert_historical_baselines
upsert_repair_rates = db.upsert_repair_rates


def load_project_group_config(project_sheet: str, project_no: str, dimensions: str) -> dict[str, str] | None:
    if hasattr(db, "load_project_group_config"):
        return db.load_project_group_config(project_sheet, project_no, dimensions)

    if get_backend_name() != "supabase" or not hasattr(db, "_get_supabase_client"):
        return None

    client = db._get_supabase_client()
    response = (
        client.table("project_group_configs")
        .select("pipe_groups,machine_groups")
        .eq("project_sheet", project_sheet)
        .eq("project_no", project_no)
        .eq("dimensions", dimensions)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    row = response.data[0]
    return {"pipe_groups": row.get("pipe_groups") or "", "machine_groups": row.get("machine_groups") or ""}


def upsert_project_group_config(
    project_sheet: str,
    project_no: str,
    dimensions: str,
    pipe_groups: str,
    machine_groups: str,
) -> int:
    if hasattr(db, "upsert_project_group_config"):
        return db.upsert_project_group_config(project_sheet, project_no, dimensions, pipe_groups, machine_groups)

    if get_backend_name() != "supabase" or not hasattr(db, "_get_supabase_client"):
        raise RuntimeError("Project group config persistence is not available in this database backend.")

    client = db._get_supabase_client()
    client.table("project_group_configs").upsert(
        {
            "project_sheet": project_sheet,
            "project_no": project_no,
            "dimensions": dimensions,
            "pipe_groups": pipe_groups.strip(),
            "machine_groups": machine_groups.strip(),
        },
        on_conflict="project_sheet,project_no,dimensions",
    ).execute()
    return 1

# Pipe-level analysis is optional so a partial/stale cloud deployment cannot
# prevent the core repair-rate dashboard from starting.
try:
    from project_parser import parse_project_pipe_repairs
    from pipe_analysis import reconcile_pipe_projects
    from project_pdf_report import build_dimension_pipe_pdf_report, build_project_pipe_pdf_report

    load_pipe_repair_details = db.load_pipe_repair_details
    load_pipe_repair_details_for_date = db.load_pipe_repair_details_for_date
    upsert_pipe_repair_details = db.upsert_pipe_repair_details
    PIPE_ANALYSIS_AVAILABLE = True
    PIPE_ANALYSIS_IMPORT_ERROR = ""
except (ImportError, AttributeError) as exc:
    PIPE_ANALYSIS_AVAILABLE = False
    PIPE_ANALYSIS_IMPORT_ERROR = str(exc)


st.set_page_config(page_title="Daily Repair Rate Trend Dashboard", layout="wide")
st.title("Daily Repair Rate Trend Dashboard")

if "last_import_summary" not in st.session_state:
    st.session_state.last_import_summary = None
if "pdf_report" not in st.session_state:
    st.session_state.pdf_report = None
if "pdf_report_name" not in st.session_state:
    st.session_state.pdf_report_name = None
if "project_pdf_report" not in st.session_state:
    st.session_state.project_pdf_report = None
if "project_pdf_report_name" not in st.session_state:
    st.session_state.project_pdf_report_name = None
if "project_pdf_report_key" not in st.session_state:
    st.session_state.project_pdf_report_key = None
if "dimension_pdf_report" not in st.session_state:
    st.session_state.dimension_pdf_report = None
if "dimension_pdf_report_name" not in st.session_state:
    st.session_state.dimension_pdf_report_name = None
if "dimension_pdf_report_key" not in st.session_state:
    st.session_state.dimension_pdf_report_key = None
if "project_group_config_key" not in st.session_state:
    st.session_state.project_group_config_key = None
if "pipe_group_spec_input" not in st.session_state:
    st.session_state.pipe_group_spec_input = ""
if "machine_group_spec_input" not in st.session_state:
    st.session_state.machine_group_spec_input = ""
if "data_refresh_version" not in st.session_state:
    st.session_state.data_refresh_version = 0


def refresh_cached_data() -> None:
    st.session_state.data_refresh_version += 1
    st.cache_data.clear()


@st.cache_data(ttl=300, show_spinner=False)
def load_dashboard_data(refresh_version: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    del refresh_version
    master = load_master_data()
    baseline = load_historical_baselines()
    return master, baseline


@st.cache_data(ttl=300, show_spinner=False)
def load_selected_date_pipe_data(refresh_version: int, selected_date) -> pd.DataFrame:
    del refresh_version
    if not PIPE_ANALYSIS_AVAILABLE:
        return pd.DataFrame()
    return load_pipe_repair_details_for_date(selected_date)


@st.cache_data(ttl=300, show_spinner=False)
def cached_project_group_config(
    refresh_version: int,
    project_sheet: str,
    project_no: str,
    dimensions: str,
) -> dict[str, str] | None:
    del refresh_version
    return load_project_group_config(project_sheet, project_no, dimensions)


@st.cache_data(show_spinner=False, max_entries=64)
def cached_reconciled_projects(daily_df: pd.DataFrame, pipe_df: pd.DataFrame) -> pd.DataFrame:
    return reconcile_pipe_projects(daily_df, pipe_df)


@st.cache_data(show_spinner=False, max_entries=64)
def cached_dimension_pipe_frame(
    selected_pipe_df: pd.DataFrame,
    reconciled_projects: pd.DataFrame,
    project_sheets: tuple[str, ...],
) -> pd.DataFrame:
    return build_dimension_pipe_frame(selected_pipe_df, reconciled_projects, list(project_sheets))


@st.cache_data(show_spinner=False, max_entries=64)
def cached_apply_project_saved_groups(
    refresh_version: int,
    dimension_pipe_df: pd.DataFrame,
    reconciled_selection: pd.DataFrame,
    config_field: str,
    fallback_label: str,
    prefix_project: bool = True,
    fallback_when_missing: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    del refresh_version
    return apply_project_saved_groups(
        dimension_pipe_df,
        reconciled_selection,
        config_field,
        fallback_label,
        prefix_project=prefix_project,
        fallback_when_missing=fallback_when_missing,
    )


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_overall_daily_trend(df: pd.DataFrame, baseline_df: pd.DataFrame):
    return charts.overall_daily_trend(df, baseline_df)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_production_type_daily_trend(
    df: pd.DataFrame,
    production_type: str,
    baseline_df: pd.DataFrame,
):
    return charts.production_type_daily_trend(df, production_type, baseline_df)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_repair_amount_trend(df: pd.DataFrame, display_unit: str):
    return charts.repair_amount_trend(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_worst_projects_today(df: pd.DataFrame, selected_date):
    return charts.worst_projects_today(df, selected_date)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_project_trend(df: pd.DataFrame, selected_project: str):
    return charts.project_trend(df, selected_project)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_production_type_analysis(df: pd.DataFrame, baseline_df: pd.DataFrame):
    return charts.production_type_analysis(df, baseline_df)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_dimension_analysis(df: pd.DataFrame):
    return charts.dimension_analysis(df)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_status_comparison(df: pd.DataFrame, display_unit: str):
    return charts.status_comparison(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_historical_benchmark_comparison(df: pd.DataFrame, baseline_df: pd.DataFrame):
    return charts.historical_benchmark_comparison(df, baseline_df)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_skelp_impact_analysis(df: pd.DataFrame, display_unit: str):
    return charts.skelp_impact_analysis(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_repair_amount_pareto(df: pd.DataFrame, display_unit: str):
    return charts.repair_amount_pareto(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_pipe_group_repair_ratio_trend(
    df: pd.DataFrame,
    group_column: str,
    display_unit: str,
    group_title: str = "Pipe Group",
):
    return charts.pipe_group_repair_ratio_trend(df, group_column, display_unit, group_title=group_title)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_pipe_group_comparison(
    df: pd.DataFrame,
    group_column: str,
    display_unit: str,
    group_title: str = "Pipe Group",
):
    return charts.pipe_group_comparison(df, group_column, display_unit, group_title=group_title)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_pipe_repair_amount_pareto(df: pd.DataFrame, display_unit: str):
    return charts.pipe_repair_amount_pareto(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_pipe_worst_ratio(df: pd.DataFrame, display_unit: str):
    return charts.pipe_worst_ratio(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_pipe_joint_count_distribution(df: pd.DataFrame, display_unit: str):
    return charts.pipe_joint_count_distribution(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_pipe_joint_count_vs_repair(df: pd.DataFrame, display_unit: str):
    return charts.pipe_joint_count_vs_repair(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_dimension_project_comparison(df: pd.DataFrame, display_unit: str):
    return dimension_project_comparison_chart(df, display_unit)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_dimension_worst_pipes(df: pd.DataFrame, display_unit: str, top_n: int):
    return dimension_worst_pipes_chart(df, display_unit, top_n)


@st.cache_data(show_spinner=False, max_entries=128)
def cached_chart_pipe_group_binned_trend(
    df: pd.DataFrame,
    group_column: str,
    display_unit: str,
    group_title: str,
    bin_size: int,
):
    return pipe_group_binned_trend_chart(df, group_column, display_unit, group_title, bin_size)


def format_preview(df: pd.DataFrame, display_unit: str = "m") -> pd.DataFrame:
    out = df.drop(columns=["excel_row"], errors="ignore").copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    unit = unit_label(display_unit)
    for col in ["project_total_pipe_length", "repaired_pipes_total_length", "repaired_spiral_length"]:
        if col in out.columns:
            out[col] = length_in_display_unit(out[col], display_unit)
            out = out.rename(columns={col: f"{col}_{unit}"})
    for col in ["total_repair_amount", "total_repair_amount_incl_skelp"]:
        if col in out.columns:
            out[col] = amount_in_display_unit(out[col], display_unit)
            out = out.rename(columns={col: f"{col}_{unit}"})
    for col in ["repair_ratio", "repair_ratio_incl_skelp"]:
        out[col] = out[col].map(lambda x: f"{x:.2%}" if pd.notna(x) else "")
    return out


def parse_pipe_group_ranges(spec: str) -> tuple[list[dict[str, int | str]], list[str]]:
    ranges: list[dict[str, int | str]] = []
    errors: list[str] = []
    for index, group_part in enumerate([part.strip() for part in spec.split(";") if part.strip()], start=1):
        if ":" in group_part:
            raw_label, range_part = group_part.split(":", 1)
            group_label = raw_label.strip()
        else:
            group_label = ""
            range_part = group_part
        if not group_label:
            group_label = f"Pipe {range_part.strip()}"
        if not group_label:
            errors.append(f"Missing pipe group in: {group_part}")
            continue
        for raw_range in [part.strip() for part in range_part.split(",") if part.strip()]:
            match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", raw_range)
            if not match:
                errors.append(f"Invalid pipe interval '{raw_range}' for group {group_label}")
                continue
            start = int(match.group(1))
            end = int(match.group(2) or match.group(1))
            if start > end:
                errors.append(f"Pipe interval start is greater than end: {group_label}:{raw_range}")
                continue
            range_text = str(start) if start == end else f"{start}-{end}"
            ranges.append(
                {
                    "group_label": group_label,
                    "start": start,
                    "end": end,
                    "range_text": range_text,
                    "display_label": group_label,
                    "sort_order": index,
                }
            )
    if not ranges and not errors:
        errors.append("At least one range is required.")
    return ranges, errors


def assign_pipe_groups(pipe_df: pd.DataFrame, ranges: list[dict[str, int | str]]) -> tuple[pd.DataFrame, list[str]]:
    out = pipe_df.copy()
    out["pipe_no_numeric"] = pd.to_numeric(out["pipe_no"], errors="coerce")
    out["pipe_group"] = pd.NA
    out["pipe_group_order"] = pd.NA
    warnings: list[str] = []

    assigned_pipe_numbers: set[int] = set()
    for range_item in ranges:
        start = int(range_item["start"])
        end = int(range_item["end"])
        mask = out["pipe_no_numeric"].between(start, end, inclusive="both")
        overlapping = sorted(
            out.loc[mask & out["pipe_group"].notna(), "pipe_no_numeric"].dropna().astype(int).unique()
        )
        if overlapping:
            warnings.append(
                f"Overlapping pipe interval for {range_item['display_label']} includes already assigned pipes: {overlapping}"
            )
        assign_mask = mask & out["pipe_group"].isna()
        out.loc[assign_mask, "pipe_group"] = str(range_item["display_label"])
        out.loc[assign_mask, "pipe_group_order"] = int(range_item["sort_order"])
        assigned_pipe_numbers.update(out.loc[mask, "pipe_no_numeric"].dropna().astype(int).tolist())

    missing_from_data = [
        str(range_item["display_label"])
        for range_item in ranges
        if out["pipe_no_numeric"].between(int(range_item["start"]), int(range_item["end"]), inclusive="both").sum() == 0
    ]
    if missing_from_data:
        warnings.append("No pipe rows found for these intervals: " + ", ".join(missing_from_data))

    unassigned = sorted(
        set(out["pipe_no_numeric"].dropna().astype(int).tolist()) - assigned_pipe_numbers
    )
    if unassigned:
        warnings.append(f"These pipes are outside the entered ranges and were excluded: {unassigned}")

    return out[out["pipe_group"].notna()].copy(), warnings


def assign_all_pipes_group(pipe_df: pd.DataFrame, label: str = "All Pipes") -> pd.DataFrame:
    out = pipe_df.copy()
    out["pipe_no_numeric"] = pd.to_numeric(out["pipe_no"], errors="coerce")
    out["pipe_group"] = label
    out["pipe_group_order"] = 1
    return out.dropna(subset=["pipe_no_numeric"]).copy()


def summarize_pipe_groups(grouped_pipe_df: pd.DataFrame, group_column_label: str, display_unit: str) -> pd.DataFrame:
    unit = unit_label(display_unit)
    summary = (
        grouped_pipe_df.groupby("pipe_group", as_index=False)
        .agg(
            **{
                "Sort": ("pipe_group_order", "min"),
                "Pipe Count": ("pipe_no_numeric", "count"),
                "Avg Repair Ratio": ("repair_ratio", "mean"),
                "Max Repair Ratio": ("repair_ratio", "max"),
                f"Total Repair Amount ({unit})": (
                    "repair_amount",
                    lambda series: amount_in_display_unit(series.sum(), display_unit),
                ),
            }
        )
        .rename(columns={"pipe_group": group_column_label})
        .sort_values("Sort")
        .drop(columns=["Sort"])
    )
    return summary


def pipe_group_style(summary_df: pd.DataFrame, display_unit: str):
    unit = unit_label(display_unit)
    return summary_df.style.format(
        {
            "Pipe Count": "{:,.0f}",
            "Avg Repair Ratio": "{:.2%}",
            "Max Repair Ratio": "{:.2%}",
            f"Total Repair Amount ({unit})": "{:,.2f}",
        }
    )


def dimension_project_comparison_chart(pipe_df: pd.DataFrame, display_unit: str):
    if hasattr(charts, "dimension_project_comparison"):
        return charts.dimension_project_comparison(pipe_df, display_unit)

    fallback = pipe_df.copy()
    fallback["pipe_group"] = fallback["project_no"].astype(str)
    project_order = {project: index + 1 for index, project in enumerate(fallback["pipe_group"].drop_duplicates())}
    fallback["pipe_group_order"] = fallback["pipe_group"].map(project_order)
    return charts.pipe_group_comparison(fallback, "pipe_group", display_unit, group_title="Project")


def dimension_worst_pipes_chart(pipe_df: pd.DataFrame, display_unit: str, top_n: int = 20):
    if hasattr(charts, "dimension_worst_pipes"):
        return charts.dimension_worst_pipes(pipe_df, display_unit, top_n=top_n)

    fallback = pipe_df.copy()
    if "project_sheet" not in fallback.columns:
        fallback["project_sheet"] = fallback["project_no"].astype(str)
    return charts.pipe_worst_ratio(fallback.nlargest(top_n, "repair_ratio"), display_unit)


def pipe_group_binned_trend_chart(
    pipe_df: pd.DataFrame,
    group_column: str,
    display_unit: str,
    group_title: str,
    bin_size: int,
):
    if hasattr(charts, "pipe_group_binned_repair_ratio_trend"):
        return charts.pipe_group_binned_repair_ratio_trend(
            pipe_df,
            group_column,
            display_unit,
            group_title=group_title,
            bin_size=bin_size,
        )
    return charts.pipe_group_repair_ratio_trend(pipe_df, group_column, display_unit, group_title=group_title)


def build_dimension_pipe_frame(
    selected_pipe_df: pd.DataFrame,
    reconciled_projects: pd.DataFrame,
    project_sheets: list[str],
) -> pd.DataFrame:
    meta = reconciled_projects[
        ["project_sheet", "project_no", "dimensions", "expected_repair_amount", "pipe_repair_amount"]
    ].copy()
    out = selected_pipe_df[selected_pipe_df["project_sheet"].isin(project_sheets)].copy()
    if out.empty:
        return out
    out = out.merge(meta, on="project_sheet", how="left")
    out["pipe_no_numeric"] = pd.to_numeric(out["pipe_no"], errors="coerce")
    out["project_pipe_label"] = out["project_no"].astype(str) + " | Pipe " + out["pipe_no_numeric"].astype("Int64").astype(str)
    return out


def apply_project_saved_groups(
    dimension_pipe_df: pd.DataFrame,
    reconciled_selection: pd.DataFrame,
    config_field: str,
    fallback_label: str,
    prefix_project: bool = True,
    fallback_when_missing: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for _, project in reconciled_selection.iterrows():
        project_sheet = str(project["project_sheet"])
        project_no = str(project["project_no"])
        dimensions = str(project["dimensions"])
        project_df = dimension_pipe_df[dimension_pipe_df["project_sheet"].eq(project_sheet)].copy()
        if project_df.empty:
            continue
        try:
            config = load_project_group_config(project_sheet, project_no, dimensions)
        except Exception as exc:
            config = None
            warnings.append(f"{project_no}: saved group settings could not be loaded ({exc})")
        spec = (config or {}).get(config_field, "").strip()
        if not spec:
            if not fallback_when_missing:
                warnings.append(f"{project_no}: saved {config_field.replace('_', ' ')} is empty.")
                continue
            grouped = assign_all_pipes_group(project_df, f"{project_no} {fallback_label}")
            grouped["pipe_group"] = f"{project_no} {fallback_label}"
            grouped["pipe_group_order"] = len(frames) + 1
            frames.append(grouped)
            continue
        ranges, errors = parse_pipe_group_ranges(spec)
        if errors:
            warnings.extend([f"{project_no}: {error}" for error in errors])
            continue
        grouped, group_warnings = assign_pipe_groups(project_df, ranges)
        warnings.extend([f"{project_no}: {warning}" for warning in group_warnings])
        if grouped.empty:
            warnings.append(f"{project_no}: no pipe rows matched saved groups.")
            continue
        if prefix_project:
            grouped["pipe_group"] = project_no + " | " + grouped["pipe_group"].astype(str)
        grouped["pipe_group_order"] = (len(frames) + 1) * 1000 + pd.to_numeric(grouped["pipe_group_order"], errors="coerce")
        frames.append(grouped)
    if not frames:
        return pd.DataFrame(), warnings
    return pd.concat(frames, ignore_index=True), warnings


def weighted_repair_ratio_for_rows(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    denominator_m = df["repaired_spiral_length"].sum() * METERS_PER_FOOT
    return float(df["total_repair_amount"].sum() / denominator_m) if denominator_m else 0.0


def production_type_summary_rows(
    filtered_df: pd.DataFrame,
    selected_date,
    selected_date_df: pd.DataFrame,
) -> list[dict[str, object]]:
    previous_dates = sorted(date for date in filtered_df["date"].dt.date.unique() if date < selected_date)
    previous_date = previous_dates[-1] if previous_dates else None
    previous_df = (
        filtered_df[filtered_df["date"].dt.date.eq(previous_date)].copy()
        if previous_date is not None
        else pd.DataFrame()
    )
    rows: list[dict[str, object]] = []
    production_types = [
        production_type
        for production_type in ["Coil", "Plate"]
        if production_type in set(selected_date_df["production_type"].dropna().astype(str))
    ]
    if not production_types:
        production_types = sorted(selected_date_df["production_type"].dropna().astype(str).unique().tolist())
    for production_type in production_types:
        current = selected_date_df[selected_date_df["production_type"].astype(str).eq(production_type)]
        previous = previous_df[previous_df["production_type"].astype(str).eq(production_type)] if not previous_df.empty else pd.DataFrame()
        current_ratio = weighted_repair_ratio_for_rows(current)
        previous_ratio = weighted_repair_ratio_for_rows(previous)
        rows.append(
            {
                "production_type": production_type,
                "current_ratio": current_ratio,
                "delta": current_ratio - previous_ratio if previous_date is not None else None,
                "project_count": int(len(current)),
            }
        )
    return rows


def render_executive_summary(
    selected_date,
    selected_date_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    display_unit: str,
) -> None:
    in_progress = selected_date_df[selected_date_df["project_status"].eq("In Progress")].copy()
    completed = selected_date_df[selected_date_df["project_status"].eq("Completed")].copy()
    summary_rows = production_type_summary_rows(filtered_df, selected_date, selected_date_df)
    unit = unit_label(display_unit)

    st.subheader("Executive Summary")
    metric_columns = st.columns(max(4 + len(summary_rows), 4))
    metric_columns[0].metric("Report Date", str(selected_date))
    metric_columns[1].metric("In Progress Projects", f"{len(in_progress):,}")
    metric_columns[2].metric("Completed Rows", f"{len(completed):,}")
    total_repair = amount_in_display_unit(selected_date_df["total_repair_amount"].sum(), display_unit)
    metric_columns[3].metric("Daily Repair Amount", f"{total_repair:,.2f} {unit}")

    for index, row in enumerate(summary_rows, start=4):
        if index >= len(metric_columns):
            break
        delta = row["delta"]
        metric_columns[index].metric(
            f"{row['production_type']} Ratio",
            f"{row['current_ratio']:.2%}",
            None if delta is None else f"{delta:+.2%}",
        )

    bullets: list[str] = []
    if not in_progress.empty:
        worst_active = in_progress.nlargest(1, "repair_ratio").iloc[0]
        bullets.append(
            "Highest in-progress repair ratio: "
            f"{worst_active['project_no']} / {worst_active['dimensions']} "
            f"at {worst_active['repair_ratio']:.2%}."
        )
    if summary_rows:
        biggest_move = max(summary_rows, key=lambda row: abs(row["delta"] or 0))
        if biggest_move["delta"] is not None:
            bullets.append(
                f"{biggest_move['production_type']} moved {biggest_move['delta']:+.2%} versus previous report day."
            )
    if bullets:
        for bullet in bullets:
            st.info(bullet)


def format_active_projects(df: pd.DataFrame, display_unit: str) -> pd.DataFrame:
    unit = unit_label(display_unit)
    columns = [
        "production_type",
        "project_status",
        "project_no",
        "dimensions",
        "qty",
        "total_repair_amount",
        "total_repair_amount_incl_skelp",
        "repair_ratio",
        "repair_ratio_incl_skelp",
    ]
    out = df[columns].copy()
    out["total_repair_amount"] = amount_in_display_unit(out["total_repair_amount"], display_unit)
    out["total_repair_amount_incl_skelp"] = amount_in_display_unit(out["total_repair_amount_incl_skelp"], display_unit)
    return out.rename(
        columns={
            "production_type": "Type",
            "project_status": "Status",
            "project_no": "Project",
            "dimensions": "Dimension",
            "qty": "Qty",
            "total_repair_amount": f"Repair Amount ({unit})",
            "total_repair_amount_incl_skelp": f"Repair Amount incl. Skelp ({unit})",
            "repair_ratio": "Repair Ratio",
            "repair_ratio_incl_skelp": "Repair Ratio incl. Skelp",
        }
    )


def project_selection_key(row) -> str:
    return f"{row['production_type']}||{row['project_no']}||{row['dimensions']}"


def project_selection_label(row) -> str:
    return f"{row['production_type']} | {row['project_no']} | {row['dimensions']}"


def add_selection_key(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        out["_selection_key"] = []
        return out
    out["_selection_key"] = (
        out["production_type"].astype(str)
        + "||"
        + out["project_no"].astype(str)
        + "||"
        + out["dimensions"].astype(str)
    )
    return out


def render_presentation_project_selector(
    selected_date_df: pd.DataFrame,
    filtered_to_selected_date: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = add_selection_key(selected_date_df)
    history = add_selection_key(filtered_to_selected_date)
    options = current["_selection_key"].tolist()
    labels = {
        row["_selection_key"]: project_selection_label(row)
        for _, row in current.iterrows()
    }
    default_keys = current.loc[current["project_status"].eq("In Progress"), "_selection_key"].tolist()
    if not default_keys:
        default_keys = options

    selected_keys = st.multiselect(
        "Projects for presentation",
        options=options,
        default=default_keys,
        format_func=lambda key: labels.get(key, key),
        help="Default selection is the projects currently In Progress on the selected date.",
    )
    if not selected_keys:
        st.warning("Select at least one project to build the presentation view.")
        return current.iloc[0:0].copy(), history.iloc[0:0].copy()

    return (
        current[current["_selection_key"].isin(selected_keys)].drop(columns=["_selection_key"], errors="ignore").copy(),
        history[history["_selection_key"].isin(selected_keys)].drop(columns=["_selection_key"], errors="ignore").copy(),
    )


def render_trend_window_control(filtered_to_selected_date: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    trend_available_dates = sorted(filtered_to_selected_date["date"].dt.date.unique())
    trend_window_size = min(20, len(trend_available_dates))
    trend_default_start_index = max(len(trend_available_dates) - trend_window_size, 0)
    trend_start_index = trend_default_start_index
    if len(trend_available_dates) > trend_window_size:
        trend_start_options = trend_available_dates[: len(trend_available_dates) - trend_window_size + 1]
        trend_start_date = st.select_slider(
            "Trend window start",
            options=trend_start_options,
            value=trend_start_options[trend_default_start_index],
            format_func=lambda value: value.strftime("%Y-%m-%d"),
            help="Controls both daily repair ratio trends and repair amount trend.",
        )
        trend_start_index = trend_available_dates.index(trend_start_date)
    trend_end_index = min(trend_start_index + trend_window_size, len(trend_available_dates))
    trend_window_dates = trend_available_dates[trend_start_index:trend_end_index]
    trend_df = filtered_to_selected_date[filtered_to_selected_date["date"].dt.date.isin(trend_window_dates)].copy()
    if trend_window_dates:
        st.caption(
            "Showing "
            f"{trend_window_dates[0].strftime('%Y-%m-%d')} to {trend_window_dates[-1].strftime('%Y-%m-%d')} "
            f"({len(trend_window_dates)} report days)."
        )
    return trend_df, trend_window_dates


def render_production_type_trends(trend_df: pd.DataFrame, baseline_for_filtered: pd.DataFrame) -> None:
    trend_types = [
        production_type
        for production_type in ["Coil", "Plate"]
        if production_type in set(trend_df["production_type"].dropna().astype(str))
    ]
    if not trend_types:
        trend_types = sorted(trend_df["production_type"].dropna().astype(str).unique().tolist())
    if len(trend_types) <= 1:
        for production_type in trend_types:
            st.plotly_chart(
                cached_chart_production_type_daily_trend(trend_df, production_type, baseline_for_filtered),
                use_container_width=True,
            )
    else:
        trend_columns = st.columns(len(trend_types))
        for column, production_type in zip(trend_columns, trend_types):
            with column:
                st.plotly_chart(
                    cached_chart_production_type_daily_trend(trend_df, production_type, baseline_for_filtered),
                    use_container_width=True,
                )


with st.sidebar:
    st.header("Import")
    uploaded = st.file_uploader("Daily Activity Excel", type=["xlsx"])
    backend = get_backend_name()
    if backend == "supabase":
        st.caption("Database: Supabase")
    else:
        st.caption(f"Database: SQLite ({DB_PATH})")
    if st.button("Refresh dashboard data"):
        refresh_cached_data()
        st.rerun()
    st.divider()
    st.header("Display")
    view_mode = st.radio(
        "Mode",
        ["Presentation Mode", "Tabbed Dashboard", "Classic Dashboard"],
        index=1,
    )
    display_unit = st.radio(
        "Unit",
        ["m", "ft"],
        index=0,
        format_func=lambda value: "Meter (m)" if value == "m" else "Feet (ft)",
        horizontal=True,
    )
    st.divider()
    st.header("Historical Baseline")
    from baseline import baseline_template_csv

    st.download_button(
        "Download baseline CSV template",
        data=baseline_template_csv(),
        file_name="historical_baseline_template.csv",
        mime="text/csv",
    )
    baseline_upload = st.file_uploader("Historical baseline CSV", type=["csv"])

if uploaded is not None:
    parsed_df, report = parse_daily_repair_rate(uploaded)
    uploaded.seek(0)
    project_pipe_df = pd.DataFrame()
    project_pipe_report = None
    if not parsed_df.empty and PIPE_ANALYSIS_AVAILABLE:
        project_pipe_df, project_pipe_report = parse_project_pipe_repairs(uploaded, parsed_df["date"].iloc[0])
    if not parsed_df.empty:
        existing_keys = get_existing_keys(parsed_df)
        report = mark_duplicate_counts(existing_keys, parsed_df, report)

    st.subheader("Validation Report")
    for name, ok in report.checks.items():
        st.write(("✅ " if ok else "❌ ") + name)

    c1, c2, c3 = st.columns(3)
    c1.metric("Import rows", report.import_rows)
    c2.metric("Update rows", report.update_rows)
    c3.metric("New rows", report.insert_rows)

    if report.errors:
        st.error("Import iptal edildi. Master database güncellenmedi.")
        for error in report.errors:
            st.error(error)
    else:
        st.success("Validation başarılı. Import için onay bekleniyor.")
        st.dataframe(format_preview(parsed_df, display_unit), use_container_width=True)
        if project_pipe_report is not None:
            st.subheader("Project Sheet Pipe-Level Preview")
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("Parsed pipe rows", project_pipe_report.parsed_rows)
            pc2.metric("Parsed project sheets", project_pipe_report.parsed_sheets)
            pc3.metric("Skipped blocks", project_pipe_report.skipped_blocks)
            for warning in project_pipe_report.warnings:
                st.warning(warning)
            if not project_pipe_df.empty:
                st.dataframe(project_pipe_df.head(100), use_container_width=True)
        if st.button("Confirm Import", type="primary"):
            try:
                affected = upsert_repair_rates(parsed_df)
                pipe_affected = 0
                if not project_pipe_df.empty:
                    try:
                        pipe_affected = upsert_pipe_repair_details(project_pipe_df)
                    except Exception as pipe_exc:
                        st.warning("Repair import tamamlandı; pipe-level kayıtlar yazılamadı.")
                        st.info("Supabase kullanıyorsanız supabase_pipe_repair_details.sql dosyasını SQL Editor'da çalıştırın.")
                        st.code(str(pipe_exc), language="text")
                refresh_cached_data()
                st.session_state.last_import_summary = {
                    "affected": affected,
                    "pipe_affected": pipe_affected,
                    "updated": report.update_rows,
                    "inserted": report.insert_rows,
                    "date": parsed_df["date"].iloc[0],
                }
                st.success(f"Import tamamlandı. {affected} repair satırı ve {pipe_affected} pipe-level kayıt işlendi.")
            except Exception as exc:
                st.error("Import sırasında database yazma hatası oluştu. Master data güncellenmedi.")
                st.info("Supabase kullanıyorsanız RLS insert/update policy veya service-role key ayarı gerekir.")
                st.code(str(exc), language="text")

if baseline_upload is not None:
    from baseline import parse_historical_baseline_csv

    baseline_df, baseline_errors = parse_historical_baseline_csv(baseline_upload)
    st.subheader("Historical Baseline Import")
    if baseline_errors:
        st.error("Historical baseline import iptal edildi.")
        for error in baseline_errors:
            st.error(error)
    else:
        st.dataframe(baseline_df, use_container_width=True)
        if st.button("Confirm Historical Baseline Import", type="primary"):
            try:
                affected = upsert_historical_baselines(baseline_df)
                refresh_cached_data()
                st.success(f"Historical baseline import tamamlandi. {affected} satir islendi.")
            except Exception as exc:
                st.error("Historical baseline database yazma hatasi olustu.")
                st.code(str(exc), language="text")

if st.session_state.last_import_summary:
    summary = st.session_state.last_import_summary
    st.success(
        "Son import: "
        f"{summary['date']} için {summary['affected']} satır işlendi "
        f"({summary['inserted']} yeni, {summary['updated']} update). "
        f"Pipe-level: {summary.get('pipe_affected', 0)}."
    )

st.divider()

try:
    master_df, baseline_master_df = load_dashboard_data(st.session_state.data_refresh_version)
except Exception as exc:
    st.error("Database bağlantısı kurulamadı veya Supabase tablosu hazır değil.")
    st.info("Supabase kullanıyorsanız önce SQL Editor içinde supabase_setup.sql dosyasındaki script'i çalıştırın.")
    st.code(str(exc), language="text")
    st.stop()
if not PIPE_ANALYSIS_AVAILABLE:
    st.warning(
        "Pipe-level analysis module is temporarily unavailable. "
        "The core dashboard and Excel import remain active."
    )
if master_df.empty:
    st.info("Dashboard için master database içinde veri yok. Önce geçerli bir Excel dosyası import edin.")
    st.stop()

if "production_type" not in master_df.columns:
    master_df["production_type"] = "Coil"
master_df["production_type"] = master_df["production_type"].fillna("Coil")

status_options = sorted(master_df["project_status"].dropna().unique())
default_status = [s for s in ["Completed", "In Progress"] if s in status_options] or status_options
type_options = sorted(master_df["production_type"].dropna().unique())
selected_status = st.multiselect("Status Filter", status_options, default=default_status)
selected_production_type = st.multiselect("Production Type Filter", type_options, default=type_options)
filtered = master_df[master_df["project_status"].isin(selected_status)] if selected_status else master_df
filtered = filtered[filtered["production_type"].isin(selected_production_type)] if selected_production_type else filtered
filtered = apply_meter_based_repair_ratios(filtered)

if filtered.empty:
    st.warning("Seçili filtrelerle veri bulunamadı.")
    st.stop()

available_dates = sorted(filtered["date"].dt.date.unique())
selected_date = st.selectbox("Date", available_dates, index=len(available_dates) - 1)
selected_date_df = filtered[filtered["date"].dt.date == selected_date].copy()
filtered_to_selected_date = filtered[filtered["date"].dt.date <= selected_date].copy()
baseline_for_filtered = baseline_master_df.copy()
if not baseline_for_filtered.empty:
    baseline_type_filter = selected_production_type or type_options
    baseline_for_filtered = baseline_for_filtered[
        baseline_for_filtered["reporting_year"].eq(selected_date.year)
        & baseline_for_filtered["production_type"].isin(baseline_type_filter)
        & baseline_for_filtered["include_in_dashboard"]
    ].copy()
try:
    selected_pipe_df = load_selected_date_pipe_data(st.session_state.data_refresh_version, selected_date)
except Exception as exc:
    st.warning("Pipe-level data could not be loaded for the selected date.")
    st.code(str(exc), language="text")
    selected_pipe_df = pd.DataFrame()

if view_mode == "Presentation Mode":
    presentation_date_df, presentation_history_df = render_presentation_project_selector(
        selected_date_df,
        filtered_to_selected_date,
    )
    if presentation_date_df.empty:
        st.stop()

    render_executive_summary(selected_date, presentation_date_df, presentation_history_df, display_unit)

    selected_in_progress = presentation_date_df[presentation_date_df["project_status"].eq("In Progress")].copy()
    st.subheader("Selected Projects")
    if presentation_date_df.empty:
        st.info("No selected projects for the selected date.")
    else:
        st.dataframe(
            format_active_projects(presentation_date_df.sort_values("repair_ratio", ascending=False), display_unit).style.format(
                {
                    "Qty": "{:,.0f}",
                    f"Repair Amount ({unit_label(display_unit)})": "{:,.2f}",
                    f"Repair Amount incl. Skelp ({unit_label(display_unit)})": "{:,.2f}",
                    "Repair Ratio": "{:.2%}",
                    "Repair Ratio incl. Skelp": "{:.2%}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        if not selected_in_progress.empty:
            st.caption(f"{len(selected_in_progress)} selected projects are currently In Progress.")

    st.subheader("Daily Repair Ratio Trend by Production Type")
    presentation_trend_df, _ = render_trend_window_control(presentation_history_df)
    render_production_type_trends(presentation_trend_df, pd.DataFrame())

    st.subheader("Repair Amount Trend")
    st.plotly_chart(cached_chart_repair_amount_trend(presentation_trend_df, display_unit), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.plotly_chart(cached_chart_worst_projects_today(presentation_date_df, selected_date), use_container_width=True)
    with right:
        st.plotly_chart(cached_chart_dimension_analysis(presentation_date_df), use_container_width=True)
    st.stop()

if view_mode == "Tabbed Dashboard":
    overview_tab, project_tab, dimension_tab, data_tab = st.tabs(
        ["Overview", "Project Deep Dive", "Dimension Analysis", "Data / Admin"]
    )

    with overview_tab:
        render_executive_summary(selected_date, selected_date_df, filtered, display_unit)
        st.subheader("Daily Repair Ratio Trend by Production Type")
        tab_trend_df, _ = render_trend_window_control(filtered_to_selected_date)
        render_production_type_trends(tab_trend_df, baseline_for_filtered)
        st.subheader("Repair Amount Trend")
        st.plotly_chart(cached_chart_repair_amount_trend(tab_trend_df, display_unit), use_container_width=True)
        left, right = st.columns(2)
        with left:
            st.plotly_chart(cached_chart_worst_projects_today(selected_date_df, selected_date), use_container_width=True)
        with right:
            st.plotly_chart(cached_chart_production_type_analysis(selected_date_df, baseline_for_filtered), use_container_width=True)

    with project_tab:
        active_projects = selected_date_df[selected_date_df["project_status"].eq("In Progress")].copy()
        st.subheader("In-Progress Projects")
        if active_projects.empty:
            st.info("No in-progress projects for the selected date.")
        else:
            st.dataframe(
                format_active_projects(active_projects.sort_values("repair_ratio", ascending=False), display_unit).style.format(
                    {
                        "Qty": "{:,.0f}",
                        f"Repair Amount ({unit_label(display_unit)})": "{:,.2f}",
                        f"Repair Amount incl. Skelp ({unit_label(display_unit)})": "{:,.2f}",
                        "Repair Ratio": "{:.2%}",
                        "Repair Ratio incl. Skelp": "{:.2%}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        projects = sorted(selected_date_df["project_no"].unique())
        selected_project_deep_dive = st.selectbox("Project", projects, key="tab_project_deep_dive")
        st.plotly_chart(
            cached_chart_project_trend(filtered_to_selected_date, selected_project_deep_dive),
            use_container_width=True,
        )
        project_rows = selected_date_df[selected_date_df["project_no"].eq(selected_project_deep_dive)].copy()
        st.dataframe(format_preview(project_rows, display_unit), use_container_width=True, hide_index=True)

    with dimension_tab:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(cached_chart_dimension_analysis(selected_date_df), use_container_width=True)
        with right:
            st.plotly_chart(cached_chart_skelp_impact_analysis(selected_date_df, display_unit), use_container_width=True)
        dimension_rows = (
            selected_date_df.groupby(["production_type", "dimensions"], as_index=False)
            .agg(
                projects=("project_no", "count"),
                repair_amount=("total_repair_amount", "sum"),
                repaired_spiral_length=("repaired_spiral_length", "sum"),
            )
            .sort_values("repair_amount", ascending=False)
        )
        denominator_m = dimension_rows["repaired_spiral_length"] * METERS_PER_FOOT
        dimension_rows["weighted_repair_ratio"] = (dimension_rows["repair_amount"] / denominator_m.where(denominator_m != 0)).fillna(0)
        dimension_rows["repair_amount"] = amount_in_display_unit(dimension_rows["repair_amount"], display_unit)
        st.dataframe(
            dimension_rows.rename(
                columns={
                    "production_type": "Type",
                    "dimensions": "Dimension",
                    "projects": "Rows",
                    "repair_amount": f"Repair Amount ({unit_label(display_unit)})",
                    "weighted_repair_ratio": "Weighted Repair Ratio",
                }
            ).style.format(
                {
                    "Rows": "{:,.0f}",
                    f"Repair Amount ({unit_label(display_unit)})": "{:,.2f}",
                    "Weighted Repair Ratio": "{:.2%}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with data_tab:
        st.download_button(
            "Download Selected Date CSV",
            data=format_preview(selected_date_df, display_unit).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"daily_repair_rate_archive_{selected_date}_{display_unit}.csv",
            mime="text/csv",
        )
        if st.button("Generate Selected Date A3 PDF Report", key="tab_generate_a3_pdf"):
            with st.spinner("A3 PDF report hazirlaniyor..."):
                st.session_state.pdf_report = build_a3_pdf_report(
                    filtered_to_selected_date,
                    selected_date,
                    selected_status,
                    baseline_for_filtered,
                    display_unit,
                )
                st.session_state.pdf_report_name = f"daily_repair_rate_report_{selected_date}.pdf"
        if st.session_state.pdf_report:
            st.download_button(
                "Download Selected Date A3 PDF Report",
                data=st.session_state.pdf_report,
                file_name=st.session_state.pdf_report_name,
                mime="application/pdf",
                key="tab_download_a3_pdf",
            )
        with st.expander("Master data"):
            st.dataframe(format_preview(filtered, display_unit), use_container_width=True)
    st.stop()

if "production_type" in selected_date_df.columns and not selected_date_df.empty:
    st.subheader("Production Type KPIs")
    production_type_source = pd.concat(
        [selected_date_df, baseline_for_filtered],
        ignore_index=True,
        sort=False,
    )
    type_summary = (
        production_type_source.groupby("production_type", as_index=False)
        .agg(
            projects=("project_no", "count"),
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
            repaired_spiral_length=("repaired_spiral_length", "sum"),
        )
        .sort_values("production_type")
    )
    type_cols = st.columns(len(type_summary))
    for col, (_, row) in zip(type_cols, type_summary.iterrows()):
        denominator_m = row["repaired_spiral_length"] * METERS_PER_FOOT
        weighted_ratio = row["total_repair_amount"] / denominator_m if denominator_m else 0
        skelp_impact = (row["total_repair_amount_incl_skelp"] - row["total_repair_amount"]) / denominator_m if denominator_m else 0
        col.metric(
            f"{row['production_type']} Repair Ratio",
            f"{weighted_ratio:.2%}",
            f"Skelp impact +{skelp_impact:.2%}",
        )
        col.caption(
            f"{int(row['projects'])} rows | "
            f"{amount_in_display_unit(row['total_repair_amount'], display_unit):,.2f} {unit_label(display_unit)} repair"
        )

st.download_button(
    "Download Selected Date CSV",
    data=format_preview(selected_date_df, display_unit).to_csv(index=False).encode("utf-8-sig"),
    file_name=f"daily_repair_rate_archive_{selected_date}_{display_unit}.csv",
    mime="text/csv",
)

if st.button("Generate Selected Date A3 PDF Report"):
    with st.spinner("A3 PDF report hazırlanıyor..."):
        st.session_state.pdf_report = build_a3_pdf_report(filtered_to_selected_date, selected_date, selected_status, baseline_for_filtered, display_unit)
        st.session_state.pdf_report_name = f"daily_repair_rate_report_{selected_date}.pdf"

if st.session_state.pdf_report:
    st.download_button(
        "Download Selected Date A3 PDF Report",
        data=st.session_state.pdf_report,
        file_name=st.session_state.pdf_report_name,
        mime="application/pdf",
    )

st.subheader("Daily Repair Ratio Trend by Production Type")
trend_filtered_to_selected_date, _ = render_trend_window_control(filtered_to_selected_date)
render_production_type_trends(trend_filtered_to_selected_date, baseline_for_filtered)
if baseline_for_filtered.empty:
    st.caption("Historical baseline is not loaded.")
else:
    st.caption(f"Historical baseline included in production-type weighted ratios: {len(baseline_for_filtered)} projects")

st.subheader("Repair Amount Trend")
st.caption("Uses the same selected trend window shown above.")
st.plotly_chart(cached_chart_repair_amount_trend(trend_filtered_to_selected_date, display_unit), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(cached_chart_worst_projects_today(selected_date_df, selected_date), use_container_width=True)
with right:
    projects = sorted(selected_date_df["project_no"].unique())
    selected_project = st.selectbox("Project", projects)
    st.plotly_chart(cached_chart_project_trend(filtered_to_selected_date, selected_project), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(
        cached_chart_production_type_analysis(selected_date_df, baseline_for_filtered),
        use_container_width=True,
    )
with right:
    st.plotly_chart(cached_chart_dimension_analysis(selected_date_df), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(cached_chart_status_comparison(selected_date_df, display_unit), use_container_width=True)
with right:
    st.plotly_chart(cached_chart_historical_benchmark_comparison(selected_date_df, baseline_for_filtered), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(cached_chart_skelp_impact_analysis(selected_date_df, display_unit), use_container_width=True)
with right:
    st.plotly_chart(cached_chart_repair_amount_pareto(selected_date_df, display_unit), use_container_width=True)

if not selected_pipe_df.empty and PIPE_ANALYSIS_AVAILABLE:
    reconciled_projects = cached_reconciled_projects(selected_date_df, selected_pipe_df)
    st.subheader("Project Pipe Analysis")
    if reconciled_projects.empty:
        st.warning(
            "Pipe-level totals do not uniquely reconcile with the selected date project totals. "
            "Project Pareto charts were not generated."
        )
    else:
        project_labels = {
            row["project_sheet"]: f"{row['project_no']} | {row['dimensions']}"
            for _, row in reconciled_projects.iterrows()
        }
        selected_sheet = st.selectbox(
            "Pipe Analysis Project",
            reconciled_projects["project_sheet"].tolist(),
            format_func=lambda sheet: project_labels[sheet],
        )
        reconciliation = reconciled_projects[
            reconciled_projects["project_sheet"].eq(selected_sheet)
        ].iloc[0]
        project_no = str(reconciliation["project_no"])
        dimensions = str(reconciliation["dimensions"])
        project_pipe_df = selected_pipe_df[
            selected_pipe_df["project_sheet"].eq(selected_sheet)
        ].copy()
        project_unit = unit_label(display_unit)
        pipe_total_display = amount_in_display_unit(
            reconciliation["pipe_repair_amount"],
            display_unit,
        )
        master_total_display = amount_in_display_unit(
            reconciliation["expected_repair_amount"],
            display_unit,
        )
        difference_display = amount_in_display_unit(
            reconciliation["difference_m"],
            display_unit,
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Pipe Rows", int(reconciliation["pipe_rows"]))
        k2.metric("Pipe Repair Total", f"{pipe_total_display:,.2f} {project_unit}")
        k3.metric("Master Repair Total", f"{master_total_display:,.2f} {project_unit}")
        k4.metric("Joint Count Coverage", f"{reconciliation['joint_count_coverage']:.0%}")
        st.success(
            "Reconciliation passed. "
            f"Difference: {difference_display:+.4f} {project_unit}."
        )
        project_group_config_key = f"{selected_sheet}|{project_no}|{dimensions}"
        if st.session_state.project_group_config_key != project_group_config_key:
            try:
                saved_config = cached_project_group_config(
                    st.session_state.data_refresh_version,
                    selected_sheet,
                    project_no,
                    dimensions,
                )
            except Exception as config_exc:
                saved_config = None
                st.warning(
                    "Saved group settings could not be loaded. "
                    "If this is the first run after the update, run supabase_project_group_configs.sql in Supabase SQL Editor."
                )
                st.code(str(config_exc), language="text")
            st.session_state.pipe_group_spec_input = (saved_config or {}).get("pipe_groups", "")
            st.session_state.machine_group_spec_input = (saved_config or {}).get("machine_groups", "")
            st.session_state.project_group_config_key = project_group_config_key

        pipe_group_spec = st.text_input(
            "Pipe Groups",
            help=(
                "Leave blank to show all pipes together. Format: 1-18; 19-49. "
                "Optional labels are supported, for example: Group 1:1-18; Group 2:19-49."
            ),
            key="pipe_group_spec_input",
        )
        machine_pipe_df = pd.DataFrame()
        machine_compare_df = pd.DataFrame()
        if pipe_group_spec.strip():
            parsed_ranges, range_errors = parse_pipe_group_ranges(pipe_group_spec)
            if range_errors:
                for error in range_errors:
                    st.error(error)
                machine_pipe_df = pd.DataFrame()
            else:
                machine_pipe_df, range_warnings = assign_pipe_groups(project_pipe_df, parsed_ranges)
                for warning in range_warnings:
                    st.warning(warning)
        else:
            machine_pipe_df = assign_all_pipes_group(project_pipe_df)

        if machine_pipe_df.empty:
            st.warning("No pipe rows matched the entered pipe groups.")
        else:
            comparison_summary = (
                machine_pipe_df.groupby("pipe_group", as_index=False)
                .agg(
                    **{
                        "Sort": ("pipe_group_order", "min"),
                        "Pipe Count": ("pipe_no_numeric", "count"),
                        "Avg Repair Ratio": ("repair_ratio", "mean"),
                        "Max Repair Ratio": ("repair_ratio", "max"),
                        f"Total Repair Amount ({project_unit})": (
                            "repair_amount",
                            lambda series: amount_in_display_unit(series.sum(), display_unit),
                        ),
                    }
                )
                .rename(columns={"pipe_group": "Pipe Group"})
                .sort_values("Sort")
                .drop(columns=["Sort"])
            )
            st.dataframe(
                comparison_summary.style.format(
                    {
                        "Pipe Count": "{:,.0f}",
                        "Avg Repair Ratio": "{:.2%}",
                        "Max Repair Ratio": "{:.2%}",
                        f"Total Repair Amount ({project_unit})": "{:,.2f}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            left, right = st.columns(2)
            with left:
                st.plotly_chart(
                    cached_chart_pipe_group_repair_ratio_trend(
                        machine_pipe_df,
                        "pipe_group",
                        display_unit,
                    ),
                    use_container_width=True,
                )
            with right:
                st.plotly_chart(
                    cached_chart_pipe_group_comparison(
                        machine_pipe_df,
                        "pipe_group",
                        display_unit,
                    ),
                    use_container_width=True,
                )

        machine_group_spec = st.text_input(
            "Machine Groups (Optional)",
            help="Optional machine comparison. Format: A:1-10,26-34; B:11-25.",
            key="machine_group_spec_input",
        )
        with st.expander("Machine group format info"):
            st.markdown(
                """
Use this field only when you want to compare repair ratios by machine.

Format:
```text
A:1-10,26-34; B:11-25
```

Rules:
- Put `:` after the machine name.
- Use `,` between multiple pipe intervals for the same machine.
- Use `;` between different machines.
- Leave this field blank if you do not want a machine comparison chart.

Examples:
```text
A:1-18; B:19-49
B:1-18; A:19-30; B:31-49
A:1-10,26-34; B:11-25
```
                """
            )
        if st.button("Save group settings"):
            try:
                upsert_project_group_config(
                    selected_sheet,
                    project_no,
                    dimensions,
                    st.session_state.pipe_group_spec_input,
                    st.session_state.machine_group_spec_input,
                )
                refresh_cached_data()
                st.success("Group settings saved for this project.")
            except Exception as save_exc:
                st.error("Group settings could not be saved.")
                st.info("If Supabase is missing the table, run supabase_project_group_configs.sql in SQL Editor.")
                st.code(str(save_exc), language="text")

        if machine_group_spec.strip():
            machine_ranges, machine_errors = parse_pipe_group_ranges(machine_group_spec)
            if machine_errors:
                for error in machine_errors:
                    st.error(error)
            else:
                machine_compare_df, machine_warnings = assign_pipe_groups(project_pipe_df, machine_ranges)
                for warning in machine_warnings:
                    st.warning(warning)
                if machine_compare_df.empty:
                    st.warning("No pipe rows matched the entered machine groups.")
                else:
                    machine_summary = (
                        machine_compare_df.groupby("pipe_group", as_index=False)
                        .agg(
                            **{
                                "Sort": ("pipe_group_order", "min"),
                                "Pipe Count": ("pipe_no_numeric", "count"),
                                "Avg Repair Ratio": ("repair_ratio", "mean"),
                                "Max Repair Ratio": ("repair_ratio", "max"),
                                f"Total Repair Amount ({project_unit})": (
                                    "repair_amount",
                                    lambda series: amount_in_display_unit(series.sum(), display_unit),
                                ),
                            }
                        )
                        .rename(columns={"pipe_group": "Machine"})
                        .sort_values("Sort")
                        .drop(columns=["Sort"])
                    )
                    st.dataframe(
                        machine_summary.style.format(
                            {
                                "Pipe Count": "{:,.0f}",
                                "Avg Repair Ratio": "{:.2%}",
                                "Max Repair Ratio": "{:.2%}",
                                f"Total Repair Amount ({project_unit})": "{:,.2f}",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    left, right = st.columns(2)
                    with left:
                        st.plotly_chart(
                            cached_chart_pipe_group_repair_ratio_trend(
                                machine_compare_df,
                                "pipe_group",
                                display_unit,
                                group_title="Machine",
                            ),
                            use_container_width=True,
                        )
                    with right:
                        st.plotly_chart(
                            cached_chart_pipe_group_comparison(
                                machine_compare_df,
                                "pipe_group",
                                display_unit,
                                group_title="Machine",
                            ),
                            use_container_width=True,
                        )

        project_report_key = f"{selected_date}|{selected_sheet}|{display_unit}|{pipe_group_spec}|{machine_group_spec}"
        if st.button("Generate Selected Project A3 PDF Report"):
            with st.spinner("Preparing project PDF report..."):
                st.session_state.project_pdf_report = build_project_pipe_pdf_report(
                    project_pipe_df,
                    reconciliation,
                    selected_date,
                    display_unit,
                    pipe_group_df=machine_pipe_df,
                    machine_group_df=machine_compare_df,
                )
                safe_project = "".join(
                    char if char.isalnum() or char in "-_" else "_"
                    for char in str(reconciliation["project_no"])
                ).strip("_")
                st.session_state.project_pdf_report_name = (
                    f"project_pipe_analysis_{safe_project}_{selected_date}.pdf"
                )
                st.session_state.project_pdf_report_key = project_report_key
        if (
            st.session_state.project_pdf_report
            and st.session_state.project_pdf_report_key == project_report_key
        ):
            st.download_button(
                "Download Selected Project A3 PDF Report",
                data=st.session_state.project_pdf_report,
                file_name=st.session_state.project_pdf_report_name,
                mime="application/pdf",
            )

        left, right = st.columns(2)
        with left:
            st.plotly_chart(
                cached_chart_pipe_repair_amount_pareto(project_pipe_df, display_unit),
                use_container_width=True,
            )
        with right:
            st.plotly_chart(
                cached_chart_pipe_worst_ratio(project_pipe_df, display_unit),
                use_container_width=True,
            )
        left, right = st.columns(2)
        with left:
            st.plotly_chart(
                cached_chart_pipe_joint_count_distribution(project_pipe_df, display_unit),
                use_container_width=True,
            )
        with right:
            st.plotly_chart(
                cached_chart_pipe_joint_count_vs_repair(project_pipe_df, display_unit),
                use_container_width=True,
            )

        critical_pipes = (
            project_pipe_df.nlargest(15, ["repair_amount", "repair_ratio"])[
                ["pipe_no", "repair_amount", "repair_ratio", "repair_count", "surface_state"]
            ]
            .assign(
                repair_amount=lambda frame: amount_in_display_unit(
                    frame["repair_amount"],
                    display_unit,
                )
            )
            .rename(
                columns={
                    "pipe_no": "Pipe No.",
                    "repair_amount": f"Repair Amount ({project_unit})",
                    "repair_ratio": "Repair Ratio",
                    "repair_count": "Band Joint Count",
                    "surface_state": "Surface State",
                }
            )
        )
        st.dataframe(
            critical_pipes.style.format(
                {f"Repair Amount ({project_unit})": "{:,.3f}", "Repair Ratio": "{:.2%}"}
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Dimension Pipe Analysis")
        dimension_options = sorted(reconciled_projects["dimensions"].dropna().astype(str).unique().tolist())
        if not dimension_options:
            st.info("No reconciled dimensions are available for dimension-level pipe analysis.")
        else:
            selected_dimension_for_pipe = st.selectbox(
                "Dimension",
                dimension_options,
                key="dimension_pipe_analysis_dimension",
            )
            dimension_projects = reconciled_projects[
                reconciled_projects["dimensions"].astype(str).eq(selected_dimension_for_pipe)
            ].copy()
            dimension_project_labels = {
                row["project_sheet"]: f"{row['project_no']} | {row['project_sheet']}"
                for _, row in dimension_projects.iterrows()
            }
            selected_dimension_sheets = st.multiselect(
                "Projects in selected dimension",
                dimension_projects["project_sheet"].tolist(),
                default=dimension_projects["project_sheet"].tolist(),
                format_func=lambda sheet: dimension_project_labels.get(sheet, sheet),
            )
            if not selected_dimension_sheets:
                st.info("Select at least one project for dimension pipe analysis.")
            else:
                selected_dimension_projects = dimension_projects[
                    dimension_projects["project_sheet"].isin(selected_dimension_sheets)
                ].copy()
                dimension_pipe_df = cached_dimension_pipe_frame(
                    selected_pipe_df,
                    reconciled_projects,
                    tuple(selected_dimension_sheets),
                )
                if dimension_pipe_df.empty:
                    st.warning("No pipe-level rows were found for the selected dimension/project combination.")
                else:
                    dimension_unit = unit_label(display_unit)
                    d1, d2, d3, d4 = st.columns(4)
                    d1.metric("Projects", f"{selected_dimension_projects['project_no'].nunique():,}")
                    d2.metric("Pipe Rows", f"{len(dimension_pipe_df):,}")
                    d3.metric(
                        "Avg Repair Ratio",
                        f"{dimension_pipe_df['repair_ratio'].mean():.2%}",
                    )
                    d4.metric(
                        "Total Repair Amount",
                        f"{amount_in_display_unit(dimension_pipe_df['repair_amount'].sum(), display_unit):,.2f} {dimension_unit}",
                    )

                    control_left, control_right = st.columns(2)
                    with control_left:
                        dimension_worst_top_n = st.selectbox(
                            "Worst pipes shown",
                            [10, 15, 20, 30],
                            index=1,
                            key="dimension_worst_pipe_count",
                        )
                    with control_right:
                        dimension_bin_size = st.selectbox(
                            "Trend interval size",
                            [1, 5, 10, 15, 20],
                            index=2,
                            key="dimension_pipe_bin_size",
                        )

                    left, right = st.columns(2)
                    with left:
                        st.plotly_chart(
                            cached_chart_dimension_project_comparison(dimension_pipe_df, display_unit),
                            use_container_width=True,
                        )
                    with right:
                        st.plotly_chart(
                            cached_chart_dimension_worst_pipes(dimension_pipe_df, display_unit, dimension_worst_top_n),
                            use_container_width=True,
                        )

                    dimension_pipe_groups_df, dimension_pipe_group_warnings = cached_apply_project_saved_groups(
                        st.session_state.data_refresh_version,
                        dimension_pipe_df,
                        selected_dimension_projects,
                        "pipe_groups",
                        "All Pipes",
                        prefix_project=True,
                        fallback_when_missing=True,
                    )
                    for warning in dimension_pipe_group_warnings:
                        st.warning(warning)
                    if not dimension_pipe_groups_df.empty:
                        st.markdown("**Saved Pipe Group Comparison**")
                        st.dataframe(
                            pipe_group_style(
                                summarize_pipe_groups(dimension_pipe_groups_df, "Pipe Group", display_unit),
                                display_unit,
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                        left, right = st.columns(2)
                        with left:
                            st.plotly_chart(
                                cached_chart_pipe_group_binned_trend(
                                    dimension_pipe_groups_df,
                                    "pipe_group",
                                    display_unit,
                                    group_title="Pipe Group",
                                    bin_size=dimension_bin_size,
                                ),
                                use_container_width=True,
                            )
                        with right:
                            st.plotly_chart(
                                cached_chart_pipe_group_comparison(
                                    dimension_pipe_groups_df,
                                    "pipe_group",
                                    display_unit,
                                    group_title="Pipe Group",
                                ),
                                use_container_width=True,
                            )

                    dimension_machine_groups_df, dimension_machine_group_warnings = cached_apply_project_saved_groups(
                        st.session_state.data_refresh_version,
                        dimension_pipe_df,
                        selected_dimension_projects,
                        "machine_groups",
                        "All Pipes",
                        prefix_project=False,
                        fallback_when_missing=False,
                    )
                    for warning in dimension_machine_group_warnings:
                        st.info(warning)
                    if dimension_machine_groups_df.empty:
                        st.info(
                            "Saved machine groups were not found for the selected projects. "
                            "Save machine groups in Project Pipe Analysis first to enable dimension-level machine comparison."
                        )
                    else:
                        st.markdown("**Saved Machine Comparison**")
                        st.dataframe(
                            pipe_group_style(
                                summarize_pipe_groups(dimension_machine_groups_df, "Machine", display_unit),
                                display_unit,
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                        left, right = st.columns(2)
                        with left:
                            st.plotly_chart(
                                cached_chart_pipe_group_binned_trend(
                                    dimension_machine_groups_df,
                                    "pipe_group",
                                    display_unit,
                                    group_title="Machine",
                                    bin_size=dimension_bin_size,
                                ),
                                use_container_width=True,
                            )
                        with right:
                            st.plotly_chart(
                                cached_chart_pipe_group_comparison(
                                    dimension_machine_groups_df,
                                    "pipe_group",
                                    display_unit,
                                    group_title="Machine",
                                ),
                                use_container_width=True,
                            )

                    dimension_report_key = (
                        f"{selected_date}|{selected_dimension_for_pipe}|{display_unit}|"
                        f"{','.join(selected_dimension_sheets)}|{dimension_worst_top_n}|{dimension_bin_size}"
                    )
                    if st.button("Generate Dimension A3 PDF Report"):
                        with st.spinner("Preparing dimension PDF report..."):
                            st.session_state.dimension_pdf_report = build_dimension_pipe_pdf_report(
                                dimension_pipe_df,
                                selected_dimension_for_pipe,
                                selected_dimension_projects,
                                selected_date,
                                display_unit,
                                worst_top_n=dimension_worst_top_n,
                                bin_size=dimension_bin_size,
                                pipe_group_df=dimension_pipe_groups_df,
                                machine_group_df=dimension_machine_groups_df,
                            )
                            safe_dimension = "".join(
                                char if char.isalnum() or char in "-_" else "_"
                                for char in str(selected_dimension_for_pipe)
                            ).strip("_")
                            st.session_state.dimension_pdf_report_name = (
                                f"dimension_pipe_analysis_{safe_dimension}_{selected_date}.pdf"
                            )
                            st.session_state.dimension_pdf_report_key = dimension_report_key
                    if (
                        st.session_state.dimension_pdf_report
                        and st.session_state.dimension_pdf_report_key == dimension_report_key
                    ):
                        st.download_button(
                            "Download Dimension A3 PDF Report",
                            data=st.session_state.dimension_pdf_report,
                            file_name=st.session_state.dimension_pdf_report_name,
                            mime="application/pdf",
                        )
else:
    st.info("Pipe-level project sheet data is not loaded for the selected date.")

with st.expander("Master data"):
    st.dataframe(format_preview(filtered, display_unit), use_container_width=True)
