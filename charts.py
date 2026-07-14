from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from calculations import (
    METERS_PER_FOOT,
    amount_in_display_unit,
    apply_meter_based_repair_ratios,
    daily_weighted_repair_ratios,
    daily_weighted_repair_ratios_for_type,
    repair_amount_trend_data,
    unit_label,
)

STATUS_COLORS = {
    "Completed": "#16a34a",
    "In Progress": "#f97316",
}

DAILY_REPAIR_VISUAL_SCALE = 100


def _label_every_third_and_last(length: int) -> list[bool]:
    labels = [(index % 3 == 0) or (index == length - 1) for index in range(length)]
    if length >= 2 and labels[-2]:
        labels[-2] = False
    return labels


def _pct_axis(fig):
    fig.update_yaxes(tickformat=".2%")
    return fig


def _daily_repair_ratio_trend_figure(grouped: pd.DataFrame, title: str):
    label_mask = _label_every_third_and_last(len(grouped))
    ratio_labels = [
        f"{value:.2%}" if show_label else ""
        for value, show_label in zip(grouped["weighted_repair_ratio"], label_mask)
    ]
    ratio_incl_labels = [
        f"{value:.2%}" if show_label else ""
        for value, show_label in zip(grouped["weighted_repair_ratio_incl_skelp"], label_mask)
    ]
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
    for date_value, ratio_value, label in zip(grouped["date"], grouped["weighted_repair_ratio"], ratio_labels):
        if label:
            fig.add_annotation(
                x=date_value,
                y=ratio_value,
                text=label,
                showarrow=False,
                yshift=18,
                font={"color": "#2563eb", "size": 12},
                bgcolor="rgba(255,255,255,0.86)",
                bordercolor="#2563eb",
                borderwidth=1,
                borderpad=2,
            )
    for date_value, ratio_value, label in zip(
        grouped["date"],
        grouped["weighted_repair_ratio_incl_skelp"],
        ratio_incl_labels,
    ):
        if label:
            fig.add_annotation(
                x=date_value,
                y=ratio_value,
                text=label,
                showarrow=False,
                yshift=-24,
                font={"color": "#dc2626", "size": 12},
                bgcolor="rgba(255,255,255,0.86)",
                bordercolor="#dc2626",
                borderwidth=1,
                borderpad=2,
            )
    if not grouped.empty:
        latest = grouped.iloc[-1]
        fig.add_trace(
            go.Scatter(
                x=[latest["date"]],
                y=[latest["weighted_repair_ratio"]],
                name="Latest Repair Ratio",
                mode="markers",
                marker={"size": 15, "color": "#facc15", "line": {"color": "#111827", "width": 2}},
                showlegend=False,
                hovertemplate="Latest Repair Ratio: %{y:.2%}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[latest["date"]],
                y=[latest["weighted_repair_ratio_incl_skelp"]],
                name="Latest Repair Ratio incl. Skelp",
                mode="markers",
                marker={"size": 15, "color": "#fb923c", "line": {"color": "#111827", "width": 2}},
                showlegend=False,
                hovertemplate="Latest Repair Ratio incl. Skelp: %{y:.2%}<extra></extra>",
            )
        )
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Weighted Ratio",
        legend_title_text="",
        hovermode="x unified",
    )
    fig.update_xaxes(tickformat="%Y-%m-%d")
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:.2%}<extra></extra>")
    return _pct_axis(fig)


def overall_daily_trend(df: pd.DataFrame, baseline_df: pd.DataFrame | None = None):
    grouped = daily_weighted_repair_ratios(df, baseline_df)
    return _daily_repair_ratio_trend_figure(grouped, "Overall Daily Repair Ratio Trend")


def production_type_daily_trend(
    df: pd.DataFrame,
    production_type: str,
    baseline_df: pd.DataFrame | None = None,
):
    grouped = daily_weighted_repair_ratios_for_type(df, production_type, baseline_df)
    return _daily_repair_ratio_trend_figure(grouped, f"{production_type} Daily Repair Ratio Trend")


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
        title="Highest Repair Ratio Projects",
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


