"""Audit trail: the code rubric applies the same thresholds the Risk Analyst is given. Offline, no tokens."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit
from config import LOGS

SITE = {"name": "T", "state": "VA", "county": "Sussex", "poi_distance_miles": None, "parcels_to_cross": None,
        "wetlands": "unknown", "land_type": "greenfield farmland", "homes_nearby": "unknown",
        "local_objections": "unknown"}


def trace(**tools):
    return [{"tool": k, "result": v} for k, v in tools.items()]


def test_network_thresholds():
    hi = trace(upgrade_costs={"county_studies": 6, "county_percentile_vs_pool": 92, "county_share_over_200_kw": 0.67})
    lo = trace(upgrade_costs={"county_studies": 5, "county_percentile_vs_pool": 31, "county_share_over_200_kw": 0.2})
    thin = trace(upgrade_costs={"county_studies": 1, "county_percentile_vs_pool": 39, "county_share_over_200_kw": 0})
    assert audit.network(SITE, hi)[0] == "higher"
    assert audit.network(SITE, lo)[0] == "lower"
    assert audit.network(SITE, thin)[0] == "uncertain"


def test_allocation_and_route_and_community():
    crowded = trace(poi_crowding={"found": True, "shared_substations": 2, "max_active_mw_one_substation": 1120,
                                  "cost_spread_iqr_over_median": 1.1})
    assert audit.allocation(SITE, crowded)[0] == "higher"
    assert audit.route(SITE, [])[0] == "uncertain"
    assert audit.route({**SITE, "poi_distance_miles": 6, "parcels_to_cross": 4}, [])[0] == "higher"
    assert audit.route({**SITE, "poi_distance_miles": 1.5, "parcels_to_cross": 1}, [])[0] == "lower"
    assert audit.community({**SITE, "local_objections": "yes"}, [])[0] == "higher"
    assert audit.community(SITE, [])[0] == "uncertain"


def test_wetlands_drive_permitting():
    assert audit.permitting({**SITE, "wetlands": "yes"}, [])[0] == "higher"
    assert audit.permitting({**SITE, "land_type": "former industrial"}, [])[0] == "lower"


def test_records_match_tool_counts():
    title, df = audit.records(SITE, "network_upgrades")
    assert len(df) == 6 and "Sussex" in title  # same 6 studies the upgrade_costs tool summarizes
    assert not df.astype(str).apply(lambda c: c.str.contains("_x00")).any().any()  # Excel escapes cleaned


def test_saved_real_run_mostly_agrees_with_rubric():
    r = json.loads((LOGS / "replay_demo.json").read_text(encoding="utf-8"))["result"]
    checks = [v["agrees"] for x in r["results"] for v in audit.audit(x).values()]
    assert sum(checks) >= len(checks) - 1
