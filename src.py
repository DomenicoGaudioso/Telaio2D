# src.py
from __future__ import annotations

from io import BytesIO
from typing import Dict, List

import pandas as pd
import openseespy.opensees as ops  # pip install openseespy

# -----------------------------
# I/O XLSX
# -----------------------------
REQUIRED_SHEETS = ["nodes", "elements", "properties", "load_cases", "restraints", "node_loads"]
OPTIONAL_SHEETS = ["dist_loads", "masses"]


def read_xlsx(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    bio = BytesIO(file_bytes)
    xls = pd.ExcelFile(bio, engine="openpyxl")
    data: Dict[str, pd.DataFrame] = {}
    for sh in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sh, engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]
        data[sh.strip().lower()] = df
    return data


def write_xlsx(sheets: Dict[str, pd.DataFrame]) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=name[:31])
    return bio.getvalue()


def ensure_sheets(sheets: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = dict(sheets)
    for sh in REQUIRED_SHEETS:
        if sh not in out or out[sh] is None:
            out[sh] = pd.DataFrame()
    for sh in OPTIONAL_SHEETS:
        if sh not in out or out[sh] is None:
            out[sh] = pd.DataFrame()
    return out


# -----------------------------
# Validazione
# -----------------------------

def validate_sheets(sheets: Dict[str, pd.DataFrame]) -> List[str]:
    s = ensure_sheets(sheets)
    errs: List[str] = []

    def need_cols(df: pd.DataFrame, cols: List[str], name: str):
        if df is None or df.empty:
            return
        miss = [c for c in cols if c not in df.columns]
        if miss:
            errs.append(f"{name}: mancano colonne {miss}")

    need_cols(s["nodes"], ["id", "x", "y"], "nodes")
    need_cols(s["elements"], ["id", "n1", "n2", "prop", "type"], "elements")
    need_cols(s["properties"], ["id", "name", "E", "A", "I"], "properties")
    need_cols(s["load_cases"], ["id", "name"], "load_cases")
    need_cols(s["restraints"], ["load_case_id", "node_id", "ux", "uy", "rz"], "restraints")
    need_cols(s["node_loads"], ["load_case_id", "node_id", "fx", "fy", "mz"], "node_loads")

    # opzionali: se presenti, devono avere colonne
    if s["dist_loads"] is not None and not s["dist_loads"].empty:
        need_cols(s["dist_loads"], ["load_case_id", "elem_id", "qx0", "qx1", "qy0", "qy1"], "dist_loads")
    if s["masses"] is not None and not s["masses"].empty:
        need_cols(s["masses"], ["load_case_id", "node_id", "mx", "my"], "masses")

    return errs


# -----------------------------
# OpenSeesPy - Setup analisi
# -----------------------------

def _analysis_linear_static():
    """Setup minimo robusto per analisi statica lineare."""
    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Plain")
    ops.test("NormDispIncr", 1e-12, 10)
    ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")


def _apply_trapezoid_as_segment_uniform(eleTag: int, qy0: float, qy1: float, qx0: float, qx1: float, nseg: int):
    """Approssima trapezio come somma di carichi uniformi (beamUniform) segmentati."""
    nseg = max(1, int(nseg))
    for k in range(nseg):
        sm = (k + 0.5) / nseg
        qy = qy0 + (qy1 - qy0) * sm
        qx = qx0 + (qx1 - qx0) * sm
        # eleLoad ... -beamUniform Wy Wx
        ops.eleLoad("-ele", int(eleTag), "-type", "-beamUniform", float(qy), float(qx))


def solve_linear_static_opensees(
    sheets: Dict[str, pd.DataFrame],
    load_case_id: int,
    trapezoid_segments: int = 10,
    geom_transf: str = "Linear",
) -> Dict[str, pd.DataFrame]:
    """Linear Static (OpenSeesPy) per telai 2D con beam elastici.

    Input: sheets (dict di DataFrame), load_case_id.
    Output: dict con DataFrame results_nodal e results_elements.

    Convenzioni:
    - type elemento: 'beam2d'
    - carico distribuito: dist_loads con qx0,qx1,qy0,qy1 (trapezio) -> segmenti uniformi
    - forze interne: eleResponse(ele,'localForce') => [P1,V1,M1,P2,V2,M2] (tipico per beam)
    """
    s = ensure_sheets(sheets)
    errs = validate_sheets(s)
    if errs:
        raise ValueError("Input non valido:\n- " + "\n- ".join(errs))

    nodes = s["nodes"].copy()
    elems = s["elements"].copy()
    props = s["properties"].copy()

    if nodes.empty or elems.empty or props.empty:
        raise ValueError("nodes/elements/properties non possono essere vuoti")

    # normalizza id
    nodes["id"] = nodes["id"].astype(int)
    elems["id"] = elems["id"].astype(int)
    elems["n1"] = elems["n1"].astype(int)
    elems["n2"] = elems["n2"].astype(int)
    elems["prop"] = elems["prop"].astype(int)
    props["id"] = props["id"].astype(int)

    coords = {int(r["id"]): (float(r["x"]), float(r["y"])) for _, r in nodes.iterrows()}
    prop_map = {int(r["id"]): r for _, r in props.iterrows()}

    # reset domain
    ops.wipe()

    # model 2D 3 dof per nodo
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    # nodes
    for nid, (x, y) in coords.items():
        ops.node(nid, x, y)

    # masses (optional)
    ms = s.get("masses", pd.DataFrame())
    if ms is not None and not ms.empty:
        ms = ms[ms["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in ms.iterrows():
            nid = int(r["node_id"])
            mx = float(r.get("mx", 0.0))
            my = float(r.get("my", 0.0))
            ops.mass(nid, mx, my, 0.0)

    # restraints
    rr = s["restraints"]
    if rr is not None and not rr.empty:
        rr = rr[rr["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in rr.iterrows():
            nid = int(r["node_id"])
            ux = 1 if bool(r.get("ux", False)) else 0
            uy = 1 if bool(r.get("uy", False)) else 0
            rz = 1 if bool(r.get("rz", False)) else 0
            ops.fix(nid, ux, uy, rz)

    # geometric transformation
    transfTag = 1
    ops.geomTransf(str(geom_transf), transfTag)

    # elements: elasticBeamColumn
    for _, e in elems.iterrows():
        if str(e.get("type", "")).strip().lower() != "beam2d":
            continue
        eleTag = int(e["id"])
        n1 = int(e["n1"])
        n2 = int(e["n2"])
        pid = int(e["prop"])
        if pid not in prop_map:
            raise ValueError(f"Elemento {eleTag}: proprietà {pid} non trovata")
        pr = prop_map[pid]
        A = float(pr["A"])
        E = float(pr["E"])
        I = float(pr["I"])
        ops.element("elasticBeamColumn", eleTag, n1, n2, A, E, I, transfTag)

    # loads: timeSeries Linear + pattern Plain
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)

    # nodal loads
    nl = s["node_loads"]
    if nl is not None and not nl.empty:
        nl = nl[nl["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in nl.iterrows():
            nid = int(r["node_id"])
            fx = float(r.get("fx", 0.0))
            fy = float(r.get("fy", 0.0))
            mz = float(r.get("mz", 0.0))
            ops.load(nid, fx, fy, mz)

    # distributed loads
    dl = s.get("dist_loads", pd.DataFrame())
    if dl is not None and not dl.empty:
        dl = dl[dl["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in dl.iterrows():
            eleTag = int(r["elem_id"])
            qx0 = float(r.get("qx0", 0.0))
            qx1 = float(r.get("qx1", 0.0))
            qy0 = float(r.get("qy0", 0.0))
            qy1 = float(r.get("qy1", 0.0))
            _apply_trapezoid_as_segment_uniform(eleTag, qy0, qy1, qx0, qx1, trapezoid_segments)

    # analysis
    _analysis_linear_static()
    ok = ops.analyze(1)
    if ok != 0:
        raise RuntimeError(f"OpenSees analyze failed with code={ok}")

    # reactions
    ops.reactions()

    # nodal results
    nodal_rows = []
    for nid in coords.keys():
        ux = ops.nodeDisp(nid, 1)
        uy = ops.nodeDisp(nid, 2)
        rz = ops.nodeDisp(nid, 3)
        rx = ops.nodeReaction(nid, 1)
        ry = ops.nodeReaction(nid, 2)
        rm = ops.nodeReaction(nid, 3)
        nodal_rows.append({
            "node_id": int(nid),
            "ux": float(ux), "uy": float(uy), "rz": float(rz),
            "Rx": float(rx), "Ry": float(ry), "Rz": float(rm)
        })

    # element forces (local)
    elem_rows = []
    for _, e in elems.iterrows():
        if str(e.get("type", "")).strip().lower() != "beam2d":
            continue
        eleTag = int(e["id"])
        lf = ops.eleResponse(eleTag, "localForce")
        lf = list(lf) if lf is not None else []
        lf = (lf + [0.0] * 6)[:6]
        P1, V1, M1, P2, V2, M2 = [float(x) for x in lf]
        elem_rows.append({
            "id": eleTag,
            "n1": int(e["n1"]), "n2": int(e["n2"]),
            "N_i": P1, "V_i": V1, "M_i": M1,
            "N_j": P2, "V_j": V2, "M_j": M2
        })

    return {
        "results_nodal": pd.DataFrame(nodal_rows),
        "results_elements": pd.DataFrame(elem_rows),
    }


def results_to_sheets(base_sheets: Dict[str, pd.DataFrame], results: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = dict(base_sheets)
    for k, df in results.items():
        out[k] = df
    return out
