"""Audit trail for every rating. Re-applies the Risk Analyst's written rubric in plain code to the exact tool results
the analyst saw, so a reviewer can see which numbers mattered, which rule fired, and whether the AI's color matches.
Also returns the underlying Berkeley Lab project records behind each driver. No LLM here.
"""
import pandas as pd

from tools import C, Q, RULES, norm_county

LABEL = {"lower": "Lower risk", "higher": "Higher risk", "watch": "Watch", "uncertain": "Uncertain"}


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _tool(trace, name):
    return next((t["result"] for t in trace if t["tool"] == name), {})


def _chk(metric, value, rule, hit):
    return {"metric": metric, "value": value, "rule": rule, "hit": bool(hit)}


def _fmt(v, unit=""):
    return "unknown" if v is None or v == "unknown" else f"{v:,}{unit}" if isinstance(v, (int, float)) else str(v)


def network(site, trace):
    u = _tool(trace, "upgrade_costs")
    n, pct, share = u.get("county_studies", 0), u.get("county_percentile_vs_pool"), u.get("county_share_over_200_kw")
    umed, pool = u.get("utility_median_network_kw"), u.get("pool_median_network_kw") or 0
    thin, util_flag = n < 3, bool(umed and pool and umed >= 2 * pool)
    hi = not thin and ((pct or 0) >= 65 or (share or 0) >= 0.3)
    lo = not thin and not hi and (pct or 100) <= 40
    rating = ("watch" if util_flag else "uncertain") if thin else "higher" if hi else "lower" if lo else "watch"
    checks = [
        _chk("County studies (2017–2022)", n, "fewer than 3 → too thin to rate", thin),
        _chk("County percentile vs. 582 PJM studies", _ord(pct) if pct is not None else "n/a", "≥ 65th → Higher", (pct or 0) >= 65),
        _chk("Share of county studies above $200/kW", f"{share:.0%}" if share is not None else "n/a",
             "≥ 30% → Higher", (share or 0) >= 0.3),
        _chk("County percentile", _ord(pct) if pct is not None else "n/a", "≤ 40th (with 3+ studies) → Lower", lo),
        _chk(f"Utility ({u.get('utility') or '?'}) median vs. pool median", "2× or more" if util_flag else "below 2×",
             "if county is thin: utility ≥ 2× pool → Watch", thin and util_flag),
    ]
    key = f"{_ord(pct)} pctile · {n} {'study' if n == 1 else 'studies'}" if n else "no county studies"
    return rating, checks, key


def allocation(site, trace):
    p, q = _tool(trace, "poi_crowding"), _tool(trace, "queue_history")
    if not p.get("found"):
        return "uncertain", [_chk("Active requests in county", 0, "none → no basis to rate", True)], "no active requests"
    shared, mx, spread = p.get("shared_substations", 0), p.get("max_active_mw_one_substation", 0), p.get("cost_spread_iqr_over_median")
    hi = shared >= 2 or mx >= 300 or (spread or 0) >= 2
    watch = not hi and (shared == 1 or (spread or 0) >= 1)
    rating = "higher" if hi else "watch" if watch else "lower"
    checks = [
        _chk("Substations shared by 2+ active requests", shared, "≥ 2 → Higher · 1 → Watch", shared >= 1),
        _chk("Most active MW queued at one substation", f"{mx:,} MW", "≥ 300 MW → Higher", mx >= 300),
        _chk("Cost spread across county studies (IQR ÷ median)", spread if spread is not None else "n/a (<4 studies)",
             "≥ 2 → Higher · ≥ 1 → Watch", (spread or 0) >= 1),
        _chk("County vs. state withdrawal rate (context)",
             f"{q.get('county_withdrawal_rate', 0):.0%} vs. {q.get('state_withdrawal_rate', 0):.0%}" if q.get("found") else "n/a",
             "each withdrawal can trigger restudies", False),
    ]
    parts = [f"{shared} shared subs", f"{mx:,} MW max"]
    if (spread or 0) >= 1:
        parts.append(f"spread {spread}")
    return rating, checks, " · ".join(parts)


def route(site, trace):
    d, n = site.get("poi_distance_miles"), site.get("parcels_to_cross")
    if d is None and n is None:
        rating = "uncertain"
    elif (d or 0) > 5 or (n or 0) >= 3:
        rating = "higher"
    elif d is not None and n is not None and d <= 2 and n <= 1:
        rating = "lower"
    else:
        rating = "watch"
    checks = [
        _chk("Distance to substation (your input)", _fmt(d, " mi"), "> 5 mi → Higher · ≤ 2 mi → Lower", d is not None and (d > 5 or d <= 2)),
        _chk("Parcels to cross (your input)", _fmt(n), "≥ 3 → Higher · ≤ 1 → Lower", n is not None and (n >= 3 or n <= 1)),
        _chk("Route known?", "no" if d is None and n is None else "yes", "unknown → Uncertain", d is None and n is None),
    ]
    key = "route unknown" if d is None and n is None else f"{_fmt(d, ' mi')} · {_fmt(n)} parcels"
    return rating, checks, key


