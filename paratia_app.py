# -*- coding: utf-8 -*-
import json
import pandas as pd
import streamlit as st
from paratia_src import (
    DatiParatia,
    valida_dati_paratia,
    calcola_paratia,
    figura_geometria_paratia,
    figura_risultati_paratia,
    DEFAULT_STRAT_PARATIA
)

# Prova a importare le librerie per il reporting
try:
    from paratia_reporting import crea_report_word_paratia
    reporting_enabled = True
except ImportError:
    reporting_enabled = False

DEFAULT_FASI = pd.DataFrame([
    {"livello_scavo_m": 5.0, "descrizione": "Scavo finale"},
])

DEFAULT_TIRANTI = pd.DataFrame([
    {"profondita_m": 2.0, "rigidezza_kN_m": 50000.0, "precarico_kN": 100.0, "fase_attivazione": 1},
])

DEFAULTS = {
    'altezza_scavo': 5.0, 'spessore_paratia': 0.6, 'lunghezza_paratia': 12.0,
    'E_cls_MPa': 30000.0, 'q_sovraccarico_kPa': 10.0, 'falda_monte_m': 7.0, 'falda_valle_m': 7.0, 'kh': 0.2, 'kv': 0.1,
    'stratigrafia_csv': DEFAULT_STRAT_PARATIA,
}

st.set_page_config(page_title='ParatieFEM', layout='wide')
st.title('ParatieFEM - Analisi di Opere di Sostegno Flessibili')
st.markdown("Strumento per l'analisi di paratie (pali, diaframmi) con il metodo degli Elementi Finiti (FEM) e interazione terreno-struttura non lineare.")

defaults = DEFAULTS.copy()
tiranti_defaults_df = DEFAULT_TIRANTI.copy()
fasi_defaults_df = DEFAULT_FASI.copy()

with st.sidebar:
    st.header('📂 Import / Export')
    up = st.file_uploader('Carica configurazione (JSON)', type=['json'])
    if up is not None:
        try:
            loaded_data = json.load(up)
            defaults.update(loaded_data)
            if 'tiranti_df' in loaded_data and isinstance(loaded_data['tiranti_df'], list):
                tiranti_defaults_df = pd.DataFrame(loaded_data['tiranti_df'])
            if 'fasi_costruttive_df' in loaded_data and isinstance(loaded_data['fasi_costruttive_df'], list):
                fasi_defaults_df = pd.DataFrame(loaded_data['fasi_costruttive_df'])
            st.success('Dati caricati con successo!')
        except Exception as e:
            st.error(f'Errore nel caricamento del file JSON: {e}')

    st.header('📐 Geometria e Materiali')
    altezza_scavo = st.number_input('Altezza Scavo H [m]', 1.0, 20.0, float(defaults['altezza_scavo']), 0.5)
    spessore_paratia = st.number_input('Spessore/Diametro Paratia [m]', 0.2, 2.0, float(defaults['spessore_paratia']), 0.1)
    lunghezza_paratia = st.number_input('Lunghezza Totale Paratia L [m]', altezza_scavo + 1.0, 50.0, float(defaults['lunghezza_paratia']), 1.0)
    E_cls_MPa = st.number_input('Modulo E Paratia [MPa]', 10000.0, 60000.0, float(defaults['E_cls_MPa']), 1000.0)

    st.header('🌍 Terreno e Falda')
    q_sovraccarico_kPa = st.number_input('Sovraccarico q [kPa]', 0.0, 100.0, float(defaults['q_sovraccarico_kPa']), 5.0)
    falda_monte_m = st.number_input('Prof. Falda a Monte [m]', 0.0, 50.0, float(defaults['falda_monte_m']), 0.5)
    falda_valle_m = st.number_input('Prof. Falda a Valle [m]', 0.0, 50.0, float(defaults['falda_valle_m']), 0.5)

    st.subheader('Stratigrafia')
    st.caption('Definire gli strati di terreno (spessore, γ, φ, c, Ks).')
    stratigrafia_csv = st.text_area('Spessore, γ, φ, c, Ks [MN/m³]', height=150, value=defaults['stratigrafia_csv'])

    st.header('🌊 Analisi Sismica (Mononobe-Okabe)')
    st.caption('Coefficienti per il calcolo delle spinte sismiche.')
    kh = st.number_input('Coefficiente Sismico Orizzontale kh', 0.0, 1.0, float(defaults.get('kh', 0.2)), 0.01)
    kv = st.number_input('Coefficiente Sismico Verticale kv', 0.0, 1.0, float(defaults.get('kv', 0.1)), 0.01)

    st.header('🏗️ Fasi Costruttive')
    st.caption('Definire i livelli di scavo successivi. L\'ultimo livello deve coincidere con l\'Altezza Scavo H.')
    edited_fasi_df = st.data_editor(
        fasi_defaults_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "livello_scavo_m": st.column_config.NumberColumn("Livello Scavo [m]", format="%.2f"),
            "descrizione": st.column_config.TextColumn("Descrizione Fase"),
        },
        key="fasi_editor"
    )

    st.header('⚓ Tiranti / Puntoni')
    st.caption('Definire i supporti e la fase di attivazione (es. Fase 1, 2, ...).')
    edited_tiranti_df = st.data_editor(
        tiranti_defaults_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "profondita_m": st.column_config.NumberColumn("Profondità [m]", format="%.2f"),
            "rigidezza_kN_m": st.column_config.NumberColumn("Rigidezza [kN/m]", format="%.0f"),
            "precarico_kN": st.column_config.NumberColumn("Precarico [kN]", format="%.0f"),
            "fase_attivazione": st.column_config.NumberColumn("Fase Attivazione", min_value=1, format="%d"),
        },
        key="tiranti_editor"
    )

    # Pulsante di download per l'export
    st.divider()
    current_input_data = {
        'altezza_scavo': altezza_scavo, 'spessore_paratia': spessore_paratia, 'lunghezza_paratia': lunghezza_paratia,
        'E_cls_MPa': E_cls_MPa, 'q_sovraccarico_kPa': q_sovraccarico_kPa, 'falda_monte_m': falda_monte_m,
        'falda_valle_m': falda_valle_m, 'stratigrafia_csv': stratigrafia_csv, 'kh': kh, 'kv': kv,
        'tiranti_df': edited_tiranti_df.to_dict('records'),
        'fasi_costruttive_df': edited_fasi_df.to_dict('records')
    }
    st.download_button(
        label="Scarica configurazione (JSON)",
        data=json.dumps(current_input_data, indent=2),
        file_name="config_paratia.json",
        mime="application/json"
    )

