# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from io import StringIO

DEFAULT_STRAT_PARATIA = """15.0, 18.0, 30, 5, 20
"""
GAMMA_W = 9.81  # Peso di volume dell'acqua in kN/m^3


@dataclass(frozen=True)
class DatiParatia:
    altezza_scavo: float
    spessore_paratia: float
    lunghezza_paratia: float
    E_cls_MPa: float
    q_sovraccarico_kPa: float
    falda_monte_m: float
    falda_valle_m: float
    stratigrafia_csv: str
    tiranti_df: pd.DataFrame
    fasi_costruttive_df: pd.DataFrame
    kh: float
    kv: float
    poisson: float = 0.2

def valida_dati_paratia(d: DatiParatia) -> List[str]:
    """Valida i dati di input per l'analisi della paratia."""
    err = []
    if d.altezza_scavo <= 0 or d.spessore_paratia <= 0 or d.lunghezza_paratia <= 0:
        err.append('Le dimensioni geometriche devono essere positive.')
    if d.lunghezza_paratia <= d.altezza_scavo:
        err.append('La lunghezza della paratia deve essere maggiore dell\'altezza di scavo.')
    if not d.stratigrafia_csv.strip():
        err.append('Inserire almeno uno strato nella stratigrafia.')
    if d.fasi_costruttive_df.empty:
        err.append('Definire almeno una fase costruttiva.')
    else:
        livelli_scavo = d.fasi_costruttive_df['livello_scavo_m']
        if not all(livelli_scavo.diff().dropna() >= 0):
            err.append('I livelli di scavo nelle fasi costruttive devono essere non decrescenti.')
        if not np.isclose(livelli_scavo.iloc[-1], d.altezza_scavo):
            err.append('Il livello di scavo dell\'ultima fase deve coincidere con l\'Altezza Scavo H.')

    if d.kh > 0 and (1 - d.kv) <= 0:
        err.append('Il coefficiente kv deve essere minore di 1 per l\'analisi sismica.')

    for index, tirante in d.tiranti_df.iterrows():
        if tirante['profondita_m'] <= 0:
            err.append(f"Tirante #{index+1}: la profondità deve essere positiva.")
        if tirante['profondita_m'] >= d.altezza_scavo:
            err.append(f"Tirante #{index+1}: la profondità deve essere minore dell'altezza di scavo.")
        if tirante['rigidezza_kN_m'] <= 0:
            err.append(f"Tirante #{index+1}: la rigidezza deve essere positiva.")
        fase_attivazione = int(tirante.get('fase_attivazione', 1))
        if not (1 <= fase_attivazione <= len(d.fasi_costruttive_df)):
            err.append(f"Tirante #{index+1}: Fase di attivazione non valida.")
        else:
            livello_scavo_attivazione = d.fasi_costruttive_df.iloc[fase_attivazione - 1]['livello_scavo_m']
            if tirante['profondita_m'] > livello_scavo_attivazione:
                err.append(f"Tirante #{index+1}: non può essere attivato prima che lo scavo superi la sua profondità.")

    return err

def _parse_stratigrafia_paratia(csv_text: str) -> pd.DataFrame:
    """Parses the CSV text for stratigraphy into a DataFrame."""
    if not csv_text.strip():
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(
            StringIO(csv_text),
            header=None,
            names=['spessore_m', 'gamma_kN_m3', 'phi_deg', 'c_kPa', 'ks_kPa_m'],
            skipinitialspace=True,
            comment='#'
        )
        df['z_top_m'] = df['spessore_m'].cumsum() - df['spessore_m']
        df['z_bot_m'] = df['spessore_m'].cumsum()
        return df
    except Exception:
        return pd.DataFrame()

def _calcola_kae_mononobe_okabe(phi_deg, delta_deg, beta_deg, i_deg, kh, kv):
    """Calcola il coefficiente di spinta attiva sismica Kae."""
    if (1 - kv) <= 0:
        return None

    phi = np.radians(phi_deg)
    delta = np.radians(delta_deg)
    beta = np.radians(beta_deg)
    i = np.radians(i_deg)
    
    theta = np.arctan(kh / (1 - kv))

    num_cos = np.cos(phi - theta - beta)
    if num_cos < 0: return None # Invalid angle combination
    num = num_cos**2

    den1_cos1 = np.cos(theta)
    den1_cos2 = np.cos(beta)**2
    den1_cos3 = np.cos(delta + beta + theta)
    if den1_cos1 == 0 or den1_cos3 == 0: return None
    den1 = den1_cos1 * den1_cos2 * den1_cos3

    sqrt_num = np.sin(phi + delta) * np.sin(phi - theta - i)
    sqrt_den_cos1 = np.cos(delta + beta + theta)
    sqrt_den_cos2 = np.cos(i - beta)
    if sqrt_den_cos1 == 0 or sqrt_den_cos2 == 0: return None
    
    sqrt_arg = sqrt_num / (sqrt_den_cos1 * sqrt_den_cos2)
    if sqrt_arg < 0: return None

    den2 = (1 + np.sqrt(sqrt_arg))**2
    
    den = den1 * den2
    if den == 0: return None

    kae = num / den
    # La spinta sismica non può essere minore di quella statica
    ka_static = np.tan(np.radians(45 - phi_deg/2))**2
    return max(kae, ka_static)