def permitting(site, trace):
    w, land = site.get("wetlands", "unknown"), (site.get("land_type") or "").lower()
    veto = (_tool(trace, "state_rules") or RULES.get(site["state"], {})).get("local_veto", False)
    zoned = any(k in land for k in ("industrial", "zoned", "brownfield", "former", "commercial"))
    green = any(k in land for k in ("green", "farm", "agricult", "rural"))
    rating = "higher" if w == "yes" else "lower" if zoned else "watch" if veto and green else "uncertain"
    checks = [
        _chk("Wetlands on site or route (your input)", w, "yes → Higher", w == "yes"),
        _chk("Land type (your input)", site.get("land_type") or "unknown", "industrial / already zoned → Lower", zoned),
        _chk(f"{site['state']} siting regime", RULES.get(site["state"], {}).get("siting_authority", "?") +
             (" · local veto" if veto else ""), "greenfield/farmland + local veto → Watch", veto and green),
    ]
    return rating, checks, f"wetlands {w} · {site.get('land_type') or 'land ?'}"


def community(site, trace):
    h, o = site.get("homes_nearby", "unknown"), site.get("local_objections", "unknown")
    q = _tool(trace, "queue_history")
    rating = ("higher" if o == "yes" else "watch" if h == "yes" else "lower" if h == o == "no"
              else "uncertain" if h == o == "unknown" else "watch")
    checks = [
        _chk("Recorded local objections (your input)", o, "yes → Higher", o == "yes"),
        _chk("Homes nearby (your input)", h, "yes → Watch", h == "yes"),
        _chk("Both unknown?", "yes" if h == o == "unknown" else "no", "→ Uncertain (no record ≠ support)", h == o == "unknown"),
        _chk("County withdrawal rate since 2015 (context)",
             f"{q.get('county_withdrawal_rate', 0):.0%} ({q.get('withdrawn', 0)} of {q.get('withdrawn', 0) + q.get('operational', 0)})"
             if q.get("found") else "n/a", "background signal only", False),
    ]
    return rating, checks, f"homes {h} · objections {o}"


RUBRIC = {"network_upgrades": network, "allocation_volatility": allocation, "connection_route": route,
          "permitting": permitting, "community_resistance": community}


def audit(result: dict) -> dict:
    """{driver: {rule_rating, checks, key, ai_rating, agrees}} for one site result (site + card + trace)."""
    out = {}
    for d in result["card"]["drivers"]:
        rating, checks, key = RUBRIC[d["driver"]](result["site"], result.get("trace", []))
        out[d["driver"]] = {"rule_rating": rating, "checks": checks, "key": key, "ai_rating": d["rating"],
                            "agrees": rating == d["rating"]}
    return out


def records(site: dict, driver: str) -> tuple[str, pd.DataFrame]:
    """Underlying Berkeley Lab rows behind a driver (title, table)."""
    title, df = _records(site, driver)
    for col in df.select_dtypes("object"):
        df[col] = df[col].fillna("").astype(str).str.replace(r"_x[0-9A-Fa-f]{4}_", "-", regex=True)
    return title, df.fillna("").reset_index(drop=True)


def _records(site: dict, driver: str) -> tuple[str, pd.DataFrame]:
    st, co = site["state"], norm_county(site["county"])
    if driver == "network_upgrades":
        d = C[(C.state == st) & (C.county == co)].sort_values("network_kw", ascending=False)
        return (f"PJM interconnection studies in {co}, {st} (solar/storage, 2017–2022)",
                d.rename(columns={"q_id": "Queue ID", "poi_name": "Substation", "utility": "Utility", "fuel": "Type",
                                  "mw": "MW", "status": "Status", "study_year": "Study year",
                                  "network_kw": "Network upgrade $/kW (2022$)"})
                [["Queue ID", "Substation", "Utility", "Type", "MW", "Status", "Study year", "Network upgrade $/kW (2022$)"]])
    if driver == "allocation_volatility":
        d = Q[(Q.state == st) & (Q.county == co) & (Q.q_status == "active")].copy()
        d["Shares substation"] = d.groupby("poi_name").q_id.transform("size").gt(1).map({True: "yes", False: ""})
        d = d.sort_values(["Shares substation", "poi_name"], ascending=[False, True])
        return (f"Active solar/storage queue requests in {co}, {st}",
                d.rename(columns={"q_id": "Queue ID", "poi_name": "Substation", "utility": "Utility",
                                  "type_clean": "Type", "mw": "MW", "q_year": "Queue year"})
                [["Queue ID", "Substation", "Shares substation", "Utility", "Type", "MW", "Queue year"]])
    if driver == "community_resistance":
        d = Q[(Q.state == st) & (Q.county == co)].sort_values("q_year", ascending=False)
        return (f"All solar/storage queue requests in {co}, {st} since 2015 (outcome history)",
                d.rename(columns={"q_id": "Queue ID", "q_status": "Status", "q_year": "Queue year",
                                  "wd_year": "Withdrawn year", "poi_name": "Substation", "type_clean": "Type", "mw": "MW"})
                [["Queue ID", "Status", "Queue year", "Withdrawn year", "Substation", "Type", "MW"]])
    if driver == "permitting":
        r = RULES.get(st, {})
        return (f"{st} siting rules (curated from statutes)",
                pd.DataFrame([{"Siting authority": r.get("siting_authority"), "Summary": r.get("summary"),
                               "Statutes": "; ".join(r.get("statutes", []))}]))
    return ("Route facts come from your site description (no public dataset used)",
            pd.DataFrame([{"Distance to substation (mi)": site.get("poi_distance_miles"),
                           "Parcels to cross": site.get("parcels_to_cross")}]))
