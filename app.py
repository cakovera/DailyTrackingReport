from __future__ import annotations

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

# Pipe-level analysis is optional so a partial/stale cloud deployment cannot
# prevent the core repair-rate dashboard from starting.
try:
    from project_parser import parse_project_pipe_repairs
    from pipe_analysis import reconcile_pipe_projects

    load_pipe_repair_details = db.load_pipe_repair_details
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


with st.sidebar:
    st.header("Import")
    uploaded = st.file_uploader("Daily Activity Excel", type=["xlsx"])
    backend = get_backend_name()
    if backend == "supabase":
        st.caption("Database: Supabase")
    else:
        st.caption(f"Database: SQLite ({DB_PATH})")
    st.divider()
    st.header("Display")
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
    master_df = load_master_data()
    baseline_master_df = load_historical_baselines()
    pipe_master_df = load_pipe_repair_details() if PIPE_ANALYSIS_AVAILABLE else pd.DataFrame()
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
selected_pipe_df = (
    pipe_master_df[pipe_master_df["date"].dt.date == selected_date].copy()
    if not pipe_master_df.empty and "date" in pipe_master_df.columns
    else pd.DataFrame()
)

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

st.plotly_chart(charts.overall_daily_trend(filtered_to_selected_date, baseline_for_filtered), use_container_width=True)
if baseline_for_filtered.empty:
    st.caption("Historical baseline is not loaded.")
else:
    st.caption(f"Historical baseline included in overall weighted ratios: {len(baseline_for_filtered)} projects")

left, right = st.columns(2)
with left:
    st.plotly_chart(charts.worst_projects_today(selected_date_df, selected_date), use_container_width=True)
with right:
    projects = sorted(selected_date_df["project_no"].unique())
    selected_project = st.selectbox("Project", projects)
    st.plotly_chart(charts.project_trend(filtered_to_selected_date, selected_project), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(
        charts.production_type_analysis(selected_date_df, baseline_for_filtered),
        use_container_width=True,
    )
with right:
    st.plotly_chart(charts.dimension_analysis(selected_date_df), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(charts.status_comparison(selected_date_df, display_unit), use_container_width=True)
with right:
    st.plotly_chart(charts.historical_benchmark_comparison(selected_date_df, baseline_for_filtered), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(charts.skelp_impact_analysis(selected_date_df, display_unit), use_container_width=True)
with right:
    st.plotly_chart(charts.repair_amount_pareto(selected_date_df, display_unit), use_container_width=True)

if not selected_pipe_df.empty and PIPE_ANALYSIS_AVAILABLE:
    reconciled_projects = reconcile_pipe_projects(selected_date_df, selected_pipe_df)
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
        project_pipe_df = selected_pipe_df[
            selected_pipe_df["project_sheet"].eq(selected_sheet)
        ].copy()

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Pipe Rows", int(reconciliation["pipe_rows"]))
        k2.metric("Pipe Repair Total", f"{reconciliation['pipe_repair_amount']:,.2f} m")
        k3.metric("Master Repair Total", f"{reconciliation['expected_repair_amount']:,.2f} m")
        k4.metric("Joint Count Coverage", f"{reconciliation['joint_count_coverage']:.0%}")
        st.success(
            "Reconciliation passed. "
            f"Difference: {reconciliation['difference_m']:+.4f} m."
        )

        left, right = st.columns(2)
        with left:
            st.plotly_chart(charts.pipe_repair_amount_pareto(project_pipe_df), use_container_width=True)
        with right:
            st.plotly_chart(charts.pipe_worst_ratio(project_pipe_df), use_container_width=True)
        left, right = st.columns(2)
        with left:
            st.plotly_chart(charts.pipe_joint_count_distribution(project_pipe_df), use_container_width=True)
        with right:
            st.plotly_chart(charts.pipe_joint_count_vs_repair(project_pipe_df), use_container_width=True)

        critical_pipes = (
            project_pipe_df.nlargest(15, ["repair_amount", "repair_ratio"])[
                ["pipe_no", "repair_amount", "repair_ratio", "repair_count", "surface_state"]
            ]
            .rename(
                columns={
                    "pipe_no": "Pipe No.",
                    "repair_amount": "Repair Amount (m)",
                    "repair_ratio": "Repair Ratio",
                    "repair_count": "Bant Eki Adedi",
                    "surface_state": "Surface State",
                }
            )
        )
        st.dataframe(
            critical_pipes.style.format(
                {"Repair Amount (m)": "{:,.3f}", "Repair Ratio": "{:.2%}"}
            ),
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("Pipe-level project sheet data is not loaded for the selected date.")

st.plotly_chart(charts.repair_amount_trend(filtered_to_selected_date, display_unit), use_container_width=True)

with st.expander("Master data"):
    st.dataframe(format_preview(filtered, display_unit), use_container_width=True)
