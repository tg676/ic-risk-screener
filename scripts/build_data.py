"""One-time: shrink the two Berkeley Lab workbooks into small CSVs the app ships with.

Raw files (not committed, ~16 MB) go in data/raw/:
  queued_up.xlsx  https://eta-publications.lbl.gov/sites/default/files/2025-08/lbnl_ix_queue_data_file_thru2024_v2.xlsx
  pjm_costs.xlsx  https://eta-publications.lbl.gov/sites/default/files/pjm_costs_2022_clean_data.xlsx
Run:  python scripts/build_data.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data"
STATES = ["VA", "PA", "OH"]


def excel_date(s):
    return pd.to_datetime(pd.to_numeric(s, errors="coerce"), unit="D", origin="1899-12-30")


q = pd.read_excel(RAW / "queued_up.xlsx", "03. Complete Queue Data", header=1)
q = q[(q.entity == "PJM") & q.state.isin(STATES)].copy()
q["county"] = q.county.fillna("").str.replace(r"^City Of ", "", regex=True).str.strip().str.title()
q["wd_year"] = excel_date(q.wd_date).dt.year
q["mw"] = q[["mw1", "mw2", "mw3"]].sum(axis=1, min_count=1)
queue = q[["q_id", "q_status", "q_year", "wd_year", "state", "county", "poi_name", "utility", "type_clean", "mw"]]
queue.to_csv(OUT / "queue_pjm.csv", index=False)

c = pd.read_excel(RAW / "pjm_costs.xlsx", "data")
c = c[c.State.isin(STATES)].rename(columns={
    "Project #": "q_id", "State": "state", "Transmission Owner": "utility", "Fuel": "fuel",
    "Nameplate MW": "mw", "Request Status": "status", "$2022 Network Cost/kW": "network_kw",
    "$2022 Total Cost/kW": "total_kw"})
c["study_year"] = pd.to_datetime(c["Study Date"]).dt.year
c = c.merge(queue[["q_id", "county", "poi_name"]], on="q_id", how="left")
costs = c[["q_id", "state", "county", "poi_name", "utility", "fuel", "mw", "status", "study_year", "network_kw", "total_kw"]]
costs.round(1).to_csv(OUT / "costs_pjm.csv", index=False)

print(f"queue rows: {len(queue)}  cost rows: {len(costs)}  costs with county: {costs.county.notna().sum()}")
