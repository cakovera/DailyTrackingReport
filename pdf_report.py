from __future__ import annotations

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
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from calculations import (
    METERS_PER_FOOT,
    amount_in_display_unit,
    apply_meter_based_repair_ratios,
    daily_weighted_repair_ratios,
    length_in_display_unit,
    repair_amount_trend_data,
    unit_label,
)


DAILY_REPAIR_VISUAL_SCALE = 100


def _pct(value: float) -> str:
    return f"{value:.2%}" if pd.notna(value) else ""


def _num(value: float) -> str:
    return f"{value:,.2f}" if pd.notna(value) else ""


def _short_num(value: float) -> str:
    if not pd.notna(value):
        return ""
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.1f}"


def _full_num(value: float) -> str:
    return f"{value:,.2f}" if pd.notna(value) else ""


def _add_point_labels(ax, x_values, y_values, formatter, color: str, y_offset: int) -> None:
    for x_value, y_value in zip(x_values, y_values):
        if not pd.notna(y_value):
            continue
        ax.annotate(
            formatter(y_value),
            xy=(x_value, y_value),
            xytext=(0, y_offset),
            textcoords="offset points",
            ha="center",
            va="bottom" if y_offset >= 0 else "top",
            fontsize=6.5,
            color=color,
            fontweight="bold",
            bbox={"boxstyle": "round,pad=0.16", "fc": "white", "ec": color, "lw": 0.4, "alpha": 0.82},
        )


def _table(data, col_widths=None, font_size=8):
    table = Table(data, colWidths=col_widths, repeatRows=1)
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
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _figure_to_image(fig, display_width=19.8 * cm, display_height=7.1 * cm):
    png_buffer = BytesIO()
    fig.savefig(png_buffer, format="png", dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    png_buffer.seek(0)
    return Image(png_buffer, width=display_width, height=display_height)


def _style_axes(ax, title: str, y_percent: bool = False):
    ax.set_title(title, fontsize=12, fontweight="bold", color="#111827", pad=10)
    ax.set_facecolor("#f8fafc")
    ax.grid(True, axis="y", color="#dbe3ef", linewidth=0.8)
    ax.tick_params(axis="both", labelsize=8, colors="#111827")
    for spine in ax.spines.values():
        spine.set_color("#cbd5e1")
    if y_percent:
        ax.yaxis.set_major_formatter(lambda value, _: f"{value:.2%}")


def _overall_chart(df: pd.DataFrame, baseline_df: pd.DataFrame | None = None):
    grouped = daily_weighted_repair_ratios(df, baseline_df)
    fig, ax = plt.subplots(figsize=(7.8, 2.9))
    ax.plot(grouped["date"], grouped["weighted_repair_ratio"], color="#2563eb", linewidth=2.6, marker="o", label="Repair Ratio")
    ax.plot(grouped["date"], grouped["weighted_repair_ratio_incl_skelp"], color="#dc2626", linewidth=2.6, marker="o", label="Repair Ratio incl. Skelp")
    _add_point_labels(ax, grouped["date"], grouped["weighted_repair_ratio"], _pct, "#2563eb", 8)
    _add_point_labels(ax, grouped["date"], grouped["weighted_repair_ratio_incl_skelp"], _pct, "#dc2626", -14)
    max_value = grouped[["weighted_repair_ratio", "weighted_repair_ratio_incl_skelp"]].max().max()
    ax.set_ylim(0, max_value * 1.28 if max_value else 1)
    _style_axes(ax, "Overall Daily Repair Ratio Trend", y_percent=True)
    ax.legend(fontsize=7, loc="best")
    fig.autofmt_xdate(rotation=20)
    return _figure_to_image(fig)


def _worst_projects_chart(df: pd.DataFrame, selected_date):
    daily = apply_meter_based_repair_ratios(df[df["date"].dt.date == selected_date]).nlargest(10, "repair_ratio").sort_values("repair_ratio").copy()
    daily["project_dimension"] = daily["project_no"] + " | " + daily["dimensions"]
    fig, ax = plt.subplots(figsize=(7.8, 2.9))
    bar_colors = ["#16a34a" if status == "Completed" else "#f97316" for status in daily["project_status"]]
    bars = ax.barh(daily["project_dimension"], daily["repair_ratio"], color=bar_colors)
    ax.bar_label(bars, labels=[_pct(value) for value in daily["repair_ratio"]], padding=3, fontsize=7, fontweight="bold")
    max_value = daily["repair_ratio"].max()
    ax.set_xlim(0, max_value * 1.22 if pd.notna(max_value) and max_value else 1)
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.2%}")
    _style_axes(ax, "Worst Projects Today")
    ax.tick_params(axis="y", labelsize=7)
    return _figure_to_image(fig)


