r"""One-off connectivity check for EODHD. Uses about 4 API calls. Writes eodhd_check.txt (key redacted).

Run from the backend folder:  .venv\Scripts\python.exe eodhd_check.py
"""
import json

import httpx

from app.core.config import get_settings

key = get_settings().eodhd_api_key or ""
out = []


def show(label, path, params):
    try:
        r = httpx.get(f"https://eodhd.com/api{path}", params={**params, "api_token": key, "fmt": "json"}, timeout=30)
        body = r.text[:1500]
        try:
            data = r.json()
            if isinstance(data, list):
                body = f"list of {len(data)} items; first 5: " + json.dumps(data[:5], indent=1)
        except ValueError:
            pass
        out.append(f"== {label}  HTTP {r.status_code}\n{body.replace(key, '***') if key else body}\n")
    except Exception as e:  # network problems
        out.append(f"== {label}  ERROR {type(e).__name__}: {e}\n")


out.append(f"Key set: {bool(key)} (ends ...{key[-4:] if key else ''})\n")
show("search dangote", "/search/dangote", {"limit": "10"})
show("exchange list XNSA", "/exchange-symbol-list/XNSA", {})
show("EOD DANGCEM.XNSA", "/eod/DANGCEM.XNSA", {"from": "2026-09-01"})
show("EOD GSPC.INDX", "/eod/GSPC.INDX", {"from": "2026-09-20"})
open("eodhd_check.txt", "w", encoding="utf-8").write("\n".join(out))
print("Saved eodhd_check.txt")
