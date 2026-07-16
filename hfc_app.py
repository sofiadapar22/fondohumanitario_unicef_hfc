"""
High Frequency Check — Línea de Base UNICEF US / FUSAL
Corre con: streamlit run hfc_app.py
Todos los archivos auxiliares deben estar en la misma carpeta:
  correcciones_geograficas.csv | distritos.csv | cantones.csv | unidadesdesalud.csv
"""

import streamlit as st
import pandas as pd
import numpy as np
import io, os, pathlib
from datetime import date, timedelta
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="HFC · UNICEF US / FUSAL", page_icon="🔍", layout="wide")

META_TAMIZAJE  = 4_000
META_NINOS     = 3_500   # niños menores de 5 años
META_MATERNAS  = 500     # embarazadas + madres lactantes (combinadas)
META_REFERIDOS = 120
META_DESNUT    = 120

# Fechas límite por contacto
FECHA_C1      = date(2026,  7, 30)   # C1: tamizaje en campo
FECHA_C2      = date(2026,  9, 15)   # C2: charla presencial en comunidades
FECHA_C3      = date(2026, 10, 21)   # C3: retamizaje en campo
FECHA_LIMITE  = date(2026, 11,  1)   # cierre general del proyecto

# Perfiles que cuentan como "maternas" tamizadas
PERFILES_EMBARAZADA = ['Mujer embarazada',
                       'Madre de niño/a menor a 5 años y mujer embarazada']
PERFILES_LACTANTE   = ['Madre lactante']
PERFILES_MATERNAS   = PERFILES_EMBARAZADA + PERFILES_LACTANTE

# Estructura de equipos de campo
EQUIPOS = [
    # (Región, Equipo, Zona, Nombre, Rol)
    ("Oriente",     "Equipo 1 Usulután",       "Usulután Este",     "Helen Romero",                    "Técnica Nutrición"),
    ("Oriente",     "Equipo 1 Usulután",       "Usulután Este",     "Fátima Gómez",                    "Promotora"),
    ("Oriente",     "Equipo 2 San Miguel",     "San Miguel Centro", "Fátima Granados",                 "Técnica Nutrición"),
    ("Oriente",     "Equipo 2 San Miguel",     "San Miguel Centro", "Dolores",                         "Promotora"),
    ("Oriente",     "Equipo 2 San Miguel",     "San Miguel Centro", "Arely Granados",                  "Promotora"),
    ("Oriente",     "Equipo 3 Moncagua",       "San Miguel Centro", "Maryori Hernández",               "Técnica Nutrición"),
    ("Oriente",     "Equipo 3 Moncagua",       "San Miguel Centro", "Yulissa Hernández",               "Promotora"),
    ("Occidente",   "Equipo 4 Santa Ana",      "Santa Ana Centro",  "Damaris González",                "Técnica Nutrición"),
    ("Occidente",   "Equipo 4 Santa Ana",      "Santa Ana Centro",  "Norma Rivera",                    "Promotora"),
    ("Occidente",   "Equipo 5 Ahuachapán",     "Ahuachapán Centro", "Yeldi Marcelino",                 "Técnica Nutrición"),
    ("Occidente",   "Equipo 5 Ahuachapán",     "Ahuachapán Centro", "Geraldina Arriola",               "Promotora"),
    ("Occidente",   "Equipo 5 Ahuachapán",     "Ahuachapán Centro", "Yeldi Pérez",                     "Promotora"),
    ("San Salvador","Equipo 6 SS Centro/Este",  "San Salvador Centro","Gaby Pino",                      "Técnica Nutrición"),
    ("San Salvador","Equipo 6 SS Centro/Este",  "San Salvador Centro","Claudia Patricia Mendez Guardado","Promotora"),
    ("San Salvador","Equipo 6 SS Centro/Este",  "San Salvador Este",  "Brenda Nerio",                   "Técnica Nutrición"),
    ("San Salvador","Equipo 6 SS Centro/Este",  "San Salvador Este",  "Rosibel Henríquez",              "Promotora"),
    # Trinidad Granados — Coordinadora (excluida de métricas de campo)
]
DF_EQUIPOS = pd.DataFrame(EQUIPOS, columns=['Región','Equipo','Zona','Nombre','Rol'])

# Meta por zona (columna "Propuesta" del plan operativo)
METAS_ZONA = {
    "San Miguel Centro":   400,
    "Ahuachapán Centro":   800,
    "Santa Ana Centro":    400,
    "San Salvador Este":   800,
    "San Salvador Centro": 800,
    "Usulután Este":       800,
}

