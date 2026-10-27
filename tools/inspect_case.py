"""Ad-hoc inspector: print one line per charged violation from a model run.

    python3 tools/inspect_case.py examples/case_acme_health_multi.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from penex import Precedents, Registry, model_case  # noqa: E402

reg, pr = Registry(), Precedents()
case = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
res = model_case(case, reg, pr)
band = res["case_band"] or {}
print(f"case {res['case_id']}  confidence={res['confidence']['level']}")
print(f"band low={band.get('low', 0):,.0f} expected={band.get('expected', 0):,.0f} "
      f"max={band.get('max', 0):,.0f} {band.get('currency', '')}")
print()
for v in res["violations"]:
    b = v["band"]
    print(f"{v['statute_id']:28} n={v['comparables']['n']:2} mode={v['calibration_mode']:20} "
          f"low={b['low']:>18,.0f} exp={b['expected']:>18,.0f} max={b['max']:>22,.0f}")
    print(f"    comparables: {', '.join(v['comparables']['ids']) or 'none'}")
for w in res["warnings"]:
    print("WARN", w)