def _dimension_chart(daily: pd.DataFrame):
    daily = apply_meter_based_repair_ratios(daily)
    grouped = daily.groupby("dimensions", as_index=False)["repair_ratio"].mean().sort_values("repair_ratio", ascending=False).head(12)
    fig, ax = plt.subplots(figsize=(7.8, 2.9))
    bars = ax.bar(grouped["dimensions"], grouped["repair_ratio"], color="#0891b2")
    ax.bar_label(bars, labels=[_pct(value) for value in grouped["repair_ratio"]], padding=3, fontsize=6.5, fontweight="bold", rotation=90)
    max_value = grouped["repair_ratio"].max()
    ax.set_ylim(0, max_value * 1.28 if pd.notna(max_value) and max_value else 1)
    _style_axes(ax, "Dimension Analysis", y_percent=True)
    ax.tick_params(axis="x", labelrotation=35, labelsize=7)
    return _figure_to_image(fig)


def _amount_chart(df: pd.DataFrame, display_unit: str = "m"):
    unit = unit_label(display_unit)
    grouped = repair_amount_trend_data(df, display_unit)
    grouped["daily_repair_amount_scaled_display"] = grouped["daily_repair_amount_display"] * DAILY_REPAIR_VISUAL_SCALE

    fig, ax = plt.subplots(figsize=(7.8, 2.9))
    x_positions = range(len(grouped))
    ax.plot(
        x_positions,
        grouped["daily_repair_amount_scaled_display"],
        color="#a855f7",
        linewidth=2.3,
        linestyle=":",
        marker="o",
        label=f"Daily Repair Amount (x{DAILY_REPAIR_VISUAL_SCALE} visual scale)",
    )
    for x_value, scaled_value, actual_value in zip(
        x_positions,
        grouped["daily_repair_amount_scaled_display"],
        grouped["daily_repair_amount_display"],
    ):
        if not pd.notna(actual_value) or not pd.notna(scaled_value):
            continue
        ax.annotate(
            _full_num(actual_value),
            xy=(x_value, scaled_value),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=6.4,
            color="#581c87",
            fontweight="bold",
            bbox={"boxstyle": "round,pad=0.14", "fc": "white", "ec": "#a855f7", "lw": 0.4, "alpha": 0.82},
        )
    ax.plot(
        x_positions,
        grouped["total_repair_amount_display"],
        color="#7c3aed",
        linewidth=2.6,
        marker="o",
        label="Total Repair Amount",
    )
    _add_point_labels(ax, x_positions, grouped["total_repair_amount_display"], _short_num, "#7c3aed", 8)
    max_value = grouped[
        [
            "total_repair_amount_display",
            "daily_repair_amount_scaled_display",
        ]
    ].max().max()
    ax.set_ylim(0, max_value * 1.28 if max_value else 1)
    _style_axes(ax, f"Repair Amount Trend ({unit}) - Daily shown as x{DAILY_REPAIR_VISUAL_SCALE}")
    ax.set_ylabel(f"Total Repair Amount ({unit})", fontsize=8)
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels([value.strftime("%Y-%m-%d") for value in grouped["date"]], rotation=20, ha="right")
    ax.legend(fontsize=6.4, loc="best")
    return _figure_to_image(fig)


