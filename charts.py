from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


STATUS_COLORS = {
    "Completed": "#16a34a",
    "In Progress": "#f97316",
}


def _pct_axis(fig):
    fig.update_yaxes(tickformat=".2%")
    return fig


def overall_daily_trend(df: pd.DataFrame):
    grouped = (
        df.groupby("date", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
            project_total_pipe_length=("project_total_pipe_length", "sum"),
        )
        .sort_values("date")
    )
    grouped["weighted_repair_ratio"] = grouped["total_repair_amount"] / grouped["project_total_pipe_length"]
    grouped["weighted_repair_ratio_incl_skelp"] = (
        grouped["total_repair_amount_incl_skelp"] / grouped["project_total_pipe_length"]
    )
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
    daily = df[df["date"].dt.date == selected_date].nlargest(10, "repair_ratio")
    fig = px.bar(
        daily,
        x="repair_ratio",
        y="project_no",
        color="project_status",
        color_discrete_map=STATUS_COLORS,
        orientation="h",
        title="Worst Projects Today",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Repair Ratio", yaxis_title="Project No.")
    fig.update_xaxes(tickformat=".2%")
    return fig


def project_trend(df: pd.DataFrame, project_no: str):
    data = df[df["project_no"] == project_no].sort_values("date")
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
    grouped = df.groupby("dimensions", as_index=False)["repair_ratio"].mean().sort_values("repair_ratio", ascending=False)
    fig = px.bar(grouped, x="dimensions", y="repair_ratio", title="Dimension Analysis", color="repair_ratio", color_continuous_scale="Turbo")
    fig.update_layout(xaxis_title="Dimension", yaxis_title="Average Repair Ratio")
    fig.update_yaxes(tickformat=".2%")
    fig.update_traces(hovertemplate="Dimension: %{x}<br>Average Repair Ratio: %{y:.2%}<extra></extra>")
    return fig


def repair_amount_trend(df: pd.DataFrame):
    grouped = (
        df.groupby("date", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
        )
        .sort_values("date")
    )
    fig = px.line(
        grouped,
        x="date",
        y=["total_repair_amount", "total_repair_amount_incl_skelp"],
        markers=True,
        title="Repair Amount Trend",
        color_discrete_sequence=["#7c3aed", "#ea580c"],
    )
    fig.update_traces(line={"width": 4}, marker={"size": 9})
    fig.update_layout(xaxis_title="Date", yaxis_title="Total Repair Amount")
    fig.update_xaxes(tickformat="%Y-%m-%d")
    return fig
