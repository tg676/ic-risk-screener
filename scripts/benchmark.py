"""Tokenomics evidence: run the 3 sample sites N times with compact tool summaries (shipped design) vs. raw
project-level rows (the naive design), and compare tokens, cost, latency and rating agreement.
Run:  python scripts/benchmark.py 3      -> logs/benchmark.json
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agents
import tools
from config import DATA, LOGS

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
TEXT = (DATA / "sample_sites.txt").read_text(encoding="utf-8")
COMPACT = dict(tools.TOOLS)


def with_raw_rows(fn, frame):
    def wrapped(state, county=None):
        out = fn(state, county) if county is not None else fn(state)
        if county is not None:
            rows = frame[(frame.state == state.upper()) & (frame.county == tools.norm_county(county))]
            out["records"] = json.loads(rows.to_json(orient="records"))
        return out
    return wrapped


RAW = {"queue_history": with_raw_rows(tools.queue_history, tools.QUEUE),
       "upgrade_costs": with_raw_rows(tools.upgrade_costs, tools.COSTS),
       "poi_crowding": with_raw_rows(tools.poi_crowding, tools.QUEUE),
       "state_rules": tools.state_rules}


def ratings(r):
    return {f"{x['site']['name']}/{d['driver']}": d["rating"] for x in r["results"] for d in x["card"]["drivers"]}


out = {}
for mode, table in (("compact", COMPACT), ("raw", RAW)):
    agents.TOOLS.clear()
    agents.TOOLS.update(table)
    runs = [agents.screen(TEXT) for _ in range(N)]
    out[mode] = {"runs": [{"totals": r["totals"], "secs": r["secs"], "ratings": ratings(r),
                           "verdicts": [x["card"]["verdict"] for x in r["results"]],
                           "verifier_actions": len(r["verifier"])} for r in runs]}
    print(mode, "done")

ref = out["compact"]["runs"][0]["ratings"]
for mode, d in out.items():
    rs = d["runs"]
    agree = [sum(r["ratings"][k] == v for k, v in ref.items()) / len(ref) for r in rs]
    d["summary"] = {k: round(statistics.mean(r["totals"][k] for r in rs), 6) for k in ("input", "cached", "output", "cost")}
    d["summary"].update(secs=round(statistics.mean(r["secs"] for r in rs), 1),
                        agreement_with_compact_run1=round(statistics.mean(agree), 2),
                        verdicts=[r["verdicts"] for r in rs])
    print(mode, json.dumps(d["summary"]))

LOGS.mkdir(exist_ok=True)
(LOGS / "benchmark.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
