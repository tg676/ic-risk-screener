"""Dash UI for the IC Risk Screener. Run:  python app.py  ->  http://127.0.0.1:8050"""
import json
import re

import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update

import config
from agents import DRIVERS, screen
from tools import chart_data

PURPLE, BLUE, TEAL, GREEN, INK, GREY = "#6A2C91", "#0072CE", "#00A9A5", "#7AB800", "#2B2B2B", "#6B6B6B"
RATING = {  # matches the legend in the AES Round 1 deck
    "lower": ("#E9FFBE", "#7AB800", "Lower risk"),
    "higher": ("#F6B6C1", "#D6336C", "Higher risk"),
    "watch": ("#E3CEF0", PURPLE, "Watch"),
    "uncertain": ("#F7F7F7", "#BDBDBD", "Uncertain"),
}
VERDICT = {"prioritize": (TEAL, "Prioritize"), "targeted": (BLUE, "Targeted diligence"),
           "deprioritize": ("#D6336C", "Deprioritize")}
DRIVER_NAME = {"network_upgrades": ("⚡", "Network upgrades"), "allocation_volatility": ("⇄", "Allocation volatility"),
               "connection_route": ("➝", "Connection route"), "permitting": ("▤", "Permitting"),
               "community_resistance": ("⌂", "Community resistance")}
SOURCE = {"LBNL-COST": "Berkeley Lab PJM interconnection cost data", "LBNL-QUEUE": "Berkeley Lab Queued Up (PJM queue)",
          "LBNL-POI": "Berkeley Lab Queued Up: active requests by substation", "RULES": "State siting statutes",
          "USER": "Your site facts"}
SAMPLE = (config.DATA / "sample_sites.txt").read_text(encoding="utf-8")

app = Dash(__name__, title="IC Risk Screener", suppress_callback_exceptions=True)


def badge(text, color, solid=True):
    return html.Span(text, className="badge",
                     style={"background": color if solid else "white", "color": "white" if solid else color,
                            "border": f"1.5px solid {color}"})


def legend():
    return html.Div([html.Span([html.Span(className="swatch", style={"background": b, "borderColor": e}), n],
                               className="legend-item") for b, e, n in RATING.values()], className="legend")


app.layout = html.Div([
    dcc.Location(id="url"), dcc.Store(id="result"), dcc.Store(id="session-tokens", storage_type="session", data=0),
    html.Header([
        html.Div([html.Div("IC Risk Screener", className="title"),
                  html.Div("Pre-queue interconnection gut check · PJM solar + storage",
                           className="subtitle")]),
        html.Div(id="meters", className="meters"),
    ]),
    html.Main([
        html.Section([
            html.H3("Candidate sites"),
            html.Div("Up to 3 sites · VA, PA, OH · state, county, MW, land, route, neighbors", className="hint"),
            dcc.Textarea(id="sites", value="", placeholder="e.g. Site A: Franklin County, PA. 100 MW solar + 50 MW "
                         "storage. Industrial land, substation 1.5 miles away...", className="input"),
            html.Div([html.Button("Load example", id="example", className="btn ghost"),
                      html.Button("Screen sites", id="go", className="btn primary")], className="row"),
            html.Div("🔒 Inputs are not stored. Ratings guide diligence; they are not cost estimates.",
                     className="hint small"),
            html.H4("Legend"), legend(),
        ], className="panel left"),
        html.Section(dcc.Loading(html.Div(id="board", children=html.Div(
            [html.Div("⚡", className="empty-icon"), html.Div("Enter sites and press Screen sites")],
            className="empty")), type="dot", color=PURPLE), className="panel right"),
    ]),
])


def replay(search):
    """?replay=<name> shows a saved real run from logs/replay_<name>.json (used for report screenshots)."""
    m = re.search(r"replay=(\w+)", search or "")
    f = config.LOGS / f"replay_{m.group(1)}.json" if m else None
    return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None


@app.callback(Output("sites", "value"), Input("example", "n_clicks"), Input("url", "search"))
def load_example(_, search):
    if ctx.triggered_id == "example":
        return SAMPLE
    rp = replay(search)
    return rp["text"] if rp else no_update


@app.callback(Output("result", "data"), Output("session-tokens", "data"),
              Input("go", "n_clicks"), Input("url", "search"), State("sites", "value"),
              State("session-tokens", "data"))
