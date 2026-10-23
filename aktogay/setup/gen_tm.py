"""Write the WoT Thing Models (models/*.tm.jsonld) from things.json.

  python -I aktogay/setup/gen_tm.py           write models/ (stale *.tm.jsonld removed)
  python -I aktogay/setup/gen_tm.py --check   exit 1 if models/ differs from things.json
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import twins  # noqa: E402

MODELS = os.path.join(os.path.dirname(HERE), "models")


def render(tm: dict) -> str:
    return json.dumps(tm, ensure_ascii=False, indent=2) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare only")
    ap.add_argument("--out", default=MODELS, help="models folder")
    a = ap.parse_args(argv)
    model = twins.Model()
    want = {name: render(tm) for name, tm in model.all_tms().items()}
    have = {n for n in os.listdir(a.out) if n.endswith(".tm.jsonld")} if os.path.isdir(a.out) else set()
    diff = []
    for name, text in want.items():
        path = os.path.join(a.out, name)
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as f:
                old = f.read()
        if old != text:
            diff.append(name)
    stale = sorted(have - set(want))
    if a.check:
        for n in diff:
            print("differs:", n)
        for n in stale:
            print("stale:", n)
        print(f"{len(want)} models, {len(diff)} differ, {len(stale)} stale")
        return 1 if diff or stale else 0
    os.makedirs(a.out, exist_ok=True)
    for name in diff:
        with open(os.path.join(a.out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(want[name])
    for name in stale:
        os.remove(os.path.join(a.out, name))
    n_types = len(model.types)
    print(f"{len(want)} models ({n_types} types, {len(model.quant)} quantities, "
          f"{len(want) - n_types - len(model.quant)} state sets): {len(diff)} written, {len(stale)} removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