def production_type_analysis(df: pd.DataFrame, baseline_df: pd.DataFrame | None = None):
    data = df.copy()
    if "production_type" not in data.columns:
        data["production_type"] = "Coil"
    if baseline_df is not None and not baseline_df.empty:
        data = pd.concat([data, baseline_df], ignore_index=True, sort=False)
    data = apply_meter_based_repair_ratios(data)
    grouped = (
        data.groupby("production_type", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
            repaired_spiral_length=("repaired_spiral_length", "sum"),
        )
        .sort_values("production_type")
    )
    denominator_m = grouped["repaired_spiral_length"] * METERS_PER_FOOT
    denominator_m = denominator_m.where(denominator_m != 0)
    grouped["repair_ratio"] = (grouped["total_repair_amount"] / denominator_m).fillna(0)
    grouped["repair_ratio_incl_skelp"] = (grouped["total_repair_amount_incl_skelp"] / denominator_m).fillna(0)
    long = grouped.melt(
        id_vars="production_type",
        value_vars=["repair_ratio", "repair_ratio_incl_skelp"],
        var_name="metric",
        value_name="ratio",
    )
    long["metric"] = long["metric"].map(
        {"repair_ratio": "Repair Ratio", "repair_ratio_incl_skelp": "Repair Ratio incl. Skelp"}
    )
    fig = px.bar(
        long,
        x="production_type",
        y="ratio",
        color="metric",
        barmode="group",
        text=long["ratio"].map(lambda value: f"{value:.2%}"),
        title="Production Type Repair Ratio",
        color_discrete_sequence=["#2563eb", "#dc2626"],
    )
    fig.update_layout(xaxis_title="Production Type", yaxis_title="Weighted Repair Ratio", legend_title_text="")
    fig.update_yaxes(tickformat=".2%")
    fig.update_traces(textposition="outside", hovertemplate="%{x}<br>%{fullData.name}: %{y:.2%}<extra></extra>")
    return fig


