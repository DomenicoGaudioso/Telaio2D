# -*- coding: utf-8 -*-
from __future__ import annotations

import streamlit as st

from reporting import create_word_report
from src import (
    default_model,
    ensure_sheets,
    figura_telaio,
    generate_multistory_multibay_frame,
    read_xlsx,
    solve_linear_static_opensees,
    tabella_sintesi,
    validate_model,
    write_xlsx,
)


st.set_page_config(page_title="Telaio2D", layout="wide")

st.title("Telaio2D CivilBox")
st.caption("Analisi statica lineare di telai piani con input XLSX, wizard strutturale e relazione Word.")

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

    with st.expander("Generatore telaio CivilBox", expanded=False):
        gen_bays = st.number_input("Campate", min_value=1, max_value=12, value=2, step=1)
        gen_stories = st.number_input("Piani", min_value=1, max_value=20, value=3, step=1)
        gen_bay_width = st.number_input("Larghezza campata", min_value=0.1, value=5.0, step=0.1)
        gen_story_height = st.number_input("Altezza piano", min_value=0.1, value=3.2, step=0.1)
        gen_E = st.number_input("Modulo E", min_value=0.1, value=30000000.0, step=100000.0, format="%.3f")
        gen_A = st.number_input("Area A", min_value=0.000001, value=0.12, step=0.01, format="%.6f")
        gen_I = st.number_input("Inerzia I", min_value=0.000000001, value=0.0036, step=0.0001, format="%.9f")
        gen_q = st.number_input("Carico distribuito travi qy", value=-18.0, step=1.0, format="%.3f")
        gen_fx = st.number_input("Forza orizzontale per piano", value=0.0, step=1.0, format="%.3f")
        if st.button("Genera telaio multipiano", use_container_width=True):
            try:
                st.session_state["sheets"] = generate_multistory_multibay_frame(
                    n_bays=int(gen_bays),
                    n_stories=int(gen_stories),
                    bay_width=float(gen_bay_width),
                    story_height=float(gen_story_height),
                    E=float(gen_E),
                    A=float(gen_A),
                    I=float(gen_I),
                    q_beams=float(gen_q),
                    horizontal_load_per_floor=float(gen_fx),
                )
                st.session_state["results"] = None
                st.success("Telaio generato.")
            except Exception as exc:
                st.error(f"Generazione non riuscita: {exc}")

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
        try:
            report_bytes = create_word_report(st.session_state.get("sheets", default_model()), results)
            st.download_button(
                "Scarica relazione Word",
                data=report_bytes,
                file_name="relazione_telaio2d_civilbox.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except Exception as exc:
            st.warning(f"Relazione Word non disponibile: {exc}")
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
