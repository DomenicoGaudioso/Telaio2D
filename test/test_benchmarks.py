"""
Test benchmark per il solver FEM Telaio2D.

Carica i JSON dalla cartella test/ e verifica i risultati analitici
del solutore OpenSeesPy entro la tolleranza dichiarata.

Richiede OpenSeesPy: pip install openseespy
Esegui con: pytest test/test_benchmarks.py -v
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd
import pytest

try:
    from src import ensure_sheets, solve_linear_static_opensees
    OPENSEES_AVAILABLE = True
except Exception:
    OPENSEES_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not OPENSEES_AVAILABLE,
    reason="OpenSeesPy non disponibile nell'ambiente corrente"
)

BENCHMARK_DIR = Path(__file__).parent


def _frame(records):
    return pd.DataFrame(records or [])


def _get_path(data, dotpath: str):
    """Naviga un dict con path 'a.b.c' o 'a.0.b'."""
    cur = data
    for part in dotpath.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


def _run_benchmark(json_file: Path) -> None:
    data = json.loads(json_file.read_text(encoding="utf-8"))
    sheets = ensure_sheets({
        name: _frame(rows)
        for name, rows in data["input"].items()
    })
    results = solve_linear_static_opensees(sheets, int(data["load_case_id"]))
    payload = {
        "results_nodal":    results["results_nodal"].set_index("node_id").to_dict("index"),
        "results_elements": results["results_elements"].set_index("element_id").to_dict("index"),
    }
    for name, check in data["risultati_attesi"].items():
        got      = float(_get_path(payload, check["path"]))
        expected = float(check["valore"])
        tol_pct  = float(check.get("tolleranza_percentuale", 1.0))
        tol_abs  = max(abs(expected) * tol_pct / 100.0, float(check.get("tolleranza_assoluta", 1e-9)))
        assert abs(got - expected) <= tol_abs, (
            f"{json_file.name} [{name}]: ottenuto {got:.6g}, atteso {expected:.6g} "
            f"(±{tol_abs:.4g})"
        )


def _collect():
    return [
        pytest.param(jf, id=jf.stem)
        for jf in sorted(BENCHMARK_DIR.glob("benchmark_*.json"))
    ]


@pytest.mark.parametrize("json_file", _collect())
def test_benchmark(json_file: Path):
    """Esegue un benchmark JSON e verifica i risultati analitici."""
    _run_benchmark(json_file)
