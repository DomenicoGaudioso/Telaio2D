# Telaio2D Web (Streamlit) — XLSX editor + Linear Static (OpenSeesPy)

App web in Streamlit nel formato:
- `src.py`: funzioni (I/O XLSX, validazione, solver OpenSeesPy, export risultati)
- `app.py`: UI Streamlit con tabelle editabili (`st.data_editor`)
- `tests/`: pytest
- `docs/`: guida HTML

## Installazione

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Avvio

```bash
streamlit run app.py
```

## Formato XLSX (fogli)

Richiesti:
- `nodes`: id, x, y
- `elements`: id, n1, n2, prop, type (beam2d)
- `properties`: id, name, E, A, I, rho, alphaT
- `load_cases`: id, name, ax, ay
- `restraints`: load_case_id, node_id, ux, uy, rz
- `node_loads`: load_case_id, node_id, fx, fy, mz

Opzionali:
- `dist_loads`: load_case_id, elem_id, qx0, qx1, qy0, qy1  (trapezio)
- `masses`: load_case_id, node_id, mx, my

## Nota carico trapezoidale

OpenSeesPy supporta `eleLoad -beamUniform` (uniforme) e `-beamPoint` (puntuale).
Il trapezio viene approssimato come somma di carichi uniformi segmentati (slider in UI).

## Output

Dopo Solve vengono aggiunti:
- `results_nodal` (spostamenti e reazioni)
- `results_elements` (forze locali d’estremità N,V,M)

## Test

```bash
pytest -q
```
