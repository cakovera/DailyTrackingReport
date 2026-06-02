from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
from database import DB_PATH, get_backend_name, get_existing_keys, load_master_data, upsert_repair_rates
from parser import parse_daily_repair_rate
from pdf_report import build_a3_pdf_report
from validators import mark_duplicate_counts


st.set_page_config(page_title="Daily Repair Rate Trend Dashboard", layout="wide")
st.title("Daily Repair Rate Trend Dashboard")

if "last_import_summary" not in st.session_state:
    st.session_state.last_import_summary = None
if "pdf_report" not in st.session_state:
    st.session_state.pdf_report = None
if "pdf_report_name" not in st.session_state:
    st.session_state.pdf_report_name = None


def format_preview(df: pd.DataFrame) -> pd.DataFrame:
    out = df.drop(columns=["excel_row"], errors="ignore").copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
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

if uploaded is not None:
    parsed_df, report = parse_daily_repair_rate(uploaded)
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
        st.dataframe(format_preview(parsed_df), use_container_width=True)
        if st.button("Confirm Import", type="primary"):
            try:
                affected = upsert_repair_rates(parsed_df)
                st.session_state.last_import_summary = {
                    "affected": affected,
                    "updated": report.update_rows,
                    "inserted": report.insert_rows,
                    "date": parsed_df["date"].iloc[0],
                }
                st.success(f"Import tamamlandı. {affected} satır işlendi.")
            except Exception as exc:
                st.error("Import sırasında database yazma hatası oluştu. Master data güncellenmedi.")
                st.info("Supabase kullanıyorsanız RLS insert/update policy veya service-role key ayarı gerekir.")
                st.code(str(exc), language="text")

if st.session_state.last_import_summary:
    summary = st.session_state.last_import_summary
    st.success(
        "Son import: "
        f"{summary['date']} için {summary['affected']} satır işlendi "
        f"({summary['inserted']} yeni, {summary['updated']} update)."
    )

st.divider()

try:
    master_df = load_master_data()
except Exception as exc:
    st.error("Database bağlantısı kurulamadı veya Supabase tablosu hazır değil.")
    st.info("Supabase kullanıyorsanız önce SQL Editor içinde supabase_setup.sql dosyasındaki script'i çalıştırın.")
    st.code(str(exc), language="text")
    st.stop()
if master_df.empty:
    st.info("Dashboard için master database içinde veri yok. Önce geçerli bir Excel dosyası import edin.")
    st.stop()

status_options = sorted(master_df["project_status"].dropna().unique())
default_status = [s for s in ["Completed", "In Progress"] if s in status_options] or status_options
selected_status = st.multiselect("Status Filter", status_options, default=default_status)
filtered = master_df[master_df["project_status"].isin(selected_status)] if selected_status else master_df

if filtered.empty:
    st.warning("Seçili filtrelerle veri bulunamadı.")
    st.stop()

available_dates = sorted(filtered["date"].dt.date.unique())
selected_date = st.selectbox("Date", available_dates, index=len(available_dates) - 1)

if st.button("Generate A3 PDF Report"):
    with st.spinner("A3 PDF report hazırlanıyor..."):
        st.session_state.pdf_report = build_a3_pdf_report(filtered, selected_date, selected_status)
        st.session_state.pdf_report_name = f"daily_repair_rate_report_{selected_date}.pdf"

if st.session_state.pdf_report:
    st.download_button(
        "Download A3 PDF Report",
        data=st.session_state.pdf_report,
        file_name=st.session_state.pdf_report_name,
        mime="application/pdf",
    )

st.plotly_chart(charts.overall_daily_trend(filtered), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(charts.worst_projects_today(filtered, selected_date), use_container_width=True)
with right:
    projects = sorted(filtered["project_no"].unique())
    selected_project = st.selectbox("Project", projects)
    st.plotly_chart(charts.project_trend(filtered, selected_project), use_container_width=True)

left, right = st.columns(2)
with left:
    st.plotly_chart(charts.dimension_analysis(filtered), use_container_width=True)
with right:
    st.plotly_chart(charts.repair_amount_trend(filtered), use_container_width=True)

with st.expander("Master data"):
    st.dataframe(format_preview(filtered), use_container_width=True)
