# Daily Repair Rate Trend Dashboard

Streamlit dashboard for importing and trending the `Daily Repair Rate` sheet from the daily Excel report.

## What It Does

- Uploads the daily Excel file.
- Reads only `Daily Repair Rate!A3:P25`.
- Uses fixed cell/column mapping instead of trusting headers.
- Validates before import.
- Blocks database updates when validation fails.
- Stores master data in SQLite.
- Upserts duplicate `Date + Project No + Dimension` rows.
- Shows repair rate trends and project/dimension analysis.

## Fixed Excel Contract

The parser accepts this workbook structure:

- Sheet: `Daily Repair Rate`
- Report date: `P1`
- Main table: `A3:P25`
- Data rows: `4:25`

The parser intentionally never reads lower tables such as `Repair Rate Calculation`, `Annual Repair Rates`, or `Daily Chart`.

## Column Mapping

| Field | Excel Column |
| --- | --- |
| Project No. | B |
| Dimensions | E |
| Qty. | H |
| Project Total Pipe Length | I |
| Repaired Pipes Total Length | J |
| Repaired Spiral Length | K |
| Total Repair Amount | L |
| Total Repair Amount incl. Skelp | M |
| Project Status | N |
| Repair Ratio | O |
| Repair Ratio incl. Skelp | P |

`Date` comes from `P1` and is applied to all imported rows.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Supabase Setup

Production/deploy için Supabase kullanın. Supabase SQL Editor içinde [supabase_setup.sql](supabase_setup.sql) dosyasındaki SQL'i bir kez çalıştırın.

Local secrets dosyası oluşturun:

```powershell
Copy-Item .streamlit\secrets.example.toml .streamlit\secrets.toml
```

Sonra `.streamlit/secrets.toml` içine kendi değerlerinizi yazın:

```toml
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_KEY = "your-supabase-key"
```

Bu değerler varsa uygulama Supabase kullanır. Yoksa lokal SQLite fallback ile çalışır.

## Run

```powershell
streamlit run app.py
```

The SQLite database is created at:

```text
data/daily_repair_rate.sqlite
```

## Validation Rules

Import is cancelled if any validation error is found:

- Required sheet is missing.
- Report date is empty or invalid.
- No valid main table rows are found.
- Project No. or Dimension is empty.
- Qty or required numeric fields are not numeric.
- Repair Ratio values are outside `0..1`.
- Repair Ratio incl. Skelp is smaller than Repair Ratio.
- Total Repair Amount incl. Skelp is smaller than Total Repair Amount.

Project numbers and dimensions are trimmed, and repeated whitespace is normalized.

## Import Flow

1. Upload Excel.
2. Review validation report.
3. Preview parsed dataframe.
4. Click `Confirm Import`.
5. Data is inserted or updated in SQLite.

Duplicate rule:

```text
date + project_no + dimensions
```

## Dashboard Calculations

Overall repair ratio is weighted, not a simple average:

```text
weighted_repair_ratio = sum(Total Repair Amount) / sum(Project Total Pipe Length)
weighted_repair_ratio_incl_skelp = sum(Total Repair Amount incl. Skelp) / sum(Project Total Pipe Length)
```

Repair ratio values are stored as decimals, for example `0.0402`, and displayed as percentages, for example `4.02%`.