def _get_sigma_v(z, strat_df, z_start=0.0, q_kpa=0.0):
    """Calcola la tensione verticale totale a una profondità z."""
    if z <= z_start or strat_df.empty:
        return 0.0
    
    # Il sovraccarico si applica solo se partiamo dal piano campagna
    sigma_v = q_kpa if z_start == 0.0 else 0.0
    
    for _, s in strat_df.iterrows():
        strato_z_top = s['z_top_m']
        strato_z_bot = s['z_bot_m']
        
        # Considera solo la porzione di strato sopra z e sotto z_start
        if z > strato_z_top:
            effective_z_top = max(strato_z_top, z_start)
            
            if z > effective_z_top:
                thickness_in_stress_calc = min(z, strato_z_bot) - effective_z_top
                sigma_v += thickness_in_stress_calc * s['gamma_kN_m3']
    return sigma_v

def _calcola_stabilita_globale_fellenius(d: DatiParatia, strat_df: pd.DataFrame) -> tuple[float, float, float, float]:
    """
    Calcola il fattore di sicurezza per stabilità globale con il metodo di Fellenius (semplificato).
    Viene analizzata una griglia di cerchi di rottura per trovare il FS minimo.
    Restituisce (fs_min, cx_critico, cy_critico, R_critico).
    """
    cx_critico, cy_critico, R_critico = None, None, None

    if strat_df.empty:
        return 999.0

    H = d.altezza_scavo
    
    # --- Definizione della griglia di centri dei cerchi di rottura ---
    # Griglia posizionata "dietro" e "sopra" il piede della paratia (punto 0, -H)
    centri_x = np.linspace(-H * 0.5, H * 1.5, 15)
    centri_y = np.linspace(H * 0.1, H * 2.0, 15)
    
    fs_min = np.inf

    # Itera su tutti i possibili centri
    for cx in centri_x:
        for cy in centri_y:
            # Il raggio è tale che il cerchio passi per il piede della paratia
            R = np.sqrt((0 - cx)**2 + (-H - cy)**2)

            # --- Analisi per un singolo cerchio di rottura ---
            # Trova il punto di intersezione superiore del cerchio con il piano campagna (y=0)
            if R**2 < cy**2:
                continue # Il cerchio non interseca il piano campagna
            
            x_start = cx - np.sqrt(R**2 - cy**2)
            x_end = 0 # Il cuneo di rottura finisce alla paratia
            
            if x_start >= x_end:
                continue

            # Discretizzazione in fette verticali
            n_fette = 30
            fette_x_bordi = np.linspace(x_start, x_end, n_fette + 1)
            dx = (x_end - x_start) / n_fette
            
            somma_num_fs = 0.0
            somma_den_fs = 0.0

            for i in range(n_fette):
                x_i = (fette_x_bordi[i] + fette_x_bordi[i+1]) / 2
                if R**2 <= (x_i - cx)**2: continue
                y_base = cy - np.sqrt(R**2 - (x_i - cx)**2)
                if y_base >= 0: continue
                z_base = -y_base
                
                alpha_i = np.arcsin((x_i - cx) / R)
                l_i = dx / np.cos(alpha_i)

                strato_df = strat_df[(strat_df['z_top_m'] <= z_base) & (strat_df['z_bot_m'] > z_base)]
                if strato_df.empty: strato_df = strat_df.iloc[[-1]] if z_base > strat_df['z_bot_m'].iloc[-1] else strat_df.iloc[[0]]
                strato = strato_df.iloc[0]
                
                W_i = _get_sigma_v(z_base, strat_df, q_kpa=d.q_sovraccarico_kPa) * dx
                u_i = GAMMA_W * max(0, z_base - d.falda_monte_m)
                num = strato['c_kPa'] * l_i + (W_i * np.cos(alpha_i) - u_i * l_i) * np.tan(np.radians(strato['phi_deg']))
                den = W_i * np.sin(alpha_i)
                if num > 0: somma_num_fs += num
                if den > 0: somma_den_fs += den

            if somma_den_fs > 1e-6:
                fs_cerchio = somma_num_fs / somma_den_fs
                if fs_cerchio < fs_min: fs_min = fs_cerchio
                    cx_critico, cy_critico, R_critico = cx, cy, R
    
    return fs_min if fs_min < np.inf else -1.0, cx_critico, cy_critico, R_critico

