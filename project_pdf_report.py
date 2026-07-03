from __future__ import annotations

from html import escape
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from calculations import amount_in_display_unit, unit_label


CHART_DPI = 260
CHART_SIZE = (9.6, 3.5)
WIDE_CHART_SIZE = (19.2, 4.7)
GROUP_COLORS = ["#2563eb", "#f97316", "#16a34a", "#dc2626", "#7c3aed", "#0891b2"]


def _style_axes(ax, title: str) -> None:
    ax.set_title(title, fontsize=12, fontweight="bold", color="#111827", pad=10)
    ax.set_facecolor("white")
    ax.grid(True, axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=8, colors="#334155")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")


def _image(fig, width_cm: float = 19.8, height_cm: float = 7.0) -> Image:
    buffer = BytesIO()
    fig.tight_layout(pad=1.0)
    fig.savefig(buffer, format="png", dpi=CHART_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buffer.seek(0)
    return Image(buffer, width=width_cm * cm, height=height_cm * cm)


def _pareto_chart(pipe_df: pd.DataFrame, display_unit: str) -> Image:
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    grouped = (
        data.groupby("pipe_no", as_index=False)
        .agg(repair_amount_display=("repair_amount_display", "sum"))
        .sort_values("repair_amount_display", ascending=False)
    )
    total = grouped["repair_amount_display"].sum()
    top = grouped.head(20).copy()
    top["cumulative_share"] = top["repair_amount_display"].cumsum() / total if total else 0

    fig, ax1 = plt.subplots(figsize=CHART_SIZE)
    positions = range(len(top))
    bars = ax1.bar(positions, top["repair_amount_display"], color="#0ea5e9")
    ax1.bar_label(
        bars,
        labels=[f"{value:.2f}" for value in top["repair_amount_display"]],
        padding=3,
        fontsize=6.8,
        fontweight="bold",
    )
    ax1.set_ylabel(f"Repair Amount ({unit})", fontsize=8)
    ax1.set_xticks(list(positions))
    ax1.set_xticklabels([f"Pipe {value}" for value in top["pipe_no"]], rotation=35, ha="right")
    _style_axes(ax1, "Pipe Repair Amount Pareto")

    ax2 = ax1.twinx()
    ax2.plot(positions, top["cumulative_share"], color="#f97316", linewidth=2.4, marker="o")
    for position, value in zip(positions, top["cumulative_share"]):
        ax2.annotate(
            f"{value:.0%}",
            (position, value),
            textcoords="offset points",
            xytext=(0, 7),
            ha="center",
            fontsize=6.8,
            color="#c2410c",
            fontweight="bold",
        )
    ax2.set_ylim(0, 1.05)
    ax2.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    ax2.set_ylabel("Cumulative Share", fontsize=8)
    ax2.spines["top"].set_visible(False)
    return _image(fig)


def _worst_ratio_chart(pipe_df: pd.DataFrame) -> Image:
    top = pipe_df.nlargest(15, "repair_ratio").sort_values("repair_ratio")
    fig, ax = plt.subplots(figsize=CHART_SIZE)
    bars = ax.barh(
        [f"Pipe {value}" for value in top["pipe_no"]],
        top["repair_ratio"],
        color="#dc2626",
    )
    ax.bar_label(
        bars,
        labels=[f"{value:.2%}" for value in top["repair_ratio"]],
        padding=4,
        fontsize=7,
        fontweight="bold",
    )
    max_value = top["repair_ratio"].max()
    ax.set_xlim(0, max_value * 1.25 if pd.notna(max_value) and max_value else 1)
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
    ax.set_xlabel("Repair Ratio", fontsize=8)
    _style_axes(ax, "Worst Pipes by Repair Ratio")
    return _image(fig)


def _joint_distribution_chart(pipe_df: pd.DataFrame) -> Image:
    data = pipe_df[pipe_df["repair_count"].notna()].copy()
    grouped = (
        data.groupby("repair_count", as_index=False)
        .agg(pipe_count=("pipe_no", "count"), repair_amount=("repair_amount", "sum"))
        .sort_values("repair_count")
    )
    fig, ax = plt.subplots(figsize=CHART_SIZE)
    if not grouped.empty:
        bars = ax.bar(grouped["repair_count"].astype(int), grouped["pipe_count"], color="#2563eb")
        ax.bar_label(bars, labels=grouped["pipe_count"].astype(str), padding=3, fontsize=7, fontweight="bold")
    ax.set_xlabel("Band Joint Count per Pipe", fontsize=8)
    ax.set_ylabel("Pipe Count", fontsize=8)
    _style_axes(ax, "Band Joint Count Distribution")
    return _image(fig)


def _joint_repair_chart(pipe_df: pd.DataFrame, display_unit: str) -> Image:
    unit = unit_label(display_unit)
    data = pipe_df[pipe_df["repair_count"].notna()].copy()
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    fig, ax = plt.subplots(figsize=CHART_SIZE)
    if not data.empty:
        sizes = data["repair_amount_display"].clip(lower=0.05) * 16
        scatter = ax.scatter(
            data["repair_count"],
            data["repair_amount_display"],
            s=sizes,
            c=data["repair_ratio"],
            cmap="turbo",
            alpha=0.75,
            edgecolors="white",
            linewidths=0.5,
        )
        colorbar = fig.colorbar(scatter, ax=ax, pad=0.02)
        colorbar.ax.yaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
        colorbar.set_label("Repair Ratio", fontsize=8)
    ax.set_xlabel("Band Joint Count", fontsize=8)
    ax.set_ylabel(f"Repair Amount ({unit})", fontsize=8)
    _style_axes(ax, "Band Joint Count vs Repair Amount")
    return _image(fig)


def _group_order(data: pd.DataFrame, group_column: str) -> list:
    order_column = f"{group_column}_order"
    if order_column in data.columns:
        return (
            data[[group_column, order_column]]
            .dropna()
            .drop_duplicates()
            .sort_values(order_column)[group_column]
            .tolist()
        )
    return sorted(data[group_column].dropna().unique().tolist())


def _group_summary_rows(group_df: pd.DataFrame, group_column: str, label: str, display_unit: str) -> list[list[str]]:
    unit = unit_label(display_unit)
    data = group_df.copy()
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    rows = [[label, "Pipe Count", "Avg Repair Ratio", "Max Repair Ratio", f"Total Repair ({unit})"]]
    for group_name in _group_order(data, group_column):
        group_data = data[data[group_column].eq(group_name)]
        rows.append(
            [
                escape(str(group_name)),
                f"{len(group_data):,}",
                f"{group_data['repair_ratio'].mean():.2%}",
                f"{group_data['repair_ratio'].max():.2%}",
                f"{group_data['repair_amount_display'].sum():,.2f}",
            ]
        )
    return rows


def _group_trend_chart(group_df: pd.DataFrame, group_column: str, title: str, display_unit: str) -> Image:
    unit = unit_label(display_unit)
    data = group_df.copy()
    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data = data.dropna(subset=["pipe_no_numeric", "repair_ratio", group_column]).sort_values("pipe_no_numeric")
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)

    fig, ax = plt.subplots(figsize=WIDE_CHART_SIZE)
    for index, group_name in enumerate(_group_order(data, group_column)):
        group_data = data[data[group_column].eq(group_name)].sort_values("pipe_no_numeric")
        color = GROUP_COLORS[index % len(GROUP_COLORS)]
        ax.plot(
            group_data["pipe_no_numeric"],
            group_data["repair_ratio"],
            color=color,
            linewidth=2.8,
            marker="o",
            markersize=5,
            label=str(group_name),
        )
        for _, row in group_data.iterrows():
            ax.annotate(
                f"{row['repair_ratio']:.1%}",
                (row["pipe_no_numeric"], row["repair_ratio"]),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=6.8,
                color=color,
                fontweight="bold",
            )
        avg = group_data["repair_ratio"].mean()
        ax.axhline(avg, color=color, linestyle="--", linewidth=1.1, alpha=0.7)
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
    ax.set_xlabel("Pipe No.", fontsize=8)
    ax.set_ylabel("Repair Ratio", fontsize=8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=4, fontsize=8, frameon=False)
    _style_axes(ax, title)
    return _image(fig, width_cm=38.0, height_cm=9.3)


