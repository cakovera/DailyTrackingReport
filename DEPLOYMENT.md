# Streamlit + Supabase Deployment

## Required Files In GitHub

Repository root must include:

- `app.py`
- `parser.py`
- `validators.py`
- `database.py`
- `charts.py`
- `pdf_report.py`
- `requirements.txt`
- `supabase_setup.sql`
- `.streamlit/config.toml`

Do not commit:

- `.streamlit/secrets.toml`
- `data/`
- `work/`
- `*.sqlite`

## Streamlit Community Cloud Deploy

1. Go to Streamlit Community Cloud.
2. Click `Create app`.
3. If the repo is not listed, paste the GitHub repository URL manually.
4. Select the correct branch, usually `main`.
5. Set main file path to:

```text
app.py
```

6. Open `Advanced settings`.
7. Add secrets:

```toml
SUPABASE_URL = "https://rtvqqmhtlbjtxfenixdl.supabase.co"
SUPABASE_KEY = "your-supabase-key"
```

8. Click `Deploy`.

## If The GitHub Repo Does Not Show

Check these items:

- Make sure you are in the Streamlit workspace matching the GitHub repo owner.
- If the repo is private, update GitHub authorization so Streamlit can access private repositories.
- If the repo belongs to a GitHub organization, authorize Streamlit for that organization.
- Paste the repository URL manually instead of using the dropdown.
- Confirm the pushed branch is the same branch selected in Streamlit.

## After Deploy

Upload the daily Excel file, review validation, then click `Confirm Import`.

If the sidebar says `Database: Supabase`, the cloud app is using persistent Supabase storage.