def calcola_paratia(d: DatiParatia) -> Dict:
    """
    Placeholder per l'analisi FEM di una paratia.
    Questa funzione verrà implementata con la logica di calcolo effettiva
    utilizzando un solutore FEM come OpenSeesPy.
    """
    # --- LOGICA DI CALCOLO (PLACEHOLDER) ---
    # Questa funzione simula un'analisi per fasi. La spinta statica del terreno è calcolata
    # con la teoria di Rankine. La spinta sismica è aggiunta con Mononobe-Okabe.
    # Viene eseguita un'analisi di stabilità globale con il metodo di Fellenius.

    strat_df = _parse_stratigrafia_paratia(d.stratigrafia_csv)

    n_punti = 50
    profondita = np.linspace(0, d.lunghezza_paratia, n_punti)
    spostamenti = np.zeros_like(profondita)
    livello_scavo_prec = 0.0

    # Calcolo pressioni idrostatiche nette
    p_acqua_monte = GAMMA_W * np.maximum(0, profondita - d.falda_monte_m)
    p_acqua_valle = GAMMA_W * np.maximum(0, profondita - d.falda_valle_m)
    # La pressione dell'acqua a valle agisce solo al di sotto del piano scavo
    p_acqua_valle[profondita < d.altezza_scavo] = 0
    p_netta_acqua = p_acqua_monte - p_acqua_valle

    # --- Calcolo Pressioni Statiche Terreno (Rankine) ---
    p_attiva_eff = np.zeros_like(profondita)
    p_passiva_eff = np.zeros_like(profondita)

    if not strat_df.empty:
        for i, z in enumerate(profondita):
            # Find stratum at depth z
            strato = strat_df[(strat_df['z_top_m'] <= z) & (strat_df['z_bot_m'] > z)]
            if strato.empty and z > 0:
                strato = strat_df.iloc[[-1]]
            
            if not strato.empty:
                phi_deg = strato['phi_deg'].iloc[0]
                c_kPa = strato['c_kPa'].iloc[0]
                
                # --- Pressione Attiva (Monte) ---
                sigma_v_monte = _get_sigma_v(z, strat_df, z_start=0.0, q_kpa=d.q_sovraccarico_kPa)
                u_monte_z = GAMMA_W * max(0, z - d.falda_monte_m)
                sigma_v_eff_monte = sigma_v_monte - u_monte_z
                
                Ka = np.tan(np.radians(45 - phi_deg / 2))**2
                p_attiva_eff[i] = max(0, Ka * sigma_v_eff_monte - 2 * c_kPa * np.sqrt(Ka))

                # --- Pressione Passiva (Valle) ---
                if z > d.altezza_scavo:
                    sigma_v_valle = _get_sigma_v(z, strat_df, z_start=d.altezza_scavo, q_kpa=0.0)
                    u_valle_z = GAMMA_W * max(0, z - d.falda_valle_m)
                    sigma_v_eff_valle = sigma_v_valle - u_valle_z
                    
                    Kp = np.tan(np.radians(45 + phi_deg / 2))**2
                    p_passiva_eff[i] = Kp * sigma_v_eff_valle + 2 * c_kPa * np.sqrt(Kp)

    pressioni_terreno_nette = p_attiva_eff - p_passiva_eff

    # Calcolo spinta sismica con Mononobe-Okabe (formula completa)
    spinta_sismica_addizionale = np.zeros_like(profondita)
    if d.kh > 0 and (1 - d.kv) > 0 and not strat_df.empty:
        # Calcolo parametri medi del terreno fino alla profondità di scavo
        H = d.altezza_scavo
        terreno_sopra_scavo = strat_df[strat_df['z_top_m'] < H]
        total_weight_phi = 0
        total_weight_gamma = 0
        total_thickness = 0

        for _, strato in terreno_sopra_scavo.iterrows():
            z_top = strato['z_top_m']
            z_bot = strato['z_bot_m']
            spessore_nello_scavo = min(z_bot, H) - z_top
            if spessore_nello_scavo > 0:
                total_weight_phi += spessore_nello_scavo * strato['phi_deg']
                total_weight_gamma += spessore_nello_scavo * strato['gamma_kN_m3']
                total_thickness += spessore_nello_scavo

        if total_thickness > 0:
            phi_medio_deg = total_weight_phi / total_thickness
            gamma_medio = total_weight_gamma / total_thickness

            # Parametri per Mononobe-Okabe
            delta_deg = phi_medio_deg / 2  # Angolo di attrito terra-muro
            beta_deg = 0             # Inclinazione del paramento sul verticale
            i_deg = 0                # Inclinazione del terrapieno

            Ka = np.tan(np.radians(45 - phi_medio_deg / 2))**2
            Kae = _calcola_kae_mononobe_okabe(phi_medio_deg, delta_deg, beta_deg, i_deg, d.kh, d.kv)

            if Kae is not None and Kae > Ka:
                # Incremento di spinta sismica distribuito uniformemente
                pressione_sismica_uniforme = 0.5 * gamma_medio * H * (Kae - Ka)
                mask = profondita <= H
                spinta_sismica_addizionale[mask] = pressione_sismica_uniforme

    # Simulazione delle fasi (placeholder)
    for index, fase in d.fasi_costruttive_df.iterrows():
        livello_scavo_attuale = fase['livello_scavo_m']
        delta_scavo = livello_scavo_attuale - livello_scavo_prec
        spostamento_fase = (delta_scavo / d.altezza_scavo) * 20 * np.sin(np.pi * profondita / d.lunghezza_paratia) * (profondita / d.lunghezza_paratia)
        spostamenti += spostamento_fase

        tiranti_attivati_in_fase = d.tiranti_df[d.tiranti_df['fase_attivazione'] == (index + 1)]
        for _, tirante in tiranti_attivati_in_fase.iterrows():
            prof_tirante = tirante['profondita_m']
            spostamento_al_tirante = np.interp(prof_tirante, profondita, spostamenti)
            riduzione = spostamento_al_tirante * 0.8 * np.exp(-((profondita - prof_tirante)**2) / (2 * 2.0**2))
            spostamenti -= riduzione
        livello_scavo_prec = livello_scavo_attuale

    # Aggiungi un contributo di spostamento dovuto alla spinta netta dell'acqua
    spostamento_acqua = (p_netta_acqua / (GAMMA_W * d.lunghezza_paratia)) * 5 * np.sin(np.pi * profondita / d.lunghezza_paratia)
    spostamenti += spostamento_acqua

    # Aggiungi un contributo di spostamento dovuto alla spinta sismica
    spostamento_sisma = (spinta_sismica_addizionale / 100) * np.sin(np.pi * profondita / d.lunghezza_paratia)
    spostamenti += spostamento_sisma

    momenti = 150 * np.sin(np.pi * profondita / d.lunghezza_paratia)
    tagli = 50 * np.cos(np.pi * profondita / d.lunghezza_paratia)

    # --- Calcolo Stabilità Globale (Fellenius) ---
    fs_globale, cx_critico, cy_critico, R_critico = _calcola_stabilita_globale_fellenius(d, strat_df)

    # Pressione totale = Pressione netta terreno (attiva-passiva) + Pressione netta acqua + Spinta sismica
    pressioni = pressioni_terreno_nette + p_netta_acqua + spinta_sismica_addizionale
    return {
        'profondita_m': profondita,
        'spostamento_mm': spostamenti,
        'momento_kNm': momenti,
        'taglio_kN': tagli,
        'pressioni_kPa': pressioni,
        'infissione_minima_m': d.lunghezza_paratia - d.altezza_scavo,
        'stratigrafia_df': strat_df,
        'fs_globale': fs_globale,
        'cx_critico': cx_critico,
        'cy_critico': cy_critico,
        'R_critico': R_critico
    }

