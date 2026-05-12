# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src import ensure_sheets, solve_linear_static_opensees


def _frame_from_records(records):
    return pd.DataFrame(records or [])


def _get_path(data, path):
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part not in cur and part.isdigit():
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


def run_one(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    sheets = ensure_sheets({name: _frame_from_records(rows) for name, rows in data["input"].items()})
    results = solve_linear_static_opensees(sheets, int(data["load_case_id"]))
    payload = {
        "results_nodal": results["results_nodal"].set_index("node_id").to_dict("index"),
        "results_elements": results["results_elements"].set_index("element_id").to_dict("index"),
    }
    for name, check in data["risultati_attesi"].items():
        value = float(_get_path(payload, check["path"]))
        expected = float(check["valore"])
        tol = abs(expected) * float(check.get("tolleranza_percentuale", 1.0)) / 100.0
        tol = max(tol, float(check.get("tolleranza_assoluta", 1e-9)))
        if abs(value - expected) > tol:
            raise AssertionError(f"{path.name} {name}: {value} != {expected} +/- {tol}")
    print(f"{path.name}: OK")


def main() -> None:
    base = Path(__file__).parent / "test"
    files = sorted(base.glob("*.json")) + sorted((base / "benchmark").glob("*.json"))
    if not files:
        raise SystemExit("Nessun benchmark JSON trovato.")
    for file in files:
        run_one(file)
    print(f"{len(files)} benchmark validati.")


if __name__ == "__main__":
    main()