st.markdown("""
<style>
.flag-high   {background:#fee2e2;border-left:4px solid #ef4444;padding:6px 10px;border-radius:4px;margin:2px 0;font-size:13px;}
.flag-medium {background:#fef3c7;border-left:4px solid #f59e0b;padding:6px 10px;border-radius:4px;margin:2px 0;font-size:13px;}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RESOLUCIÓN DE RUTAS (funciona local Y en Streamlit Cloud)
# ─────────────────────────────────────────────
def _resolve(fname):
    """Busca un archivo junto al script, luego en el directorio de trabajo."""
    candidatos = [
        pathlib.Path(__file__).parent / fname,   # junto al .py (local)
        pathlib.Path.cwd() / fname,              # cwd (Streamlit Cloud = raíz del repo)
    ]
    for p in candidatos:
        if p.exists():
            return str(p)
    return None


# ─────────────────────────────────────────────
# CATÁLOGOS GEOGRÁFICOS
# ─────────────────────────────────────────────
@st.cache_data
def cargar_catalogos():
    def _load(fname, sep=';'):
        p = _resolve(fname)
        return pd.read_csv(p, sep=sep) if p else pd.DataFrame()

    distritos = _load('distritos.csv')
    cantones  = _load('cantones.csv')
    unidades  = _load('unidadesdesalud.csv')

    dist_map = distritos.set_index('adm3_pcode')['adm3_name'].to_dict() if not distritos.empty else {}
    cant_map = cantones.set_index('adm4_pcode')['adm4_name'].to_dict()  if not cantones.empty  else {}
    us_map   = unidades.set_index('u_code')['u_name'].to_dict()         if not unidades.empty   else {}
    return dist_map, cant_map, us_map


@st.cache_data
def cargar_correcciones():
    p = _resolve('correcciones_geograficas.csv')
    return pd.read_csv(p, dtype={'_id': int}) if p else pd.DataFrame()


# ─────────────────────────────────────────────
# CARGA Y LIMPIEZA
# ─────────────────────────────────────────────
@st.cache_data
def cargar_raw(archivo, mod_time=None):
    # mod_time se usa como clave de caché: cuando el archivo cambia en el repo,
    # su fecha de modificación cambia y Streamlit recarga los datos automáticamente.
    xl = pd.ExcelFile(archivo)
    main  = pd.read_excel(xl, sheet_name=0)
    ninos = pd.read_excel(xl, sheet_name='group_sr9jz33')       if 'group_sr9jz33'       in xl.sheet_names else pd.DataFrame()
    sec3  = pd.read_excel(xl, sheet_name='sec3_salud_nutricion') if 'sec3_salud_nutricion' in xl.sheet_names else pd.DataFrame()
    adic  = pd.read_excel(xl, sheet_name='ninos_adicionales')    if 'ninos_adicionales'    in xl.sheet_names else pd.DataFrame()
    # Normalizar columnas de ninos_adicionales para que sean compatibles con las otras hojas
    if not adic.empty:
        adic = adic.rename(columns={
            'Nombre del niño/a':             '¿Cuál es el nombre del niño/a?',
            'Fecha de nacimiento':           'Fecha de nacimiento del niño a evaluar',
            '¿Cuál es el estado nutricional?': '¿Cuál es el diagnóstico nutricional del peso y la talla?',
        })
    return main, ninos, sec3, adic


def unificar(df, dist_map, cant_map, us_map):
    pares = {
        'nombre':     ('Nombre de la persona entrevistada',                    'Nombre de la persona entrevistada.1'),
        'fecha_ent':  ('Fecha de la entrevista',                               'Fecha de la entrevista.1'),
        'encuestador':('Encuestador',                                          'Encuestador.1'),
        'sexo':       ('Sexo',                                                 'Sexo.1'),
        'perfil':     ('Perfil de la persona entrevistada',                    'Perfil de la persona entrevistada.1'),
        'unidad_cod': ('Unidad de Salud a la que pertenece/asiste su familia', 'Unidad de Salud a la que pertenece/asiste su familia.1'),
        'telefono':   ('Número de teléfono',                                   'Número de teléfono.1'),
        'sabe_leer':  ('¿Sabe leer y escribir?',                               '¿Sabe leer y escribir?.1'),
        'peso':       ('Peso (kg)',                                             'Peso (kg)'),
        'talla':      ('Talla (mts)',                                          'Talla (mts)'),
        'imc':        ('imc_embarazada',                                       'IMC'),
        'eg_sem':     ('Edad gestacional: Semanas',                            'Edad gestacional: Semanas.1'),
        'referencia': ('¿Se brindó referencia?',                               '¿Se brindó referencia?.1'),
        'consejeria': ('¿Se le brindó consejería?',                            '¿Se le brindó consejería?.1'),
    }
    for col_new, (c1, c2) in pares.items():
        s1 = df[c1] if c1 in df.columns else pd.Series(dtype='object', index=df.index)
        s2 = df[c2] if c2 in df.columns else pd.Series(dtype='object', index=df.index)
        df[col_new] = s1.fillna(s2)

    df['nombre']      = df['nombre'].astype(str).str.strip().str.title().replace('Nan', pd.NA)
    df['encuestador'] = df['encuestador'].astype(str).str.strip().replace('nan', pd.NA)

    # Normalización de nombres de encuestadoras (variantes en Kobo → nombre canónico)
    _ENC_ALIASES = {
        'Brenda Nerios':    'Brenda Nerio',
        'Fatima Gomez':     'Fátima Gómez',
        'Rosibel Arriola':  'Rosibel Henríquez',
        'Trinidad Granados':'Gaby Pino',   # Coordinadora → registro contabilizado en SS Centro
    }
    df['encuestador'] = df['encuestador'].replace(_ENC_ALIASES)

    df['start']     = pd.to_datetime(df['start'],    errors='coerce')
    df['end']       = pd.to_datetime(df['end'],      errors='coerce')
    df['fecha_ent'] = pd.to_datetime(df['fecha_ent'],errors='coerce')
    df['fecha_dia'] = df['start'].dt.date
    df['semana']    = df['start'].dt.to_period('W').apply(lambda p: p.start_time.date() if pd.notna(p) else None)
    df['mes']       = df['start'].dt.to_period('M').astype(str)
    df['duracion_min'] = (df['end'] - df['start']).dt.total_seconds() / 60

    df['talla'] = pd.to_numeric(df['talla'], errors='coerce')
    df.loc[df['talla'] > 3, 'talla'] /= 100
    for c in ['peso', 'imc', 'eg_sem']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    # Decodificar geografía
    df['distrito_cod']    = df['Distrito'].astype(str).where(df['Distrito'].notna())
    df['canton_cod']      = df['Cantón'].astype(str).where(df['Cantón'].notna())
    df['distrito_nombre'] = df['distrito_cod'].map(dist_map)
    df['canton_nombre']   = df['canton_cod'].map(cant_map)
    df['unidad_cod_int']  = pd.to_numeric(df['unidad_cod'], errors='coerce')
    df['unidad_nombre']   = df['unidad_cod_int'].map(us_map)

    # Asegurar que Municipio sea texto
    df['Municipio'] = df['Municipio'].astype(object)

    return df


def aplicar_correcciones(df, corr):
    if corr.empty:
        return df, 0
    df = df.copy()
    for col in ['Municipio', 'distrito_nombre', 'canton_nombre', 'unidad_nombre']:
        df[col] = df[col].astype(object)
    n = 0
    for _, row in corr.iterrows():
        mask = df['_id'] == row['_id']
        if mask.any():
            df.loc[mask, 'Municipio']       = row['municipio_correcto']
            df.loc[mask, 'distrito_nombre'] = row['distrito_correcto']
            df.loc[mask, 'canton_nombre']   = row['canton_correcto']
            df.loc[mask, 'unidad_nombre']   = row['unidad_salud_correcta']
            n += int(mask.sum())
    return df, n


def construir_ninos(df_ninos, df_sec3, df_main, df_adic=None):
    ref_cols = ['_id', 'fecha_dia', 'semana', 'mes', 'encuestador', 'Municipio',
                'distrito_nombre', 'canton_nombre', 'nombre', 'telefono', 'unidad_nombre']
    ref = df_main[[c for c in ref_cols if c in df_main.columns]].copy()

    frames = []
    sheets_to_process = [(df_ninos, '_submission__id'), (df_sec3, '_submission__id')]
    if df_adic is not None and not df_adic.empty:
        sheets_to_process.append((df_adic, '_submission__id'))
    for sheet, id_col in sheets_to_process:
        if sheet.empty:
            continue
        s = sheet.copy()
        if 'Edad' in s.columns:
            s['edad_txt'] = s['Edad']
        elif 'edad_nino' in s.columns:
            s['edad_txt'] = s['edad_nino']
        else:
            s['edad_txt'] = pd.NA

        cols_keep = [id_col, '¿Cuál es el nombre del niño/a?', 'Sexo',
                     'Fecha de nacimiento del niño a evaluar', 'edad_txt',
                     '¿Cuál es el peso en Kg del niño/a?', '¿Cuál es la talla en cm del niño/a?',
                     'Medida del perímetro braquial en cm',
                     '¿Cuál es el diagnóstico nutricional de la talla y edad?',
                     '¿Cuál es el diagnóstico nutricional de peso edad?',
                     '¿Cuál es el diagnóstico nutricional del peso y la talla?',
                     'Diagnóstico nutricional según perímetro braquial',
                     '¿Se brindó referencia?',
                     '¿Se le brindó consejería a niños y niñas?',
                     '¿Se le brindó consejería a la madre embarazada, lactante o adulto/a responsable?']
        cols_keep = [c for c in cols_keep if c in s.columns]
        s = s[cols_keep].rename(columns={id_col: '_submission_id'})
        frames.append(s)

    if not frames:
        return pd.DataFrame()

    ninos = pd.concat(frames, ignore_index=True)
    ninos = ninos.merge(ref, left_on='_submission_id', right_on='_id', how='left')
    ninos['peso_nino']  = pd.to_numeric(ninos.get('¿Cuál es el peso en Kg del niño/a?'),  errors='coerce')
    ninos['talla_nino'] = pd.to_numeric(ninos.get('¿Cuál es la talla en cm del niño/a?'), errors='coerce')
    ninos['muac']       = pd.to_numeric(ninos.get('Medida del perímetro braquial en cm'),  errors='coerce')

    # Corrección automática: talla ingresada sin punto decimal (ej: 915 en vez de 91.5 cm)
    # Rango normal <5 años: 45–130 cm. Valores >200 son errores de entrada → dividir entre 10.
    mask_talla_err = ninos['talla_nino'] > 200
    ninos.loc[mask_talla_err, 'talla_nino'] = ninos.loc[mask_talla_err, 'talla_nino'] / 10
    ninos['talla_corregida'] = mask_talla_err  # flag para mostrar en Flags HFC

    # Deduplicar: un niño puede aparecer en group_sr9jz33 (v2) Y sec3_salud_nutricion (v1)
    # si el export de Kobo incluye ambas versiones. Se usa submission + nombre + fecha de nacimiento.
    _dedup_cols = [c for c in ['_submission_id', '¿Cuál es el nombre del niño/a?',
                                'Fecha de nacimiento del niño a evaluar'] if c in ninos.columns]
    if _dedup_cols:
        ninos = ninos.drop_duplicates(subset=_dedup_cols, keep='first').reset_index(drop=True)

    return ninos


# ─────────────────────────────────────────────
# CHECKS HFC
# ─────────────────────────────────────────────
def check_duplicados(df, ninos=None):
    """
    Detecta duplicados y los clasifica:
    - 🔴 Duplicado probable: misma madre, misma fecha, mismo perfil, sin hijos distintos
    - 🟡 Distinto hijo (no eliminar): misma madre, misma fecha, pero hijos distintos en repeat group
    - ℹ️ Perfiles distintos: misma madre, misma fecha, pero perfiles diferentes → se cuenta por separado, solo aviso
    """
    mask = df.duplicated(subset=['nombre', 'fecha_ent'], keep=False) & df['nombre'].notna()
    cols_base = ['_id','nombre','fecha_ent','fecha_dia','encuestador','Municipio','peso','talla','imc']
    if 'perfil' in df.columns:
        cols_base.append('perfil')
    cands = df[mask][cols_base].copy()

    if cands.empty:
        return pd.DataFrame()

    # Construir mapa: submission_id → set de nombres de hijos
    hijos_por_id = {}
    if ninos is not None and not ninos.empty and '_submission_id' in ninos.columns:
        col_nombre_nino = '¿Cuál es el nombre del niño/a?'
        if col_nombre_nino in ninos.columns:
            for sid, grp in ninos.groupby('_submission_id'):
                nombres = set(grp[col_nombre_nino].dropna().astype(str).str.strip().str.title())
                hijos_por_id[sid] = nombres

    # Para cada grupo (nombre + fecha), determinar si hay hijos distintos entre las filas
    resultados = []
    grupos = cands.groupby(['nombre', 'fecha_ent'])
    for (nombre, fecha), grp in grupos:
        ids_grupo = grp['_id'].tolist()
        hijos_grupo = [hijos_por_id.get(i, set()) for i in ids_grupo]

        # ── Perfiles distintos: no es duplicado, solo aviso ──
        perfiles_grupo = grp['perfil'].dropna().unique().tolist() if 'perfil' in grp.columns else []
        if len(set(perfiles_grupo)) > 1:
            tipo    = 'ℹ️ Perfiles distintos (no eliminar)'
            sev     = 'Baja'
            detalle = f"Perfiles: {', '.join(sorted(set(str(p) for p in perfiles_grupo)))}"
            # Hijos como info adicional
            todos_hijos = [h for h in hijos_grupo if h]
            if todos_hijos:
                union_hijos = set().union(*todos_hijos)
                detalle += f" · Hijos: {', '.join(sorted(union_hijos))}"
            for _, row in grp.iterrows():
                resultados.append({
                    '_id': row['_id'], 'nombre': row['nombre'],
                    'fecha_dia': row['fecha_dia'], 'encuestador': row['encuestador'],
                    'Municipio': row['Municipio'], 'flag': tipo, 'detalle': detalle, 'severidad': sev,
                })
            continue

        # ── Mismo perfil: revisar hijos ──
        todos_hijos = [h for h in hijos_grupo if h]  # excluir sets vacíos

        if len(todos_hijos) >= 2:
            union_hijos = set().union(*todos_hijos)
            intersecc   = todos_hijos[0].intersection(*todos_hijos[1:]) if len(todos_hijos) > 1 else todos_hijos[0]
            hijos_distintos = union_hijos - intersecc

            if hijos_distintos:
                # Hijos distintos → no eliminar
                tipo = '🟡 Distinto hijo (no eliminar)'
                sev  = 'Media'
                detalle = f"Hijos: {', '.join(sorted(union_hijos))}"
            else:
                tipo = '🔴 Duplicado probable'
                sev  = 'Alta'
                detalle = f"Hijos: {', '.join(sorted(union_hijos)) or 'ninguno registrado'}"
        else:
            tipo = '🔴 Duplicado probable (sin niños en repeat group)'
            sev  = 'Alta'
            detalle = 'Sin niños registrados'

        # ¿Misma encuestadora?
        encuestadoras = grp['encuestador'].dropna().unique()
        if len(encuestadoras) > 1:
            detalle += f" · Encuestadoras distintas: {', '.join(encuestadoras)}"

        # ¿Variables clave idénticas? (peso + talla)
        if 'peso' in grp.columns and grp['peso'].notna().all() and grp['peso'].nunique() == 1:
            detalle += ' · Peso idéntico ⚠️'

        for _, row in grp.iterrows():
            resultados.append({
                '_id':         row['_id'],
                'nombre':      row['nombre'],
                'fecha_dia':   row['fecha_dia'],
                'encuestador': row['encuestador'],
                'Municipio':   row['Municipio'],
                'flag':        tipo,
                'detalle':     detalle,
                'severidad':   sev,
            })

    return pd.DataFrame(resultados) if resultados else pd.DataFrame()

def check_desnutricion(ninos):
    """
    Detecta niños con diagnóstico de desnutrición o emaciación en cualquier indicador.
    Equivalencia: emaciado / emaciado severo = desnutrición / desnutrición severa (término actualizado en Kobo).
    """
    if ninos.empty:
        return pd.DataFrame()

    # Términos que activan el flag (ambas versiones del formulario)
    TERMINOS_ALERTA = [
        'desnutrici', 'desnutricion', 'emaciado', 'emaciacion',
        'aguda severa', 'aguda moderada', 'riesgo de desnutri'
    ]
    # Columnas de diagnóstico nutricional en niños
    diag_cols = [c for c in ninos.columns if any(k in c.lower() for k in
                 ['diagnóstico', 'diagnostico', 'diagnóst', 'diagnos', 'perímetro', 'perimetro'])]

    rows = []
    for _, row in ninos.iterrows():
        for col in diag_cols:
            val = str(row.get(col, '') or '').lower().strip()
            if not val or val in ('nan', ''):
                continue
            if any(t in val for t in TERMINOS_ALERTA):
                # Determinar severidad
                if 'riesgo' in val:
                    sev   = 'Media'
                    icono = '🟡'
                else:
                    sev   = 'Alta'
                    icono = '🔴'
                nombre_nino = row.get('¿Cuál es el nombre del niño/a?', 'Sin nombre')
                rows.append({
                    '_id':         row.get('_submission_id', ''),
                    'nombre':      f"{nombre_nino} (niño/a)",
                    'fecha_dia':   row.get('fecha_dia', ''),
                    'encuestador': row.get('encuestador', ''),
                    'Municipio':   row.get('Municipio', ''),
                    'flag':        f"{icono} Desnutrición detectada: {val.title()} ({col.split('?')[-1].strip() if '?' in col else col[:40]})",
                    'severidad':   sev,
                })
                break  # un flag por niño es suficiente

    return pd.DataFrame(rows) if rows else pd.DataFrame()

def check_referencia_congruencia(df, ninos):
    """
    Dos tipos de incongruencia entre diagnóstico peso/talla y referencia:
      🔴 Debería referirse  — diagnóstico crítico (emaciado/desnutrición) pero SIN referencia
      🟡 Referencia dudosa  — SE hizo referencia pero diagnóstico peso/talla es normal
    Se revisa tanto en niños (diag peso/talla) como en maternas (campo referencia).
    """
    # Términos que EXIGEN referencia
    CRITICOS   = ['desnutrici','emaciado','emaciacion','aguda severa','aguda moderada']
    # Términos que indican estado normal (no debería referirse por peso/talla)
    NORMALES   = ['normal','adecuado','eutrófico','eutr','bien nutrido']
    RIESGO     = ['riesgo']  # gris: referencia razonable, no flag

    rows = []

    # ── NIÑOS ────────────────────────────────────────────────────────────────
    if not ninos.empty:
        # Columna específica de diagnóstico peso/talla (la más relevante para referencia)
        col_pt = next((c for c in ninos.columns if 'peso' in c.lower() and 'talla' in c.lower()
                       and ('diagnós' in c.lower() or 'diagnos' in c.lower())), None)
        # Fallback: cualquier columna de diagnóstico
        if not col_pt:
            col_pt = next((c for c in ninos.columns if 'diagnós' in c.lower() or 'diagnos' in c.lower()), None)

        col_ref_n = '¿Se brindó referencia?' if '¿Se brindó referencia?' in ninos.columns else None

        if col_pt and col_ref_n:
            for _, row in ninos.iterrows():
                diag    = str(row.get(col_pt, '') or '').lower().strip()
                ref_val = str(row.get(col_ref_n, '') or '').lower().strip()
                tiene_ref = 'sí' in ref_val or 'si' in ref_val
                es_critico = any(t in diag for t in CRITICOS)
                es_normal  = any(t in diag for t in NORMALES)
                es_riesgo  = any(t in diag for t in RIESGO)
                nombre_n   = row.get('¿Cuál es el nombre del niño/a?', 'Sin nombre')

                base = {
                    '_id':         row.get('_submission_id', ''),
                    'nombre':      f"{nombre_n} (niño/a)",
                    'fecha_dia':   row.get('fecha_dia', ''),
                    'encuestador': row.get('encuestador', ''),
                    'Municipio':   row.get('Municipio', ''),
                }
                if es_critico and not tiene_ref:
                    rows.append({**base,
                        'flag':      f"🔴 Sin referencia — diagnóstico crítico: {diag.title()}",
                        'severidad': 'Alta',
                    })
                elif tiene_ref and es_normal and not es_riesgo and diag:
                    rows.append({**base,
                        'flag':      f"🟡 Referencia con diagnóstico normal: {diag.title()}",
                        'severidad': 'Media',
                    })

    # ── MATERNAS ─────────────────────────────────────────────────────────────
    # Para maternas: usamos IMC / estado nutricional si está disponible
    if not df.empty:
        col_ref_m = 'referencia' if 'referencia' in df.columns else None
        # Columna de diagnóstico nutricional de la madre (IMC / estado)
        col_diag_m = next((c for c in df.columns if 'diagnós' in c.lower() or 'estado nutricional' in c.lower()
                           or 'imc' == c.lower()), None)

        if col_ref_m and col_diag_m:
            for _, row in df.iterrows():
                diag    = str(row.get(col_diag_m, '') or '').lower().strip()
                ref_val = str(row.get(col_ref_m, '') or '').lower().strip()
                tiene_ref  = 'sí' in ref_val or 'si' in ref_val
                es_critico = any(t in diag for t in CRITICOS)
                es_normal  = any(t in diag for t in NORMALES)
                es_riesgo  = any(t in diag for t in RIESGO)

                base = {
                    '_id':         row.get('_id', ''),
                    'nombre':      row.get('nombre', 'Sin nombre'),
                    'fecha_dia':   row.get('fecha_dia', ''),
                    'encuestador': row.get('encuestador', ''),
                    'Municipio':   row.get('Municipio', ''),
                }
                if es_critico and not tiene_ref and diag:
                    rows.append({**base,
                        'flag':      f"🔴 Sin referencia — diagnóstico crítico: {diag.title()}",
                        'severidad': 'Alta',
                    })
                elif tiene_ref and es_normal and not es_riesgo and diag:
                    rows.append({**base,
                        'flag':      f"🟡 Referencia con diagnóstico normal: {diag.title()}",
                        'severidad': 'Media',
                    })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def check_duracion(df):
    rows = []
    dur = df['duracion_min']
    for cond, fn, sev in [
        (dur < 5,             lambda x: f'🔴 Muy corta ({x:.1f} min)',            'Alta'),
        ((dur>90)&(dur<1000), lambda x: f'🟡 Larga ({x:.1f} min > 90)',           'Media'),
        (dur >= 1000,         lambda x: f'🟡 Subido con retraso ({x/60:.0f}h — sin internet en campo)', 'Media'),
    ]:
        sub = df[cond][['_id','nombre','fecha_dia','encuestador','Municipio','duracion_min']].copy()
        if not sub.empty:
            sub['flag'] = sub['duracion_min'].apply(fn)
            sub['severidad'] = sev
            rows.append(sub)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

def check_outliers(df):
    rows = []
    rangos = {
        'peso':   (30, 120,  'Peso fuera de rango ({:.1f} kg)'),
        'talla':  (1.3, 2.0, 'Talla fuera de rango ({:.2f} m)'),
        'imc':    (10, 50,   'IMC fuera de rango ({:.1f})'),
        'eg_sem': (4, 44,    'Semanas gestación fuera de rango ({:.0f})'),
    }
    for col, (lo, hi, tmpl) in rangos.items():
        if col not in df.columns: continue
        mask = df[col].notna() & ((df[col]<lo)|(df[col]>hi))
        if mask.any():
            sub = df[mask][['_id','nombre','fecha_dia','encuestador','Municipio',col]].copy()
            sub['flag'] = sub[col].apply(lambda x: f'🟡 {tmpl.format(x)}')
            sub['severidad'] = 'Media'
            rows.append(sub.drop(columns=[col]))
    if 'imc' in df.columns:
        mask0 = df['imc'] == 0
        if mask0.any():
            sub = df[mask0][['_id','nombre','fecha_dia','encuestador','Municipio']].copy()
            sub['flag'] = '🔴 IMC = 0 (error de captura)'; sub['severidad'] = 'Alta'
            rows.append(sub)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

def check_nulos(df):
    rows = []
    for col, lbl in [('nombre','Nombre vacío'),('encuestador','Encuestador vacío'),
                     ('Municipio','Municipio vacío'),('perfil','Perfil vacío')]:
        if col not in df.columns: continue
        mask = df[col].isna() | (df[col].astype(str).str.strip() == '')
        if mask.any():
            sub = df[mask][['_id','nombre','fecha_dia','encuestador','Municipio']].copy()
            sub['flag'] = f'🟡 {lbl}'; sub['severidad'] = 'Media'
            rows.append(sub)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

def check_geo(df):
    mask = df['distrito_nombre'].isna() | df['canton_nombre'].isna()
    sub = df[mask][['_id','nombre','fecha_dia','encuestador','Municipio']].copy()
    if not sub.empty:
        sub['flag'] = '🟡 Distrito o cantón sin decodificar'; sub['severidad'] = 'Media'
    return sub if not sub.empty else pd.DataFrame()

def stats_enc(df):
    g = df.groupby('encuestador', dropna=True)
    s = pd.DataFrame({
        'Encuestas':          g.size(),
        'Días campo':         g['fecha_dia'].nunique(),
        'Dur. mediana (min)': g['duracion_min'].median().round(1),
        '% < 5 min':          g['duracion_min'].apply(lambda x: (x<5).mean()*100).round(1),
        '% > 90 min':         g['duracion_min'].apply(lambda x: (x>90).mean()*100).round(1),
        'Enc./día':           (g.size() / g['fecha_dia'].nunique()).round(1),
    }).reset_index()
    s.columns = ['Encuestador/a','Encuestas','Días campo','Dur. mediana (min)','% < 5 min','% > 90 min','Enc./día']
    return s.sort_values('Encuestas', ascending=False)


# ─────────────────────────────────────────────
# PROYECCIÓN — modelo de 3 contactos con fechas fijas
# ─────────────────────────────────────────────
def _dias_habiles_entre(inicio: date, fin: date, dias_sem: int) -> int:
    """Días de campo disponibles entre dos fechas, dado días/semana de trabajo."""
    total_cal = max((fin - inicio).days, 0)
    semanas   = total_cal / 7
    return int(semanas * dias_sem)

def calcular_proyeccion(actual, meta, tasa_dia, dias_sem, n_equipos):
    """
    Proyecta si el equipo puede completar los 3 contactos dentro de las fechas límite.

    C1 (tamizaje campo):          hoy → FECHA_C1  (30 jul)
    C2 (charla presencial):  FECHA_C1 → FECHA_C2  (15 sep)
    C3 (retamizaje campo):   FECHA_C2 → FECHA_C3  (21 oct)
    """
    hoy           = date.today()
    cap_dia_total = tasa_dia * n_equipos
    cap_sem       = cap_dia_total * dias_sem

    if cap_dia_total <= 0 or dias_sem <= 0:
        return {
            'cap_dia': 0, 'cap_sem': 0,
            'fecha_fin_c1': None, 'fecha_fin_c2': None, 'fecha_fin_c3': None,
            'cap_c1': 0, 'cap_c2': 0, 'cap_c3': 0,
            'cumple_c1': False, 'cumple_c2': False, 'cumple_c3': False, 'cumple': False,
        }

    # ── C1: tamizajes restantes dentro de la ventana hoy→FECHA_C1 ──
    restante_c1    = max(meta - actual, 0)
    dias_c1        = _dias_habiles_entre(hoy, FECHA_C1, dias_sem)
    cap_c1         = cap_dia_total * dias_c1          # capacidad total en ventana C1
    cumple_c1      = cap_c1 >= restante_c1
    # fecha proyectada en que termina C1 (si hay capacidad)
    if cap_dia_total > 0:
        dias_campo_c1  = restante_c1 / cap_dia_total
        dias_cal_c1    = int((dias_campo_c1 / dias_sem) * 7) if dias_sem > 0 else 0
        fecha_fin_c1   = hoy + timedelta(days=dias_cal_c1) if dias_cal_c1 < 3650 else None
    else:
        fecha_fin_c1   = None

    # ── C2: charla presencial — mismas 4,000 personas, ventana C1→C2 ──
    dias_c2   = _dias_habiles_entre(FECHA_C1, FECHA_C2, dias_sem)
    cap_c2    = cap_dia_total * dias_c2
    cumple_c2 = cap_c2 >= meta
    dias_cal_c2   = int((meta / cap_dia_total / dias_sem) * 7) if cap_dia_total > 0 else 0
    fecha_fin_c2  = FECHA_C1 + timedelta(days=dias_cal_c2) if dias_cal_c2 < 3650 else None

    # ── C3: retamizaje — mismas 4,000 personas, ventana C2→C3 ──
    dias_c3   = _dias_habiles_entre(FECHA_C2, FECHA_C3, dias_sem)
    cap_c3    = cap_dia_total * dias_c3
    cumple_c3 = cap_c3 >= meta
    dias_cal_c3   = int((meta / cap_dia_total / dias_sem) * 7) if cap_dia_total > 0 else 0
    fecha_fin_c3  = FECHA_C2 + timedelta(days=dias_cal_c3) if dias_cal_c3 < 3650 else None

    cumple = cumple_c1 and cumple_c2 and cumple_c3

    return {
        'cap_dia':      int(cap_dia_total),
        'cap_sem':      int(cap_sem),
        'fecha_fin_c1': fecha_fin_c1,
        'fecha_fin_c2': fecha_fin_c2,
        'fecha_fin_c3': fecha_fin_c3,
        'cap_c1':       int(cap_c1),
        'cap_c2':       int(cap_c2),
        'cap_c3':       int(cap_c3),
        'cumple_c1':    cumple_c1,
        'cumple_c2':    cumple_c2,
        'cumple_c3':    cumple_c3,
        'cumple':       cumple,
    }


# ─────────────────────────────────────────────
# INTERFAZ PRINCIPAL
# ─────────────────────────────────────────────
st.title("🔍 HFC · Línea de Base UNICEF US / FUSAL")
st.caption("El Salvador · Meta: 4,000 personas tamizadas · Cierre: 15 noviembre 2026")

dist_map, cant_map, us_map = cargar_catalogos()
correcciones = cargar_correcciones()

ADMIN_PIN = "fusal2026"   # ← cambia esto cuando quieras

# ── SIDEBAR ──
with st.sidebar:
    st.header("📂 Datos")

    n_corr_total = len(correcciones)
    if n_corr_total:
        st.success(f"✅ {n_corr_total} correcciones geo cargadas")
    else:
        st.warning("⚠️ Sin correcciones_geograficas.csv")

    # ── Modo 1: datos publicados (visibles para todos) ──
    archivo_repo = _resolve('datos_actuales.xlsx')
    archivo = None

    if archivo_repo:
        st.success("📊 Datos publicados cargados")
        import datetime
        mtime_repo = pathlib.Path(archivo_repo).stat().st_mtime
        fecha_mod  = datetime.datetime.fromtimestamp(mtime_repo).strftime('%d/%m/%Y %H:%M')
        st.caption(f"Última actualización: {fecha_mod}")
        if st.button("🔄 Recargar datos del repo"):
            st.cache_data.clear()
            st.rerun()
        archivo = archivo_repo   # se pasa como ruta string, se maneja abajo

    else:
        st.info("No hay datos publicados aún.\nSube `datos_actuales.xlsx` al repo de GitHub para que todos puedan ver los resultados.")

    # ── Modo 2: admin — subir datos nuevos ──
    st.markdown("---")
    with st.expander("🔐 Actualizar datos (Admin)"):
        pin = st.text_input("Clave de acceso", type="password", key="admin_pin")
        if pin == ADMIN_PIN:
            st.success("✅ Acceso admin")
            archivo_admin = st.file_uploader("Sube export KoboToolbox (.xlsx)", type=['xlsx'], key="admin_upload")
            if archivo_admin:
                archivo = archivo_admin
                st.success("Usando datos recién subidos (solo esta sesión)")
                st.info(
                    "Para que todos vean estos datos, súbelos a GitHub como `datos_actuales.xlsx` "
                    "(Add file → Upload files → nombra el archivo exactamente así)."
                )
        elif pin:
            st.error("Clave incorrecta")

    if archivo:
        # Pasar la fecha de modificación como clave de caché.
        # Cuando subes un archivo nuevo al repo, su mtime cambia → caché se invalida → datos frescos.
        if isinstance(archivo, str):
            mod_time = pathlib.Path(archivo).stat().st_mtime
        else:
            mod_time = None   # archivo subido en sesión: Streamlit lo hashea por contenido

        df_raw, df_ninos_raw, df_sec3_raw, df_adic_raw = cargar_raw(archivo, mod_time)
        df = unificar(df_raw.copy(), dist_map, cant_map, us_map)
        df, n_corr = aplicar_correcciones(df, correcciones)
        ninos = construir_ninos(df_ninos_raw, df_sec3_raw, df, df_adic_raw)

        st.markdown("**Filtros**")
        municipios = ['Todos'] + sorted(df['Municipio'].dropna().astype(str).unique().tolist())
        sel_mun = st.selectbox("Municipio", municipios)

        distritos_disp = ['Todos'] + sorted(df['distrito_nombre'].dropna().astype(str).unique().tolist())
        sel_dist = st.selectbox("Distrito", distritos_disp)

        cantones_disp = ['Todos'] + sorted(df['canton_nombre'].dropna().astype(str).unique().tolist())
        sel_cant = st.selectbox("Cantón", cantones_disp)

        encuestadores = ['Todos'] + sorted(df['encuestador'].dropna().astype(str).unique().tolist())
        sel_enc = st.selectbox("Encuestador/a", encuestadores)

        fechas = sorted(df['fecha_dia'].dropna().unique())
        if fechas:
            rango = st.date_input("Rango fechas", value=(fechas[0], fechas[-1]),
                                  min_value=fechas[0], max_value=fechas[-1])

        # Aplicar filtros
        mask = pd.Series(True, index=df.index)
        if sel_mun  != 'Todos': mask &= df['Municipio'].astype(str)        == sel_mun
        if sel_dist != 'Todos': mask &= df['distrito_nombre'].astype(str)  == sel_dist
        if sel_cant != 'Todos': mask &= df['canton_nombre'].astype(str)    == sel_cant
        if sel_enc  != 'Todos': mask &= df['encuestador'].astype(str)      == sel_enc
        if fechas and len(rango) == 2:
            mask &= (df['fecha_dia'] >= rango[0]) & (df['fecha_dia'] <= rango[1])
        df_f = df[mask].copy()

        if not ninos.empty:
            n_mask = pd.Series(True, index=ninos.index)
            if sel_mun  != 'Todos' and 'Municipio'       in ninos.columns: n_mask &= ninos['Municipio'].astype(str)       == sel_mun
            if sel_dist != 'Todos' and 'distrito_nombre' in ninos.columns: n_mask &= ninos['distrito_nombre'].astype(str) == sel_dist
            if sel_enc  != 'Todos' and 'encuestador'     in ninos.columns: n_mask &= ninos['encuestador'].astype(str)     == sel_enc
            ninos_f = ninos[n_mask].copy()
        else:
            ninos_f = ninos.copy()

        st.markdown("---")
        st.metric("Entrevistas en vista", len(df_f))
        st.metric("Niños en vista", len(ninos_f))
        if n_corr:
            st.caption(f"📍 {n_corr} registros corregidos geo")

    st.markdown("---")
    st.caption("Coloca todos los CSV auxiliares junto a hfc_app.py")


if not archivo:
    st.info("📭 No hay datos disponibles aún.")
    st.markdown("""
    **Para administradores:** sube `datos_actuales.xlsx` al repositorio de GitHub
    para que todos los usuarios puedan ver los resultados automáticamente.

    O usa la sección **🔐 Actualizar datos** en el sidebar para ver datos en tu sesión.
    """)
    with st.expander("Archivos necesarios en el repositorio"):
        st.code("hfc_app.py\ndatos_actuales.xlsx\ncorrecciones_geograficas.csv\ndistritos.csv\ncantones.csv\nunidadesdesalud.csv")
    st.stop()

# Asignar vars filtradas
df      = df_f
ninos   = ninos_f

# Checks
f_dup  = check_duplicados(df, ninos)
f_dur  = check_duracion(df)
f_out  = check_outliers(df)
f_nul  = check_nulos(df)
f_geo  = check_geo(df)
f_desn = check_desnutricion(ninos)
f_ref  = check_referencia_congruencia(df, ninos)
todos  = pd.concat([f for f in [f_dup,f_dur,f_out,f_nul,f_geo,f_desn,f_ref] if not f.empty], ignore_index=True)

n_alta  = int((todos['severidad']=='Alta').sum())  if not todos.empty else 0
n_media = int((todos['severidad']=='Media').sum()) if not todos.empty else 0

# KPIs de avance
total_ninos   = len(ninos)
if 'perfil' in df.columns:
    # Deduplicar por (nombre, perfil): si una mujer aparece con perfiles distintos
    # (ej: embarazada en un registro, lactante en otro) se cuenta para cada perfil.
    # Si aparece dos veces con el mismo perfil → solo se cuenta una vez.
    df_madres_unicas = df.dropna(subset=['nombre']).drop_duplicates(subset=['nombre', 'perfil'])
    n_embarazadas = int(df_madres_unicas['perfil'].isin(PERFILES_EMBARAZADA).sum())
    n_lactantes   = int(df_madres_unicas['perfil'].isin(PERFILES_LACTANTE).sum())
else:
    n_embarazadas = 0
    n_lactantes   = 0
total_maternas  = n_embarazadas + n_lactantes
total_tamizados = total_ninos + total_maternas
pct_meta        = total_tamizados / META_TAMIZAJE * 100
pct_ninos       = total_ninos    / META_NINOS    * 100
pct_maternas    = total_maternas / META_MATERNAS * 100
dias_restantes  = (FECHA_LIMITE - date.today()).days
dias_campo      = df['fecha_dia'].nunique()
tasa_actual     = total_tamizados / dias_campo if dias_campo > 0 else 0


# ══════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════
tab_avance, tab_escenarios, tab_indicadores, tab_flags, tab_ref_check, tab_dur, tab_dups, tab_out, tab_enc, tab_geo_tab, tab_export, tab_unicef = st.tabs([
    "📊 Avance General",
    "🎯 Proyección & Escenarios",
    "🥗 Indicadores Nutricionales",
    "🚦 Flags HFC",
    "🚨 Referencias",
    "⏱️ Duración",
    "👥 Duplicados",
    "📈 Outliers",
    "👩‍💼 Por Encuestadora",
    "📍 Geo / Correcciones",
    "📥 Exportar",
    "🇺🇳 Reporte UNICEF",
])


# ── TAB 1: AVANCE GENERAL ──────────────────────
with tab_avance:
    st.subheader("📊 Avance General del Proyecto")

    # ── Fila 1: Total general ──
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🧑‍🤝‍🧑 Total tamizados (C1)", f"{total_tamizados:,}", help="Niños + embarazadas + lactantes")
    c2.metric("Meta total", f"{META_TAMIZAJE:,}")
    c3.metric("% avance total", f"{pct_meta:.1f}%")
    c4.metric("Días restantes", dias_restantes, help=f"Al {FECHA_LIMITE.strftime('%d/%m/%Y')}")
    st.progress(min(pct_meta / 100, 1.0))
    st.caption(f"**{total_tamizados:,}** de **{META_TAMIZAJE:,}** — faltan **{META_TAMIZAJE - total_tamizados:,}**")

    st.markdown("---")

    # ── Fila 2: Desglose por tipo ──
    st.markdown("**Desglose por tipo de persona tamizada**")
    col_n, col_e, col_l, col_m = st.columns(4)

    with col_n:
        st.markdown(
            f"<div style='background:#1e3a5f;border-radius:10px;padding:14px 16px;text-align:center'>"
            f"<div style='font-size:13px;color:#90caf9;font-weight:600'>👶 Niños &lt;5 años</div>"
            f"<div style='font-size:34px;font-weight:800;color:white'>{total_ninos:,}</div>"
            f"<div style='font-size:12px;color:#90caf9'>Meta: {META_NINOS:,}</div>"
            f"<div style='font-size:18px;font-weight:700;color:#{'10b981' if pct_ninos>=50 else 'f59e0b'}'>{pct_ninos:.1f}%</div>"
            f"<div style='background:#0d2137;border-radius:4px;height:8px;margin-top:6px'>"
            f"<div style='background:#3b82f6;width:{min(pct_ninos,100):.0f}%;height:8px;border-radius:4px'></div></div>"
            f"<div style='font-size:11px;color:#64748b;margin-top:4px'>Faltan {max(META_NINOS-total_ninos,0):,}</div>"
            f"</div>", unsafe_allow_html=True)

    with col_e:
        pct_emb = n_embarazadas / (META_MATERNAS/2) * 100  # ~250 embarazadas
        st.markdown(
            f"<div style='background:#3b1f5e;border-radius:10px;padding:14px 16px;text-align:center'>"
            f"<div style='font-size:13px;color:#c4b5fd;font-weight:600'>🤰 Embarazadas</div>"
            f"<div style='font-size:34px;font-weight:800;color:white'>{n_embarazadas:,}</div>"
            f"<div style='font-size:12px;color:#c4b5fd'>Meta estimada: ~250</div>"
            f"<div style='font-size:18px;font-weight:700;color:#{'10b981' if pct_emb>=50 else 'f59e0b'}'>{pct_emb:.1f}%</div>"
            f"<div style='background:#1e0f3a;border-radius:4px;height:8px;margin-top:6px'>"
            f"<div style='background:#8b5cf6;width:{min(pct_emb,100):.0f}%;height:8px;border-radius:4px'></div></div>"
            f"<div style='font-size:11px;color:#64748b;margin-top:4px'>Faltan {max(250-n_embarazadas,0):,}</div>"
            f"</div>", unsafe_allow_html=True)

    with col_l:
        pct_lac = n_lactantes / (META_MATERNAS/2) * 100  # ~250 lactantes
        st.markdown(
            f"<div style='background:#1f3b2e;border-radius:10px;padding:14px 16px;text-align:center'>"
            f"<div style='font-size:13px;color:#6ee7b7;font-weight:600'>🤱 Madres lactantes</div>"
            f"<div style='font-size:34px;font-weight:800;color:white'>{n_lactantes:,}</div>"
            f"<div style='font-size:12px;color:#6ee7b7'>Meta estimada: ~250</div>"
            f"<div style='font-size:18px;font-weight:700;color:#{'10b981' if pct_lac>=50 else 'f59e0b'}'>{pct_lac:.1f}%</div>"
            f"<div style='background:#0d2018;border-radius:4px;height:8px;margin-top:6px'>"
            f"<div style='background:#10b981;width:{min(pct_lac,100):.0f}%;height:8px;border-radius:4px'></div></div>"
            f"<div style='font-size:11px;color:#64748b;margin-top:4px'>Faltan {max(250-n_lactantes,0):,}</div>"
            f"</div>", unsafe_allow_html=True)

    with col_m:
        st.markdown(
            f"<div style='background:#3b2a10;border-radius:10px;padding:14px 16px;text-align:center'>"
            f"<div style='font-size:13px;color:#fcd34d;font-weight:600'>🌸 Maternas (total)</div>"
            f"<div style='font-size:34px;font-weight:800;color:white'>{total_maternas:,}</div>"
            f"<div style='font-size:12px;color:#fcd34d'>Meta: {META_MATERNAS:,}</div>"
            f"<div style='font-size:18px;font-weight:700;color:#{'10b981' if pct_maternas>=50 else 'f59e0b'}'>{pct_maternas:.1f}%</div>"
            f"<div style='background:#1f1505;border-radius:4px;height:8px;margin-top:6px'>"
            f"<div style='background:#f59e0b;width:{min(pct_maternas,100):.0f}%;height:8px;border-radius:4px'></div></div>"
            f"<div style='font-size:11px;color:#64748b;margin-top:4px'>Faltan {max(META_MATERNAS-total_maternas,0):,}</div>"
            f"</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.metric("⚡ Ritmo actual", f"{tasa_actual:.1f} tamizajes/día de campo",
              help=f"Promedio sobre {dias_campo} días de campo realizados")
    st.markdown("---")

    col_izq, col_der = st.columns(2)
    with col_izq:
        st.markdown("**Niños tamizados por semana**")
        if not ninos.empty and 'semana' in ninos.columns:
            por_sem = ninos.groupby('semana').size().reset_index(name='Niños')
            por_sem['semana'] = por_sem['semana'].astype(str)
            st.bar_chart(por_sem.set_index('semana'))
        else:
            st.info("Sin datos.")
    with col_der:
        st.markdown("**Niños tamizados por mes**")
        if not ninos.empty and 'mes' in ninos.columns:
            por_mes = ninos.groupby('mes').size().reset_index(name='Niños')
            st.bar_chart(por_mes.set_index('mes'))
        else:
            st.info("Sin datos.")

    st.markdown("---")
    # ── Avance por zona vs meta propuesta ──
    st.markdown("**Avance por zona vs. meta propuesta**")
    # Siempre mostrar las 6 zonas del plan, aunque tengan 0 tamizados
    mun_base = pd.DataFrame({
        'Municipio': list(METAS_ZONA.keys()),
        'Meta zona': list(METAS_ZONA.values()),
    })
    if not ninos.empty and 'Municipio' in ninos.columns:
        mun_actual = ninos.groupby('Municipio').size().reset_index(name='Tamizados')
    else:
        mun_actual = pd.DataFrame(columns=['Municipio','Tamizados'])

    mun_n = mun_base.merge(mun_actual, on='Municipio', how='left')
    mun_n['Tamizados'] = mun_n['Tamizados'].fillna(0).astype(int)
    mun_n['Pendientes'] = (mun_n['Meta zona'] - mun_n['Tamizados']).clip(lower=0)
    mun_n['% avance']   = (mun_n['Tamizados'] / mun_n['Meta zona'] * 100).round(1)
    mun_n = mun_n.sort_values('Tamizados', ascending=False)
    st.dataframe(mun_n[['Municipio','Meta zona','Tamizados','Pendientes','% avance']],
                 use_container_width=True, hide_index=True)

    # Barras comparativas
    bar_data = mun_n.set_index('Municipio')[['Tamizados','Meta zona']]
    st.bar_chart(bar_data)

    st.markdown("---")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Indicadores del proyecto**")
        n_ref_maternas = int(df['referencia'].astype(str).str.contains('Sí|Si', case=False, na=False).sum()) if 'referencia' in df.columns else 0
        n_ref_ninos    = int(ninos['¿Se brindó referencia?'].astype(str).str.contains('Sí|Si', case=False, na=False).sum()) if (not ninos.empty and '¿Se brindó referencia?' in ninos.columns) else 0
        n_ref = n_ref_maternas + n_ref_ninos
        ind_df = pd.DataFrame({
            'Indicador': [
                'Total tamizados (C1)',
                '— Niños <5 años',
                '— Embarazadas',
                '— Madres lactantes',
                'Personas referidas',
            ],
            'Meta':   [4000, 3500, 250, 250, 120],
            'Actual': [total_tamizados, total_ninos, n_embarazadas, n_lactantes, n_ref],
        })
        ind_df['Avance %'] = (ind_df['Actual'] / ind_df['Meta'] * 100).round(1)
        st.dataframe(ind_df, use_container_width=True, hide_index=True)

    with col_b:
        st.markdown("**Zonas sin meta asignada en el plan**")
        if not ninos.empty and 'Municipio' in ninos.columns:
            zonas_conocidas = set(METAS_ZONA.keys())
            zonas_data = set(ninos['Municipio'].dropna().unique())
            sin_meta = zonas_data - zonas_conocidas
            if sin_meta:
                st.warning(f"Zonas en datos sin meta definida: {', '.join(sorted(sin_meta))}")
            else:
                st.success("✅ Todas las zonas tienen meta asignada.")

    st.markdown("---")

    # ── Tabla de personas referidas ──
    st.markdown("**📋 Personas referidas**")

    # Helper: busca columna de "unidad de referencia" (varios nombres posibles en el formulario)
    def _get_unidad_ref(row, df_src):
        for cand in ['¿A qué unidad de salud refiere?','Unidad de salud de referencia',
                     'unidad_referencia','Unidad_referencia','Unidad de referencia']:
            if cand in df_src.columns:
                v = row.get(cand, '')
                if pd.notna(v) and str(v).strip() not in ('','nan'):
                    return str(v).strip()
        return ''

    # Maternas referidas
    ref_rows = []
    if 'referencia' in df.columns:
        df_ref_mat = df[df['referencia'].astype(str).str.contains('Sí|Si', case=False, na=False)].copy()
        for _, row in df_ref_mat.iterrows():
            ref_rows.append({
                'Nombre':            row.get('nombre', ''),
                'Mamá':              '',                          # N/A para maternas
                'Tipo':              row.get('perfil', 'Materna'),
                'Peso (kg)':         row.get('peso', ''),
                'Talla (m)':         row.get('talla', ''),
                'MUAC (cm)':         '',                          # MUAC no aplica a maternas
                'Unidad referencia': _get_unidad_ref(row, df),
                'Teléfono':          row.get('telefono', ''),
                'Fecha':             row.get('fecha_dia', ''),
                'Encuestadora':      row.get('encuestador', ''),
                'Municipio':         row.get('Municipio', ''),
                'Distrito':          row.get('distrito_nombre', ''),
                'Cantón':            row.get('canton_nombre', ''),
            })

    # Niños referidos
    if not ninos.empty and '¿Se brindó referencia?' in ninos.columns:
        df_ref_nin = ninos[ninos['¿Se brindó referencia?'].astype(str).str.contains('Sí|Si', case=False, na=False)].copy()
        nombre_nino_col = '¿Cuál es el nombre del niño/a?' if '¿Cuál es el nombre del niño/a?' in df_ref_nin.columns else None
        for _, row in df_ref_nin.iterrows():
            ref_rows.append({
                'Nombre':            row[nombre_nino_col] if nombre_nino_col else '',
                'Mamá':              row.get('nombre', ''),       # nombre de la entrevistada (mamá)
                'Tipo':              'Niño/a',
                'Peso (kg)':         row.get('peso_nino', ''),
                'Talla (m)':         row.get('talla_nino', ''),
                'MUAC (cm)':         row.get('muac', ''),
                'Unidad referencia': _get_unidad_ref(row, ninos),
                'Teléfono':          row.get('telefono', ''),     # teléfono de la mamá
                'Fecha':             row.get('fecha_dia', ''),
                'Encuestadora':      row.get('encuestador', ''),
                'Municipio':         row.get('Municipio', ''),
                'Distrito':          row.get('distrito_nombre', ''),
                'Cantón':            row.get('canton_nombre', ''),
            })

    if not ref_rows:
        st.info("Aún no hay personas referidas registradas.")
    else:
        df_ref_all = pd.DataFrame(ref_rows)
        col_r1, col_r2, col_r3 = st.columns(3)
        col_r1.metric("Total referidas", len(df_ref_all))
        col_r2.metric("Niños/as", int((df_ref_all['Tipo'] == 'Niño/a').sum()))
        col_r3.metric("Maternas", int((df_ref_all['Tipo'] != 'Niño/a').sum()))

        df_ref_all['Fecha'] = pd.to_datetime(df_ref_all['Fecha'], errors='coerce')

        # Orden de columnas: info de contacto primero, luego medidas, luego ubicación
        _col_order = ['Nombre','Mamá','Tipo','Teléfono','Peso (kg)','Talla (m)','MUAC (cm)',
                      'Unidad referencia','Fecha','Encuestadora','Municipio','Distrito','Cantón']
        df_ref_all = df_ref_all[[c for c in _col_order if c in df_ref_all.columns]]

        st.dataframe(df_ref_all.sort_values('Fecha', ascending=False), use_container_width=True, hide_index=True)

        with st.expander("📊 Referencias por encuestadora"):
            ref_enc = df_ref_all.groupby('Encuestadora').size().reset_index(name='Referencias').sort_values('Referencias', ascending=False)
            st.dataframe(ref_enc, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Tabla de desagregación por sexo/edad ──
    st.markdown("**📋 Tabla de desagregación por sexo y edad**")

    def _sexo_es(serie, valores_m, valores_f):
        """Normaliza y cuenta masculinos y femeninos."""
        s = serie.astype(str).str.lower().str.strip()
        m = s.isin(valores_m)
        f = s.isin(valores_f)
        return int(m.sum()), int(f.sum())

    VAL_M = ['masculino','m','hombre','niño','male','masc']
    VAL_F = ['femenino','f','mujer','niña','female','fem']

    # Niños/Niñas (<5) — desde repeat group
    if not ninos.empty and 'Sexo' in ninos.columns:
        n_ninos_m, n_ninos_f = _sexo_es(ninos['Sexo'], VAL_M, VAL_F)
    else:
        n_ninos_m = n_ninos_f = 0

    # Mujeres tamizadas = solo las que tienen peso, talla o IMC (embarazadas/lactantes con medición)
    # Hombres = siempre 0 (no son tamizados, solo acompañantes)
    df_mujeres_tam = df.dropna(subset=['nombre']).drop_duplicates(subset=['nombre'])
    df_mujeres_tam = df_mujeres_tam[
        df_mujeres_tam[['peso','talla','imc']].notna().any(axis=1)
    ] if all(c in df_mujeres_tam.columns for c in ['peso','talla','imc']) else df_mujeres_tam[df_mujeres_tam['perfil'].isin(PERFILES_MATERNAS)] if 'perfil' in df_mujeres_tam.columns else pd.DataFrame()
    n_adult_f = len(df_mujeres_tam)
    n_adult_m = 0  # hombres no son tamizados

    # Consejería — hoja principal (todas las filas con consejería = Sí)
    if 'consejeria' in df.columns:
        df_cons = df[df['consejeria'].astype(str).str.contains('Sí|Si|sí|si', case=False, na=False)]
        df_cons_u = df_cons.dropna(subset=['nombre']).drop_duplicates(subset=['nombre'])
        cons_f = len(df_cons_u)
        cons_m = 0
        total_cons = cons_f
    else:
        cons_m = cons_f = total_cons = 0

    # ── Tabla global ──
    tabla_desag = pd.DataFrame([
        {
            'Actividad':     'Personas tamizadas',
            'Niños (<5)':    n_ninos_m, 'Niñas (<5)': n_ninos_f,
            'Mujeres (≥18)': n_adult_f, 'Hombres (≥18)': 0,
            'Total':         n_ninos_m + n_ninos_f + n_adult_f,
        },
        {
            'Actividad':     'Personas que recibieron consejería',
            'Niños (<5)':    '—', 'Niñas (<5)': '—',
            'Mujeres (≥18)': cons_f, 'Hombres (≥18)': 0,
            'Total':         total_cons,
        },
    ])
    st.dataframe(tabla_desag, use_container_width=True, hide_index=True)
    st.caption("Mujeres ≥18 = embarazadas/lactantes con medición (peso, talla o IMC). Hombres = 0 (no son tamizados).")

    # ── Tabla por zona ──
    st.markdown("**📋 Desagregación por zona**")
    filas_zona = []
    zonas_lista = sorted(set(
        list(ninos['Municipio'].dropna().unique() if not ninos.empty and 'Municipio' in ninos.columns else []) +
        list(df['Municipio'].dropna().unique() if 'Municipio' in df.columns else [])
    ))
    for zona in zonas_lista:
        # Niños/Niñas de esa zona
        n_zona = ninos[ninos['Municipio'] == zona] if not ninos.empty and 'Municipio' in ninos.columns else pd.DataFrame()
        nm, nf = _sexo_es(n_zona['Sexo'], VAL_M, VAL_F) if not n_zona.empty and 'Sexo' in n_zona.columns else (0, 0)

        # Mujeres tamizadas de esa zona (con medición), deduplicadas por nombre
        df_zona_f = df[(df['Municipio'] == zona)].dropna(subset=['nombre']).drop_duplicates(subset=['nombre']) if 'Municipio' in df.columns else pd.DataFrame()
        if not df_zona_f.empty and all(c in df_zona_f.columns for c in ['peso','talla','imc']):
            df_zona_f = df_zona_f[df_zona_f[['peso','talla','imc']].notna().any(axis=1)]
        elif not df_zona_f.empty and 'perfil' in df_zona_f.columns:
            df_zona_f = df_zona_f[df_zona_f['perfil'].isin(PERFILES_MATERNAS)]
        af = len(df_zona_f)

        # Consejería zona
        df_cons_zona = df[(df['Municipio'] == zona) & df['consejeria'].astype(str).str.contains('Sí|Si|sí|si', case=False, na=False)].dropna(subset=['nombre']).drop_duplicates(subset=['nombre']) if 'consejeria' in df.columns and 'Municipio' in df.columns else pd.DataFrame()
        cons_zona = len(df_cons_zona)

        total_zona = nm + nf + af
        if total_zona > 0 or cons_zona > 0:
            filas_zona.append({
                'Zona': zona,
                'Niños': nm, 'Niñas': nf,
                'Mujeres ≥18': af, 'Hombres ≥18': 0,
                'Total tamizados': total_zona,
                'Con consejería': cons_zona,
            })

    if filas_zona:
        df_zona_tabla = pd.DataFrame(filas_zona)
        # Fila total
        total_row = {
            'Zona': '📊 TOTAL',
            'Niños': df_zona_tabla['Niños'].sum(),
            'Niñas': df_zona_tabla['Niñas'].sum(),
            'Mujeres ≥18': df_zona_tabla['Mujeres ≥18'].sum(),
            'Hombres ≥18': df_zona_tabla['Hombres ≥18'].sum(),
            'Total tamizados': df_zona_tabla['Total tamizados'].sum(),
            'Con consejería': df_zona_tabla['Con consejería'].sum(),
        }
        df_zona_tabla = pd.concat([df_zona_tabla, pd.DataFrame([total_row])], ignore_index=True)
        st.dataframe(df_zona_tabla, use_container_width=True, hide_index=True)
    else:
        st.info("Sin datos por zona disponibles.")

    # ── Tabla por cantón ──
    st.markdown("**📋 Desagregación por cantón**")
    canton_col = 'canton_nombre'
    filas_canton = []
    if canton_col in ninos.columns or canton_col in df.columns:
        cantones_lista = sorted(set(
            list(ninos[canton_col].dropna().unique() if canton_col in ninos.columns else []) +
            list(df[canton_col].dropna().unique() if canton_col in df.columns else [])
        ))
        for canton in cantones_lista:
            # Niños de ese cantón
            n_cant = ninos[ninos[canton_col] == canton] if canton_col in ninos.columns and not ninos.empty else pd.DataFrame()
            nm_c, nf_c = _sexo_es(n_cant['Sexo'], VAL_M, VAL_F) if not n_cant.empty and 'Sexo' in n_cant.columns else (0, 0)

            # Mujeres tamizadas de ese cantón
            df_cant = df[(df[canton_col] == canton)].dropna(subset=['nombre']).drop_duplicates(subset=['nombre']) if canton_col in df.columns else pd.DataFrame()
            if not df_cant.empty and all(c in df_cant.columns for c in ['peso','talla','imc']):
                df_cant = df_cant[df_cant[['peso','talla','imc']].notna().any(axis=1)]
            elif not df_cant.empty and 'perfil' in df_cant.columns:
                df_cant = df_cant[df_cant['perfil'].isin(PERFILES_MATERNAS)]
            af_c = len(df_cant)

            total_c = nm_c + nf_c + af_c
            if total_c > 0:
                zona_c = ninos.loc[ninos[canton_col] == canton, 'Municipio'].mode()[0] if canton_col in ninos.columns and not ninos.empty and 'Municipio' in ninos.columns and (ninos[canton_col] == canton).any() else ''
                filas_canton.append({
                    'Zona': zona_c,
                    'Cantón': canton,
                    'Niños': nm_c, 'Niñas': nf_c,
                    'Mujeres ≥18': af_c, 'Hombres ≥18': 0,
                    'Total': total_c,
                })
        if filas_canton:
            df_canton_tabla = pd.DataFrame(filas_canton).sort_values(['Zona','Cantón'])
            total_row_c = {
                'Zona': '', 'Cantón': '📊 TOTAL',
                'Niños': df_canton_tabla['Niños'].sum(),
                'Niñas': df_canton_tabla['Niñas'].sum(),
                'Mujeres ≥18': df_canton_tabla['Mujeres ≥18'].sum(),
                'Hombres ≥18': 0,
                'Total': df_canton_tabla['Total'].sum(),
            }
            df_canton_tabla = pd.concat([df_canton_tabla, pd.DataFrame([total_row_c])], ignore_index=True)
            st.dataframe(df_canton_tabla, use_container_width=True, hide_index=True)
        else:
            st.info("Sin datos por cantón disponibles.")
    else:
        st.info("No se encontró columna de cantón — verificar catálogos geográficos.")

    st.markdown("---")

    # ── Gráfica avance diario ──
    st.markdown("**📅 Avance diario de tamizados (niños + maternas)**")
    if not ninos.empty and 'fecha_dia' in ninos.columns:
        diario_n = ninos.groupby('fecha_dia').size().reset_index(name='Niños')
        if 'fecha_dia' in df.columns:
            if all(c in df.columns for c in ['peso','talla','imc']):
                _dm = df.dropna(subset=['nombre']).drop_duplicates(subset=['nombre'])
                _dm = _dm[_dm[['peso','talla','imc']].notna().any(axis=1)]
            elif 'perfil' in df.columns:
                _dm = df[df['perfil'].isin(PERFILES_MATERNAS)].dropna(subset=['nombre']).drop_duplicates(subset=['nombre'])
            else:
                _dm = pd.DataFrame()
            diario_m = _dm.groupby('fecha_dia').size().reset_index(name='Maternas') if not _dm.empty else pd.DataFrame(columns=['fecha_dia','Maternas'])
        else:
            diario_m = pd.DataFrame(columns=['fecha_dia','Maternas'])
        diario = diario_n.merge(diario_m, on='fecha_dia', how='outer').fillna(0)
        diario['Total'] = diario['Niños'] + diario['Maternas']
        diario['fecha_dia'] = diario['fecha_dia'].astype(str)
        st.bar_chart(diario.set_index('fecha_dia')[['Niños','Maternas']])

    # (Ver proyección completa en tab "Proyección & Escenarios")


# ── TAB 2: PROYECCIÓN ──────────────────────────
with tab_escenarios:
    st.subheader("🎯 Proyección a Meta — Modelo de 3 Contactos")

    col_tl1, col_tl2, col_tl3, col_tl4 = st.columns(4)
    col_tl1.metric("📅 Cierre C1 (tamizaje)",    FECHA_C1.strftime("%d %b %Y"),  help="Tamizaje campo: peso, talla, MUAC")
    col_tl2.metric("📅 Cierre C2 (charla)",       FECHA_C2.strftime("%d %b %Y"),  help="Charla presencial en comunidades ya visitadas")
    col_tl3.metric("📅 Cierre C3 (retamizaje)",   FECHA_C3.strftime("%d %b %Y"),  help="Segunda medición en campo")
    col_tl4.metric("🏁 Cierre proyecto",           FECHA_LIMITE.strftime("%d %b %Y"))

    st.markdown("""
    | Contacto | Modalidad | Ventana | Descripción |
    |----------|-----------|---------|-------------|
    | **C1** 🏥 | Presencial campo | hoy → 30 jul | Tamizaje: peso, talla, MUAC |
    | **C2** 🏘️ | Presencial comunidad | 30 jul → 15 sep | Charla en las comunidades visitadas (no es tamizaje) |
    | **C3** 🏥 | Presencial campo | 15 sep → 21 oct | Retamizaje: segunda medición |
    """)

    # ── Gráfico de progreso y proyección ────────────────────────────────────
    st.markdown("### 📈 Progreso acumulado y proyección de avance C1")
    if not ninos.empty and 'fecha_dia' in ninos.columns:
        _n_dia = ninos.groupby('fecha_dia').size().reset_index(name='n')
        if 'fecha_dia' in df.columns and all(c in df.columns for c in ['peso','talla','imc']):
            _dm = df.dropna(subset=['nombre']).drop_duplicates(subset=['nombre'])
            _dm = _dm[_dm[['peso','talla','imc']].notna().any(axis=1)]
            _m_dia = _dm.groupby('fecha_dia').size().reset_index(name='m')
        elif 'fecha_dia' in df.columns and 'perfil' in df.columns:
            _dm = df[df['perfil'].isin(PERFILES_MATERNAS)].dropna(subset=['nombre']).drop_duplicates(subset=['nombre'])
            _m_dia = _dm.groupby('fecha_dia').size().reset_index(name='m')
        else:
            _m_dia = pd.DataFrame(columns=['fecha_dia','m'])
        _cum = _n_dia.merge(_m_dia, on='fecha_dia', how='outer').fillna(0)
        _cum['n'] = _cum['n'] + _cum.get('m', 0)
        _cum = _cum.sort_values('fecha_dia')
        _cum['Avance Acumulado'] = _cum['n'].cumsum().astype(int)
        _cum['fecha_dia'] = pd.to_datetime(_cum['fecha_dia'])

        _ultimo      = int(_cum['Avance Acumulado'].iloc[-1])
        _ult_fecha   = _cum['fecha_dia'].iloc[-1].date()
        _hoy         = date.today()
        _dias_c1     = max((FECHA_C1 - _hoy).days, 1)
        _restante    = max(META_TAMIZAJE - _ultimo, 0)
        _tasa_rec    = _cum.tail(min(7, len(_cum)))['n'].mean()
        _tasa_ideal  = _restante / _dias_c1
        _fecha_meta  = _hoy + timedelta(days=int(_restante / _tasa_rec)) if _tasa_rec > 0 else None

        col_r1, col_r2, col_r3 = st.columns(3)
        col_r1.metric("Tasa actual (últ. 7 días)", f"{_tasa_rec:.0f} / día")
        col_r2.metric("Tasa ideal para meta C1",   f"{_tasa_ideal:.0f} / día",
                      help=f"Necesario antes del {FECHA_C1.strftime('%d/%m')}")
        col_r3.metric("Meta con ritmo actual",
                      _fecha_meta.strftime('%d/%m/%Y') if _fecha_meta else '—',
                      delta="✅ Antes del límite" if _fecha_meta and _fecha_meta <= FECHA_C1 else "⚠️ Después del límite C1",
                      delta_color="normal" if _fecha_meta and _fecha_meta <= FECHA_C1 else "inverse")

        # Construir series
        _hist = _cum[['fecha_dia','Avance Acumulado']].set_index('fecha_dia')

        _dias_proy = int(_restante / _tasa_rec) + 5 if _tasa_rec > 0 else _dias_c1
        _f_actual  = [_hoy + timedelta(days=i) for i in range(1, _dias_proy + 1)]
        _v_actual  = [min(_ultimo + _tasa_rec * i,   META_TAMIZAJE) for i in range(1, _dias_proy + 1)]
        _f_ideal   = [_hoy + timedelta(days=i) for i in range(1, _dias_c1 + 1)]
        _v_ideal   = [min(_ultimo + _tasa_ideal * i, META_TAMIZAJE) for i in range(1, _dias_c1 + 1)]

        _all_dates = sorted(set(list(_cum['fecha_dia']) + [pd.Timestamp(f) for f in _f_actual] + [pd.Timestamp(f) for f in _f_ideal]))
        _chart = pd.DataFrame(index=pd.to_datetime(_all_dates)); _chart.index.name = 'fecha'
        _chart['Avance Acumulado']  = _chart.index.map(_hist['Avance Acumulado'])
        _chart['Meta Total']        = META_TAMIZAJE
        _chart['Ritmo actual']      = _chart.index.map(pd.Series(_v_actual, index=pd.to_datetime(_f_actual)))
        _chart['Ritmo ideal (C1)']  = _chart.index.map(pd.Series(_v_ideal,  index=pd.to_datetime(_f_ideal)))
        for _c in ['Ritmo actual','Ritmo ideal (C1)']:
            _chart.loc[pd.Timestamp(_ult_fecha), _c] = _ultimo

        st.line_chart(_chart[['Avance Acumulado','Ritmo actual','Ritmo ideal (C1)','Meta Total']])
        st.caption(f"Faltan **{_restante:,}** tamizajes para completar C1 antes del {FECHA_C1.strftime('%d/%m/%Y')}.")

    st.markdown("---")

    # ── AVANCE SEMANAL ────────────────────────────────────────────────────────
    st.markdown("### 📅 Avance por semana")
    if not ninos.empty and 'semana' in ninos.columns:
        _sem_n = ninos.groupby('semana').size().reset_index(name='Tamizados semana')
        _sem_n['semana'] = pd.to_datetime(_sem_n['semana'].astype(str))
        _sem_n = _sem_n.sort_values('semana')
        _sem_n['Acumulado']     = _sem_n['Tamizados semana'].cumsum()
        _sem_n['% Meta']        = (_sem_n['Acumulado'] / META_TAMIZAJE * 100).round(1)
        # Tasa de crecimiento semana a semana
        _sem_n['Crecimiento %'] = _sem_n['Tamizados semana'].pct_change().mul(100).round(1)
        _sem_n['semana_str']    = _sem_n['semana'].dt.strftime('Sem %d/%m')

        # KPIs
        _sc1, _sc2, _sc3 = st.columns(3)
        _ult_sem  = _sem_n.iloc[-1]
        _pen_sem  = _sem_n.iloc[-2] if len(_sem_n) >= 2 else None
        _sc1.metric("Última semana", f"{int(_ult_sem['Tamizados semana'])} tamizajes")
        _sc2.metric("Crecimiento vs semana anterior",
                    f"{_ult_sem['Crecimiento %']:+.1f}%" if pd.notna(_ult_sem['Crecimiento %']) else "—",
                    delta_color="normal")
        _sc3.metric("Promedio por semana", f"{_sem_n['Tamizados semana'].mean():.0f} tamizajes")

        # Tabla
        _sem_display = _sem_n[['semana_str','Tamizados semana','Acumulado','% Meta','Crecimiento %']].copy()
        _sem_display.columns = ['Semana','Tamizados','Acumulado','% Meta','Crec. sem. ant. (%)']
        st.dataframe(_sem_display, use_container_width=True, hide_index=True)

        # Gráfica semanal
        st.bar_chart(_sem_n.set_index('semana_str')['Tamizados semana'])
    else:
        st.info("Sin datos de semana disponibles.")

    st.markdown("---")

    # Equipo actual
    N_EQUIPOS_ACTUAL  = 6   # parejas actuales
    N_PERSONAS_TOTAL  = 13  # personas individuales (sin la promotora pendiente)

    st.info(
        f"C1 actual: **{total_tamizados:,}** tamizados · **{META_TAMIZAJE - total_tamizados:,}** pendientes · **{pct_meta:.1f}%** completado  \n"
        f"Equipo: **{N_EQUIPOS_ACTUAL} parejas** ({N_PERSONAS_TOTAL} personas) · Ritmo actual: **{tasa_actual:.0f} tamizajes/día de campo**"
    )
    st.markdown("---")

    # Tasa actual es el TOTAL de todos los equipos ese día
    tasa_total_actual = max(int(round(tasa_actual)), 6)
    tasa_por_equipo   = max(tasa_total_actual // N_EQUIPOS_ACTUAL, 3)

    st.markdown(f"> **Ritmo actual:** {tasa_total_actual} tamizajes/día en total · {tasa_por_equipo} por equipo (÷ {N_EQUIPOS_ACTUAL} equipos)")

    # ── ESCENARIOS EN EQUIPOS (parejas) ──
    # ── CÁLCULO META SEMANAL ────────────────────────────────────────────────
    st.markdown("### 🎯 Cálculo de Meta Semanal")
    _fecha_inicio_of = date(2026, 5, 29)
    _hoy_ms          = date.today()
    # Solo días laborales (lunes a viernes)
    _dias_trab       = max(int(np.busday_count(_fecha_inicio_of, _hoy_ms)), 1)
    _n_equipos_ms    = 7   # equipos de campo activos (sin coordinación)
    _logrados_ms     = total_tamizados   # niños + maternas sin niños
    _faltantes_ms    = max(META_TAMIZAJE - _logrados_ms, 0)
    _ritmo_real_ms   = round(_logrados_ms / _dias_trab)
    _ritmo_real_sem  = _ritmo_real_ms * 5   # 5 días laborales/semana
    _dias_c1_ms      = max(int(np.busday_count(_hoy_ms, FECHA_C1)), 1)
    _semanas_rest    = max(_dias_c1_ms / 5, 1)
    _ritmo_opt_sem   = round(_faltantes_ms / _semanas_rest) if _semanas_rest > 0 else _faltantes_ms
    _ritmo_opt_eq    = round(_ritmo_opt_sem / _n_equipos_ms) if _n_equipos_ms > 0 else _ritmo_opt_sem  # por equipo/semana
    _ritmo_opt_eq_dia = round(_ritmo_opt_eq / 5)  # por equipo/día (÷ 5 días laborales)
    _ritmo_esp_sem   = round(META_TAMIZAJE / ((_hoy_ms - _fecha_inicio_of + timedelta(days=_dias_c1_ms)).days / 5))
    _diferencia      = _ritmo_real_sem - _ritmo_esp_sem
    _fecha_opt       = _hoy_ms + timedelta(days=int(_faltantes_ms / _ritmo_real_ms)) if _ritmo_real_ms > 0 else None

    _ms_c1, _ms_c2 = st.columns(2)
    with _ms_c1:
        st.markdown("**📋 Resumen de avance**")
        _tabla_ms = {
            'Concepto': [
                'Meta total (niños C1)', 'Logrados a la fecha', 'Faltantes',
                'Fecha inicio oficial', 'Días trabajados',
                'Ritmo real diario', 'Ritmo real semanal',
                'Fecha estimada finalización', 'Fecha óptima C1',
                'Días restantes C1',
            ],
            'Valor': [
                f"{META_TAMIZAJE:,}", f"{_logrados_ms:,}", f"{_faltantes_ms:,}",
                _fecha_inicio_of.strftime('%d/%m/%Y'), str(_dias_trab),
                f"{_ritmo_real_ms}/día", f"{_ritmo_real_sem}/semana",
                _fecha_opt.strftime('%d/%m/%Y') if _fecha_opt else '—',
                FECHA_C1.strftime('%d/%m/%Y'),
                str(_dias_c1_ms),
            ]
        }
        st.dataframe(pd.DataFrame(_tabla_ms), use_container_width=True, hide_index=True)

    with _ms_c2:
        st.markdown("**🚀 Ritmo óptimo para cumplir meta**")
        _tabla_opt = {
            'Concepto': [
                'N° equipos de campo', 'Semanas restantes C1',
                'Ritmo esperado semanal', 'Ritmo real semanal', 'Diferencia',
                'Personas faltantes',
                'Ritmo óptimo SEMANAL (todo el equipo)',
                f'Por equipo/semana ({_n_equipos_ms} equipos)',
                f'Por equipo/día ({_n_equipos_ms} equipos × 5 días)',
            ],
            'Valor': [
                str(_n_equipos_ms), f"{_semanas_rest:.1f}",
                f"{_ritmo_esp_sem:,}/semana", f"{_ritmo_real_sem:,}/semana",
                f"{_diferencia:+d} {'✅' if _diferencia >= 0 else '⚠️'}",
                f"{_faltantes_ms:,}",
                f"{_ritmo_opt_sem:,}/semana",
                f"{_ritmo_opt_eq:,}/semana por equipo",
                f"{_ritmo_opt_eq_dia}/día por equipo",
            ]
        }
        st.dataframe(pd.DataFrame(_tabla_opt), use_container_width=True, hide_index=True)

        # Gráfica ritmo: real vs esperado vs meta óptima — con data labels
        _fig_ritmo = go.Figure()
        _ritmo_labels = ['Ritmo real\nsemanal', 'Ritmo esperado\nsemanal', 'Meta óptima\nsemanal']
        _ritmo_values = [_ritmo_real_sem, _ritmo_esp_sem, _ritmo_opt_sem]
        _ritmo_colors = ['#2ecc71', '#3498db', '#e74c3c']
        _fig_ritmo.add_trace(go.Bar(
            x=_ritmo_labels, y=_ritmo_values,
            marker_color=_ritmo_colors,
            text=_ritmo_values, textposition='outside',
            textfont=dict(size=13)
        ))
        _fig_ritmo.update_layout(
            margin=dict(t=40, b=20), height=320,
            yaxis_title='Tamizajes/semana',
            plot_bgcolor='white',
            yaxis=dict(showgrid=True, gridcolor='#e8e8e8'),
            showlegend=False
        )
        st.plotly_chart(_fig_ritmo, use_container_width=True)

    st.markdown("---")

    st.markdown("### 👥 Escenarios trabajando en equipos (parejas)")
    st.caption("Cada equipo = 2 personas (técnica + promotora). Los sliders son **por equipo**. La capacidad total se calcula automáticamente.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**🟡 Conservador**")
        tam_A = st.slider("Tamizajes/día por equipo (A)", 3, 60, tasa_por_equipo,         2, key='A1')
        sem_A = st.slider("Días campo/semana (A)",        1, 6,  3,                       1, key='A2')
        eq_A  = st.slider("N° de equipos (A)",            6, 12, 6,                       1, key='A3')
        st.metric("🔢 Capacidad total/día", f"{tam_A * eq_A} tamizajes",
                  help="tamizajes/día por equipo × número de equipos")
        st.metric("📅 Capacidad semanal", f"{tam_A * eq_A * sem_A} tamizajes")
    with col2:
        st.markdown("**🟠 Moderado**")
        tam_B = st.slider("Tamizajes/día por equipo (B)", 3, 60, min(tasa_por_equipo+3, 60), 2, key='B1')
        sem_B = st.slider("Días campo/semana (B)",        1, 6,  4,                          1, key='B2')
        eq_B  = st.slider("N° de equipos (B)",            6, 12, 8,                          1, key='B3')
        st.metric("🔢 Capacidad total/día", f"{tam_B * eq_B} tamizajes")
        st.metric("📅 Capacidad semanal",   f"{tam_B * eq_B * sem_B} tamizajes")
    with col3:
        st.markdown("**🔴 Intensivo**")
        tam_C = st.slider("Tamizajes/día por equipo (C)", 3, 60, min(tasa_por_equipo+6, 60), 2, key='C1')
        sem_C = st.slider("Días campo/semana (C)",        1, 6,  5,                          1, key='C2')
        eq_C  = st.slider("N° de equipos (C)",            6, 12, 10,                         1, key='C3')
        st.metric("🔢 Capacidad total/día", f"{tam_C * eq_C} tamizajes")
        st.metric("📅 Capacidad semanal",   f"{tam_C * eq_C * sem_C} tamizajes")

    escenarios_eq = {
        '🟡 Conservador (equipos)': calcular_proyeccion(total_tamizados, META_TAMIZAJE, tam_A, sem_A, eq_A),
        '🟠 Moderado (equipos)':    calcular_proyeccion(total_tamizados, META_TAMIZAJE, tam_B, sem_B, eq_B),
        '🔴 Intensivo (equipos)':   calcular_proyeccion(total_tamizados, META_TAMIZAJE, tam_C, sem_C, eq_C),
    }

    st.markdown("---")

    # ── ESCENARIOS INDIVIDUALES ──
    st.markdown("### 🧍 Escenarios trabajando de forma individual")
    st.caption(
        f"Cada persona trabaja de forma independiente. "
        f"Team actual: {N_PERSONAS_TOTAL} personas. Tamizajes individuales suelen ser menores (sin pareja de apoyo)."
    )

    col_i1, col_i2, col_i3 = st.columns(3)
    with col_i1:
        tam_ind = st.slider("Tamizajes/día por persona", 3, 40, tasa_por_equipo, 1, key='I1')
        sem_ind = st.slider("Días campo/semana",          1, 6,  4,              1, key='I2')
    with col_i2:
        n_ind   = st.slider("N° de personas en campo", 6, N_PERSONAS_TOTAL, N_PERSONAS_TOTAL, 1, key='I3')
        st.caption(f"Equipo completo: {N_PERSONAS_TOTAL} personas")
    with col_i3:
        st.metric("🔢 Capacidad total/día", f"{tam_ind * n_ind} tamizajes",
                  help="tamizajes/día por persona × personas en campo")
        st.metric("📅 Capacidad semanal",   f"{tam_ind * n_ind * sem_ind} tamizajes")

    escenario_ind = calcular_proyeccion(total_tamizados, META_TAMIZAJE, tam_ind, sem_ind, n_ind)

    # ── TABLA COMPARATIVA ──
    st.markdown("---")
    st.markdown("### 📊 Comparativa de todos los escenarios")

    todos_esc = {**escenarios_eq, f'🧍 Individual ({n_ind} personas)': escenario_ind}
    filas = []
    for nombre, e in todos_esc.items():
        def _fmt(d): return d.strftime('%d/%m/%Y') if d else '⚠️'
        def _cumple(ok): return '✅' if ok else '❌'
        filas.append({
            'Escenario':          nombre,
            'Cap./día':           e['cap_dia'],
            'Cap./semana':        e['cap_sem'],
            f"C1 ≤ {FECHA_C1.strftime('%d/%m')}":  _cumple(e['cumple_c1']) + ' ' + _fmt(e['fecha_fin_c1']),
            f"C2 ≤ {FECHA_C2.strftime('%d/%m')}":  _cumple(e['cumple_c2']) + ' ' + _fmt(e['fecha_fin_c2']),
            f"C3 ≤ {FECHA_C3.strftime('%d/%m')}":  _cumple(e['cumple_c3']) + ' ' + _fmt(e['fecha_fin_c3']),
            '🏁 Cumple todo':     '✅ Sí' if e['cumple'] else '❌ No',
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    st.markdown("---")

    for nombre, e in todos_esc.items():
        color = "#d1fae5" if e['cumple'] else "#fee2e2"
        icono = "✅" if e['cumple'] else "❌"
        def _fmt(d): return d.strftime('%d %b %Y') if d else 'fuera de rango'
        def _ok(ok, label, limit): return f"{'✅' if ok else '❌'} {label}: <b>{_fmt(e[f'fecha_fin_{label.lower()}'])}</b> (límite {limit.strftime('%d/%m')})"
        st.markdown(f"""
        <div style="background:{color};border-radius:8px;padding:12px 16px;margin:6px 0;">
        <strong>{nombre}</strong> — {icono} {'Cumple todos los deadlines' if e['cumple'] else 'NO cumple todos los deadlines'}<br>
        <small>
        {'✅' if e['cumple_c1'] else '❌'} C1 termina: <b>{_fmt(e['fecha_fin_c1'])}</b> (límite {FECHA_C1.strftime('%d/%m')}) &nbsp;·&nbsp;
        {'✅' if e['cumple_c2'] else '❌'} C2 termina: <b>{_fmt(e['fecha_fin_c2'])}</b> (límite {FECHA_C2.strftime('%d/%m')}) &nbsp;·&nbsp;
        {'✅' if e['cumple_c3'] else '❌'} C3 termina: <b>{_fmt(e['fecha_fin_c3'])}</b> (límite {FECHA_C3.strftime('%d/%m')}) &nbsp;·&nbsp;
        Capacidad: <b>{e['cap_dia']} /día · {e['cap_sem']}/semana</b>
        </small></div>
        """, unsafe_allow_html=True)


# ── TAB 3: INDICADORES NUTRICIONALES ───────────
with tab_indicadores:
    st.subheader("🥗 Indicadores Nutricionales — Niños <5 años")

    if ninos.empty:
        st.info("Sin datos de niños disponibles.")
    else:
        # ── Resumen de medidas ──
        st.markdown("### 📏 Resumen de medidas antropométricas")
        med_data = []
        for col, lbl, unidad in [
            ('peso_nino',  'Peso',  'kg'),
            ('talla_nino', 'Talla', 'cm'),
            ('muac',       'MUAC (perímetro braquial)', 'cm'),
        ]:
            s = ninos[col].dropna() if col in ninos.columns else pd.Series(dtype=float)
            if not s.empty:
                med_data.append({
                    'Medida': f"{lbl} ({unidad})",
                    'N con dato': len(s),
                    '% con dato': f"{len(s)/len(ninos)*100:.0f}%",
                    'Mín':    round(s.min(), 1),
                    'P25':    round(s.quantile(0.25), 1),
                    'Mediana':round(s.median(), 1),
                    'P75':    round(s.quantile(0.75), 1),
                    'Máx':    round(s.max(), 1),
                })
        if med_data:
            st.dataframe(pd.DataFrame(med_data), use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Distribución de diagnósticos ──
        st.markdown("### 🩺 Distribución de diagnósticos nutricionales")

        DIAG_COLS = {
            '¿Cuál es el diagnóstico nutricional de la talla y edad?':  'Talla/Edad (T/E)',
            '¿Cuál es el diagnóstico nutricional de peso edad?':         'Peso/Edad (P/E)',
            '¿Cuál es el diagnóstico nutricional del peso y la talla?':  'Peso/Talla (P/T)',
            'Diagnóstico nutricional según perímetro braquial':           'MUAC',
        }

        diag_resumen = []
        for col_raw, etiqueta in DIAG_COLS.items():
            col_diag = None
            # Buscar en ninos directo
            if col_raw in ninos.columns:
                col_diag = ninos[col_raw]
            if col_diag is not None and col_diag.notna().any():
                counts = col_diag.value_counts(dropna=True)
                total_diag = counts.sum()
                for diag, cnt in counts.items():
                    diag_resumen.append({
                        'Indicador': etiqueta,
                        'Diagnóstico': str(diag),
                        'N': int(cnt),
                        '%': f"{cnt/total_diag*100:.1f}%",
                    })

        if diag_resumen:
            df_diag = pd.DataFrame(diag_resumen)
            # Mostrar por indicador en columnas
            col_te, col_pe, col_pt = st.columns(3)
            for col_widget, indicador in [(col_te,'Talla/Edad (T/E)'), (col_pe,'Peso/Edad (P/E)'), (col_pt,'Peso/Talla (P/T)')]:
                sub = df_diag[df_diag['Indicador']==indicador][['Diagnóstico','N','%']]
                if not sub.empty:
                    col_widget.markdown(f"**{indicador}**")
                    col_widget.dataframe(sub, use_container_width=True, hide_index=True)

            muac_sub = df_diag[df_diag['Indicador']=='MUAC'][['Diagnóstico','N','%']]
            if not muac_sub.empty:
                st.markdown("**MUAC (perímetro braquial)**")
                st.dataframe(muac_sub, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de diagnóstico nutricional en la base actual.")

        st.markdown("---")

        # ── Tabla cruzada: diagnósticos por zona ──
        st.markdown("### 📍 Diagnóstico P/T por zona (desnutrición aguda)")
        col_pt_raw = '¿Cuál es el diagnóstico nutricional del peso y la talla?'
        if col_pt_raw in ninos.columns and 'Municipio' in ninos.columns:
            tabla_zona = pd.crosstab(
                ninos['Municipio'].fillna('Sin zona'),
                ninos[col_pt_raw].fillna('Sin dato')
            )
            tabla_zona['TOTAL'] = tabla_zona.sum(axis=1)
            st.dataframe(tabla_zona, use_container_width=True)
        else:
            st.info("Sin columnas de diagnóstico o municipio disponibles.")

        st.markdown("---")

        # ── Histogramas ──
        st.markdown("### 📊 Distribución de peso y talla")
        col_h1, col_h2 = st.columns(2)

        with col_h1:
            st.markdown("**Peso (kg)**")
            if 'peso_nino' in ninos.columns:
                p = ninos['peso_nino'].dropna()
                p = p[(p >= 2) & (p <= 35)]
                if not p.empty:
                    hist_p, edges_p = np.histogram(p, bins=range(2, 36, 2))
                    hp_df = pd.DataFrame({
                        'kg': [f"{int(edges_p[i])}-{int(edges_p[i+1])}" for i in range(len(hist_p))],
                        'Niños': hist_p,
                    })
                    st.bar_chart(hp_df.set_index('kg'))

        with col_h2:
            st.markdown("**Talla (cm)**")
            if 'talla_nino' in ninos.columns:
                t = ninos['talla_nino'].dropna()
                t = t[(t >= 40) & (t <= 130)]
                if not t.empty:
                    hist_t, edges_t = np.histogram(t, bins=range(40, 135, 5))
                    ht_df = pd.DataFrame({
                        'cm': [f"{int(edges_t[i])}-{int(edges_t[i+1])}" for i in range(len(hist_t))],
                        'Niños': hist_t,
                    })
                    st.bar_chart(ht_df.set_index('cm'))

        # ── Indicadores de madres (embarazadas) ──
        st.markdown("---")
        st.markdown("### 🤰 Indicadores de mujeres embarazadas")
        df_emb = df[df['perfil'].isin(PERFILES_EMBARAZADA)].copy() if 'perfil' in df.columns else pd.DataFrame()
        if not df_emb.empty and 'talla' in df_emb.columns and 'peso' in df_emb.columns:
            emb_med = []
            for col, lbl, unidad in [('peso','Peso','kg'),('talla','Talla','m'),('imc','IMC',''),('eg_sem','Edad gestacional','sem')]:
                s = df_emb[col].dropna() if col in df_emb.columns else pd.Series(dtype=float)
                if not s.empty:
                    emb_med.append({'Medida':f"{lbl} ({unidad})" if unidad else lbl,
                                    'N':len(s),'Mín':round(s.min(),2),'Mediana':round(s.median(),2),'Máx':round(s.max(),2)})
            if emb_med:
                st.dataframe(pd.DataFrame(emb_med), use_container_width=True, hide_index=True)
        else:
            st.info("Sin datos de embarazadas en la base actual.")


# ── TAB 4: FLAGS ───────────────────────────────
with tab_flags:
    st.subheader("🚦 Resumen de Flags de Calidad")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total entrevistas", len(df))
    c2.metric("🔴 Flags críticos", n_alta)
    c3.metric("🟡 Flags medios",  n_media)
    c4.metric("Registros con flag", todos['_id'].nunique() if not todos.empty else 0)

    if todos.empty:
        st.success("✅ Sin problemas detectados.")
    else:
        resumen = todos.groupby(['flag','severidad']).size().reset_index(name='n').sort_values(['severidad','n'], ascending=[True,False])
        for _, row in resumen.iterrows():
            cls = 'flag-high' if row['severidad']=='Alta' else 'flag-medium'
            st.markdown(f'<div class="{cls}"><strong>{row["flag"]}</strong> — {row["n"]} registro(s)</div>', unsafe_allow_html=True)
        st.markdown("---")
        cols = [c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','distrito_nombre','flag','severidad'] if c in todos.columns]
        st.dataframe(todos[cols].sort_values('severidad'), use_container_width=True, hide_index=True)


# ── TAB: REFERENCIAS ───────────────────────────────────────────────────────
with tab_ref_check:
    st.subheader("🚨 Control de Calidad — Referencias")
    st.caption(
        "Revisión de congruencia entre diagnóstico nutricional (peso/talla) y referencia. "
        "**Rojo** = debería haberse referido y no se hizo. **Amarillo** = se hizo referencia pero el diagnóstico es normal."
    )

    if f_ref.empty:
        st.success("✅ Sin inconsistencias de referencia detectadas.")
    else:
        # KPIs
        n_sin_ref   = int((f_ref['severidad'] == 'Alta').sum())
        n_ref_dudosa= int((f_ref['severidad'] == 'Media').sum())
        k1, k2, k3 = st.columns(3)
        k1.metric("Total inconsistencias", len(f_ref))
        k2.metric("🔴 Sin referencia (debería)", n_sin_ref)
        k3.metric("🟡 Referencia dudosa (dx normal)", n_ref_dudosa)

        st.markdown("---")

        # ── Casos sin referencia (prioritario) ─────────────────────────────
        f_sin_ref = f_ref[f_ref['severidad'] == 'Alta']
        if not f_sin_ref.empty:
            st.markdown(f"### 🔴 Sin referencia — diagnóstico crítico ({len(f_sin_ref)} casos)")
            st.caption("Estos niños/as o personas tienen desnutrición aguda / emaciación registrada pero **no se les hizo referencia**. Requieren seguimiento inmediato.")
            cols_show = [c for c in ['nombre','fecha_dia','encuestador','Municipio','distrito_nombre','flag'] if c in f_sin_ref.columns]
            st.dataframe(
                f_sin_ref[cols_show].rename(columns={'fecha_dia':'Fecha','encuestador':'Encuestadora','distrito_nombre':'Distrito'})
                .sort_values('Fecha', ascending=False),
                use_container_width=True, hide_index=True
            )

            # Descarga
            buf_sr = io.BytesIO()
            f_sin_ref[cols_show].to_excel(buf_sr, index=False); buf_sr.seek(0)
            st.download_button("⬇️ Descargar listado sin referencia (.xlsx)", buf_sr,
                               "sin_referencia_urgente.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            st.markdown("---")

        # ── Referencias dudosas ─────────────────────────────────────────────
        f_dud = f_ref[f_ref['severidad'] == 'Media']
        if not f_dud.empty:
            with st.expander(f"🟡 Referencia con diagnóstico normal ({len(f_dud)} casos) — clic para ver"):
                cols_show2 = [c for c in ['nombre','fecha_dia','encuestador','Municipio','distrito_nombre','flag'] if c in f_dud.columns]
                st.dataframe(
                    f_dud[cols_show2].rename(columns={'fecha_dia':'Fecha','encuestador':'Encuestadora','distrito_nombre':'Distrito'})
                    .sort_values('Fecha', ascending=False),
                    use_container_width=True, hide_index=True
                )

        # ── Resumen por encuestadora ────────────────────────────────────────
        st.markdown("---")
        st.markdown("**Por encuestadora**")
        if 'encuestador' in f_ref.columns:
            resumen_enc = (
                f_ref.groupby(['encuestador','severidad'])
                .size().unstack(fill_value=0).reset_index()
                .rename(columns={'encuestador':'Encuestadora','Alta':'Sin referencia 🔴','Media':'Ref. dudosa 🟡'})
            )
            st.dataframe(resumen_enc, use_container_width=True, hide_index=True)


# ── TAB 5: DURACIÓN ────────────────────────────
with tab_dur:
    st.subheader("⏱️ Duración de Entrevistas")
    dur = df['duracion_min'].dropna()
    dur_v = dur[dur < 1000]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Mediana", f"{dur_v.median():.1f} min")
    c2.metric("< 5 min", int((dur_v<5).sum()))
    c3.metric("> 90 min", int((dur_v>90).sum()))
    c4.metric("Subidos con retraso (>1000 min)", int((dur>=1000).sum()), help="Sin internet en campo — la duración no refleja el tiempo real de entrevista")
    if len(dur_v) > 0:
        hist, edges = np.histogram(dur_v.clip(upper=120), bins=range(0,125,5))
        # Usar etiquetas con cero a la izquierda para que ordenen correctamente como texto
        hdf = pd.DataFrame({
            'Minutos': [f"{int(edges[i]):03d}-{int(edges[i+1]):03d}" for i in range(len(hist))],
            'Entrevistas': hist
        })
        st.bar_chart(hdf.set_index('Minutos'))
        st.caption("Eje X: rango de duración en minutos. La mayoría de entrevistas dura entre 5 y 15 minutos.")
    if not f_dur.empty:
        cols = [c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','duracion_min','flag'] if c in f_dur.columns]
        st.dataframe(f_dur[cols], use_container_width=True, hide_index=True)


# ── TAB 5: DUPLICADOS ──────────────────────────
with tab_dups:
    st.subheader("👥 Duplicados")
    if f_dup.empty:
        st.success("✅ Sin duplicados detectados.")
    else:
        dup_prob   = f_dup[f_dup['severidad']=='Alta']
        dup_verif  = f_dup[f_dup['severidad']=='Media']

        c1, c2 = st.columns(2)
        c1.metric("🔴 Duplicados probables (eliminar)", dup_prob['nombre'].nunique() if not dup_prob.empty else 0, help="Misma madre, misma fecha, sin hijos distintos")
        c2.metric("🟡 Verificar (posibles hijos distintos)", dup_verif['nombre'].nunique() if not dup_verif.empty else 0)

        if not dup_prob.empty:
            st.markdown("#### 🔴 Duplicados probables — recomendado eliminar")
            st.caption("Misma madre, misma fecha. No se detectaron hijos distintos en el repeat group. Conserva el registro con más datos o el primero cronológicamente.")
            cols = [c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','detalle'] if c in dup_prob.columns]
            st.dataframe(dup_prob[cols], use_container_width=True, hide_index=True)

        if not dup_verif.empty:
            st.markdown("#### 🟡 Verificar antes de eliminar — posibles hijos distintos")
            st.caption("Misma madre, misma fecha, pero se detectaron nombres de hijos distintos en los submissions. NO eliminar sin revisar.")
            cols = [c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','detalle'] if c in dup_verif.columns]
            st.dataframe(dup_verif[cols], use_container_width=True, hide_index=True)


# ── TAB 6: OUTLIERS ────────────────────────────
with tab_out:
    st.subheader("📈 Valores Fuera de Rango")
    num_cols = {'peso':'Peso (kg)','talla':'Talla (m)','imc':'IMC','eg_sem':'Sem. gestación'}
    resumen_n = []
    for col, lbl in num_cols.items():
        if col in df.columns and df[col].notna().any():
            resumen_n.append({'Variable':lbl,'N':int(df[col].notna().sum()),
                              'Mín':round(float(df[col].min()),2),
                              'Mediana':round(float(df[col].median()),2),
                              'Máx':round(float(df[col].max()),2)})
    if resumen_n:
        st.dataframe(pd.DataFrame(resumen_n), use_container_width=True, hide_index=True)

    # Tallas auto-corregidas (ingresadas sin decimal)
    if not ninos.empty and 'talla_corregida' in ninos.columns:
        corr_talla = ninos[ninos['talla_corregida'] == True]
        if not corr_talla.empty:
            st.warning(f"⚠️ {len(corr_talla)} tallas de niños auto-corregidas (valor ingresado sin punto decimal, ej: 915 → 91.5 cm)")
            cols_ct = [c for c in ['¿Cuál es el nombre del niño/a?','fecha_dia','Municipio','peso_nino','talla_nino'] if c in corr_talla.columns]
            ct_show = corr_talla[cols_ct].copy()
            ct_show.columns = [c.replace('¿Cuál es el nombre del niño/a?','Nombre niño/a')
                                 .replace('fecha_dia','Fecha').replace('peso_nino','Peso (kg)')
                                 .replace('talla_nino','Talla corregida (cm)') for c in ct_show.columns]
            st.dataframe(ct_show, use_container_width=True, hide_index=True)

    st.markdown("**Niños con medidas fuera de rango (tras corrección)**")
    if not ninos.empty:
        mask_n = (
            (ninos['peso_nino'].notna() & ((ninos['peso_nino']<3)|(ninos['peso_nino']>35))) |
            (ninos['talla_nino'].notna() & ((ninos['talla_nino']<40)|(ninos['talla_nino']>130))) |
            (ninos['muac'].notna() & ((ninos['muac']<8)|(ninos['muac']>22)))
        )
        ninos_out = ninos[mask_n]
        if not ninos_out.empty:
            st.warning(f"{len(ninos_out)} niños con medidas fuera de rango")
            cols_n = [c for c in ['¿Cuál es el nombre del niño/a?','fecha_dia','encuestador','Municipio','peso_nino','talla_nino','muac'] if c in ninos_out.columns]
            st.dataframe(ninos_out[cols_n], use_container_width=True, hide_index=True)
        else:
            st.success("✅ Sin outliers en medidas de niños.")

    if f_out.empty:
        st.success("✅ Sin outliers en madres.")
    else:
        cols = [c for c in ['_id','nombre','fecha_dia','encuestador','flag'] if c in f_out.columns]
        st.dataframe(f_out[cols], use_container_width=True, hide_index=True)


# ── TAB 7: POR ENCUESTADORA ────────────────────
with tab_enc:
    st.subheader("👩‍💼 Equipos y Encuestadoras")

    # ── RESUMEN CONSOLIDADO POR EQUIPO ───────────────────────────────────────
    st.markdown("### 📊 Resumen por equipo")

    if not ninos.empty and 'encuestador' in ninos.columns and 'fecha_dia' in ninos.columns:
        # Mapa encuestador → equipo y zona
        _enc_equipo = DF_EQUIPOS[['Nombre','Equipo','Zona','Región']].drop_duplicates('Nombre').set_index('Nombre')

        # Tamizajes de niños por encuestador
        _ninos_enc = ninos.groupby('encuestador').agg(
            Tamizados=('encuestador','count'),
            Dias_campo=('fecha_dia', pd.Series.nunique)
        ).reset_index()
        _ninos_enc['Equipo']  = _ninos_enc['encuestador'].map(_enc_equipo['Equipo'])
        _ninos_enc['Región']  = _ninos_enc['encuestador'].map(_enc_equipo['Región'])
        _ninos_enc['Zona']    = _ninos_enc['encuestador'].map(_enc_equipo['Zona'])

        # Para días de campo por equipo: días ÚNICOS donde cualquier miembro del equipo trabajó
        _ninos_with_equipo = ninos.copy()
        _ninos_with_equipo['Equipo'] = _ninos_with_equipo['encuestador'].map(_enc_equipo['Equipo'])
        _dias_por_equipo = (
            _ninos_with_equipo.dropna(subset=['Equipo','fecha_dia'])
            .groupby('Equipo')['fecha_dia'].nunique()
            .reset_index(name='Días campo equipo')
        )

        # Agrupar por equipo (nivel detalle)
        _resumen_equipo = _ninos_enc.dropna(subset=['Equipo']).groupby(['Región','Equipo','Zona']).agg(
            Tamizados=('Tamizados','sum')
        ).reset_index()
        _resumen_equipo = _resumen_equipo.merge(_dias_por_equipo, on='Equipo', how='left')
        _resumen_equipo['Prom./día'] = (_resumen_equipo['Tamizados'] / _resumen_equipo['Días campo equipo']).round(1)

        # Días únicos con actividad (cualquier equipo) — para promedio global consistente
        _dias_globales = ninos['fecha_dia'].nunique() if 'fecha_dia' in ninos.columns else 1
        # Total tamizados = niños + maternas sin niños (igual que el dashboard principal)
        _ids_con_ninos_enc = set(ninos['_submission_id'].dropna()) if '_submission_id' in ninos.columns else set()
        _mat_sin_ninos = len(df[~df['_id'].isin(_ids_con_ninos_enc)]) if '_id' in df.columns else 0
        _total_global = len(ninos) + _mat_sin_ninos
        _prom_global  = _total_global / _dias_globales if _dias_globales > 0 else 0

        # KPIs rápidos
        _col1, _col2, _col3 = st.columns(3)
        _col1.metric("Total equipos activos", int((_resumen_equipo['Tamizados'] > 0).sum()))
        _col2.metric("Promedio tamizajes/día (global)", f"{_prom_global:.1f}",
                     help=f"({_total_global} tamizados ÷ {_dias_globales} días de campo únicos) — igual al dashboard principal")
        _col3.metric("Equipo más productivo", _resumen_equipo.loc[_resumen_equipo['Tamizados'].idxmax(), 'Equipo'] if not _resumen_equipo.empty else "—")

        # Tabla por equipo — solo avance, sin metas
        st.dataframe(
            _resumen_equipo[['Región','Equipo','Zona','Tamizados','Días campo equipo','Prom./día']]
            .sort_values('Tamizados', ascending=False),
            use_container_width=True, hide_index=True
        )
        # Para la gráfica mantenemos el mismo dataframe
        _resumen_eq_meta = _resumen_equipo.copy()

        # Gráfica: tamizados por equipo
        st.markdown("**📊 Tamizados por equipo**")
        _chart_eq_agg = _resumen_eq_meta.groupby('Equipo', as_index=False).agg(
            Tamizados=('Tamizados','sum')
        ).sort_values('Tamizados')
        _fig_eq = go.Figure(go.Bar(
            x=_chart_eq_agg['Equipo'].tolist(), y=_chart_eq_agg['Tamizados'].tolist(),
            marker_color='#4472C4', text=_chart_eq_agg['Tamizados'].tolist(), textposition='outside'
        ))
        _fig_eq.update_layout(margin=dict(t=40, b=60), height=360,
                               yaxis_title='Tamizados', xaxis_tickangle=-20, plot_bgcolor='white')
        st.plotly_chart(_fig_eq, use_container_width=True)

        # Gráfica: promedio diario por equipo
        st.markdown("**⚡ Promedio diario por equipo**")
        _chart_prom = _resumen_eq_meta.dropna(subset=['Prom./día']).set_index('Equipo')['Prom./día'].sort_values()
        _fig_prom = go.Figure(go.Bar(
            x=_chart_prom.index.tolist(), y=_chart_prom.values.tolist(),
            marker_color='#3498db',
            text=[f"{v:.1f}" for v in _chart_prom.values], textposition='outside'
        ))
        _fig_prom.update_layout(margin=dict(t=40, b=20), height=320, yaxis_title='Tamizajes/día')
        st.plotly_chart(_fig_prom, use_container_width=True)

        # Gráficas de avance diario por equipo (una por equipo)
        st.markdown("**📅 Avance diario por equipo**")
        if not ninos.empty and 'fecha_dia' in ninos.columns and 'encuestador' in ninos.columns:
            _ninos_eq = ninos.copy()
            # Normalizar fecha_dia a solo fecha (sin timestamp)
            _ninos_eq['fecha_dia'] = pd.to_datetime(_ninos_eq['fecha_dia'], errors='coerce').dt.date
            _ninos_eq['Equipo'] = _ninos_eq['encuestador'].map(_enc_equipo['Equipo'])

            # Filtro por semana
            if 'semana' in _ninos_eq.columns:
                _ninos_eq['semana_dt']  = pd.to_datetime(_ninos_eq['semana'].astype(str), errors='coerce')
                _ninos_eq['semana_str'] = _ninos_eq['semana_dt'].dt.strftime('Sem %d/%m/%Y')
                _ninos_eq['semana_str'] = _ninos_eq['semana_str'].fillna('Sin fecha')
                _sems_disp = ['Todas'] + sorted(
                    [s for s in _ninos_eq['semana_str'].unique() if s != 'Sin fecha']
                ) + (['Sin fecha'] if 'Sin fecha' in _ninos_eq['semana_str'].values else [])
                _sem_sel_eq = st.selectbox("Filtrar por semana", _sems_disp, key='sem_eq_diario')
                if _sem_sel_eq != 'Todas':
                    _ninos_eq = _ninos_eq[_ninos_eq['semana_str'] == _sem_sel_eq]

            _equipos_activos = sorted(_ninos_eq['Equipo'].dropna().unique())
            # 2 columnas
            _cols_eq = st.columns(2)
            for _i, _eq in enumerate(_equipos_activos):
                _subset = _ninos_eq[_ninos_eq['Equipo'] == _eq]
                _diario_eq = _subset.groupby('fecha_dia').size().reset_index(name='Tamizados')
                _diario_eq['fecha_dia'] = pd.to_datetime(_diario_eq['fecha_dia'], errors='coerce').dt.strftime('%d/%m')
                with _cols_eq[_i % 2]:
                    _fig_deq = go.Figure(go.Bar(
                        x=_diario_eq['fecha_dia'].tolist(),
                        y=_diario_eq['Tamizados'].tolist(),
                        marker_color='#4472C4',
                        text=_diario_eq['Tamizados'].tolist(),
                        textposition='outside',
                        textfont=dict(size=11)
                    ))
                    _fig_deq.update_layout(
                        title=dict(text=_eq, font=dict(size=13)),
                        margin=dict(t=40, b=50, l=30, r=10), height=280,
                        xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
                        yaxis=dict(showgrid=True, gridcolor='#e8e8e8', zeroline=False),
                        plot_bgcolor='white', showlegend=False
                    )
                    st.plotly_chart(_fig_deq, use_container_width=True)
    else:
        st.info("Sin datos suficientes para resumen por equipo.")

    st.markdown("---")

    _enc_eq_map = DF_EQUIPOS[['Nombre','Equipo','Zona','Región','Rol']].drop_duplicates('Nombre').set_index('Nombre')
    # Niños tamizados por encuestadora (sin doble conteo)
    _ids_con_n = set(ninos['_submission_id'].dropna()) if not ninos.empty and '_submission_id' in ninos.columns else set()

    # ── MÉTRICAS DE RENDIMIENTO ───────────────────────────────────────────────
    st.markdown("**Métricas de rendimiento por encuestadora**")
    metricas = stats_enc(df)
    metricas = metricas.merge(
        DF_EQUIPOS[['Nombre','Rol','Equipo','Zona','Región']],
        left_on='Encuestador/a', right_on='Nombre', how='left'
    ).drop(columns=['Nombre'], errors='ignore')
    col_orden = [c for c in ['Región','Equipo','Zona','Encuestador/a','Rol','Encuestas','Días campo',
                              'Dur. mediana (min)','% < 5 min','% > 90 min','Enc./día'] if c in metricas.columns]
    _met_sorted = metricas[col_orden].sort_values(['Región','Equipo'], na_position='last')
    # Fila de totales
    _met_tot = {c: '' for c in col_orden}
    _met_tot['Encuestador/a'] = '📊 TOTAL'
    if 'Encuestas' in col_orden:
        _met_tot['Encuestas'] = int(_met_sorted['Encuestas'].sum())
    if 'Días campo' in col_orden:
        _met_tot['Días campo'] = int(_met_sorted['Días campo'].sum())
    _met_sorted_display = pd.concat([_met_sorted, pd.DataFrame([_met_tot])], ignore_index=True)
    st.dataframe(_met_sorted_display, use_container_width=True, hide_index=True)

    # Gráfica: encuestas por encuestadora, coloreada por zona
    if 'Encuestador/a' in _met_sorted.columns and 'Encuestas' in _met_sorted.columns:
        _ZONA_COLORES = {
            'Usulután Este':       '#2ecc71',
            'San Miguel Centro':   '#e74c3c',
            'Santa Ana Centro':    '#f39c12',
            'Ahuachapán Centro':   '#9b59b6',
            'San Salvador Centro': '#3498db',
            'San Salvador Este':   '#1abc9c',
        }
        _chart_m_df = (_met_sorted.dropna(subset=['Encuestas'])
                       [['Encuestador/a','Encuestas','Zona']]
                       .sort_values('Encuestas'))
        _enc_colors = [_ZONA_COLORES.get(z, '#95a5a6') for z in _chart_m_df['Zona'].fillna('')]
        _fig_enc = go.Figure(go.Bar(
            x=_chart_m_df['Encuestador/a'].tolist(),
            y=_chart_m_df['Encuestas'].tolist(),
            marker_color=_enc_colors,
            text=_chart_m_df['Encuestas'].tolist(), textposition='outside',
            customdata=_chart_m_df['Zona'].fillna('Sin zona').tolist(),
            hovertemplate='<b>%{x}</b><br>Encuestas: %{y}<br>Zona: %{customdata}<extra></extra>'
        ))
        # Leyenda manual por zona
        for _zona, _color in _ZONA_COLORES.items():
            if _zona in _chart_m_df['Zona'].values:
                _fig_enc.add_trace(go.Bar(x=[None], y=[None], name=_zona, marker_color=_color))
        _fig_enc.update_layout(
            margin=dict(t=40, b=80), height=380, yaxis_title='Encuestas',
            xaxis_tickangle=-30, plot_bgcolor='white',
            yaxis=dict(showgrid=True, gridcolor='#e8e8e8'),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0)
        )
        st.plotly_chart(_fig_enc, use_container_width=True)

    enc_datos  = set(df['encuestador'].dropna().astype(str).unique())
    enc_plan   = set(DF_EQUIPOS['Nombre'].unique())
    sin_equipo = enc_datos - enc_plan
    if sin_equipo:
        st.warning(f"⚠️ Encuestadoras sin equipo asignado: {', '.join(sorted(sin_equipo))}")

    st.markdown("---")

    # ── BASE COMBINADA: niños + maternas sin niños ────────────────────────────
    # (sin doble conteo: las maternas con hijos ya están en ninos)
    _ids_con_n = set(ninos['_submission_id'].dropna()) if not ninos.empty and '_submission_id' in ninos.columns else set()
    _mat_sn = df[~df['_id'].isin(_ids_con_n)][['encuestador','fecha_dia','semana']].copy() if '_id' in df.columns else pd.DataFrame()
    _nin_cols = ninos[['encuestador','fecha_dia','semana']].copy() if not ninos.empty else pd.DataFrame()
    _todos_tam = pd.concat([_nin_cols, _mat_sn], ignore_index=True)
    # NO filtramos por encuestador.notna() para que el total cuadre con el dashboard

    # ── TOTAL POR ENCUESTADORA (todos los tamizajes) ──────────────────────────
    st.markdown("**Total tamizajes por encuestadora (niños + maternas)**")
    if not _todos_tam.empty:
        _ne_all = _todos_tam.groupby('encuestador').size().reset_index(name='Total tamizados').sort_values('Total tamizados', ascending=False)
        _ne_all_tot = pd.DataFrame([{'encuestador':'📊 TOTAL', 'Total tamizados': _ne_all['Total tamizados'].sum()}])
        st.dataframe(pd.concat([_ne_all, _ne_all_tot], ignore_index=True), use_container_width=True, hide_index=True)
        _ne_sorted = _ne_all.set_index('encuestador')['Total tamizados'].sort_values()
        _fig_ne = go.Figure(go.Bar(
            x=_ne_sorted.index.tolist(), y=_ne_sorted.values.tolist(),
            marker_color='#1abc9c',
            text=_ne_sorted.values.tolist(), textposition='outside'
        ))
        _fig_ne.update_layout(margin=dict(t=40, b=20), height=350, yaxis_title='Total tamizados')
        st.plotly_chart(_fig_ne, use_container_width=True)

    st.markdown("---")

    # ── ENCUESTAS POR DÍA Y ENCUESTADORA ─────────────────────────────────────
    st.markdown("**Tamizajes por día y encuestadora (todos)**")
    if not _todos_tam.empty:
        _todos_tam_dia = _todos_tam.copy()
        _todos_tam_dia['fecha_dia'] = _todos_tam_dia['fecha_dia'].fillna('Sin fecha')
        _pivot_dia = _todos_tam_dia.groupby(['fecha_dia','encuestador']).size().reset_index(name='n')
        _pivot_dia_w = _pivot_dia.pivot(index='fecha_dia', columns='encuestador', values='n').fillna(0).astype(int)
        # Ordenar fechas cronológicamente (Sin fecha al final)
        _idx_fechas = sorted([i for i in _pivot_dia_w.index if i != 'Sin fecha'])
        if 'Sin fecha' in _pivot_dia_w.index: _idx_fechas.append('Sin fecha')
        _pivot_dia_w = _pivot_dia_w.reindex(_idx_fechas)
        _pivot_dia_w['TOTAL'] = _pivot_dia_w.sum(axis=1)
        _pivot_dia_w.loc['📊 TOTAL'] = _pivot_dia_w.sum()
        st.dataframe(_pivot_dia_w, use_container_width=True)

    st.markdown("---")

    # ── POR SEMANA Y ENCUESTADORA (todos) ────────────────────────────────────
    st.markdown("**Tamizajes por semana y encuestadora (niños + maternas)**")
    if not _todos_tam.empty and 'semana' in _todos_tam.columns:
        # Semana como fecha real para ordenar correctamente
        _todos_tam['semana_dt']  = pd.to_datetime(_todos_tam['semana'].astype(str), errors='coerce')
        _todos_tam['semana_str'] = _todos_tam['semana_dt'].dt.strftime('Sem %d/%m')
        # Registros sin fecha válida → "Sin fecha" para no perderlos del total
        _todos_tam['semana_str'] = _todos_tam['semana_str'].fillna('Sin fecha')
        # Orden cronológico de semanas (Sin fecha al final)
        _sem_order = _todos_tam[_todos_tam['semana_str'] != 'Sin fecha'].groupby('semana_str')['semana_dt'].min().sort_values().index.tolist()
        if 'Sin fecha' in _todos_tam['semana_str'].values:
            _sem_order.append('Sin fecha')

        _pivot_ns = _todos_tam.groupby(['semana_str','encuestador']).size().reset_index(name='n')
        _pivot_ns_w = _pivot_ns.pivot(index='encuestador', columns='semana_str', values='n').fillna(0).astype(int)
        # Reordenar columnas cronológicamente
        _sem_cols_ord = [c for c in _sem_order if c in _pivot_ns_w.columns]
        _pivot_ns_w = _pivot_ns_w[_sem_cols_ord]
        _pivot_ns_w['Total'] = _pivot_ns_w.sum(axis=1)
        _pivot_ns_w = _pivot_ns_w.sort_values('Total', ascending=False)
        # Fila de totales por columna
        _pivot_ns_w.loc['📊 TOTAL'] = _pivot_ns_w.sum()
        st.dataframe(_pivot_ns_w, use_container_width=True)

        # Gráfica evolución semanal por equipo
        _todos_tam['Equipo'] = _todos_tam['encuestador'].map(_enc_eq_map['Equipo'])
        _pivot_eq = _todos_tam.dropna(subset=['Equipo']).groupby(['semana_str','Equipo']).size().reset_index(name='n')
        if not _pivot_eq.empty:
            _pivot_eq_w = _pivot_eq.pivot(index='semana_str', columns='Equipo', values='n').fillna(0)
            _pivot_eq_w = _pivot_eq_w.reindex([c for c in _sem_order if c in _pivot_eq_w.index])
            st.markdown("**Evolución semanal por equipo**")
            _fig_sem_eq = go.Figure()
            for _eq_col in _pivot_eq_w.columns:
                _vals = _pivot_eq_w[_eq_col].tolist()
                _fig_sem_eq.add_trace(go.Bar(
                    name=_eq_col,
                    x=_pivot_eq_w.index.tolist(),
                    y=_vals,
                    text=_vals, textposition='outside'
                ))
            _fig_sem_eq.update_layout(barmode='group', margin=dict(t=40, b=20), height=380, yaxis_title='Tamizados')
            st.plotly_chart(_fig_sem_eq, use_container_width=True)

    st.markdown("---")

    if not todos.empty and 'encuestador' in todos.columns:
        st.markdown("**Flags por encuestadora**")
        fe = todos.groupby(['encuestador','severidad']).size().unstack(fill_value=0).reset_index()
        fe['Total'] = fe.drop(columns='encuestador').sum(axis=1)
        st.dataframe(fe.sort_values('Total', ascending=False), use_container_width=True, hide_index=True)

    st.markdown("---")
    with st.expander("📋 Directorio de equipos"):
        st.dataframe(DF_EQUIPOS, use_container_width=True, hide_index=True)


# ── TAB 8: GEO / CORRECCIONES ─────────────────
with tab_geo_tab:
    st.subheader("📍 Geográfico y Correcciones")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Por municipio (corregido)**")
        mun_dist = df.groupby('Municipio').size().reset_index(name='Encuestas')
        st.dataframe(mun_dist.sort_values('Encuestas', ascending=False), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Por distrito**")
        dist_dist = df.groupby('distrito_nombre', dropna=True).size().reset_index(name='Encuestas')
        st.dataframe(dist_dist.sort_values('Encuestas', ascending=False), use_container_width=True, hide_index=True)

    st.markdown("**Por cantón**")
    cant_dist = df.groupby('canton_nombre', dropna=True).size().reset_index(name='Encuestas').sort_values('Encuestas', ascending=False)
    st.dataframe(cant_dist, use_container_width=True, hide_index=True)
    st.markdown("---")
    st.markdown("**Correcciones geográficas aplicadas**")
    if correcciones.empty:
        st.warning("No se encontró correcciones_geograficas.csv")
    else:
        ids_presentes = correcciones[correcciones['_id'].isin(df_raw['_id'])]
        st.success(f"{len(ids_presentes)} correcciones aplicadas a esta descarga")
        st.dataframe(ids_presentes[['_id','nombre_referencia','municipio_correcto','distrito_correcto',
                                     'canton_correcto','unidad_salud_correcta','nota']],
                     use_container_width=True, hide_index=True)
        st.markdown("**Para agregar una corrección:** abre `correcciones_geograficas.csv` en Excel, agrega una fila con el `_id` del submission y sube al repo.")


# ── TAB 10: EXPORTAR ───────────────────────────
with tab_export:
    st.subheader("📥 Exportar bases de datos")
    st.caption(
        "Base consolidada completa: **todas las variables** del formulario, v1 y v2 unificadas en una sola columna. "
        "Una fila por niño (si la entrevistada tiene varios niños se repite su info). "
        "Las personas sin niños aparecen con campos de niño vacíos. "
        "Correcciones de talla y geografía aplicadas. Columnas `hfc_*` con flags de calidad."
    )

    ids_corregidos = set(correcciones['_id'].tolist()) if not correcciones.empty and '_id' in correcciones.columns else set()

    # ─── helper: unifica col.1 → col para cualquier DataFrame ─────────────────
    def _unify_versions(frame: pd.DataFrame) -> pd.DataFrame:
        """Fusiona todas las columnas 'X.1' en su base 'X' (fillna) y las elimina."""
        frame = frame.copy()
        dot1 = [c for c in frame.columns if c.endswith('.1') and c[:-2] in frame.columns]
        for c in dot1:
            frame[c[:-2]] = frame[c[:-2]].fillna(frame[c])
        frame = frame.drop(columns=dot1, errors='ignore')
        # También manejar .2 si existiera
        dot2 = [c for c in frame.columns if c.endswith('.2') and c[:-2] in frame.columns]
        for c in dot2:
            frame[c[:-2]] = frame[c[:-2]].fillna(frame[c])
        frame = frame.drop(columns=dot2, errors='ignore')
        return frame

    # Columnas de sistema KoboToolbox que no aportan al análisis
    _KOBO_SYS = {
        'formhub/uuid','meta/instanceID','meta/deprecatedID',
        '_notes','_tags','_bamboo_dataset_id','_submitted_by',
        '_version_','_xform_id_string','_attachments',
        '__version__','_geolocation',
    }

    # ─── 1. Entrevistada: todas las variables unificadas + correcciones ─────────
    ent_all = _unify_versions(df_raw).copy() if not df_raw.empty else pd.DataFrame()

    if not ent_all.empty:
        # Quitar columnas de sistema (solo las que no tienen datos analíticos)
        ent_all = ent_all.drop(columns=[c for c in _KOBO_SYS if c in ent_all.columns], errors='ignore')

        # Corrección talla madre: > 3 m → dividir /100 (estaba en cm)
        _talla_col = 'Talla (mts)'
        if _talla_col in ent_all.columns:
            _t_raw = pd.to_numeric(ent_all[_talla_col], errors='coerce')
            ent_all[_talla_col]              = _t_raw.where(_t_raw <= 3, _t_raw / 100)
            ent_all['hfc_talla_madre_corregida'] = _t_raw > 3
        else:
            ent_all['hfc_talla_madre_corregida'] = False

        # Corrección geografía desde df procesado
        if '_id' in df.columns and '_id' in ent_all.columns:
            geo_cols = [c for c in ['distrito_nombre','canton_nombre','unidad_nombre'] if c in df.columns]
            if geo_cols:
                _geo = df.set_index('_id')[geo_cols]
                ent_all = ent_all.set_index('_id').join(_geo, how='left').reset_index()

        # Flag geo corregida
        if '_id' in ent_all.columns:
            ent_all['hfc_geo_corregida'] = ent_all['_id'].isin(ids_corregidos)

        # Flag duplicado
        if not f_dup.empty and '_id' in f_dup.columns and 'flag' in f_dup.columns and '_id' in ent_all.columns:
            _dup_map = f_dup.drop_duplicates('_id').set_index('_id')['flag']
            ent_all['hfc_duplicado'] = ent_all['_id'].map(_dup_map).fillna('')
        else:
            ent_all['hfc_duplicado'] = ''

    # ─── 2. Niños: todas las variables unificadas + correcciones ───────────────
    raw_ninos_all = pd.concat(
        [s for s in [df_ninos_raw, df_sec3_raw, df_adic_raw] if not s.empty], ignore_index=True
    ) if (not df_ninos_raw.empty or not df_sec3_raw.empty or not df_adic_raw.empty) else pd.DataFrame()

    ninos_all = pd.DataFrame()
    if not raw_ninos_all.empty:
        ninos_all = _unify_versions(raw_ninos_all)
        ninos_all = ninos_all.drop(columns=[c for c in _KOBO_SYS if c in ninos_all.columns], errors='ignore')

        # Corrección talla niño: > 200 cm → dividir /10 (probablemente en mm)
        _talla_n = '¿Cuál es la talla en cm del niño/a?'
        if _talla_n in ninos_all.columns:
            _tn_raw = pd.to_numeric(ninos_all[_talla_n], errors='coerce')
            ninos_all[_talla_n]                  = _tn_raw.where(_tn_raw <= 200, _tn_raw / 10)
            ninos_all['hfc_talla_nino_corregida'] = _tn_raw > 200
        else:
            ninos_all['hfc_talla_nino_corregida'] = False

        # Prefixear columnas del niño que colisionan con las de entrevistada
        # (excepto las de join y las hfc_)
        _JOIN_KEYS = {'_parent_index', '_submission__id', '_id', '_index', 'hfc_talla_nino_corregida'}
        if not ent_all.empty:
            _collision = {
                c: f'nino_{c}'
                for c in ninos_all.columns
                if c in ent_all.columns and c not in _JOIN_KEYS
            }
            ninos_all = ninos_all.rename(columns=_collision)

    # ─── 3. JOIN: entrevistada (left) ← niños (right) ─────────────────────────
    # Guardar lista de columnas del niño ANTES del merge para reordenar correctamente después
    _nino_col_names = set(ninos_all.columns) if not ninos_all.empty else set()
    _DROP_FROM_NINO = {'_parent_index', '_submission__id', '_ent_id', '_index', '_id'}

    consolidado = pd.DataFrame()
    if not ent_all.empty and not ninos_all.empty:
        # Resolver _parent_index → _id de entrevistada
        if '_index' in ent_all.columns and '_parent_index' in ninos_all.columns:
            _idx2id = ent_all.set_index('_index')['_id']
            ninos_all['_ent_id'] = ninos_all['_parent_index'].map(_idx2id)
            _join_on = '_ent_id'
        elif '_submission__id' in ninos_all.columns:
            ninos_all['_ent_id'] = ninos_all['_submission__id']
            _join_on = '_ent_id'
        else:
            _join_on = None

        if _join_on and '_id' in ent_all.columns:
            consolidado = ent_all.merge(
                ninos_all.drop(columns=['_parent_index','_submission__id'], errors='ignore'),
                left_on='_id', right_on=_join_on, how='left'
            ).drop(columns=[_join_on], errors='ignore')
        else:
            consolidado = ent_all.copy()
    elif not ent_all.empty:
        consolidado = ent_all.copy()

    # Reordenar: columnas clave de identificación → entrevistada → niño → hfc_
    # Usamos _nino_col_names (capturado antes del merge) para saber exactamente qué es del niño
    if not consolidado.empty:
        _hfc_cols  = [c for c in consolidado.columns if c.startswith('hfc_')]
        # Columnas que vinieron de ninos_all (excluir claves de join ya droppeadas)
        _nino_cols = [c for c in consolidado.columns
                      if c in _nino_col_names and c not in _DROP_FROM_NINO and not c.startswith('hfc_')]
        _ent_cols  = [c for c in consolidado.columns
                      if c not in _nino_cols and c not in _hfc_cols]

        # Columnas de niño: nombre primero, luego el resto
        _NINO_PRIORITY = ['¿Cuál es el nombre del niño/a?', 'Sexo', 'Fecha de nacimiento del niño a evaluar',
                          'edad_nino', '¿Cuál es el peso en Kg del niño/a?', '¿Cuál es la talla en cm del niño/a?',
                          'Medida del perímetro braquial en cm']
        _nino_first = [c for c in _NINO_PRIORITY if c in _nino_cols]
        _nino_rest  = [c for c in _nino_cols if c not in _nino_first]
        _nino_ordered = _nino_first + _nino_rest

        consolidado = consolidado[_ent_cols + _nino_ordered + _hfc_cols]

    st.markdown("---")

    # ─── 4. Descarga base consolidada ─────────────────────────────────────────
    st.markdown("### 📋 Base consolidada completa con limpieza HFC")
    st.caption(
        "Todas las variables del formulario · v1/v2 unificadas · correcciones de talla y geo aplicadas · "
        "columnas `hfc_*` al final con flags de calidad de datos."
    )
    if not consolidado.empty:
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.caption(f"{len(consolidado)} filas · {len(consolidado.columns)} columnas")
        c2.metric("Filas", len(consolidado))
        c3.metric("Columnas", len(consolidado.columns))

        buf_cons = io.BytesIO()
        consolidado.to_excel(buf_cons, index=False); buf_cons.seek(0)
        st.download_button(
            "⬇️ Base consolidada HFC (.xlsx)", buf_cons,
            "base_consolidada_hfc.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        with st.expander("👁️ Vista previa (primeras 10 filas)"):
            st.dataframe(consolidado.head(10), use_container_width=True, hide_index=True)
    else:
        st.warning("No hay datos para exportar.")

    st.markdown("---")

    # ── REPORTE DE FLAGS ──────────────────────────────────────────────────────
    st.markdown("### 🚦 Reporte de flags HFC")
    if not todos.empty:
        cols_f = [c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','distrito_nombre','flag','severidad'] if c in todos.columns]
        buf_flags = io.BytesIO()
        with pd.ExcelWriter(buf_flags, engine='openpyxl') as w:
            todos[cols_f].to_excel(w, sheet_name='Flags', index=False)
            stats_enc(df).to_excel(w, sheet_name='Por encuestadora', index=False)
        buf_flags.seek(0)
        st.download_button("⬇️ Reporte de flags (.xlsx)", buf_flags, "hfc_flags.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.success("✅ Sin flags — no hay reporte que exportar.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: REPORTE UNICEF
# ═══════════════════════════════════════════════════════════════════════════════
with tab_unicef:
    st.subheader("🇺🇳 Reporte UNICEF — Herramienta de Reportería")
    st.caption(
        "Tabla en el formato exacto de la Herramienta de Reportería de UNICEF. "
        "Selecciona el mes y descarga el Excel listo para enviar."
    )

    # ── Helpers de conteo ────────────────────────────────────────────────────
    DISTRITOS_UNICEF = [
        'Ahuachapán Centro','San Miguel Centro','San Salvador Centro',
        'San Salvador Este','Santa Ana Centro','Usulután Este',
    ]
    # La matriz usa "Usulatán Este" (con acento en U) — map inverso para mostrar
    DIST_LABEL = {d: d for d in DISTRITOS_UNICEF}
    DIST_LABEL['Usulután Este'] = 'Usulatán Este'

    AGE_GROUPS = ['0-5m','6-11m','12-23m','24-59m','5-9a','10-14a','15-17a','18-24a','25-59a','60+a']

    def _unicef_edad_adulto(row, ref=date.today()):
        e = row.get('edad_a', np.nan) if hasattr(row, 'get') else np.nan
        dob = row.get('dob_calc', pd.NaT) if hasattr(row, 'get') else pd.NaT
        if pd.isna(e) and pd.notna(dob):
            try: e = (ref - dob.date()).days / 365.25
            except: e = np.nan
        if pd.isna(e): return '25-59a'
        e = float(e)
        if e < 15: return '10-14a'
        elif e < 18: return '15-17a'
        elif e < 25: return '18-24a'
        elif e < 60: return '25-59a'
        else: return '60+a'

    def _unicef_edad_nino(dob, ref=date.today()):
        if pd.isna(dob): return 'desc'
        try:
            m = (ref - dob.date()).days / 30.44
        except: return 'desc'
        if m < 6: return '0-5m'
        elif m < 12: return '6-11m'
        elif m < 24: return '12-23m'
        elif m < 60: return '24-59m'
        elif m < 120: return '5-9a'
        elif m < 180: return '10-14a'
        elif m < 216: return '15-17a'
        else: return '25-59a'

    def _build_breakdown(df_main_sel, df_ninos_sel):
        """Devuelve dict {(grupo_edad, sexo): count}"""
        import re as _re
        bd = {}
        # Adultos
        if not df_main_sel.empty:
            edad_txt = df_main_sel.get('edad_txt', pd.Series(dtype=str)) if 'edad_txt' in df_main_sel.columns else pd.Series(dtype=str, index=df_main_sel.index)
            def _parse_e(s):
                m = _re.search(r'(\d+)\s*año', str(s)); return float(m.group(1)) if m else np.nan
            edad_a = edad_txt.apply(_parse_e)
            dob_col = df_main_sel.get('dob_calc', pd.Series(dtype=object)) if 'dob_calc' in df_main_sel.columns else pd.Series(dtype=object, index=df_main_sel.index)
            sexo_col = df_main_sel.get('sexo_std_u', pd.Series(dtype=str)) if 'sexo_std_u' in df_main_sel.columns else pd.Series(dtype=str, index=df_main_sel.index)
            for i in df_main_sel.index:
                g = _unicef_edad_adulto({'edad_a': edad_a.get(i, np.nan), 'dob_calc': dob_col.get(i, pd.NaT)})
                s = 'M' if 'masc' in str(sexo_col.get(i,'')).lower() else 'F'
                bd[(g,s)] = bd.get((g,s),0) + 1
        # Niños
        if not df_ninos_sel.empty:
            dob_n = pd.to_datetime(df_ninos_sel.get('Fecha de nacimiento del niño a evaluar', pd.Series(dtype=object)), errors='coerce') if 'Fecha de nacimiento del niño a evaluar' in df_ninos_sel.columns else pd.Series(dtype=object, index=df_ninos_sel.index)
            sexo_n = df_ninos_sel.get('Sexo', pd.Series(dtype=str, index=df_ninos_sel.index))
            for i in df_ninos_sel.index:
                g = _unicef_edad_nino(dob_n.get(i, pd.NaT))
                s = 'M' if 'masc' in str(sexo_n.get(i,'')).lower() else 'F'
                bd[(g,s)] = bd.get((g,s),0) + 1
        return bd

    # Enriquecer df con columnas auxiliares para este tab
    _df_u = df.copy() if not df.empty else pd.DataFrame()
    _ninos_u = ninos.copy() if not ninos.empty else pd.DataFrame()

    if not _df_u.empty:
        import re as _re2
        def _pe(s):
            m = _re2.search(r'(\d+)\s*año', str(s)); return float(m.group(1)) if m else np.nan
        _df_u['edad_txt'] = _df_u.get('edad_entrevistado', pd.Series(dtype=str, index=_df_u.index)) if 'edad_entrevistado' in _df_u.columns else pd.Series(dtype=str, index=_df_u.index)
        _df_u['edad_a']   = _df_u['edad_txt'].apply(_pe)
        _dob_raw = df_raw.get('Fecha de nacimiento de la persona entrevistada') if 'Fecha de nacimiento de la persona entrevistada' in df_raw.columns else None
        if _dob_raw is None:
            _dob_raw = df_raw.get('Fecha de nacimiento de la persona entrevistada.1') if 'Fecha de nacimiento de la persona entrevistada.1' in df_raw.columns else None
        if _dob_raw is not None and '_id' in df_raw.columns and '_id' in _df_u.columns:
            _dob_map = df_raw.set_index('_id')[_dob_raw.name] if hasattr(_dob_raw, 'name') else df_raw.set_index('_id').get('Fecha de nacimiento de la persona entrevistada')
            _df_u['dob_calc'] = pd.to_datetime(_df_u['_id'].map(_dob_map) if _dob_map is not None else pd.NaT, errors='coerce')
        else:
            _df_u['dob_calc'] = pd.NaT
        _df_u['sexo_std_u'] = _df_u.get('sexo', pd.Series(dtype=str, index=_df_u.index)).astype(str).str.lower()

    # ── Selector de mes ───────────────────────────────────────────────────────
    _meses_disp = sorted(_df_u['mes'].dropna().unique().tolist()) if not _df_u.empty and 'mes' in _df_u.columns else []
    if not _meses_disp:
        st.warning("No hay datos cargados.")
    else:
        _mes_sel = st.selectbox("Mes de reporte", _meses_disp, index=len(_meses_disp)-1, key='unicef_mes')

        with st.expander("🔍 Debug — valores en datos", expanded=False):
            st.write("**Meses disponibles:**", _meses_disp)
            st.write("**Mes seleccionado:**", _mes_sel)
            if not _df_u.empty:
                _dist_vals_m = _df_u['Municipio'].dropna().unique().tolist() if 'Municipio' in _df_u.columns else []
                st.write("**Municipio (maternas) — valores únicos:**", sorted(_dist_vals_m))
                st.write(f"**Total maternas en mes {_mes_sel}:**", len(_df_u[_df_u['mes'] == _mes_sel]) if 'mes' in _df_u.columns else 'n/a')
            if not _ninos_u.empty:
                _dist_vals_n = _ninos_u['Municipio'].dropna().unique().tolist() if 'Municipio' in _ninos_u.columns else []
                st.write("**Municipio (niños) — valores únicos:**", sorted(_dist_vals_n))
                st.write(f"**Total niños en mes {_mes_sel}:**", len(_ninos_u[_ninos_u['mes'] == _mes_sel]) if 'mes' in _ninos_u.columns else 'n/a')
            st.write("**DISTRITOS_UNICEF:**", DISTRITOS_UNICEF)

        INDICADORES = [
            ('TAM',  '# de personas tamizadas para detectar desnutrición aguda en los municipios priorizados.'),
            ('IYCF', '# de personas que se benefician de la orientación e información comunitaria sobre alimentación de lactantes y niñas/niños pequeños en situaciones de emergencia (IYCF-E).'),
            ('REF',  '# de personas referidas a primer nivel de atención para el tratamiento de desnutrición aguda.'),
            ('DESN', '# de personas con nutrición aguda identificadas'),
        ]

        # Construir tabla
        rows_tabla = []
        rows_export = []   # para el Excel descargable

        # Columna de distrito para filtrar — Municipio contiene "Ahuachapán Centro" etc.
        _dist_col_m = 'Municipio' if not _df_u.empty and 'Municipio' in _df_u.columns else 'distrito_nombre'
        _dist_col_n = 'Municipio' if not _ninos_u.empty and 'Municipio' in _ninos_u.columns else 'distrito_nombre'

        # IDs de entrevistadas que YA tienen niños registrados → no contar doble en TAM
        _ids_con_ninos = set()
        if not _ninos_u.empty:
            for _col_id in ['_submission_id', '_submission__id', '_parent_index']:
                if _col_id in _ninos_u.columns:
                    _ids_con_ninos = set(_ninos_u[_col_id].dropna().astype(int))
                    break

        for ind_key, ind_label in INDICADORES:
            for dist in DISTRITOS_UNICEF:
                if not _df_u.empty and 'mes' in _df_u.columns and _dist_col_m in _df_u.columns:
                    _mm = _df_u[(_df_u['mes'] == _mes_sel) & (_df_u[_dist_col_m] == dist)]
                else:
                    _mm = pd.DataFrame()
                if not _ninos_u.empty and 'mes' in _ninos_u.columns and _dist_col_n in _ninos_u.columns:
                    _mn = _ninos_u[(_ninos_u['mes'] == _mes_sel) & (_ninos_u[_dist_col_n] == dist)]
                else:
                    _mn = pd.DataFrame()

                if ind_key == 'TAM':
                    # Solo contar maternas SIN niños (las que tienen niños ya se cuentan a través de _mn)
                    _mm_sin_ninos = _mm[~_mm['_id'].isin(_ids_con_ninos)] if not _mm.empty and '_id' in _mm.columns and _ids_con_ninos else _mm
                    bd = _build_breakdown(_mm_sin_ninos, _mn)
                    total = sum(bd.values())   # consistente con el desglose por edad
                elif ind_key == 'IYCF':
                    # Solo consejería de niños
                    _SI = 'Sí|Si|1|True'
                    _col_cons_n = '¿Se le brindó consejería a niños y niñas?'
                    _mn_cons = pd.DataFrame()
                    if not _mn.empty and _col_cons_n in _mn.columns:
                        _mn_cons = _mn[_mn[_col_cons_n].astype(str).str.contains(_SI, case=False, na=False)]
                    bd = _build_breakdown(pd.DataFrame(), _mn_cons)
                    total = sum(bd.values())
                elif ind_key == 'REF':
                    # Niños: emaciado o emaciado severo en diagnóstico peso/talla
                    _COL_PT = '¿Cuál es el diagnóstico nutricional del peso y la talla?'
                    _EMAC_RE = 'emaciado|desnutrici|aguda severa|aguda moderada'
                    _nr = pd.DataFrame()
                    if not _mn.empty and _COL_PT in _mn.columns:
                        _nr = _mn[_mn[_COL_PT].astype(str).str.lower().str.contains(_EMAC_RE, na=False)]
                    # Maternas: embarazada/lactante con diagnóstico de desnutrición
                    _mr = pd.DataFrame()
                    if not _mm.empty:
                        _col_diag_m = next((c for c in _mm.columns
                                            if 'diagnós' in c.lower() or 'estado nutricional' in c.lower()), None)
                        _col_perfil = 'perfil' if 'perfil' in _mm.columns else None
                        if _col_diag_m and _col_perfil:
                            _mask_m = (
                                _mm[_col_diag_m].astype(str).str.lower().str.contains(_EMAC_RE, na=False) &
                                _mm[_col_perfil].astype(str).str.lower().str.contains('embaraz|lactant', na=False)
                            )
                            _mr = _mm[_mask_m]
                    bd = _build_breakdown(_mr, _nr)
                    total = sum(bd.values())
                elif ind_key == 'DESN':
                    # Desnutrición AGUDA: solo P/T (emaciado/emaciado severo) y MUAC
                    _DESN_RE = 'emaciado|desnutrici|aguda severa|aguda moderada'
                    _COL_PT_D  = '¿Cuál es el diagnóstico nutricional del peso y la talla?'
                    _COL_MUAC  = 'Diagnóstico nutricional según perímetro braquial'
                    _nd = pd.DataFrame()
                    if not _mn.empty:
                        _mask_d = pd.Series(False, index=_mn.index)
                        if _COL_PT_D in _mn.columns:
                            _mask_d |= _mn[_COL_PT_D].astype(str).str.lower().str.contains(_DESN_RE, na=False)
                        if _COL_MUAC in _mn.columns:
                            _mask_d |= _mn[_COL_MUAC].astype(str).str.lower().str.contains(_DESN_RE, na=False)
                        _nd = _mn[_mask_d]
                    bd = _build_breakdown(pd.DataFrame(), _nd)
                    total = sum(bd.values())
                else:
                    total, bd = 0, {}

                row = {
                    'Indicador': ind_label,
                    'Distrito':  DIST_LABEL.get(dist, dist),
                    'Total':     total,
                    'Nuevos':    total,
                }
                for g in AGE_GROUPS:
                    row[f'Niños {g}']  = bd.get((g,'M'), 0)
                    row[f'Niñas {g}']  = bd.get((g,'F'), 0)

                # Vista resumida para la tabla en pantalla
                rows_tabla.append({
                    'Indicador': ind_key,
                    'Distrito':  DIST_LABEL.get(dist, dist),
                    'Total':     total,
                    **{g: bd.get((g,'M'),0) + bd.get((g,'F'),0) for g in AGE_GROUPS},
                })
                rows_export.append(row)

        df_tabla = pd.DataFrame(rows_tabla)
        df_export = pd.DataFrame(rows_export)

        # ── Vista en pantalla: pivot por indicador ────────────────────────────
        for ind_key, ind_label in INDICADORES:
            st.markdown(f"**{ind_key} — {ind_label[:80]}{'…' if len(ind_label)>80 else ''}**")
            sub = df_tabla[df_tabla['Indicador']==ind_key].drop(columns='Indicador').set_index('Distrito')
            # Solo mostrar grupos con algún dato
            cols_con_datos = ['Total'] + [c for c in AGE_GROUPS if sub[c].sum() > 0]
            st.dataframe(sub[cols_con_datos], use_container_width=True)
            st.markdown("")

        # ── Descarga Excel en formato UNICEF ─────────────────────────────────
        st.markdown("---")
        st.markdown("### ⬇️ Descargar en formato Herramienta de Reportería UNICEF")

        _MATRIZ_PATH = str(_resolve('4. Matriz de Indicadores - FUSAL.xlsx'))
        _matriz_existe = os.path.isfile(_MATRIZ_PATH)

        if _matriz_existe:
            # Llenar la matriz original
            import shutil as _shutil
            from openpyxl import load_workbook as _load_wb

            _buf_matriz = io.BytesIO()
            with open(_MATRIZ_PATH, 'rb') as _f:
                _buf_matriz.write(_f.read())
            _buf_matriz.seek(0)

            _wb = _load_wb(_buf_matriz)
            _ws = _wb['Herramienta de Reportería']

            _COL_MAP = {
                ('0-5m','M'):8,  ('0-5m','F'):9,
                ('6-11m','M'):10,('6-11m','F'):11,
                ('12-23m','M'):12,('12-23m','F'):13,
                ('24-59m','M'):14,('24-59m','F'):15,
                ('5-9a','M'):16, ('5-9a','F'):17,
                ('10-14a','M'):18,('10-14a','F'):19,
                ('15-17a','M'):20,('15-17a','F'):21,
                ('18-24a','M'):22,('18-24a','F'):23,
                ('25-59a','M'):24,('25-59a','F'):25,
                ('60+a','M'):26, ('60+a','F'):27,
            }
            _DIST_INV = {v: k for k, v in DIST_LABEL.items()}
            _export_idx = {(r['Indicador'], r['Distrito']): r for r in rows_export}

            for _row in _ws.iter_rows(min_row=9, max_row=260):
                _ind = _row[2].value; _mes = str(_row[3].value) if _row[3].value else ''; _dist = _row[4].value
                if not _ind or not _mes or not _dist: continue
                if _mes != _mes_sel: continue
                if 'afirman' in str(_ind).lower() or 'mecanismo' in str(_ind).lower(): continue

                # buscar en export_idx por indicador label + distrito
                _key = None
                for (ik, idl) in INDICADORES:
                    if idl == _ind or (ik == 'TAM' and 'tamizad' in _ind.lower()) \
                       or (ik == 'IYCF' and 'orientación' in _ind.lower() and 'lactante' in _ind.lower()) \
                       or (ik == 'REF' and 'referid' in _ind.lower()) \
                       or (ik == 'DESN' and 'con nutrición aguda' in _ind.lower()):
                        _key = (idl, _dist)
                        break
                if _key not in _export_idx: continue

                _rec = _export_idx[_key]
                _row[5].value = _rec['Total']
                _row[6].value = _rec['Total']
                for _ci in range(8, 32): _row[_ci-1].value = 0
                for _g in AGE_GROUPS:
                    _row[_COL_MAP[(_g,'M')]-1].value = int(_rec.get(f'Niños {_g}', 0))
                    _row[_COL_MAP[(_g,'F')]-1].value = int(_rec.get(f'Niñas {_g}', 0))

            _out_buf = io.BytesIO()
            _wb.save(_out_buf)
            _out_buf.seek(0)
            st.download_button(
                f"⬇️ Herramienta de Reportería UNICEF — {_mes_sel} (.xlsx)",
                _out_buf,
                f"Reporte_UNICEF_FUSAL_{_mes_sel}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            # Si no hay matriz, descargar tabla simple
            _buf_simple = io.BytesIO()
            df_export.to_excel(_buf_simple, index=False)
            _buf_simple.seek(0)
            st.download_button(
                f"⬇️ Datos para reporte UNICEF — {_mes_sel} (.xlsx)",
                _buf_simple,
                f"Reporte_UNICEF_FUSAL_{_mes_sel}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.info("💡 Para generar el Excel en formato exacto de UNICEF, sube el archivo `4. Matriz de Indicadores - FUSAL.xlsx` al repositorio.")