def skelp_impact_analysis(df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = apply_meter_based_repair_ratios(df).copy()
    if "production_type" not in data.columns:
        data["production_type"] = "Coil"
    data["project_dimension"] = data["project_no"] + " | " + data["dimensions"] + " | " + data["production_type"]
    data["skelp_amount_impact_display"] = amount_in_display_unit(
        data["total_repair_amount_incl_skelp"] - data["total_repair_amount"],
        display_unit,
    )
    grouped = (
        data.groupby("project_dimension", as_index=False)
        .agg(
            skelp_amount_impact=("total_repair_amount_incl_skelp", "sum"),
            repair_amount=("total_repair_amount", "sum"),
            skelp_amount_impact_display=("skelp_amount_impact_display", "sum"),
            repaired_spiral_length=("repaired_spiral_length", "sum"),
        )
    )
    denominator_m = (grouped["repaired_spiral_length"] * METERS_PER_FOOT).where(grouped["repaired_spiral_length"] != 0)
    grouped["skelp_ratio_impact"] = ((grouped["skelp_amount_impact"] - grouped["repair_amount"]) / denominator_m).fillna(0)
    grouped = grouped.sort_values("skelp_ratio_impact", ascending=False).head(10)
    fig = px.bar(
        grouped.sort_values("skelp_ratio_impact"),
        x="skelp_ratio_impact",
        y="project_dimension",
        orientation="h",
        text=grouped.sort_values("skelp_ratio_impact")["skelp_ratio_impact"].map(lambda value: f"+{value:.2%}"),
        color="skelp_amount_impact_display",
        color_continuous_scale="OrRd",
        title="Skelp Impact Analysis",
    )
    fig.update_layout(
        xaxis_title="Repair Ratio Increase from Skelp-end Welds",
        yaxis_title="Project / Dimension / Type",
        coloraxis_colorbar_title=f"Extra Repair ({unit})",
    )
    fig.update_xaxes(tickformat=".2%")
    fig.update_traces(
        textposition="outside",
        hovertemplate=(
            "%{y}<br>"
            "Ratio impact: %{x:.2%}<br>"
            f"Extra repair amount: %{{marker.color:,.2f}} {unit}<extra></extra>"
        ),
    )
    return fig


def repair_amount_pareto(df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = df.copy()
    if "production_type" not in data.columns:
        data["production_type"] = "Coil"
    data["project_dimension"] = data["project_no"] + " | " + data["dimensions"] + " | " + data["production_type"]
    data["repair_amount_display"] = amount_in_display_unit(data["total_repair_amount"], display_unit)
    grouped_all = (
        data.groupby("project_dimension", as_index=False)
        .agg(repair_amount_display=("repair_amount_display", "sum"))
        .sort_values("repair_amount_display", ascending=False)
    )
    total = grouped_all["repair_amount_display"].sum()
    grouped = grouped_all.head(12).copy()
    grouped["cumulative_share"] = grouped["repair_amount_display"].cumsum() / total if total else 0
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=grouped["project_dimension"],
            y=grouped["repair_amount_display"],
            name="Repair Amount",
            marker_color="#0ea5e9",
            text=grouped["repair_amount_display"].map(lambda value: f"{value:,.2f}"),
            textposition="outside",
            hovertemplate=f"%{{x}}<br>Repair amount: %{{y:,.2f}} {unit}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=grouped["project_dimension"],
            y=grouped["cumulative_share"],
            name="Cumulative %",
            yaxis="y2",
            mode="lines+markers+text",
            line={"color": "#f97316", "width": 3},
            marker={"size": 8},
            text=grouped["cumulative_share"].map(lambda value: f"{value:.0%}"),
            textposition="top center",
            hovertemplate="%{x}<br>Cumulative share: %{y:.2%}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Repair Amount Pareto ({unit})",
        xaxis_title="Project / Dimension / Type",
        yaxis_title=f"Repair Amount ({unit})",
        yaxis2={"title": "Cumulative Share", "overlaying": "y", "side": "right", "tickformat": ".0%", "range": [0, 1.05]},
        legend_title_text="",
    )
    fig.update_xaxes(tickangle=35)
    return fig


def status_comparison(df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = df.copy()
    grouped = (
        data.groupby("project_status", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
            repaired_spiral_length=("repaired_spiral_length", "sum"),
        )
        .sort_values("project_status")
    )
    denominator_m = (grouped["repaired_spiral_length"] * METERS_PER_FOOT).where(grouped["repaired_spiral_length"] != 0)
    grouped["repair_ratio"] = (grouped["total_repair_amount"] / denominator_m).fillna(0)
    grouped["repair_ratio_incl_skelp"] = (grouped["total_repair_amount_incl_skelp"] / denominator_m).fillna(0)
    grouped["repair_amount_display"] = amount_in_display_unit(grouped["total_repair_amount"], display_unit)
    long = grouped.melt(
        id_vars=["project_status", "repair_amount_display"],
        value_vars=["repair_ratio", "repair_ratio_incl_skelp"],
        var_name="metric",
        value_name="ratio",
    )
    long["metric"] = long["metric"].map(
        {"repair_ratio": "Repair Ratio", "repair_ratio_incl_skelp": "Repair Ratio incl. Skelp"}
    )
    fig = px.bar(
        long,
        x="project_status",
        y="ratio",
        color="metric",
        barmode="group",
        text=long["ratio"].map(lambda value: f"{value:.2%}"),
        title="Completed vs In Progress Quality",
        color_discrete_sequence=["#2563eb", "#dc2626"],
        custom_data=["repair_amount_display"],
    )
    fig.update_layout(xaxis_title="Status", yaxis_title="Weighted Repair Ratio", legend_title_text="")
    fig.update_yaxes(tickformat=".2%")
    fig.update_traces(
        textposition="outside",
        hovertemplate="%{x}<br>%{fullData.name}: %{y:.2%}<br>" + f"Repair amount: %{{customdata[0]:,.2f}} {unit}<extra></extra>",
    )
    return fig


def historical_benchmark_comparison(df: pd.DataFrame, baseline_df: pd.DataFrame | None = None):
    data = df.copy()
    rows = []
    if not data.empty:
        denominator_m = data["repaired_spiral_length"].sum() * METERS_PER_FOOT
        rows.append(
            {
                "group": "Selected Active Projects",
                "repair_ratio": data["total_repair_amount"].sum() / denominator_m if denominator_m else 0,
                "repair_ratio_incl_skelp": data["total_repair_amount_incl_skelp"].sum() / denominator_m if denominator_m else 0,
            }
        )
    if baseline_df is not None and not baseline_df.empty:
        denominator_m = baseline_df["repaired_spiral_length"].sum() * METERS_PER_FOOT
        rows.append(
            {
                "group": "Historical Completed Baseline",
                "repair_ratio": baseline_df["total_repair_amount"].sum() / denominator_m if denominator_m else 0,
                "repair_ratio_incl_skelp": baseline_df["total_repair_amount_incl_skelp"].sum() / denominator_m if denominator_m else 0,
            }
        )
    benchmark = pd.DataFrame(rows)
    if benchmark.empty:
        fig = go.Figure()
        fig.update_layout(title="Historical Benchmark Comparison")
        return fig
    long = benchmark.melt(id_vars="group", value_vars=["repair_ratio", "repair_ratio_incl_skelp"], var_name="metric", value_name="ratio")
    long["metric"] = long["metric"].map(
        {"repair_ratio": "Repair Ratio", "repair_ratio_incl_skelp": "Repair Ratio incl. Skelp"}
    )
    fig = px.bar(
        long,
        x="group",
        y="ratio",
        color="metric",
        barmode="group",
        text=long["ratio"].map(lambda value: f"{value:.2%}"),
        title="Historical Benchmark Comparison",
        color_discrete_sequence=["#2563eb", "#dc2626"],
    )
    fig.update_layout(xaxis_title="", yaxis_title="Weighted Repair Ratio", legend_title_text="")
    fig.update_yaxes(tickformat=".2%")
    fig.update_traces(textposition="outside", hovertemplate="%{x}<br>%{fullData.name}: %{y:.2%}<extra></extra>")
    return fig


def pipe_worst_ratio(pipe_df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = pipe_df.nlargest(15, "repair_ratio").copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Worst Pipes by Repair Ratio")
        return fig
    data["pipe_label"] = data["project_sheet"] + " | Pipe " + data["pipe_no"].astype(str)
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    fig = px.bar(
        data.sort_values("repair_ratio"),
        x="repair_ratio",
        y="pipe_label",
        orientation="h",
        color="repair_amount_display",
        color_continuous_scale="Reds",
        text=data.sort_values("repair_ratio")["repair_ratio"].map(lambda value: f"{value:.2%}"),
        title="Worst Pipes by Repair Ratio",
    )
    fig.update_layout(
        xaxis_title="Repair Ratio",
        yaxis_title="Project / Pipe",
        coloraxis_colorbar_title=f"Repair Amount ({unit})",
    )
    fig.update_xaxes(tickformat=".2%")
    fig.update_traces(textposition="outside")
    return fig


def pipe_repair_amount_pareto(pipe_df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Pipe Repair Amount Pareto")
        return fig
    data["pipe_label"] = data["project_sheet"] + " | Pipe " + data["pipe_no"].astype(str)
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    grouped = (
        data.groupby("pipe_label", as_index=False)
        .agg(repair_amount_display=("repair_amount_display", "sum"), repair_ratio=("repair_ratio", "max"))
        .sort_values("repair_amount_display", ascending=False)
    )
    total = grouped["repair_amount_display"].sum()
    top = grouped.head(20).copy()
    top["cumulative_share"] = top["repair_amount_display"].cumsum() / total if total else 0
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=top["pipe_label"],
            y=top["repair_amount_display"],
            name="Repair Amount",
            marker_color="#0ea5e9",
            text=top["repair_amount_display"].map(lambda value: f"{value:,.2f}"),
            textposition="outside",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=top["pipe_label"],
            y=top["cumulative_share"],
            yaxis="y2",
            name="Cumulative %",
            mode="lines+markers+text",
            line={"color": "#f97316", "width": 3},
            text=top["cumulative_share"].map(lambda value: f"{value:.0%}"),
            textposition="top center",
        )
    )
    fig.update_layout(
        title="Pipe Repair Amount Pareto",
        xaxis_title="Project / Pipe",
        yaxis_title=f"Repair Amount ({unit})",
        yaxis2={"title": "Cumulative Share", "overlaying": "y", "side": "right", "tickformat": ".0%", "range": [0, 1.05]},
        legend_title_text="",
    )
    fig.update_xaxes(tickangle=35)
    return fig


def pipe_category_distribution(pipe_df: pd.DataFrame):
    data = pipe_df.copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Pipe Repair Category Distribution")
        return fig
    grouped = (
        data.groupby("repair_category", as_index=False)
        .agg(repair_amount=("repair_amount", "sum"), pipes=("pipe_no", "count"))
        .sort_values("repair_amount", ascending=False)
        .head(12)
    )
    fig = px.bar(
        grouped,
        x="repair_category",
        y="repair_amount",
        color="pipes",
        color_continuous_scale="Viridis",
        text=grouped["repair_amount"].map(lambda value: f"{value:,.2f}"),
        title="Pipe Repair Category Distribution",
    )
    fig.update_layout(xaxis_title="Repair Category", yaxis_title="Repair Amount (m)", coloraxis_colorbar_title="Pipe Count")
    fig.update_traces(textposition="outside")
    return fig


def pipe_project_outlier_scatter(pipe_df: pd.DataFrame):
    data = pipe_df.copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Pipe-Level Outlier Map")
        return fig
    fig = px.scatter(
        data,
        x="pipe_no",
        y="repair_ratio",
        size="repair_amount",
        color="project_sheet",
        hover_data=["repair_amount", "repair_category", "block_cell"],
        title="Pipe-Level Outlier Map",
    )
    fig.update_layout(xaxis_title="Pipe No.", yaxis_title="Repair Ratio", legend_title_text="Project")
    fig.update_yaxes(tickformat=".2%")
    return fig


def pipe_joint_count_distribution(pipe_df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = pipe_df[pipe_df["repair_count"].notna()].copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Band Joint Count Distribution")
        return fig
    data["repair_count"] = data["repair_count"].astype(int)
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    grouped = (
        data.groupby("repair_count", as_index=False)
        .agg(pipe_count=("pipe_no", "count"), repair_amount_display=("repair_amount_display", "sum"))
        .sort_values("repair_count")
    )
    fig = px.bar(
        grouped,
        x="repair_count",
        y="pipe_count",
        color="repair_amount_display",
        color_continuous_scale="Blues",
        text="pipe_count",
        title="Band Joint Count Distribution",
    )
    fig.update_layout(
        xaxis_title="Band Joint Count per Pipe",
        yaxis_title="Pipe Count",
        coloraxis_colorbar_title=f"Repair Amount ({unit})",
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate=(
            "Band joints: %{x}<br>"
            "Pipe count: %{y}<br>"
            f"Total repair: %{{marker.color:,.2f}} {unit}<extra></extra>"
        ),
    )
    return fig


def pipe_joint_count_vs_repair(pipe_df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = pipe_df[pipe_df["repair_count"].notna()].copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Band Joint Count vs Repair Amount")
        return fig
    data["pipe_label"] = "Pipe " + data["pipe_no"].astype(str)
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    fig = px.scatter(
        data,
        x="repair_count",
        y="repair_amount_display",
        size="repair_amount_display",
        color="repair_ratio",
        color_continuous_scale="Turbo",
        hover_name="pipe_label",
        title="Band Joint Count vs Repair Amount",
    )
    fig.update_layout(
        xaxis_title="Band Joint Count",
        yaxis_title=f"Repair Amount ({unit})",
        coloraxis_colorbar_title="Repair Ratio",
    )
    fig.update_coloraxes(colorbar_tickformat=".2%")
    return fig


def pipe_threshold_repair_ratio_trend(pipe_df: pd.DataFrame, split_pipe_no: int = 19, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title=f"Pipe Repair Ratio Trend - Before Pipe {split_pipe_no} vs Pipe {split_pipe_no}+")
        return fig

    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data = data.dropna(subset=["pipe_no_numeric", "repair_ratio"]).sort_values("pipe_no_numeric")
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title=f"Pipe Repair Ratio Trend - Before Pipe {split_pipe_no} vs Pipe {split_pipe_no}+")
        return fig

    before_label = f"Pipe < {split_pipe_no}"
    after_label = f"Pipe >= {split_pipe_no}"
    data["comparison_group"] = data["pipe_no_numeric"].map(
        lambda value: after_label if value >= split_pipe_no else before_label
    )
    data["pipe_label"] = "Pipe " + data["pipe_no_numeric"].astype(int).astype(str)
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)

    fig = px.line(
        data,
        x="pipe_no_numeric",
        y="repair_ratio",
        color="comparison_group",
        markers=True,
        text=data["repair_ratio"].map(lambda value: f"{value:.1%}"),
        custom_data=["pipe_label", "repair_amount_display", "repair_count"],
        title=f"Pipe Repair Ratio Trend - Before Pipe {split_pipe_no} vs Pipe {split_pipe_no}+",
        color_discrete_map={before_label: "#2563eb", after_label: "#f97316"},
    )

    averages = data.groupby("comparison_group", as_index=False)["repair_ratio"].mean()
    color_map = {before_label: "#2563eb", after_label: "#f97316"}
    for _, row in averages.iterrows():
        fig.add_hline(
            y=row["repair_ratio"],
            line_dash="dash",
            line_color=color_map.get(row["comparison_group"], "#64748b"),
            annotation_text=f"{row['comparison_group']} avg {row['repair_ratio']:.2%}",
            annotation_position="top left" if row["comparison_group"] == before_label else "bottom right",
        )

    fig.update_layout(
        xaxis_title="Pipe No.",
        yaxis_title="Repair Ratio",
        legend_title_text="Pipe Group",
    )
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(tickformat=".1%")
    fig.update_traces(
        textposition="top center",
        hovertemplate=(
            "%{customdata[0]}<br>"
            "Repair Ratio: %{y:.2%}<br>"
            f"Repair Amount: %{{customdata[1]:,.3f}} {unit}<br>"
            "Band Joint Count: %{customdata[2]}<extra></extra>"
        ),
    )
    return fig


def pipe_threshold_group_comparison(pipe_df: pd.DataFrame, split_pipe_no: int = 19, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title=f"Before/After Pipe {split_pipe_no} Comparison")
        return fig

    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data = data.dropna(subset=["pipe_no_numeric", "repair_ratio"])
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title=f"Before/After Pipe {split_pipe_no} Comparison")
        return fig

    before_label = f"Pipe < {split_pipe_no}"
    after_label = f"Pipe >= {split_pipe_no}"
    data["comparison_group"] = data["pipe_no_numeric"].map(
        lambda value: after_label if value >= split_pipe_no else before_label
    )
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    grouped = (
        data.groupby("comparison_group", as_index=False)
        .agg(
            avg_repair_ratio=("repair_ratio", "mean"),
            max_repair_ratio=("repair_ratio", "max"),
            total_repair_amount=("repair_amount_display", "sum"),
            pipe_count=("pipe_no_numeric", "count"),
        )
        .sort_values("comparison_group")
    )

    fig = px.bar(
        grouped,
        x="comparison_group",
        y="avg_repair_ratio",
        color="comparison_group",
        text=grouped["avg_repair_ratio"].map(lambda value: f"{value:.2%}"),
        custom_data=["pipe_count", "total_repair_amount", "max_repair_ratio"],
        title=f"Before/After Pipe {split_pipe_no} Average Repair Ratio",
        color_discrete_map={before_label: "#2563eb", after_label: "#f97316"},
    )
    fig.update_layout(
        xaxis_title="Pipe Group",
        yaxis_title="Average Repair Ratio",
        legend_title_text="",
        showlegend=False,
    )
    fig.update_yaxes(tickformat=".1%")
    fig.update_traces(
        textposition="outside",
        hovertemplate=(
            "%{x}<br>"
            "Average Repair Ratio: %{y:.2%}<br>"
            "Max Repair Ratio: %{customdata[2]:.2%}<br>"
            f"Total Repair Amount: %{{customdata[1]:,.2f}} {unit}<br>"
            "Pipe Count: %{customdata[0]}<extra></extra>"
        ),
    )
    return fig


def pipe_group_repair_ratio_trend(
    pipe_df: pd.DataFrame,
    group_column: str,
    display_unit: str = "m",
    group_title: str = "Pipe Group",
):
    unit = unit_label(display_unit)
    chart_title = f"{group_title} Repair Ratio Trend"
    data = pipe_df.copy()
    if data.empty or group_column not in data.columns:
        fig = go.Figure()
        fig.update_layout(title=chart_title)
        return fig

    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data = data.dropna(subset=["pipe_no_numeric", "repair_ratio", group_column]).sort_values("pipe_no_numeric")
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title=chart_title)
        return fig

    data["pipe_label"] = "Pipe " + data["pipe_no_numeric"].astype(int).astype(str)
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    colors = ["#2563eb", "#f97316", "#16a34a", "#dc2626", "#7c3aed", "#0891b2"]
    fig = go.Figure()
    group_order_column = f"{group_column}_order"
    if group_order_column in data.columns:
        group_names = (
            data[[group_column, group_order_column]]
            .drop_duplicates()
            .sort_values(group_order_column)[group_column]
            .tolist()
        )
    else:
        group_names = sorted(data[group_column].dropna().unique().tolist())

    for index, group_name in enumerate(group_names):
        group_data = data[data[group_column].eq(group_name)].sort_values("pipe_no_numeric")
        fig.add_trace(
            go.Scatter(
                x=group_data["pipe_no_numeric"],
                y=group_data["repair_ratio"],
                name=str(group_name),
                mode="lines+markers+text",
                line={"color": colors[index % len(colors)], "width": 3},
                marker={"size": 8},
                text=group_data["repair_ratio"].map(lambda value: f"{value:.1%}"),
                textposition="top center",
                customdata=group_data[["pipe_label", "repair_amount_display", "repair_count"]],
                hovertemplate=(
                    "%{customdata[0]}<br>"
                    "Repair Ratio: %{y:.2%}<br>"
                    f"Repair Amount: %{{customdata[1]:,.3f}} {unit}<br>"
                    "Band Joint Count: %{customdata[2]}<extra></extra>"
                ),
            )
        )
        average_ratio = group_data["repair_ratio"].mean()
        fig.add_hline(
            y=average_ratio,
            line_dash="dash",
            line_color=colors[index % len(colors)],
            annotation_text=f"{group_name} avg {average_ratio:.2%}",
            annotation_position="top left" if index % 2 == 0 else "bottom right",
        )

    fig.update_layout(
        title=chart_title,
        xaxis_title="Pipe No.",
        yaxis_title="Repair Ratio",
        legend_title_text=group_title,
        height=460,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"size": 12, "color": "#111827"},
        hovermode="closest",
        margin={"l": 60, "r": 30, "t": 70, "b": 80},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.28, "xanchor": "center", "x": 0.5},
    )
    fig.update_xaxes(dtick=1, gridcolor="#e5e7eb", zeroline=False)
    fig.update_yaxes(tickformat=".1%", gridcolor="#e5e7eb", zeroline=False)
    return fig


