import pandas as pd
from src import write_xlsx, read_xlsx, ensure_sheets


def test_roundtrip_xlsx():
    sheets = ensure_sheets({
        "nodes": pd.DataFrame([{"id": 1, "x": 0.0, "y": 0.0}]),
        "elements": pd.DataFrame([{"id": 1, "n1": 1, "n2": 1, "prop": 1, "type": "beam2d"}]),
        "properties": pd.DataFrame([{"id": 1, "name": "p", "E": 210000.0, "A": 0.01, "I": 1e-6, "rho": 0.0, "alphaT": 0.0}]),
        "load_cases": pd.DataFrame([{"id": 1, "name": "LC1", "ax": 0.0, "ay": 0.0}]),
        "restraints": pd.DataFrame([{"load_case_id": 1, "node_id": 1, "ux": True, "uy": True, "rz": True}]),
        "node_loads": pd.DataFrame([{"load_case_id": 1, "node_id": 1, "fx": 0.0, "fy": 0.0, "mz": 0.0}]),
        "dist_loads": pd.DataFrame(),
        "masses": pd.DataFrame(),
    })
    b = write_xlsx(sheets)
    out = ensure_sheets(read_xlsx(b))
    assert "nodes" in out and not out["nodes"].empty