def _group_comparison_chart(group_df: pd.DataFrame, group_column: str, title: str, display_unit: str) -> Image:
    unit = unit_label(display_unit)
    data = group_df.copy()
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    rows = []
    for group_name in _group_order(data, group_column):
        group_data = data[data[group_column].eq(group_name)]
        rows.append(
            {
                "group": str(group_name),
                "avg_repair_ratio": group_data["repair_ratio"].mean(),
                "total_repair": group_data["repair_amount_display"].sum(),
                "pipe_count": len(group_data),
            }
        )
    grouped = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=CHART_SIZE)
    positions = range(len(grouped))
    bars = ax.bar(positions, grouped["avg_repair_ratio"], color=[GROUP_COLORS[i % len(GROUP_COLORS)] for i in positions])
    ax.bar_label(
        bars,
        labels=[f"{value:.2%}" for value in grouped["avg_repair_ratio"]],
        padding=4,
        fontsize=8,
        fontweight="bold",
    )
    for position, row in grouped.iterrows():
        ax.annotate(
            f"{row['total_repair']:,.1f} {unit}\n{int(row['pipe_count'])} pipes",
            (position, row["avg_repair_ratio"]),
            textcoords="offset points",
            xytext=(0, -28),
            ha="center",
            va="top",
            fontsize=6.8,
            color="#334155",
        )
    max_value = grouped["avg_repair_ratio"].max()
    ax.set_ylim(0, max_value * 1.4 if pd.notna(max_value) and max_value else 1)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(grouped["group"], rotation=15, ha="right")
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
    ax.set_ylabel("Average Repair Ratio", fontsize=8)
    _style_axes(ax, title)
    return _image(fig)