def run(_, search, text, used):
    if ctx.triggered_id != "go":
        rp = replay(search)
        return (rp["result"], used or 0) if rp else (no_update, no_update)
    try:
        r = screen(text, used or 0)
    except Exception as e:  # network / model failure: show it, don't crash the app
        r = {"blocked": f"Something went wrong talking to the model: {type(e).__name__}. Try again."}
    t = r.get("totals", {})
    return r, (used or 0) + t.get("input", 0) + t.get("output", 0)


@app.callback(Output("meters", "children"), Input("result", "data"), Input("session-tokens", "data"))
def meters(r, used):
    t = (r or {}).get("totals") or {"input": 0, "cached": 0, "output": 0, "cost": 0, "calls": 0}
    caught = len((r or {}).get("verifier", [])) + (1 if (r or {}).get("defense") else 0)
    return [
        html.Div([html.B(f"{t['input'] + t['output']:,}"), " tokens"], className="meter",
                 title=f"input {t['input']:,} (cached {t['cached']:,}) · output {t['output']:,} · {t['calls']} calls"),
        html.Div([html.B(f"${t['cost']:.4f}"), " this run"], className="meter"),
        html.Div([html.B(f"{caught}"), " 🛡 caught"], className="meter",
                 title="Verifier + injection guard actions this run"),
        html.Div([html.B(f"{100 * used / config.SESSION_TOKEN_BUDGET:.0f}%"), " budget"], className="meter",
                 title=f"Session cap {config.SESSION_TOKEN_BUDGET:,} tokens"),
    ]


def tile(i, d):
    bg, edge, _ = RATING[d["rating"]]
    return html.Button(d["label"], id={"type": "tile", "site": i, "driver": d["driver"]}, className="tile",
                       style={"background": bg, "borderLeft": f"5px solid {edge}"}, title=d["reason"])


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def charts(results):
    f1, f2 = go.Figure(), go.Figure()
    for x in reversed(results):
        s = x["site"]
        cd = chart_data(s["state"], s["county"])
        pct, n = cd["pct"], len(cd["county"])
        color = "#BDBDBD" if n < 3 else "#D6336C" if pct >= 65 else GREEN if pct <= 40 else PURPLE
        f1.add_trace(go.Bar(y=[s["name"]], x=[pct or 0], orientation="h", marker_color=color,
                            text=[f"{ordinal(pct)} · {n} {'study' if n == 1 else 'studies'}" if n else "no studies"], textposition="auto",
                            hovertemplate=f"{s['county']}, {s['state']}: county median sits at the %{{x}}th "
                                          f"percentile of PJM solar/storage studies<extra></extra>"))
        f2.add_trace(go.Bar(y=[s["name"]], x=[cd["county_wd"] or 0], orientation="h", marker_color=PURPLE,
                            name=s["name"], text=[f"{(cd['county_wd'] or 0):.0%}"], textposition="inside"))
        f2.add_trace(go.Scatter(y=[s["name"]], x=[cd["state_wd"]], mode="markers", marker=dict(symbol="line-ns-open",
                                size=26, color=INK, line_width=3), name=f"{s['state']} average",
                                hovertemplate=f"{s['state']} average %{{x:.0%}}<extra></extra>"))
    for f, title in ((f1, "Upgrade cost level: percentile vs. PJM history"),
                     (f2, "Withdrawal rate: county (bar) vs. state (|)")):
        f.update_layout(title=dict(text=title, font_size=14, x=0), height=200, margin=dict(l=10, r=10, t=36, b=24),
                        showlegend=False, plot_bgcolor="white", paper_bgcolor="white", font_family="Arial")
    f1.add_vline(x=50, line_dash="dot", line_color=GREY, annotation_text="PJM median", annotation_font_size=10)
    f1.update_xaxes(range=[0, 100], ticksuffix="th", showgrid=False)
    f2.update_xaxes(tickformat=".0%", range=[0, 1], showgrid=False)
    cfg = {"displayModeBar": False}
    return html.Div([dcc.Graph(figure=f1, config=cfg, className="chart"),
                     dcc.Graph(figure=f2, config=cfg, className="chart")], className="charts")