def pipe_group_comparison(
    pipe_df: pd.DataFrame,
    group_column: str,
    display_unit: str = "m",
    group_title: str = "Pipe Group",
):
    unit = unit_label(display_unit)
    chart_title = f"{group_title} Average Repair Ratio"
    data = pipe_df.copy()
    if data.empty or group_column not in data.columns:
        fig = go.Figure()
        fig.update_layout(title=chart_title)
        return fig

    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data = data.dropna(subset=["pipe_no_numeric", "repair_ratio", group_column])
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title=chart_title)
        return fig

    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    group_order_column = f"{group_column}_order"
    agg_kwargs = {
        "avg_repair_ratio": ("repair_ratio", "mean"),
        "max_repair_ratio": ("repair_ratio", "max"),
        "total_repair_amount": ("repair_amount_display", "sum"),
        "pipe_count": ("pipe_no_numeric", "count"),
    }
    if group_order_column in data.columns:
        agg_kwargs["sort_order"] = (group_order_column, "min")
    grouped = (
        data.groupby(group_column, as_index=False)
        .agg(**agg_kwargs)
        .sort_values("sort_order" if "sort_order" in agg_kwargs else group_column)
    )

    fig = px.bar(
        grouped,
        x=group_column,
        y="avg_repair_ratio",
        color=group_column,
        text=grouped["avg_repair_ratio"].map(lambda value: f"{value:.2%}"),
        custom_data=["pipe_count", "total_repair_amount", "max_repair_ratio"],
        title=chart_title,
        color_discrete_sequence=["#2563eb", "#f97316", "#16a34a", "#dc2626", "#7c3aed", "#0891b2"],
    )
    fig.update_layout(
        xaxis_title=group_title,
        yaxis_title="Average Repair Ratio",
        legend_title_text="",
        showlegend=False,
        height=430,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"size": 12, "color": "#111827"},
        margin={"l": 60, "r": 30, "t": 70, "b": 80},
    )
    max_ratio = grouped["avg_repair_ratio"].max()
    fig.update_yaxes(
        tickformat=".1%",
        gridcolor="#e5e7eb",
        zeroline=False,
        range=[0, max_ratio * 1.35 if pd.notna(max_ratio) and max_ratio else 1],
    )
    fig.update_xaxes(tickangle=0)
    fig.update_traces(
        textposition="outside",
        hovertemplate=(
            "%{x}<br>"
            "Average Repair Ratio: %{y:.2%}<br>"
            "Max Repair Ratio: %{customdata[2]:.2%}<br>"
            f"Total Repair Amount: %{{customdata[1]:,.2f}} {unit}<br>"
            "Pipe Count: %{customdata[0]}<extra></extra>"
        ),
    )
    return fig