def figura_geometria_paratia(d: DatiParatia, r: Dict) -> go.Figure:
    """Crea una figura Plotly che mostra la geometria del problema."""
    fig = go.Figure()

    # Paratia
    fig.add_shape(type="rect", x0=-d.spessore_paratia/2, y0=0, x1=d.spessore_paratia/2, y1=-d.lunghezza_paratia,
                  fillcolor="LightSteelBlue", line_color="black", name="Paratia")

    # Terreno a monte
    fig.add_shape(type="rect", x0=d.spessore_paratia/2, y0=0, x1=d.spessore_paratia/2 + 5, y1=-d.lunghezza_paratia,
                  fillcolor="SaddleBrown", opacity=0.3)
    # Terreno a valle
    fig.add_shape(type="rect", x0=-d.spessore_paratia/2 - 5, y0=-d.altezza_scavo, x1=-d.spessore_paratia/2,
                  fillcolor="SaddleBrown", opacity=0.3)

    # Falda a monte
    fig.add_shape(type="rect", x0=d.spessore_paratia/2, y0=-d.falda_monte_m, x1=d.spessore_paratia/2 + 5, y1=-d.lunghezza_paratia,
                  fillcolor="LightSkyBlue", opacity=0.4, layer="below")
    fig.add_shape(type="line", x0=d.spessore_paratia/2, y0=-d.falda_monte_m, x1=d.spessore_paratia/2 + 5, y1=-d.falda_monte_m,
                  line=dict(color="Blue", width=1, dash="dot"))

    # Falda a valle
    if d.falda_valle_m <= d.lunghezza_paratia:
        fig.add_shape(type="rect", x0=-d.spessore_paratia/2 - 5, y0=-d.falda_valle_m, x1=-d.spessore_paratia/2,
                      fillcolor="LightSkyBlue", opacity=0.4, layer="below")
        fig.add_shape(type="line", x0=-d.spessore_paratia/2 - 5, y0=-d.falda_valle_m, x1=-d.spessore_paratia/2, y1=-d.falda_valle_m,
                      line=dict(color="Blue", width=1, dash="dot"))

    # Linea di scavo
    fig.add_shape(type="line", x0=-10, y0=-d.altezza_scavo, x1=10, y1=-d.altezza_scavo,
                  line=dict(color="Red", width=2, dash="dash"), name="Piano Scavo")

    # Linee delle fasi di scavo intermedie
    for index, fase in d.fasi_costruttive_df.iterrows():
        livello_scavo_fase = -fase['livello_scavo_m']
        if not np.isclose(livello_scavo_fase, -d.altezza_scavo):
            fig.add_shape(type="line", x0=-10, y0=livello_scavo_fase, x1=-d.spessore_paratia/2, y1=livello_scavo_fase,
                          line=dict(color="gray", width=1, dash="dot"), name=f"Fase {index+1}")

    # Aggiungi tiranti
    for index, tirante in d.tiranti_df.iterrows():
        prof_tirante = -tirante['profondita_m']
        fig.add_shape(type="line", x0=d.spessore_paratia/2, y0=prof_tirante, x1=d.spessore_paratia/2 + 3, y1=prof_tirante,
                      line=dict(color="black", width=2))
        fig.add_trace(go.Scatter(
            x=[d.spessore_paratia/2 + 3.5], y=[prof_tirante],
            mode='markers',
            marker=dict(symbol='circle-x', size=12, color='black'),
            name=f'Tirante {index+1}',
            hovertext=f"Fase: {tirante['fase_attivazione']}<br>Prof: {-prof_tirante:.2f} m<br>Rig: {tirante['rigidezza_kN_m']:.0f} kN/m"
        ))

    # Aggiungi il cerchio di rottura critico se disponibile
    if r.get('fs_globale', -1.0) > 0 and r.get('cx_critico') is not None:
        cx = r['cx_critico']
        cy = r['cy_critico']
        R = r['R_critico']
        fig.add_shape(type="circle",
                      xref="x", yref="y",
                      x0=cx - R, y0=cy - R, x1=cx + R, y1=cy + R,
                      line_color="DarkGreen", line_width=2, line_dash="dash",
                      name=f"Cerchio Critico FS={r['fs_globale']:.2f}")

    fig.update_layout(title='Geometria e Stratigrafia',
                      xaxis_title="X [m]", yaxis_title="Z [m]",
                      yaxis=dict(range=[-d.lunghezza_paratia - 1, 1]),
                      xaxis=dict(range=[-5, 5]),
                      showlegend=False)
    return fig

def figura_risultati_paratia(r: Dict, data_key: str, title: str) -> go.Figure:
    """Crea un grafico dei risultati (spostamento, momento, taglio) lungo la paratia."""
    fig = go.Figure()

    profondita = r['profondita_m']
    valori = r[data_key]

    fig.add_trace(go.Scatter(x=valori, y=-profondita, mode='lines', name=title,
                             fill='tozerox', line=dict(color='darkslateblue')))

    # Aggiunge la linea della paratia
    fig.add_trace(go.Scatter(x=[0, 0], y=[0, -profondita.max()], mode='lines',
                             line=dict(color='black', width=1, dash='dot')))

    fig.update_layout(
        title=title,
        yaxis_title="Profondità [m]",
        xaxis_title=f"Valore [{title.split('[')[1].split(']')[0]}]",
        template='plotly_white',
        showlegend=False
    )
    return fig