def _dimension_project_comparison_chart(pipe_df: pd.DataFrame, display_unit: str) -> Image:
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    grouped = (
        data.groupby("project_no", as_index=False)
        .agg(
            avg_repair_ratio=("repair_ratio", "mean"),
            max_repair_ratio=("repair_ratio", "max"),
            total_repair=("repair_amount_display", "sum"),
            pipe_count=("pipe_no", "count"),
        )
        .sort_values("avg_repair_ratio", ascending=False)
    )

    fig, ax = plt.subplots(figsize=CHART_SIZE)
    positions = range(len(grouped))
    bars = ax.bar(positions, grouped["avg_repair_ratio"], color="#2563eb")
    ax.bar_label(
        bars,
        labels=[f"{value:.2%}" for value in grouped["avg_repair_ratio"]],
        padding=4,
        fontsize=7.5,
        fontweight="bold",
    )
    for position, row in grouped.iterrows():
        ax.annotate(
            f"{row['total_repair']:,.1f} {unit}\n{int(row['pipe_count'])} pipes",
            (position, row["avg_repair_ratio"]),
            textcoords="offset points",
            xytext=(0, -27),
            ha="center",
            va="top",
            fontsize=6.5,
            color="#334155",
        )
    max_value = grouped["avg_repair_ratio"].max()
    ax.set_ylim(0, max_value * 1.45 if pd.notna(max_value) and max_value else 1)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(grouped["project_no"].astype(str), rotation=20, ha="right")
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
    ax.set_ylabel("Average Repair Ratio", fontsize=8)
    _style_axes(ax, "Dimension Project Comparison")
    return _image(fig)


def _dimension_worst_pipes_chart(pipe_df: pd.DataFrame, display_unit: str, top_n: int) -> Image:
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    data["repair_amount_display"] = amount_in_display_unit(data["repair_amount"], display_unit)
    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data["label"] = (
        data["project_no"].astype(str)
        + " | Pipe "
        + data["pipe_no_numeric"].astype("Int64").astype(str)
    )
    top = data.nlargest(max(int(top_n or 15), 1), "repair_ratio").sort_values("repair_ratio")

    fig, ax = plt.subplots(figsize=CHART_SIZE)
    bars = ax.barh(top["label"], top["repair_ratio"], color="#dc2626")
    ax.bar_label(
        bars,
        labels=[
            f"{ratio:.2%} | {amount:,.1f} {unit}"
            for ratio, amount in zip(top["repair_ratio"], top["repair_amount_display"])
        ],
        padding=4,
        fontsize=6.8,
        fontweight="bold",
    )
    max_value = top["repair_ratio"].max()
    ax.set_xlim(0, max_value * 1.45 if pd.notna(max_value) and max_value else 1)
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
    ax.set_xlabel("Repair Ratio", fontsize=8)
    _style_axes(ax, f"Worst {len(top)} Pipes in Dimension")
    return _image(fig)