def pipe_group_binned_repair_ratio_trend(
    pipe_df: pd.DataFrame,
    group_column: str,
    display_unit: str = "m",
    group_title: str = "Pipe Group",
    bin_size: int = 10,
):
    unit = unit_label(display_unit)
    bin_size = max(int(bin_size or 1), 1)
    chart_title = f"{group_title} Repair Ratio Trend - {bin_size} Pipe Average"
    data = pipe_df.copy()
    if data.empty or group_column not in data.columns:
        fig = go.Figure()
        fig.update_layout(title=chart_title)
        return fig

    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data = data.dropna(subset=["pipe_no_numeric", "repair_ratio", group_column]).copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title=chart_title)
        return fig

    data["pipe_no_numeric"] = data["pipe_no_numeric"].astype(int)
    data["bin_start"] = ((data["pipe_no_numeric"] - 1) // bin_size) * bin_size + 1
    data["bin_end"] = data["bin_start"] + bin_size - 1
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    group_order_column = f"{group_column}_order"
    group_keys = [group_column, "bin_start", "bin_end"]
    agg_kwargs = {
        "avg_repair_ratio": ("repair_ratio", "mean"),
        "max_repair_ratio": ("repair_ratio", "max"),
        "total_repair_amount": ("repair_amount_display", "sum"),
        "pipe_count": ("pipe_no_numeric", "count"),
    }
    if group_order_column in data.columns:
        agg_kwargs["sort_order"] = (group_order_column, "min")
    grouped = data.groupby(group_keys, as_index=False).agg(**agg_kwargs)
    grouped["bin_label"] = grouped["bin_start"].astype(str) + "-" + grouped["bin_end"].astype(str)
    grouped["x_label"] = grouped[group_column].astype(str) + " | " + grouped["bin_label"]

    colors = ["#2563eb", "#f97316", "#16a34a", "#dc2626", "#7c3aed", "#0891b2"]
    if "sort_order" in grouped.columns:
        group_names = (
            grouped[[group_column, "sort_order"]]
            .drop_duplicates()
            .sort_values("sort_order")[group_column]
            .tolist()
        )
    else:
        group_names = sorted(grouped[group_column].dropna().unique().tolist())

    fig = go.Figure()
    for index, group_name in enumerate(group_names):
        group_data = grouped[grouped[group_column].eq(group_name)].sort_values("bin_start")
        fig.add_trace(
            go.Scatter(
                x=group_data["bin_start"],
                y=group_data["avg_repair_ratio"],
                name=str(group_name),
                mode="lines+markers+text",
                line={"color": colors[index % len(colors)], "width": 3},
                marker={"size": 9},
                text=group_data["avg_repair_ratio"].map(lambda value: f"{value:.1%}"),
                textposition="top center",
                customdata=group_data[["bin_label", "pipe_count", "total_repair_amount", "max_repair_ratio"]],
                hovertemplate=(
                    "Pipe interval: %{customdata[0]}<br>"
                    "Average Repair Ratio: %{y:.2%}<br>"
                    "Max Repair Ratio: %{customdata[3]:.2%}<br>"
                    f"Total Repair Amount: %{{customdata[2]:,.2f}} {unit}<br>"
                    "Pipe Count: %{customdata[1]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=chart_title,
        xaxis_title="Pipe Interval",
        yaxis_title="Average Repair Ratio",
        legend_title_text=group_title,
        height=460,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"size": 12, "color": "#111827"},
        hovermode="closest",
        margin={"l": 60, "r": 30, "t": 70, "b": 90},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.30, "xanchor": "center", "x": 0.5},
    )
    tick_values = sorted(grouped["bin_start"].unique().tolist())
    tick_text = [f"{value}-{value + bin_size - 1}" for value in tick_values]
    fig.update_xaxes(tickmode="array", tickvals=tick_values, ticktext=tick_text, gridcolor="#e5e7eb", zeroline=False)
    fig.update_yaxes(tickformat=".1%", gridcolor="#e5e7eb", zeroline=False)
    return fig


def dimension_project_comparison(pipe_df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Dimension Project Comparison")
        return fig
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    grouped = (
        data.groupby("project_no", as_index=False)
        .agg(
            avg_repair_ratio=("repair_ratio", "mean"),
            max_repair_ratio=("repair_ratio", "max"),
            total_repair_amount=("repair_amount_display", "sum"),
            pipe_count=("pipe_no", "count"),
        )
        .sort_values("avg_repair_ratio", ascending=False)
    )
    fig = px.bar(
        grouped,
        x="project_no",
        y="avg_repair_ratio",
        color="project_no",
        text=grouped["avg_repair_ratio"].map(lambda value: f"{value:.2%}"),
        custom_data=["pipe_count", "total_repair_amount", "max_repair_ratio"],
        title="Dimension Project Comparison",
        color_discrete_sequence=["#2563eb", "#f97316", "#16a34a", "#dc2626", "#7c3aed", "#0891b2"],
    )
    max_ratio = grouped["avg_repair_ratio"].max()
    fig.update_layout(
        xaxis_title="Project",
        yaxis_title="Average Repair Ratio",
        showlegend=False,
        height=430,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"size": 12, "color": "#111827"},
        margin={"l": 60, "r": 30, "t": 70, "b": 80},
    )
    fig.update_yaxes(
        tickformat=".1%",
        gridcolor="#e5e7eb",
        zeroline=False,
        range=[0, max_ratio * 1.35 if pd.notna(max_ratio) and max_ratio else 1],
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate=(
            "Project: %{x}<br>"
            "Average Repair Ratio: %{y:.2%}<br>"
            "Max Repair Ratio: %{customdata[2]:.2%}<br>"
            f"Total Repair Amount: %{{customdata[1]:,.2f}} {unit}<br>"
            "Pipe Count: %{customdata[0]}<extra></extra>"
        ),
    )
    return fig


def dimension_worst_pipes(pipe_df: pd.DataFrame, display_unit: str = "m", top_n: int = 20):
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(title="Worst Pipes in Dimension")
        return fig
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    data["project_pipe_label"] = data["project_no"].astype(str) + " | Pipe " + data["pipe_no"].astype(str)
    top_n = max(int(top_n or 20), 1)
    top = data.nlargest(top_n, "repair_ratio").sort_values("repair_ratio")
    fig = px.bar(
        top,
        x="repair_ratio",
        y="project_pipe_label",
        orientation="h",
        color="project_no",
        text=top["repair_ratio"].map(lambda value: f"{value:.2%}"),
        custom_data=["repair_amount_display", "repair_count"],
        title=f"Worst {top_n} Pipes in Dimension",
        color_discrete_sequence=["#dc2626", "#f97316", "#2563eb", "#16a34a", "#7c3aed", "#0891b2"],
    )
    max_ratio = top["repair_ratio"].max()
    fig.update_layout(
        xaxis_title="Repair Ratio",
        yaxis_title="Project / Pipe",
        legend_title_text="Project",
        height=520,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"size": 12, "color": "#111827"},
        margin={"l": 130, "r": 30, "t": 70, "b": 60},
    )
    fig.update_xaxes(
        tickformat=".1%",
        gridcolor="#e5e7eb",
        zeroline=False,
        range=[0, max_ratio * 1.25 if pd.notna(max_ratio) and max_ratio else 1],
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate=(
            "%{y}<br>"
            "Repair Ratio: %{x:.2%}<br>"
            f"Repair Amount: %{{customdata[0]:,.2f}} {unit}<br>"
            "Band Joint Count: %{customdata[1]}<extra></extra>"
        ),
    )
    return fig


