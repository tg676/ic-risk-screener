"""Build self-contained report.html and slides.html (images inlined as base64) in the repo root.
Run:  python report/build.py
"""
import base64
import html
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TODO = '<div class="todo"><b>TO FILL:</b> {}</div>'


def inline_images(s: str) -> str:
    def sub(m):
        p = HERE / m.group(1)
        mime = "image/svg+xml" if p.suffix == ".svg" else "image/png"
        return f'src="data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"'
    return re.sub(r'src="(img/[^"]+)"', sub, s)


def pytest_output() -> str:
    r = subprocess.run([sys.executable, "-m", "pytest", "-v", "--no-header", "-p", "no:cacheprovider"], cwd=ROOT,
                       capture_output=True, text=True)
    lines = [l.replace(str(ROOT), "").strip() for l in r.stdout.splitlines() if "PASSED" in l or "FAILED" in l
             or re.search(r"\d+ (passed|failed)", l)]
    return html.escape("$ python -m pytest -v\n" + "\n".join(lines))


inputs = json.loads((HERE / "user_inputs.json").read_text(encoding="utf-8")) if (HERE / "user_inputs.json").exists() else {}
svg = (HERE / "diagram.svg").read_text(encoding="utf-8")

rep = (HERE / "report.src.html").read_text(encoding="utf-8")
rep = rep.replace("{{DIAGRAM}}", svg).replace("{{PYTEST}}", pytest_output())
rep = rep.replace("{{MANUAL_TIME}}", inputs.get("manual_time") or TODO.format("manual screening time per site (team estimate or user)"))
rep = rep.replace("{{USER_TEST}}", inputs.get("user_test") or TODO.format("real user test: who, quote, before/after time"))
(ROOT / "report.html").write_text(inline_images(rep), encoding="utf-8")
print("report.html", round((ROOT / "report.html").stat().st_size / 1e6, 2), "MB")

if (HERE / "slides.src.html").exists():
    sl = (HERE / "slides.src.html").read_text(encoding="utf-8").replace("{{DIAGRAM}}", svg)
    for k, v in inputs.items():
        sl = sl.replace("{{" + k.upper() + "}}", v)
    sl = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: f'<span class="todo">TO FILL: {m.group(1).lower()}</span>', sl)
    (ROOT / "slides.html").write_text(inline_images(sl), encoding="utf-8")
    print("slides.html", round((ROOT / "slides.html").stat().st_size / 1e6, 2), "MB")