def _group_binned_trend_chart(
    group_df: pd.DataFrame,
    group_column: str,
    title: str,
    display_unit: str,
    bin_size: int,
) -> Image:
    data = group_df.copy()
    bin_size = max(int(bin_size or 1), 1)
    data["pipe_no_numeric"] = pd.to_numeric(data["pipe_no"], errors="coerce")
    data = data.dropna(subset=["pipe_no_numeric", "repair_ratio", group_column]).copy()
    data["pipe_no_numeric"] = data["pipe_no_numeric"].astype(int)
    data["bin_start"] = ((data["pipe_no_numeric"] - 1) // bin_size) * bin_size + 1
    data["bin_end"] = data["bin_start"] + bin_size - 1
    grouped = (
        data.groupby([group_column, "bin_start", "bin_end"], as_index=False)
        .agg(avg_repair_ratio=("repair_ratio", "mean"), pipe_count=("pipe_no_numeric", "count"))
        .sort_values(["bin_start", group_column])
    )

    fig, ax = plt.subplots(figsize=WIDE_CHART_SIZE)
    for index, group_name in enumerate(_group_order(data, group_column)):
        group_data = grouped[grouped[group_column].eq(group_name)].sort_values("bin_start")
        if group_data.empty:
            continue
        color = GROUP_COLORS[index % len(GROUP_COLORS)]
        ax.plot(
            group_data["bin_start"],
            group_data["avg_repair_ratio"],
            color=color,
            linewidth=2.8,
            marker="o",
            markersize=5,
            label=str(group_name),
        )
        for _, row in group_data.iterrows():
            ax.annotate(
                f"{row['avg_repair_ratio']:.1%}",
                (row["bin_start"], row["avg_repair_ratio"]),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=6.8,
                color=color,
                fontweight="bold",
            )
    tick_values = sorted(grouped["bin_start"].unique().tolist())
    ax.set_xticks(tick_values)
    ax.set_xticklabels([f"{value}-{value + bin_size - 1}" for value in tick_values], rotation=20, ha="right")
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
    ax.set_xlabel("Pipe Interval", fontsize=8)
    ax.set_ylabel("Average Repair Ratio", fontsize=8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4, fontsize=8, frameon=False)
    _style_axes(ax, f"{title} - {bin_size} Pipe Average")
    return _image(fig, width_cm=38.0, height_cm=9.3)


def _styled_table(rows, widths, font_size=8) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-2, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build_project_pipe_pdf_report(
    pipe_df: pd.DataFrame,
    reconciliation: pd.Series,
    selected_date,
    display_unit: str = "m",
    pipe_group_df: pd.DataFrame | None = None,
    machine_group_df: pd.DataFrame | None = None,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A3),
        leftMargin=1.1 * cm,
        rightMargin=1.1 * cm,
        topMargin=0.9 * cm,
        bottomMargin=0.9 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ProjectReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111827"),
    )
    right_style = ParagraphStyle(
        "ProjectReportMeta",
        parent=styles["Normal"],
        fontSize=8,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#475569"),
    )
    section_style = ParagraphStyle(
        "ProjectReportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#111827"),
        spaceAfter=6,
    )

    report_date = pd.to_datetime(selected_date).date()
    unit = unit_label(display_unit)
    project_no = str(reconciliation["project_no"])
    dimensions = str(reconciliation["dimensions"])
    joint_coverage = float(reconciliation["joint_count_coverage"])
    known_joint_rows = pipe_df["repair_count"].notna().sum()
    top_five_share = (
        pipe_df.nlargest(5, "repair_amount")["repair_amount"].sum() / pipe_df["repair_amount"].sum()
        if pipe_df["repair_amount"].sum()
        else 0
    )
    pipe_total_display = amount_in_display_unit(pipe_df["repair_amount"].sum(), display_unit)
    master_total_display = amount_in_display_unit(
        float(reconciliation["expected_repair_amount"]),
        display_unit,
    )
    difference_display = amount_in_display_unit(float(reconciliation["difference_m"]), display_unit)

    story = [
        Paragraph("Project Pipe Repair Analysis", title_style),
        Paragraph(
            f"Report date: {report_date} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Project: {escape(project_no)} &nbsp;&nbsp;|&nbsp;&nbsp; Dimension: {escape(dimensions)}",
            right_style,
        ),
        Spacer(1, 0.25 * cm),
    ]
    kpis = [
        [
            "Pipe Rows",
            "Pipe Repair Total",
            "Master Repair Total",
            "Reconciliation Difference",
            "Joint Count Coverage",
            "Top 5 Repair Share",
        ],
        [
            f"{len(pipe_df):,}",
            f"{pipe_total_display:,.2f} {unit}",
            f"{master_total_display:,.2f} {unit}",
            f"{difference_display:+.4f} {unit}",
            f"{joint_coverage:.0%} ({known_joint_rows:,}/{len(pipe_df):,})",
            f"{top_five_share:.1%}",
        ],
    ]
    story.append(
        _styled_table(
            kpis,
            [4.0 * cm, 5.1 * cm, 5.1 * cm, 5.4 * cm, 5.4 * cm, 4.8 * cm],
            font_size=10,
        )
    )

    chart_grid = Table(
        [
            [_pareto_chart(pipe_df, display_unit), _worst_ratio_chart(pipe_df)],
            [_joint_distribution_chart(pipe_df), _joint_repair_chart(pipe_df, display_unit)],
        ],
        colWidths=[20.4 * cm, 20.4 * cm],
        rowHeights=[7.5 * cm, 7.5 * cm],
    )
    chart_grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.extend([Spacer(1, 0.2 * cm), chart_grid])

    group_sections: list[tuple[str, str, pd.DataFrame]] = []
    if pipe_group_df is not None and not pipe_group_df.empty:
        group_sections.append(("Pipe Group Analysis", "Pipe Group", pipe_group_df))
    if machine_group_df is not None and not machine_group_df.empty:
        group_sections.append(("Machine Analysis", "Machine", machine_group_df))

    for section_title, label, group_df in group_sections:
        story.extend([PageBreak(), Paragraph(section_title, section_style)])
        story.append(
            _styled_table(
                _group_summary_rows(group_df, "pipe_group", label, display_unit),
                [9.0 * cm, 5.0 * cm, 6.0 * cm, 6.0 * cm, 7.0 * cm],
                font_size=8.5,
            )
        )
        story.append(Spacer(1, 0.2 * cm))
        story.append(_group_trend_chart(group_df, "pipe_group", f"{label} Repair Ratio Trend", display_unit))
        story.append(Spacer(1, 0.1 * cm))
        story.append(_group_comparison_chart(group_df, "pipe_group", f"{label} Average Repair Ratio", display_unit))

    story.extend([PageBreak(), Paragraph("Critical Pipes", section_style)])

    critical = pipe_df.nlargest(30, ["repair_amount", "repair_ratio"])
    rows = [["Pipe No.", f"Repair Amount ({unit})", "Repair Ratio", "Band Joint Count", "Surface State"]]
    for _, row in critical.iterrows():
        joint_count = "" if pd.isna(row["repair_count"]) else str(int(row["repair_count"]))
        rows.append(
            [
                str(int(row["pipe_no"])),
                f"{amount_in_display_unit(row['repair_amount'], display_unit):,.3f}",
                f"{row['repair_ratio']:.2%}",
                joint_count,
                str(row["surface_state"]),
            ]
        )
    story.append(
        _styled_table(
            rows,
            [5.0 * cm, 7.0 * cm, 6.0 * cm, 6.0 * cm, 12.0 * cm],
            font_size=8.5,
        )
    )
    doc.build(story)
    return buffer.getvalue()


