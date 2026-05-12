# -*- coding: utf-8 -*-
from __future__ import annotations

import streamlit as st

from src import (
    default_model,
    ensure_sheets,
    figura_telaio,
    read_xlsx,
    solve_linear_static_opensees,
    tabella_sintesi,
    validate_model,
    write_xlsx,
)


st.set_page_config(page_title="Telaio2D", layout="wide")

st.title("Telaio2D")
st.caption("Analisi statica lineare di telai piani con input XLSX e risultati tabellari.")

if "sheets" not in st.session_state:
    st.session_state["sheets"] = default_model()
if "results" not in st.session_state:
    st.session_state["results"] = None

with st.sidebar:
    st.header("Import / Export")
    uploaded = st.file_uploader("Carica modello XLSX", type=["xlsx"])
    if uploaded is not None:
        try:
            st.session_state["sheets"] = ensure_sheets(read_xlsx(uploaded.getvalue()))
            st.session_state["results"] = None
            st.success("Modello caricato.")
        except Exception as exc:
            st.error(f"XLSX non valido: {exc}")

    st.download_button(
        "Salva modello XLSX",
        data=write_xlsx(st.session_state.get("results") or st.session_state.get("sheets", default_model())),
        file_name="telaio2d_modello.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    load_cases = st.session_state.get("sheets", default_model())["load_cases"]
    case_ids = [int(v) for v in load_cases["id"].dropna().tolist()] or [1]
    load_case_id = st.selectbox("Caso di carico", case_ids, index=0)
    scale = st.slider("Scala deformata", 1.0, 500.0, 50.0, 1.0)

    if st.button("Esegui analisi", type="primary"):
        errors = validate_model(st.session_state.get("sheets", default_model()))
        if errors:
            for error in errors:
                st.error(error)
        else:
            try:
                st.session_state["results"] = solve_linear_static_opensees(
                    st.session_state.get("sheets", default_model()), int(load_case_id)
                )
                st.success("Analisi completata.")
            except Exception as exc:
                st.error(f"Analisi non riuscita: {exc}")


tabs = st.tabs(["Input", "Schema", "Risultati", "Log tecnico"])

with tabs[0]:
    st.subheader("Fogli modello")
    st.caption("Le tabelle possono essere copiate/incollate da Excel.")
    sheets = st.session_state.get("sheets", default_model())
    for name in [
        "nodes",
        "elements",
        "properties",
        "load_cases",
        "restraints",
        "node_loads",
        "dist_loads",
        "masses",
    ]:
        with st.expander(name, expanded=name in {"nodes", "elements", "node_loads"}):
            sheets[name] = st.data_editor(
                sheets[name],
                use_container_width=True,
                num_rows="dynamic",
                key=f"editor_{name}",
            )
    st.session_state["sheets"] = ensure_sheets(sheets)

with tabs[1]:
    st.plotly_chart(
        figura_telaio(
            st.session_state.get("sheets", default_model()),
            st.session_state.get("results"),
            scale=scale,
        ),
        use_container_width=True,
    )

with tabs[2]:
    results = st.session_state.get("results")
    if results is None:
        st.info("Eseguire l'analisi per visualizzare i risultati.")
    else:
        st.subheader("Sintesi")
        st.dataframe(tabella_sintesi(results), use_container_width=True, hide_index=True)
        st.subheader("Risultati nodali")
        st.dataframe(results["results_nodal"], use_container_width=True, hide_index=True)
        st.subheader("Risultati elementi")
        st.dataframe(results["results_elements"], use_container_width=True, hide_index=True)

with tabs[3]:
    errors = validate_model(st.session_state.get("sheets", default_model()))
    if errors:
        for error in errors:
            st.warning(error)
    else:
        st.success("Modello valido per l'analisi lineare statica.")
    st.markdown(
        """
        **Ipotesi principali**

        - elementi beam2d Euler-Bernoulli;
        - piccoli spostamenti e materiale lineare elastico;
        - carichi nodali e carichi distribuiti equivalenti;
        - risultati in unita coerenti con quelle inserite dall'utente.
        """
    )