# Costruzione istanza Dati
dati_paratia = DatiParatia(
    altezza_scavo=altezza_scavo, spessore_paratia=spessore_paratia, lunghezza_paratia=lunghezza_paratia,
    E_cls_MPa=E_cls_MPa, q_sovraccarico_kPa=q_sovraccarico_kPa, falda_monte_m=falda_monte_m,
    falda_valle_m=falda_valle_m, stratigrafia_csv=stratigrafia_csv, tiranti_df=edited_tiranti_df,
    fasi_costruttive_df=edited_fasi_df, kh=kh, kv=kv
)

# Validazione
err = valida_dati_paratia(dati_paratia)
if err:
    for e in err:
        st.error(e)
    st.stop()

# Calcolo
try:
    with st.spinner("Analisi interazione terreno-struttura in corso..."):
        risultati = calcola_paratia(dati_paratia)

    momento_max = risultati['momento_kNm'].max()
    spostamento_max = risultati['spostamento_mm'].max()
    infissione_min = risultati['infissione_minima_m']
    fs_globale = risultati.get('fs_globale', -1.0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Infissione Minima [m]", f"{infissione_min:.2f}")
    c2.metric("Spostamento Max [mm]", f"{spostamento_max:.1f}")
    c3.metric("Momento Max [kNm/m]", f"{momento_max:.1f}")
    c4.metric("FS Stabilità Globale", f"{fs_globale:.2f}" if fs_globale > 0 else "N/A")

    # Tabs per i risultati
    tab_geom, tab_diag, tab_report = st.tabs(['Geometria', 'Diagrammi Risultati', 'Report'])

    with tab_geom:
        st.subheader("Geometria del Modello e Stratigrafia")
        st.plotly_chart(figura_geometria_paratia(dati_paratia, risultati), use_container_width=True)

    with tab_diag:
        st.subheader("Risultati dell'Analisi")
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(figura_risultati_paratia(risultati, 'spostamento_mm', 'Spostamento [mm]'), use_container_width=True)
            st.plotly_chart(figura_risultati_paratia(risultati, 'taglio_kN', 'Taglio [kN/m]'), use_container_width=True)
        with col2:
            st.plotly_chart(figura_risultati_paratia(risultati, 'momento_kNm', 'Momento [kNm/m]'), use_container_width=True)
            st.plotly_chart(figura_risultati_paratia(risultati, 'pressioni_kPa', 'Pressioni [kPa]'), use_container_width=True)

    if reporting_enabled:
        with tab_report:
            st.subheader("Generazione Relazione Tecnica")
            st.markdown(
                "Crea un report di calcolo in formato Microsoft Word (.docx) contenente i dati di input, "
                "i risultati di sintesi e le visualizzazioni grafiche dell'analisi."
            )
            if st.button("Genera Relazione Paratia (.docx)"):
                with st.spinner("Creazione del documento Word in corso..."):
                    try:
                        report_bytes = crea_report_word_paratia(dati_paratia, risultati)
                        st.download_button(
                            label="Scarica Relazione Word",
                            data=report_bytes,
                            file_name="Relazione_ParatiaFEM.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    except Exception as report_e:
                        st.error(f"Errore durante la generazione del report: {report_e}")

except Exception as e:
    st.error(f"Errore critico durante l'analisi: {e}")
    st.exception(e)