def repair_amount_trend(df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    grouped = repair_amount_trend_data(df, display_unit)
    grouped["daily_repair_amount_scaled_display"] = grouped["daily_repair_amount_display"] * DAILY_REPAIR_VISUAL_SCALE

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=grouped["date"],
            y=grouped["daily_repair_amount_scaled_display"],
            name=f"Daily Repair Amount (x{DAILY_REPAIR_VISUAL_SCALE} visual scale)",
            mode="lines+markers+text",
            line={"color": "#a855f7", "width": 3, "dash": "dot"},
            marker={"size": 8},
            text=grouped["daily_repair_amount_display"].map(lambda value: f"{value:,.2f}"),
            textposition="top center",
            customdata=grouped["daily_repair_amount_display"],
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>"
                "Daily Repair Amount: %{customdata:,.2f}<br>"
                f"Displayed as: daily x{DAILY_REPAIR_VISUAL_SCALE} = "
                "%{y:,.2f}<extra></extra>"
            ),
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
            hovertemplate="Date: %{x|%Y-%m-%d}<br>Total Repair Amount: %{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Repair Amount Trend ({unit}) - Daily line shown as x{DAILY_REPAIR_VISUAL_SCALE}",
        xaxis_title="Date",
        yaxis_title=f"Repair Amount ({unit})",
        legend_title_text="",
    )
    fig.update_xaxes(tickformat="%Y-%m-%d")
    return fig