def build_dimension_pipe_pdf_report(
    pipe_df: pd.DataFrame,
    selected_dimension: str,
    selected_projects: pd.DataFrame,
    selected_date,
    display_unit: str = "m",
    worst_top_n: int = 15,
    bin_size: int = 10,
    pipe_group_df: pd.DataFrame | None = None,
    machine_group_df: pd.DataFrame | None = None,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A3),
        leftMargin=1.1 * cm,
        rightMargin=1.1 * cm,
        topMargin=0.9 * cm,
        bottomMargin=0.9 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DimensionReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111827"),
    )
    right_style = ParagraphStyle(
        "DimensionReportMeta",
        parent=styles["Normal"],
        fontSize=8,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#475569"),
    )
    section_style = ParagraphStyle(
        "DimensionReportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#111827"),
        spaceAfter=6,
    )

    report_date = pd.to_datetime(selected_date).date()
    unit = unit_label(display_unit)
    data = pipe_df.copy()
    total_repair_display = amount_in_display_unit(data["repair_amount"].sum(), display_unit)
    worst_ratio = data["repair_ratio"].max() if not data.empty else 0
    project_count = selected_projects["project_no"].nunique() if not selected_projects.empty else data["project_no"].nunique()

    story = [
        Paragraph("Dimension Pipe Analysis", title_style),
        Paragraph(
            f"Report date: {report_date} &nbsp;&nbsp;|&nbsp;&nbsp; Dimension: {escape(str(selected_dimension))}",
            right_style,
        ),
        Spacer(1, 0.25 * cm),
    ]
    kpis = [
        ["Projects", "Pipe Rows", "Average Repair Ratio", "Worst Pipe Ratio", f"Total Repair Amount ({unit})"],
        [
            f"{project_count:,}",
            f"{len(data):,}",
            f"{data['repair_ratio'].mean():.2%}" if not data.empty else "0.00%",
            f"{worst_ratio:.2%}",
            f"{total_repair_display:,.2f}",
        ],
    ]
    story.append(_styled_table(kpis, [5.5 * cm, 5.5 * cm, 6.5 * cm, 6.5 * cm, 7.5 * cm], font_size=10))

    selected_project_rows = [["Project", "Project Sheet", "Pipe Rows", "Avg Repair Ratio", f"Repair Amount ({unit})"]]
    display_data = data.copy()
    display_data["repair_amount_display"] = amount_in_display_unit(display_data["repair_amount"], display_unit)
    project_summary = (
        display_data.groupby(["project_no", "project_sheet"], as_index=False)
        .agg(
            pipe_rows=("pipe_no", "count"),
            avg_repair_ratio=("repair_ratio", "mean"),
            total_repair=("repair_amount_display", "sum"),
        )
        .sort_values("avg_repair_ratio", ascending=False)
    )
    for _, row in project_summary.iterrows():
        selected_project_rows.append(
            [
                escape(str(row["project_no"])),
                escape(str(row["project_sheet"])),
                f"{int(row['pipe_rows']):,}",
                f"{row['avg_repair_ratio']:.2%}",
                f"{row['total_repair']:,.2f}",
            ]
        )
    story.extend(
        [
            Spacer(1, 0.25 * cm),
            _styled_table(
                selected_project_rows,
                [5.0 * cm, 11.0 * cm, 4.5 * cm, 5.5 * cm, 6.5 * cm],
                font_size=8.5,
            ),
            Spacer(1, 0.25 * cm),
        ]
    )

    chart_grid = Table(
        [[_dimension_project_comparison_chart(data, display_unit), _dimension_worst_pipes_chart(data, display_unit, worst_top_n)]],
        colWidths=[20.4 * cm, 20.4 * cm],
        rowHeights=[7.5 * cm],
    )
    chart_grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(chart_grid)

    group_sections: list[tuple[str, str, pd.DataFrame]] = []
    if pipe_group_df is not None and not pipe_group_df.empty:
        group_sections.append(("Saved Pipe Group Analysis", "Pipe Group", pipe_group_df))
    if machine_group_df is not None and not machine_group_df.empty:
        group_sections.append(("Saved Machine Analysis", "Machine", machine_group_df))

    for section_title, label, group_df in group_sections:
        story.extend([PageBreak(), Paragraph(section_title, section_style)])
        story.append(
            _styled_table(
                _group_summary_rows(group_df, "pipe_group", label, display_unit),
                [11.0 * cm, 4.5 * cm, 5.8 * cm, 5.8 * cm, 7.0 * cm],
                font_size=8.2,
            )
        )
        story.append(Spacer(1, 0.2 * cm))
        story.append(
            _group_binned_trend_chart(
                group_df,
                "pipe_group",
                f"{label} Repair Ratio Trend",
                display_unit,
                bin_size,
            )
        )
        story.append(Spacer(1, 0.1 * cm))
        story.append(_group_comparison_chart(group_df, "pipe_group", f"{label} Average Repair Ratio", display_unit))

    story.extend([PageBreak(), Paragraph("Critical Pipes in Dimension", section_style)])
    critical = display_data.nlargest(40, ["repair_amount", "repair_ratio"])
    rows = [["Project", "Pipe No.", f"Repair Amount ({unit})", "Repair Ratio", "Band Joint Count", "Surface State"]]
    for _, row in critical.iterrows():
        pipe_no = "" if pd.isna(row["pipe_no"]) else str(int(float(row["pipe_no"])))
        joint_count = "" if pd.isna(row["repair_count"]) else str(int(float(row["repair_count"])))
        rows.append(
            [
                escape(str(row["project_no"])),
                pipe_no,
                f"{row['repair_amount_display']:,.3f}",
                f"{row['repair_ratio']:.2%}",
                joint_count,
                escape(str(row["surface_state"])),
            ]
        )
    story.append(
        _styled_table(
            rows,
            [5.0 * cm, 4.0 * cm, 6.0 * cm, 5.0 * cm, 5.0 * cm, 12.0 * cm],
            font_size=8.0,
        )
    )

    doc.build(story)
    return buffer.getvalue()
