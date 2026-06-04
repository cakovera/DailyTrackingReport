from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from calculations import amount_in_display_unit, apply_meter_based_repair_ratios, daily_weighted_repair_ratios, unit_label

STATUS_COLORS = {
    "Completed": "#16a34a",
    "In Progress": "#f97316",
}


def _pct_axis(fig):
    fig.update_yaxes(tickformat=".2%")
    return fig


def overall_daily_trend(df: pd.DataFrame, baseline_df: pd.DataFrame | None = None):
    grouped = daily_weighted_repair_ratios(df, baseline_df)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=grouped["date"],
            y=grouped["weighted_repair_ratio"],
            name="Repair Ratio",
            mode="lines+markers",
            line={"color": "#2563eb", "width": 4},
            marker={"size": 9},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=grouped["date"],
            y=grouped["weighted_repair_ratio_incl_skelp"],
            name="Repair Ratio incl. Skelp",
            mode="lines+markers",
            line={"color": "#dc2626", "width": 4},
            marker={"size": 9},
        )
    )
    fig.update_layout(title="Overall Daily Repair Ratio Trend", xaxis_title="Date", yaxis_title="Weighted Ratio")
    fig.update_xaxes(tickformat="%Y-%m-%d")
    return _pct_axis(fig)


def worst_projects_today(df: pd.DataFrame, selected_date):
    daily = apply_meter_based_repair_ratios(df[df["date"].dt.date == selected_date]).nlargest(10, "repair_ratio").copy()
    daily["project_dimension"] = daily["project_no"] + " | " + daily["dimensions"]
    fig = px.bar(
        daily,
        x="repair_ratio",
        y="project_dimension",
        color="project_status",
        color_discrete_map=STATUS_COLORS,
        orientation="h",
        title="Worst Projects Today",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Repair Ratio", yaxis_title="Project / Dimension")
    fig.update_xaxes(tickformat=".2%")
    return fig


def project_trend(df: pd.DataFrame, project_no: str):
    data = apply_meter_based_repair_ratios(df[df["project_no"] == project_no]).sort_values("date")
    fig = px.line(
        data,
        x="date",
        y=["repair_ratio", "repair_ratio_incl_skelp"],
        markers=True,
        title="Project Trend",
        color_discrete_sequence=["#2563eb", "#dc2626"],
    )
    fig.update_traces(line={"width": 4}, marker={"size": 9})
    fig.update_layout(xaxis_title="Date", yaxis_title="Repair Ratio")
    fig.update_xaxes(tickformat="%Y-%m-%d")
    return _pct_axis(fig)


def dimension_analysis(df: pd.DataFrame):
    data = apply_meter_based_repair_ratios(df)
    grouped = data.groupby("dimensions", as_index=False)["repair_ratio"].mean().sort_values("repair_ratio", ascending=False)
    fig = px.bar(grouped, x="dimensions", y="repair_ratio", title="Dimension Analysis", color="repair_ratio", color_continuous_scale="Turbo")
    fig.update_layout(xaxis_title="Dimension", yaxis_title="Average Repair Ratio")
    fig.update_yaxes(tickformat=".2%")
    fig.update_traces(hovertemplate="Dimension: %{x}<br>Average Repair Ratio: %{y:.2%}<extra></extra>")
    return fig


def repair_amount_trend(df: pd.DataFrame, display_unit: str = "m"):
    grouped = (
        df.groupby("date", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
        )
        .sort_values("date")
    )
    unit = unit_label(display_unit)
    grouped["total_repair_amount_display"] = amount_in_display_unit(grouped["total_repair_amount"], display_unit)
    grouped["daily_repair_amount_display"] = grouped["total_repair_amount_display"].diff()
    grouped["daily_repair_amount_display"] = grouped["daily_repair_amount_display"].fillna(grouped["total_repair_amount_display"])

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=grouped["date"],
            y=grouped["daily_repair_amount_display"],
            name="Daily Repair Amount",
            marker_color="#a78bfa",
            opacity=0.72,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=grouped["date"],
            y=grouped["total_repair_amount_display"],
            name="Total Repair Amount",
            mode="lines+markers",
            line={"color": "#7c3aed", "width": 4},
            marker={"size": 9},
        )
    )
    fig.update_layout(
        title=f"Repair Amount Trend ({unit})",
        xaxis_title="Date",
        yaxis_title=f"Repair Amount ({unit})",
        legend_title_text="",
    )
    fig.update_xaxes(tickformat="%Y-%m-%d")
    return fig
