import pandas as pd
from src import ensure_sheets, solve_linear_static_opensees


def test_opensees_cantilever_tip_load_runs():
    sheets = ensure_sheets({
        "nodes": pd.DataFrame([
            {"id": 1, "x": 0.0, "y": 0.0},
            {"id": 2, "x": 1.0, "y": 0.0},
        ]),
        "elements": pd.DataFrame([
            {"id": 1, "n1": 1, "n2": 2, "prop": 1, "type": "beam2d"},
        ]),
        "properties": pd.DataFrame([
            {"id": 1, "name": "beam", "E": 210000.0, "A": 0.01, "I": 1e-6, "rho": 0.0, "alphaT": 0.0},
        ]),
        "load_cases": pd.DataFrame([
            {"id": 1, "name": "LC1", "ax": 0.0, "ay": 0.0},
        ]),
        "restraints": pd.DataFrame([
            {"load_case_id": 1, "node_id": 1, "ux": True, "uy": True, "rz": True},
        ]),
        "node_loads": pd.DataFrame([
            {"load_case_id": 1, "node_id": 2, "fx": 0.0, "fy": -10.0, "mz": 0.0},
        ]),
        "dist_loads": pd.DataFrame(),
        "masses": pd.DataFrame(),
    })

    res = solve_linear_static_opensees(sheets, 1)
    nod = res["results_nodal"].set_index("node_id")
    assert abs(nod.loc[1, "ux"]) < 1e-9
    assert nod.loc[2, "uy"] < 0.0