def under_hood(r):
    rows = [html.Tr([html.Td(c["agent"]), html.Td(c["site"]), html.Td(f"{c['input']:,}"), html.Td(f"{c['cached']:,}"),
                     html.Td(f"{c['output']:,}"), html.Td(f"{c['secs']}s"), html.Td(f"${c['cost']:.5f}")])
            for c in r.get("usage", [])]
    table = html.Table([html.Thead(html.Tr([html.Th(h) for h in
                                            ("Agent", "Site", "Input", "Cached", "Output", "Time", "Cost")])),
                        html.Tbody(rows)], className="usage")
    ver = [html.Li(v) for v in r.get("verifier", [])] or [html.Li("No corrections needed.")]
    return html.Details(open=bool(r.get("_hood_open")), children=[html.Summary(f"Under the hood · {len(rows)} model calls · {r.get('secs', 0)}s"),
                         html.Div([html.Div([html.H4("Token usage"), table]),
                                   html.Div([html.H4("🛡 Verifier actions"), html.Ul(ver)])], className="hood")],
                        className="details")


@app.callback(Output("board", "children"), Input("result", "data"), prevent_initial_call=True)
def board(r):
    if not r:
        return no_update
    if r.get("blocked"):
        return html.Div([html.Div("🛡", className="empty-icon"), html.B(r["blocked"]),
                         html.Div(f"Defense: {r['defense']}", className="hint") if r.get("defense") else None],
                        className="empty blocked")
    res = r["results"]
    port = r["portfolio"]
    head = [html.Div(className="corner")]
    for x in res:
        s, c = x["site"], x["card"]
        col, word = VERDICT[c["verdict"]]
        mw = " + ".join(f"{v:g} MW {k}" for k, v in (("PV", s["mw_solar"]), ("BESS", s["mw_storage"])) if v)
        head.append(html.Div([html.Div(s["name"], className="site-name"),
                              html.Div(f"{s['county']}, {s['state']} · {mw}", className="site-meta"),
                              badge(word, col)], className="site-head"))
    grid = head
    for k in DRIVERS:
        icon, name = DRIVER_NAME[k]
        grid.append(html.Div([html.Span(icon, className="icon"), name], className="driver"))
        for i, x in enumerate(res):
            grid.append(tile(i, next(d for d in x["card"]["drivers"] if d["driver"] == k)))
    grid.append(html.Div("Next step", className="driver"))
    grid += [html.Div("→ " + x["card"]["next_action"], className="next") for x in res]
    top = html.Div([html.Span("Diligence order: ", className="hint"),
                    *[badge(f"{n + 1}. {name}", PURPLE, solid=n == 0) for n, name in enumerate(port["ranking"])],
                    html.Span(port["headline"], className="headline")], className="portfolio") if len(res) > 1 else None
    skipped = html.Div(f"Skipped (outside VA, PA, OH): {', '.join(r['skipped'])}", className="hint",
                       style={"marginBottom": "10px", "color": "#D6336C"}) if r.get("skipped") else None
    return [skipped, top,
            html.Div(grid, className="grid", style={"gridTemplateColumns": f"190px repeat({len(res)}, 1fr)"}),
            html.Div(id="detail", className="detail", children=detail_view(r, *r["_open"]) if r.get("_open") else
                     html.Span("Click any tile for the why and the sources.", className="hint")),
            charts(res), under_hood(r)]


@app.callback(Output("detail", "children"), Input({"type": "tile", "site": ALL, "driver": ALL}, "n_clicks"),
              State("result", "data"), prevent_initial_call=True)
def detail(clicks, r):
    if not ctx.triggered_id or not any(clicks):
        return no_update
    return detail_view(r, ctx.triggered_id["site"], ctx.triggered_id["driver"])


def detail_view(r, i, k):
    x = r["results"][i]
    d = next(d for d in x["card"]["drivers"] if d["driver"] == k)
    bg, edge, word = RATING[d["rating"]]
    chips = [html.Span([html.B(SOURCE.get(c.split(":")[0], c)), f" · {c.split(':', 1)[1]}"], className="chip")
             for c in d["cites"]] or [html.Span("No source: rated Uncertain", className="chip")]
    return html.Div([html.Span(className="swatch big", style={"background": bg, "borderColor": edge}),
                     html.Div([html.B(f"{x['site']['name']} · {DRIVER_NAME[k][1]} · {word}"),
                               html.Div(d["reason"]), html.Div(chips, className="chips")])], className="detail-row")


if __name__ == "__main__":
    app.run(debug=False, port=8050)  # debug off: no auto-reloader, one process
