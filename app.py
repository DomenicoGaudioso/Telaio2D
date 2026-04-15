# app.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src import (
    read_xlsx, write_xlsx, ensure_sheets, validate_sheets,
    solve_linear_static_opensees, results_to_sheets
)

st.set_page_config(page_title="Telaio2D Web — OpenSeesPy", layout="wide")

st.title("Telaio2D Web (Streamlit) — XLSX editor + Linear Static OpenSeesPy")
st.caption("Importa XLSX → modifica tabelle → Solve (OpenSeesPy) → esporta XLSX con risultati")

# Session state
if "sheets" not in st.session_state:
    st.session_state.sheets = ensure_sheets({})
if "results" not in st.session_state:
    st.session_state.results = None

# Sidebar
with st.sidebar:
    st.header("File")
    up = st.file_uploader("Carica input .xlsx", type=["xlsx"])
    if up is not None:
        st.session_state.sheets = ensure_sheets(read_xlsx(up.getvalue()))
        st.session_state.results = None
        st.success("XLSX caricato.")

    lc_df = st.session_state.sheets.get("load_cases", pd.DataFrame())
    if lc_df is not None and not lc_df.empty and "id" in lc_df.columns:
        lc_ids = [int(x) for x in lc_df["id"].dropna().tolist()] or [1]
    else:
        lc_ids = [1]
    active_lc = st.selectbox("Load case attivo", lc_ids, index=0)

    st.divider()
    st.header("Solve (OpenSeesPy)")
    trapezoid_segments = st.slider("Segmenti per carico trapezoidale", 1, 50, 10, 1)

    if st.button("Valida modello"):
        errs = validate_sheets(st.session_state.sheets)
        if errs:
            st.error("Problemi trovati:\n" + "\n".join([f"• {e}" for e in errs]))
        else:
            st.success("OK: input coerente.")

    if st.button("Solve ▸ Linear Static"):
        errs = validate_sheets(st.session_state.sheets)
        if errs:
            st.error("Correggi prima gli errori:\n" + "\n".join([f"• {e}" for e in errs]))
        else:
            try:
                st.session_state.results = solve_linear_static_opensees(
                    st.session_state.sheets,
                    int(active_lc),
                    trapezoid_segments=trapezoid_segments,
                    geom_transf="Linear",
                )
                st.success("Analisi completata.")
            except Exception as ex:
                st.exception(ex)

    st.divider()
    st.header("Export")
    out_sheets = st.session_state.sheets
    if st.session_state.results is not None:
        out_sheets = results_to_sheets(out_sheets, st.session_state.results)
    xbytes = write_xlsx(out_sheets)
    st.download_button("Scarica XLSX (con risultati)", data=xbytes, file_name="telaio2d_output.xlsx")


# Main tabs
labels = [
    "nodes", "elements", "properties", "load_cases",
    "restraints", "node_loads", "dist_loads", "masses",
    "results", "plot"
]

tabs = st.tabs(labels)


def edit_sheet(name: str, default_cols: list):
    df = st.session_state.sheets.get(name, pd.DataFrame(columns=default_cols))
    if df is None:
        df = pd.DataFrame(columns=default_cols)
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"edit_{name}")
    st.session_state.sheets[name] = edited


with tabs[0]:
    st.subheader("nodes (id, x, y)")
    edit_sheet("nodes", ["id", "x", "y"])

with tabs[1]:
    st.subheader("elements (id, n1, n2, prop, type)")
    st.caption("type: beam2d (MVP)")
    edit_sheet("elements", ["id", "n1", "n2", "prop", "type"])

with tabs[2]:
    st.subheader("properties (id, name, E, A, I, rho, alphaT)")
    edit_sheet("properties", ["id", "name", "E", "A", "I", "rho", "alphaT"])

with tabs[3]:
    st.subheader("load_cases (id, name, ax, ay)")
    edit_sheet("load_cases", ["id", "name", "ax", "ay"])

with tabs[4]:
    st.subheader("restraints (load_case_id, node_id, ux, uy, rz)")
    edit_sheet("restraints", ["load_case_id", "node_id", "ux", "uy", "rz"])

with tabs[5]:
    st.subheader("node_loads (load_case_id, node_id, fx, fy, mz)")
    edit_sheet("node_loads", ["load_case_id", "node_id", "fx", "fy", "mz"])

with tabs[6]:
    st.subheader("dist_loads (load_case_id, elem_id, qx0, qx1, qy0, qy1)")
    st.caption("Trapezio approssimato come somma di carichi uniformi (segmenti)")
    edit_sheet("dist_loads", ["load_case_id", "elem_id", "qx0", "qx1", "qy0", "qy1"])

with tabs[7]:
    st.subheader("masses (load_case_id, node_id, mx, my)")
    edit_sheet("masses", ["load_case_id", "node_id", "mx", "my"])

with tabs[8]:
    st.subheader("results")
    if st.session_state.results is None:
        st.info("Esegui Solve per vedere i risultati.")
    else:
        st.markdown("### results_nodal")
        st.dataframe(st.session_state.results["results_nodal"], use_container_width=True)
        st.markdown("### results_elements (localForce → N,V,M)")
        st.dataframe(st.session_state.results["results_elements"], use_container_width=True)

with tabs[9]:
    st.subheader("plot (schema + deformata)")
    nodes = st.session_state.sheets.get("nodes", pd.DataFrame())
    elems = st.session_state.sheets.get("elements", pd.DataFrame())

    if nodes is None or nodes.empty or elems is None or elems.empty:
        st.info("Inserisci nodes ed elements.")
    else:
        coords = {int(r["id"]): (float(r["x"]), float(r["y"])) for _, r in nodes.iterrows() if pd.notna(r.get("id"))}
        fig = go.Figure()

        # undeformed
        for _, e in elems.iterrows():
            if str(e.get("type", "")).strip().lower() != "beam2d":
                continue
            n1 = int(e["n1"]); n2 = int(e["n2"])
            if n1 not in coords or n2 not in coords:
                continue
            x1, y1 = coords[n1]; x2, y2 = coords[n2]
            fig.add_trace(go.Scatter(x=[x1, x2], y=[y1, y2], mode="lines",
                                     line=dict(color="#888", width=2), showlegend=False))

        # deformed
        if st.session_state.results is not None:
            scale = st.slider("Scala deformata", 0.0, 500.0, 50.0, 1.0)
            disp = st.session_state.results["results_nodal"].set_index("node_id")
            dcoords = {}
            for nid, (x, y) in coords.items():
                ux = float(disp.loc[nid, "ux"]) if nid in disp.index else 0.0
                uy = float(disp.loc[nid, "uy"]) if nid in disp.index else 0.0
                dcoords[nid] = (x + scale * ux, y + scale * uy)

            for _, e in elems.iterrows():
                if str(e.get("type", "")).strip().lower() != "beam2d":
                    continue
                n1 = int(e["n1"]); n2 = int(e["n2"])
                if n1 not in dcoords or n2 not in dcoords:
                    continue
                x1, y1 = dcoords[n1]; x2, y2 = dcoords[n2]
                fig.add_trace(go.Scatter(x=[x1, x2], y=[y1, y2], mode="lines",
                                         line=dict(color="#1f77b4", width=3), showlegend=False))

        fig.update_layout(
            xaxis=dict(scaleanchor="y", title="X"),
            yaxis=dict(title="Y"),
            margin=dict(l=10, r=10, t=10, b=10),
            height=600
        )
        st.plotly_chart(fig, use_container_width=True)
