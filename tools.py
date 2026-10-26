"""Deterministic data tools over the Berkeley Lab PJM data. The agents call these; no LLM here.

Every tool result carries `cite` IDs. The verifier only accepts citations that a tool actually returned.
"""
import json

import pandas as pd

from config import DATA

QUEUE = pd.read_csv(DATA / "queue_pjm.csv")
COSTS = pd.read_csv(DATA / "costs_pjm.csv")
RULES = json.loads((DATA / "state_rules.json").read_text(encoding="utf-8"))

SOLAR_Q = {"Solar", "Battery", "Solar+Battery"}
SOLAR_C = {"Solar", "Solar Hybrid", "Storage"}
Q = QUEUE[QUEUE.type_clean.isin(SOLAR_Q) & (QUEUE.q_year >= 2015)]
C = COSTS[COSTS.fuel.isin(SOLAR_C) & (COSTS.study_year >= 2017)]
STATES = sorted(RULES)


def norm_county(county: str) -> str:
    c = (county or "").strip().title()
    for suffix in (" County", " City", " Co."):
        c = c.removesuffix(suffix)
    return c.removeprefix("City Of ").strip()


def _wd_rate(df) -> float | None:
    done = df[df.q_status.isin(["withdrawn", "operational"])]
    return round(float((done.q_status == "withdrawn").mean()), 2) if len(done) else None


def queue_history(state: str, county: str) -> dict:
    """Solar/storage queue outcomes in a county since 2015 vs. the state."""
    state, county = state.upper(), norm_county(county)
    d = Q[(Q.state == state) & (Q.county == county)]
    s = Q[Q.state == state]
    cite = f"LBNL-QUEUE:{state}-{county}"
    if d.empty:
        return {"found": False, "cite": cite, "note": f"No solar/storage queue requests in {county}, {state} since 2015."}
    return {
        "found": True, "cite": cite,
        "requests": len(d),
        "withdrawn": int((d.q_status == "withdrawn").sum()),
        "active": int((d.q_status == "active").sum()),
        "operational": int((d.q_status == "operational").sum()),
        "county_withdrawal_rate": _wd_rate(d),
        "state_withdrawal_rate": _wd_rate(s),
        "active_mw": round(d[d.q_status == "active"].mw.sum()),
        "main_utility": d.utility.mode().iat[0],
    }


def upgrade_costs(state: str, county: str) -> dict:
    """Historical network-upgrade cost levels from PJM studies (2017+), county vs. utility vs. 3-state pool."""
    state, county = state.upper(), norm_county(county)
    d = C[(C.state == state) & (C.county == county)]
    util = Q[(Q.state == state) & (Q.county == county)].utility.mode()
    util = util.iat[0] if len(util) else None
    u = C[C.utility == util] if util else C.iloc[0:0]
    pool_med = C.network_kw.median()
    out = {"cite": f"LBNL-COST:{state}-{county}", "pool_median_network_kw": round(pool_med),
           "county_studies": len(d), "utility": util, "utility_studies": len(u)}
    if util:
        out["utility_cite"] = f"LBNL-COST:{util}"
        out["utility_median_network_kw"] = round(u.network_kw.median()) if len(u) else None
    if len(d):
        med = d.network_kw.median()
        out.update(county_median_network_kw=round(med),
                   county_percentile_vs_pool=round((C.network_kw < med).mean() * 100),
                   county_share_over_200_kw=round(float((d.network_kw > 200).mean()), 2))
    return out


def poi_crowding(state: str, county: str) -> dict:
    """How many active solar/storage requests share the same substations (shared-upgrade / reallocation risk)."""
    state, county = state.upper(), norm_county(county)
    a = Q[(Q.state == state) & (Q.county == county) & (Q.q_status == "active")]
    cite = f"LBNL-POI:{state}-{county}"
    if a.empty:
        return {"found": False, "cite": cite, "note": "No active solar/storage requests in county."}
    g = a.groupby("poi_name").agg(n=("q_id", "size"), mw=("mw", "sum")).sort_values("mw", ascending=False)
    cd = C[(C.state == state) & (C.county == county)].network_kw
    spread = round(float((cd.quantile(.75) - cd.quantile(.25)) / max(cd.median(), 1)), 1) if len(cd) >= 4 else None
    return {
        "found": True, "cite": cite,
        "active_requests": len(a), "substations": len(g),
        "shared_substations": int((g.n >= 2).sum()),
        "max_active_mw_one_substation": round(g.mw.iat[0]),
        "top_substations": g.head(3).index.tolist(),
        "cost_spread_iqr_over_median": spread,
    }


def state_rules(state: str) -> dict:
    """Permitting regime for the state (curated from statutes)."""
    r = RULES.get(state.upper())
    if not r:
        return {"found": False, "cite": f"RULES:{state.upper()}", "note": f"Only {', '.join(STATES)} are covered."}
    return {"found": True, "cite": f"RULES:{state.upper()}", **r}


TOOLS = {f.__name__: f for f in (queue_history, upgrade_costs, poi_crowding, state_rules)}

_SC = {"type": "object", "additionalProperties": False, "required": ["state", "county"],
       "properties": {"state": {"type": "string", "enum": STATES}, "county": {"type": "string"}}}
TOOL_SCHEMAS = [
    {"type": "function", "name": n, "description": f.__doc__, "strict": True,
     "parameters": _SC if n != "state_rules" else
     {"type": "object", "additionalProperties": False, "required": ["state"],
      "properties": {"state": {"type": "string", "enum": STATES}}}}
    for n, f in TOOLS.items()
]


def chart_data(state: str, county: str) -> dict:
    """Numbers for the UI mini-charts (not sent to the model)."""
    state, county = state.upper(), norm_county(county)
    d = C[(C.state == state) & (C.county == county)].network_kw.tolist()
    qh = queue_history(state, county)
    pct = round(float((C.network_kw < pd.Series(d).median()).mean() * 100)) if d else None
    return {"pct": pct, "county": d,
            "county_wd": qh.get("county_withdrawal_rate"), "state_wd": _wd_rate(Q[Q.state == state])}