def build_a3_pdf_report(
    df: pd.DataFrame,
    selected_date,
    statuses: list[str],
    baseline_df: pd.DataFrame | None = None,
    display_unit: str = "m",
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
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111827"),
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#111827"),
        spaceBefore=8,
        spaceAfter=5,
    )
    right_style = ParagraphStyle(
        "Right",
        parent=styles["Normal"],
        fontSize=8,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#475569"),
    )

    report_date = pd.to_datetime(selected_date).date()
    daily = apply_meter_based_repair_ratios(df[df["date"].dt.date == report_date])
    unit = unit_label(display_unit)

    total_length = daily["project_total_pipe_length"].sum()
    total_spiral_length = daily["repaired_spiral_length"].sum()
    baseline_repair = baseline_df["total_repair_amount"].sum() if baseline_df is not None and not baseline_df.empty else 0
    baseline_repair_incl = baseline_df["total_repair_amount_incl_skelp"].sum() if baseline_df is not None and not baseline_df.empty else 0
    baseline_spiral = baseline_df["repaired_spiral_length"].sum() if baseline_df is not None and not baseline_df.empty else 0
    total_spiral_with_baseline = total_spiral_length + baseline_spiral
    weighted_ratio = (
        (daily["total_repair_amount"].sum() + baseline_repair) / (total_spiral_with_baseline * METERS_PER_FOOT)
    ) if total_spiral_with_baseline else 0
    weighted_ratio_incl = (
        (daily["total_repair_amount_incl_skelp"].sum() + baseline_repair_incl) / (total_spiral_with_baseline * METERS_PER_FOOT)
    ) if total_spiral_with_baseline else 0

    story = [
        Paragraph("Daily Repair Rate Trend Dashboard", title_style),
        Paragraph(
            f"Report date: {report_date} &nbsp;&nbsp;|&nbsp;&nbsp; Display unit: {unit} &nbsp;&nbsp;|&nbsp;&nbsp; Status filter: {', '.join(statuses) if statuses else 'All'}",
            right_style,
        ),
        Spacer(1, 0.25 * cm),
    ]

    kpis = [
        [
            "Projects",
            f"Total Pipe Length ({unit})",
            f"Total Repair Amount ({unit})",
            f"Repair Amount incl. Skelp ({unit})",
            "Weighted Repair Ratio",
            "Weighted Ratio incl. Skelp",
        ],
        [
            f"{len(daily):,}",
            _num(length_in_display_unit(daily["project_total_pipe_length"].sum(), display_unit)),
            _num(amount_in_display_unit(daily["total_repair_amount"].sum(), display_unit)),
            _num(amount_in_display_unit(daily["total_repair_amount_incl_skelp"].sum(), display_unit)),
            _pct(weighted_ratio),
            _pct(weighted_ratio_incl),
        ],
    ]
    story.append(_table(kpis, col_widths=[4.0 * cm, 5.0 * cm, 5.2 * cm, 5.8 * cm, 5.0 * cm, 5.4 * cm], font_size=10))

    chart_grid = Table(
        [
            [
                _overall_chart(df, baseline_df),
                _worst_projects_chart(df, report_date),
            ],
            [
                _dimension_chart(daily),
                _amount_chart(df, display_unit),
            ],
        ],
        colWidths=[20.4 * cm, 20.4 * cm],
        rowHeights=[7.6 * cm, 7.6 * cm],
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

    worst = daily.nlargest(12, "repair_ratio")[
        [
            "project_no",
            "dimensions",
            "qty",
            "project_total_pipe_length",
            "total_repair_amount",
            "total_repair_amount_incl_skelp",
            "project_status",
            "repair_ratio",
            "repair_ratio_incl_skelp",
        ]
    ]
    worst_rows = [["Project No.", "Dimension", "Qty", f"Pipe Length ({unit})", f"Repair Amt ({unit})", f"Repair Amt incl. ({unit})", "Status", "Ratio", "Ratio incl."]]
    for _, row in worst.iterrows():
        worst_rows.append(
            [
                row["project_no"],
                row["dimensions"],
                _num(row["qty"]),
                _num(length_in_display_unit(row["project_total_pipe_length"], display_unit)),
                _num(amount_in_display_unit(row["total_repair_amount"], display_unit)),
                _num(amount_in_display_unit(row["total_repair_amount_incl_skelp"], display_unit)),
                row["project_status"],
                _pct(row["repair_ratio"]),
                _pct(row["repair_ratio_incl_skelp"]),
            ]
        )
    story.extend([Paragraph("Worst Projects Today", section_style), _table(worst_rows, font_size=7.4)])

    dimension = (
        daily.groupby("dimensions", as_index=False)
        .agg(avg_repair_ratio=("repair_ratio", "mean"), projects=("project_no", "count"), total_repair_amount=("total_repair_amount", "sum"))
        .sort_values("avg_repair_ratio", ascending=False)
        .head(12)
    )
    dim_rows = [["Dimension", "Projects", "Average Repair Ratio", f"Total Repair Amount ({unit})"]]
    for _, row in dimension.iterrows():
        dim_rows.append(
            [
                row["dimensions"],
                f"{int(row['projects'])}",
                _pct(row["avg_repair_ratio"]),
                _num(amount_in_display_unit(row["total_repair_amount"], display_unit)),
            ]
        )

    trend = daily_weighted_repair_ratios(df, baseline_df).tail(10)
    trend_rows = [["Date", "Weighted Ratio", "Weighted Ratio incl.", f"Repair Amount ({unit})", f"Repair Amount incl. ({unit})"]]
    for _, row in trend.iterrows():
        trend_rows.append(
            [
                row["date"].strftime("%Y-%m-%d"),
                _pct(row["weighted_repair_ratio"]),
                _pct(row["weighted_repair_ratio_incl_skelp"]),
                _num(amount_in_display_unit(row["total_repair_amount"], display_unit)),
                _num(amount_in_display_unit(row["total_repair_amount_incl_skelp"], display_unit)),
            ]
        )

    two_col = Table(
        [
            [Paragraph("Dimension Analysis", section_style), Paragraph("Recent Daily Trend", section_style)],
            [_table(dim_rows, col_widths=[8.0 * cm, 2.2 * cm, 4.5 * cm, 4.5 * cm], font_size=7.8), _table(trend_rows, font_size=7.8)],
        ],
        colWidths=[20.5 * cm, 20.5 * cm],
    )
    two_col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(two_col)

    doc.build(story)
    return buffer.getvalue()
