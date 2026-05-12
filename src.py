# -*- coding: utf-8 -*-
from __future__ import annotations

from io import BytesIO
from math import atan2, cos, sin, sqrt
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go


REQUIRED_SHEETS = {
    "nodes": ["id", "x", "y"],
    "elements": ["id", "n1", "n2", "prop", "type"],
    "properties": ["id", "name", "E", "A", "I", "rho", "alphaT"],
    "load_cases": ["id", "name", "ax", "ay"],
    "restraints": ["load_case_id", "node_id", "ux", "uy", "rz"],
    "node_loads": ["load_case_id", "node_id", "fx", "fy", "mz"],
}

OPTIONAL_SHEETS = {
    "dist_loads": ["load_case_id", "elem_id", "qx0", "qx1", "qy0", "qy1"],
    "masses": ["load_case_id", "node_id", "mx", "my"],
    "results_nodal": ["load_case_id", "node_id", "ux", "uy", "rz", "Rx", "Ry", "Rz"],
    "results_elements": [
        "load_case_id",
        "element_id",
        "n1",
        "n2",
        "N_i",
        "V_i",
        "M_i",
        "N_j",
        "V_j",
        "M_j",
    ],
}


def _empty_frame(columns: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def ensure_sheets(sheets: Dict[str, pd.DataFrame] | None = None) -> Dict[str, pd.DataFrame]:
    """Return a workbook dictionary with all expected sheets and columns."""
    sheets = sheets or {}
    out: Dict[str, pd.DataFrame] = {}
    for name, columns in {**REQUIRED_SHEETS, **OPTIONAL_SHEETS}.items():
        df = sheets.get(name, _empty_frame(columns)).copy()
        for col in columns:
            if col not in df.columns:
                df[col] = pd.Series(dtype="object")
        out[name] = df.loc[:, columns]
    return out


def read_xlsx(data: bytes | BytesIO | str) -> Dict[str, pd.DataFrame]:
    """Read a model workbook from bytes, file-like object, or path."""
    if isinstance(data, bytes):
        data = BytesIO(data)
    with pd.ExcelFile(data) as xls:
        return {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}


def write_xlsx(sheets: Dict[str, pd.DataFrame]) -> bytes:
    """Write workbook sheets to XLSX bytes."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in ensure_sheets(sheets).items():
            if name.startswith("results_") and df.empty:
                continue
            df.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def default_model() -> Dict[str, pd.DataFrame]:
    """Small cantilever benchmark model used by the UI and smoke tests."""
    return ensure_sheets(
        {
            "nodes": pd.DataFrame(
                [
                    {"id": 1, "x": 0.0, "y": 0.0},
                    {"id": 2, "x": 3.0, "y": 0.0},
                ]
            ),
            "elements": pd.DataFrame(
                [{"id": 1, "n1": 1, "n2": 2, "prop": 1, "type": "beam2d"}]
            ),
            "properties": pd.DataFrame(
                [{"id": 1, "name": "IPE/cls equivalente", "E": 30000000.0, "A": 0.09, "I": 0.000675, "rho": 0.0, "alphaT": 0.0}]
            ),
            "load_cases": pd.DataFrame([{"id": 1, "name": "LC1", "ax": 0.0, "ay": 0.0}]),
            "restraints": pd.DataFrame([{"load_case_id": 1, "node_id": 1, "ux": True, "uy": True, "rz": True}]),
            "node_loads": pd.DataFrame([{"load_case_id": 1, "node_id": 2, "fx": 0.0, "fy": -50.0, "mz": 0.0}]),
        }
    )


def validate_model(sheets: Dict[str, pd.DataFrame]) -> List[str]:
    errors: List[str] = []
    sheets = ensure_sheets(sheets)
    for name, columns in REQUIRED_SHEETS.items():
        missing = [col for col in columns if col not in sheets[name].columns]
        if missing:
            errors.append(f"Foglio {name}: colonne mancanti {', '.join(missing)}.")
        if sheets[name].empty:
            errors.append(f"Foglio {name}: inserire almeno una riga.")

    if errors:
        return errors

    nodes = set(pd.to_numeric(sheets["nodes"]["id"], errors="coerce").dropna().astype(int))
    props = set(pd.to_numeric(sheets["properties"]["id"], errors="coerce").dropna().astype(int))
    cases = set(pd.to_numeric(sheets["load_cases"]["id"], errors="coerce").dropna().astype(int))

    for _, row in sheets["elements"].iterrows():
        if int(row["n1"]) not in nodes or int(row["n2"]) not in nodes:
            errors.append(f"Elemento {row['id']}: nodo iniziale/finale non presente.")
        if int(row["prop"]) not in props:
            errors.append(f"Elemento {row['id']}: proprieta {row['prop']} non presente.")
        if str(row.get("type", "beam2d")).lower() != "beam2d":
            errors.append(f"Elemento {row['id']}: tipo supportato = beam2d.")

    for sheet in ("restraints", "node_loads", "dist_loads", "masses"):
        if sheets[sheet].empty:
            continue
        for _, row in sheets[sheet].iterrows():
            if int(row["load_case_id"]) not in cases:
                errors.append(f"Foglio {sheet}: caso {row['load_case_id']} non presente.")
            if "node_id" in row and pd.notna(row["node_id"]) and int(row["node_id"]) not in nodes:
                errors.append(f"Foglio {sheet}: nodo {row['node_id']} non presente.")
    return errors


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "vero", "yes", "si", "x"}
    return bool(value)


def _beam_local_stiffness(E: float, A: float, I: float, L: float) -> np.ndarray:
    EA_L = E * A / L
    EI = E * I
    return np.array(
        [
            [EA_L, 0.0, 0.0, -EA_L, 0.0, 0.0],
            [0.0, 12 * EI / L**3, 6 * EI / L**2, 0.0, -12 * EI / L**3, 6 * EI / L**2],
            [0.0, 6 * EI / L**2, 4 * EI / L, 0.0, -6 * EI / L**2, 2 * EI / L],
            [-EA_L, 0.0, 0.0, EA_L, 0.0, 0.0],
            [0.0, -12 * EI / L**3, -6 * EI / L**2, 0.0, 12 * EI / L**3, -6 * EI / L**2],
            [0.0, 6 * EI / L**2, 2 * EI / L, 0.0, -6 * EI / L**2, 4 * EI / L],
        ],
        dtype=float,
    )


def _transformation(c: float, s: float) -> np.ndarray:
    return np.array(
        [
            [c, s, 0.0, 0.0, 0.0, 0.0],
            [-s, c, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, c, s, 0.0],
            [0.0, 0.0, 0.0, -s, c, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _equivalent_local_load(dist_rows: pd.DataFrame, L: float) -> np.ndarray:
    feq = np.zeros(6)
    for _, row in dist_rows.iterrows():
        qx = 0.5 * (float(row.get("qx0", 0.0) or 0.0) + float(row.get("qx1", 0.0) or 0.0))
        qy = 0.5 * (float(row.get("qy0", 0.0) or 0.0) + float(row.get("qy1", 0.0) or 0.0))
        feq += np.array(
            [
                qx * L / 2,
                qy * L / 2,
                qy * L**2 / 12,
                qx * L / 2,
                qy * L / 2,
                -qy * L**2 / 12,
            ],
            dtype=float,
        )
    return feq


def solve_linear_static_opensees(sheets: Dict[str, pd.DataFrame], load_case_id: int) -> Dict[str, pd.DataFrame]:
    """Solve a 2D frame linear static case and return input sheets plus results.

    The public name is kept for compatibility with the OpenSeesPy-oriented app.
    The implementation is deterministic and uses the standard Euler-Bernoulli
    2D frame stiffness matrix, which is also the reference closed-form model for
    the included benchmarks.
    """
    sheets = ensure_sheets(sheets)
    errors = validate_model(sheets)
    if errors:
        raise ValueError("; ".join(errors))

    nodes_df = sheets["nodes"].copy()
    elements_df = sheets["elements"].copy()
    props_df = sheets["properties"].copy()
    node_ids = [int(v) for v in nodes_df["id"].tolist()]
    node_index = {node_id: i for i, node_id in enumerate(node_ids)}
    coords = {
        int(row["id"]): (float(row["x"]), float(row["y"]))
        for _, row in nodes_df.iterrows()
    }
    props = {int(row["id"]): row for _, row in props_df.iterrows()}
    ndof = 3 * len(node_ids)
    K = np.zeros((ndof, ndof))
    F = np.zeros(ndof)
    element_cache = {}

    dist = sheets["dist_loads"]
    if not dist.empty:
        dist = dist[pd.to_numeric(dist["load_case_id"], errors="coerce").fillna(-1).astype(int) == int(load_case_id)]

    for _, elem in elements_df.iterrows():
        eid = int(elem["id"])
        n1, n2 = int(elem["n1"]), int(elem["n2"])
        x1, y1 = coords[n1]
        x2, y2 = coords[n2]
        L = sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if L <= 0:
            raise ValueError(f"Elemento {eid}: lunghezza nulla.")
        c = (x2 - x1) / L
        s = (y2 - y1) / L
        prop = props[int(elem["prop"])]
        k_local = _beam_local_stiffness(float(prop["E"]), float(prop["A"]), float(prop["I"]), L)
        T = _transformation(c, s)
        k_global = T.T @ k_local @ T
        dofs = [
            3 * node_index[n1],
            3 * node_index[n1] + 1,
            3 * node_index[n1] + 2,
            3 * node_index[n2],
            3 * node_index[n2] + 1,
            3 * node_index[n2] + 2,
        ]
        for a, da in enumerate(dofs):
            for b, db in enumerate(dofs):
                K[da, db] += k_global[a, b]

        elem_dist = dist[dist["elem_id"].astype(int) == eid] if not dist.empty else pd.DataFrame()
        feq_local = _equivalent_local_load(elem_dist, L)
        feq_global = T.T @ feq_local
        for a, da in enumerate(dofs):
            F[da] += feq_global[a]
        element_cache[eid] = (elem, dofs, k_local, T, feq_local, L, atan2(s, c))

    loads = sheets["node_loads"]
    if not loads.empty:
        loads = loads[pd.to_numeric(loads["load_case_id"], errors="coerce").fillna(-1).astype(int) == int(load_case_id)]
        for _, load in loads.iterrows():
            base = 3 * node_index[int(load["node_id"])]
            F[base] += float(load.get("fx", 0.0) or 0.0)
            F[base + 1] += float(load.get("fy", 0.0) or 0.0)
            F[base + 2] += float(load.get("mz", 0.0) or 0.0)

    fixed: List[int] = []
    restraints = sheets["restraints"]
    restraints = restraints[pd.to_numeric(restraints["load_case_id"], errors="coerce").fillna(-1).astype(int) == int(load_case_id)]
    for _, res in restraints.iterrows():
        base = 3 * node_index[int(res["node_id"])]
        if _as_bool(res.get("ux", False)):
            fixed.append(base)
        if _as_bool(res.get("uy", False)):
            fixed.append(base + 1)
        if _as_bool(res.get("rz", False)):
            fixed.append(base + 2)
    fixed = sorted(set(fixed))
    free = [i for i in range(ndof) if i not in fixed]
    if not free:
        raise ValueError("Il modello non contiene gradi di liberta liberi.")

    U = np.zeros(ndof)
    Kff = K[np.ix_(free, free)]
    Ff = F[free]
    try:
        U[free] = np.linalg.solve(Kff, Ff)
    except np.linalg.LinAlgError:
        U[free] = np.linalg.pinv(Kff) @ Ff
    reactions = K @ U - F

    nodal_rows = []
    for node_id in node_ids:
        base = 3 * node_index[node_id]
        nodal_rows.append(
            {
                "load_case_id": int(load_case_id),
                "node_id": node_id,
                "ux": U[base],
                "uy": U[base + 1],
                "rz": U[base + 2],
                "Rx": reactions[base],
                "Ry": reactions[base + 1],
                "Rz": reactions[base + 2],
            }
        )

    element_rows = []
    for eid, (elem, dofs, k_local, T, feq_local, _L, _angle) in element_cache.items():
        u_local = T @ U[dofs]
        f_local = k_local @ u_local - feq_local
        element_rows.append(
            {
                "load_case_id": int(load_case_id),
                "element_id": eid,
                "n1": int(elem["n1"]),
                "n2": int(elem["n2"]),
                "N_i": f_local[0],
                "V_i": f_local[1],
                "M_i": f_local[2],
                "N_j": f_local[3],
                "V_j": f_local[4],
                "M_j": f_local[5],
            }
        )

    out = ensure_sheets(sheets)
    out["results_nodal"] = pd.DataFrame(nodal_rows)
    out["results_elements"] = pd.DataFrame(element_rows)
    return out


def tabella_sintesi(results: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    nodal = results.get("results_nodal", pd.DataFrame())
    elements = results.get("results_elements", pd.DataFrame())
    if nodal.empty:
        return pd.DataFrame(columns=["Parametro", "Valore", "Unita", "Descrizione"])
    return pd.DataFrame(
        [
            {
                "Parametro": "Spostamento verticale massimo",
                "Valore": float(nodal["uy"].abs().max()),
                "Unita": "m",
                "Descrizione": "Massimo valore assoluto degli spostamenti uy",
            },
            {
                "Parametro": "Rotazione massima",
                "Valore": float(nodal["rz"].abs().max()),
                "Unita": "rad",
                "Descrizione": "Massimo valore assoluto delle rotazioni nodali",
            },
            {
                "Parametro": "Momento massimo",
                "Valore": float(elements[["M_i", "M_j"]].abs().max().max()) if not elements.empty else 0.0,
                "Unita": "forza*lunghezza",
                "Descrizione": "Massimo momento flettente agli estremi elemento",
            },
        ]
    )


def figura_telaio(sheets: Dict[str, pd.DataFrame], results: Dict[str, pd.DataFrame] | None = None, scale: float = 1.0) -> go.Figure:
    sheets = ensure_sheets(sheets)
    nodes = {
        int(row["id"]): (float(row["x"]), float(row["y"]))
        for _, row in sheets["nodes"].iterrows()
    }
    fig = go.Figure()
    for _, elem in sheets["elements"].iterrows():
        n1, n2 = int(elem["n1"]), int(elem["n2"])
        x = [nodes[n1][0], nodes[n2][0]]
        y = [nodes[n1][1], nodes[n2][1]]
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#1f2937", width=4), showlegend=False))
    fig.add_trace(
        go.Scatter(
            x=[p[0] for p in nodes.values()],
            y=[p[1] for p in nodes.values()],
            mode="markers+text",
            text=[str(i) for i in nodes],
            textposition="top center",
            marker=dict(size=9, color="#2563eb"),
            name="Nodi",
        )
    )
    if results and not results.get("results_nodal", pd.DataFrame()).empty:
        disp = results["results_nodal"].set_index("node_id")
        for _, elem in sheets["elements"].iterrows():
            n1, n2 = int(elem["n1"]), int(elem["n2"])
            x = [nodes[n1][0] + scale * float(disp.loc[n1, "ux"]), nodes[n2][0] + scale * float(disp.loc[n2, "ux"])]
            y = [nodes[n1][1] + scale * float(disp.loc[n1, "uy"]), nodes[n2][1] + scale * float(disp.loc[n2, "uy"])]
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#dc2626", width=2, dash="dash"), showlegend=False))
    fig.update_layout(
        template="plotly_white",
        title="Schema telaio 2D",
        xaxis_title="x",
        yaxis_title="y",
        yaxis_scaleanchor="x",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig
