from __future__ import annotations

from io import BytesIO

import pandas as pd
import plotly.io as pio
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import charts


def _pct(value: float) -> str:
    return f"{value:.2%}" if pd.notna(value) else ""


def _num(value: float) -> str:
    return f"{value:,.2f}" if pd.notna(value) else ""


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


def _chart_image(fig, width_px=900, height_px=320, display_width=19.8 * cm, display_height=7.1 * cm):
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="#f8fafc",
        margin={"l": 55, "r": 25, "t": 55, "b": 55},
        font={"size": 14, "color": "#111827"},
        legend={"orientation": "h", "y": -0.22},
    )
    fig.update_xaxes(showgrid=True, gridcolor="#dbe3ef", zeroline=False, tickfont={"color": "#111827", "size": 12})
    fig.update_yaxes(showgrid=True, gridcolor="#dbe3ef", zeroline=False, tickfont={"color": "#111827", "size": 12})
    png = pio.to_image(fig, format="png", width=width_px, height=height_px, scale=1)
    return Image(BytesIO(png), width=display_width, height=display_height)


def build_a3_pdf_report(df: pd.DataFrame, selected_date, statuses: list[str]) -> bytes:
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
    daily = df[df["date"].dt.date == report_date].copy()

    total_length = daily["project_total_pipe_length"].sum()
    weighted_ratio = daily["total_repair_amount"].sum() / total_length if total_length else 0
    weighted_ratio_incl = daily["total_repair_amount_incl_skelp"].sum() / total_length if total_length else 0

    story = [
        Paragraph("Daily Repair Rate Trend Dashboard", title_style),
        Paragraph(
            f"Report date: {report_date} &nbsp;&nbsp;|&nbsp;&nbsp; Status filter: {', '.join(statuses) if statuses else 'All'}",
            right_style,
        ),
        Spacer(1, 0.25 * cm),
    ]

    kpis = [
        ["Projects", "Total Pipe Length", "Total Repair Amount", "Repair Amount incl. Skelp", "Weighted Repair Ratio", "Weighted Ratio incl. Skelp"],
        [
            f"{len(daily):,}",
            _num(daily["project_total_pipe_length"].sum()),
            _num(daily["total_repair_amount"].sum()),
            _num(daily["total_repair_amount_incl_skelp"].sum()),
            _pct(weighted_ratio),
            _pct(weighted_ratio_incl),
        ],
    ]
    story.append(_table(kpis, col_widths=[4.0 * cm, 5.0 * cm, 5.2 * cm, 5.8 * cm, 5.0 * cm, 5.4 * cm], font_size=10))

    chart_grid = Table(
        [
            [
                _chart_image(charts.overall_daily_trend(df)),
                _chart_image(charts.worst_projects_today(df, report_date)),
            ],
            [
                _chart_image(charts.dimension_analysis(daily)),
                _chart_image(charts.repair_amount_trend(df)),
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
    worst_rows = [["Project No.", "Dimension", "Qty", "Pipe Length", "Repair Amt", "Repair Amt incl.", "Status", "Ratio", "Ratio incl."]]
    for _, row in worst.iterrows():
        worst_rows.append(
            [
                row["project_no"],
                row["dimensions"],
                _num(row["qty"]),
                _num(row["project_total_pipe_length"]),
                _num(row["total_repair_amount"]),
                _num(row["total_repair_amount_incl_skelp"]),
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
    dim_rows = [["Dimension", "Projects", "Average Repair Ratio", "Total Repair Amount"]]
    for _, row in dimension.iterrows():
        dim_rows.append([row["dimensions"], f"{int(row['projects'])}", _pct(row["avg_repair_ratio"]), _num(row["total_repair_amount"])])

    trend = (
        df.groupby("date", as_index=False)
        .agg(
            total_repair_amount=("total_repair_amount", "sum"),
            total_repair_amount_incl_skelp=("total_repair_amount_incl_skelp", "sum"),
            project_total_pipe_length=("project_total_pipe_length", "sum"),
        )
        .sort_values("date")
        .tail(10)
    )
    trend["weighted_repair_ratio"] = trend["total_repair_amount"] / trend["project_total_pipe_length"]
    trend["weighted_repair_ratio_incl_skelp"] = trend["total_repair_amount_incl_skelp"] / trend["project_total_pipe_length"]
    trend_rows = [["Date", "Weighted Ratio", "Weighted Ratio incl.", "Repair Amount", "Repair Amount incl."]]
    for _, row in trend.iterrows():
        trend_rows.append(
            [
                row["date"].strftime("%Y-%m-%d"),
                _pct(row["weighted_repair_ratio"]),
                _pct(row["weighted_repair_ratio_incl_skelp"]),
                _num(row["total_repair_amount"]),
                _num(row["total_repair_amount_incl_skelp"]),
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
