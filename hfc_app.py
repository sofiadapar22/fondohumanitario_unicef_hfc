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
    ("Oriente",     "Equipo 1 Usulután",          "Usulután Este",        "Helen Romero",      "Técnica Nutrición"),
    ("Oriente",     "Equipo 1 Usulután",          "Usulután Este",        "Fátima Gómez",      "Promotora"),
    ("Oriente",     "Equipo 2 San Miguel Centro",  "San Miguel Centro",    "Fátima Granados",   "Técnica Nutrición"),
    ("Oriente",     "Equipo 2 San Miguel Centro",  "San Miguel Centro",    "Dolores",           "Promotora"),
    ("Oriente",     "Equipo 3 Moncagua/San Miguel","San Miguel Centro",    "Maryori Hernández", "Técnica Nutrición"),
    ("Oriente",     "Equipo 3 Moncagua/San Miguel","San Miguel Centro",    "Yulissa Hernández", "Promotora"),
    ("Occidente",   "Equipo 1 Santa Ana Centro",   "Santa Ana Centro",     "Damaris González",  "Técnica Nutrición"),
    ("Occidente",   "Equipo 1 Santa Ana Centro",   "Santa Ana Centro",     "Norma Rivera",      "Promotora"),
    ("Occidente",   "Equipo 2 Ahuachapán",         "Ahuachapán Centro",    "Geraldina Arriola", "Promotora"),
    ("Occidente",   "Equipo 2 Ahuachapán",         "Ahuachapán Centro",    "Yeldi Marcelino",   "Técnica Nutrición"),
    ("San Salvador","Equipo SS Centro/Tonacatepeque","San Salvador Centro","Gaby Pino",          "Técnica Nutrición"),
    ("San Salvador","Equipo SS Centro/Tonacatepeque","San Salvador Centro","Brenda Nerios",      "Técnica Nutrición"),
    ("San Salvador","Equipo SS Centro/Tonacatepeque","San Salvador Este",  "Rosibel Henríquez", "Promotora"),
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
    return main, ninos, sec3


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


def construir_ninos(df_ninos, df_sec3, df_main):
    ref_cols = ['_id', 'fecha_dia', 'semana', 'mes', 'encuestador', 'Municipio', 'distrito_nombre', 'canton_nombre']
    ref = df_main[[c for c in ref_cols if c in df_main.columns]].copy()

    frames = []
    for sheet, id_col in [(df_ninos, '_submission__id'), (df_sec3, '_submission__id')]:
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
                     '¿Se brindó referencia?']
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

    return ninos


# ─────────────────────────────────────────────
# CHECKS HFC
# ─────────────────────────────────────────────
def check_duplicados(df, ninos=None):
    """
    Detecta duplicados y los clasifica:
    - 🔴 Duplicado probable: misma madre, misma fecha, sin hijos distintos detectados
    - 🟡 Posible distinto hijo: misma madre, misma fecha, pero los IDs tienen hijos distintos en el repeat group
    """
    mask = df.duplicated(subset=['nombre', 'fecha_ent'], keep=False) & df['nombre'].notna()
    cands = df[mask][['_id','nombre','fecha_ent','fecha_dia','encuestador','Municipio','peso','talla','imc']].copy()

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

        # Hijos de cada submission
        todos_hijos = [h for h in hijos_grupo if h]  # excluir sets vacíos

        if len(todos_hijos) >= 2:
            # Verificar si hay hijos distintos entre los IDs
            union_hijos = set().union(*todos_hijos)
            intersecc   = todos_hijos[0].intersection(*todos_hijos[1:]) if len(todos_hijos) > 1 else todos_hijos[0]
            hijos_distintos = union_hijos - intersecc

            if hijos_distintos:
                # Tienen hijos distintos → no eliminar
                tipo = '🟡 Distinto hijo (no eliminar)'
                sev  = 'Media'
                detalle = f"Hijos: {', '.join(sorted(union_hijos))}"
            else:
                # Mismos hijos o sin hijos → duplicado probable
                tipo = '🔴 Duplicado probable'
                sev  = 'Alta'
                detalle = f"Hijos: {', '.join(sorted(union_hijos)) or 'ninguno registrado'}"
        else:
            # Sin hijos en ninguno → duplicado probable
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

        df_raw, df_ninos_raw, df_sec3_raw = cargar_raw(archivo, mod_time)
        df = unificar(df_raw.copy(), dist_map, cant_map, us_map)
        df, n_corr = aplicar_correcciones(df, correcciones)
        ninos = construir_ninos(df_ninos_raw, df_sec3_raw, df)

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
todos  = pd.concat([f for f in [f_dup,f_dur,f_out,f_nul,f_geo] if not f.empty], ignore_index=True)

n_alta  = int((todos['severidad']=='Alta').sum())  if not todos.empty else 0
n_media = int((todos['severidad']=='Media').sum()) if not todos.empty else 0

# KPIs de avance
total_ninos   = len(ninos)
if 'perfil' in df.columns:
    # Deduplicar por nombre antes de contar maternas:
    # si una embarazada/lactante tiene 2 hijos y hay 2 submissions, solo se cuenta una vez.
    df_madres_unicas = df.dropna(subset=['nombre']).drop_duplicates(subset=['nombre'])
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
tab_avance, tab_escenarios, tab_indicadores, tab_flags, tab_dur, tab_dups, tab_out, tab_enc, tab_geo_tab, tab_export = st.tabs([
    "📊 Avance General",
    "🎯 Proyección & Escenarios",
    "🥗 Indicadores Nutricionales",
    "🚦 Flags HFC",
    "⏱️ Duración",
    "👥 Duplicados",
    "📈 Outliers",
    "👩‍💼 Por Encuestadora",
    "📍 Geo / Correcciones",
    "📥 Exportar",
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
        n_ref = int(df['referencia'].astype(str).str.contains('Sí|Si', case=False, na=False).sum()) if 'referencia' in df.columns else 0
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

    # Estructura de equipos
    st.markdown("**Estructura de equipos de campo**")
    st.dataframe(DF_EQUIPOS, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Métricas de rendimiento
    st.markdown("**Métricas de rendimiento por encuestadora**")
    metricas = stats_enc(df)

    # Cruzar con equipo/rol
    metricas = metricas.merge(
        DF_EQUIPOS[['Nombre','Rol','Equipo','Región']],
        left_on='Encuestador/a', right_on='Nombre', how='left'
    ).drop(columns=['Nombre'], errors='ignore')

    # Reordenar columnas
    col_orden = [c for c in ['Región','Equipo','Encuestador/a','Rol','Encuestas','Días campo',
                              'Dur. mediana (min)','% < 5 min','% > 90 min','Enc./día'] if c in metricas.columns]
    st.dataframe(metricas[col_orden].sort_values(['Región','Equipo'], na_position='last'),
                 use_container_width=True, hide_index=True)

    # Encuestadoras en datos que no están en el directorio de equipos
    enc_datos = set(df['encuestador'].dropna().astype(str).unique())
    enc_plan  = set(DF_EQUIPOS['Nombre'].unique())
    sin_equipo = enc_datos - enc_plan
    if sin_equipo:
        st.warning(f"⚠️ Encuestadoras en datos sin equipo asignado: {', '.join(sorted(sin_equipo))}")

    st.markdown("---")
    if not ninos.empty and 'encuestador' in ninos.columns:
        st.markdown("**Niños tamizados por encuestadora**")
        ne = ninos.groupby('encuestador').size().reset_index(name='Niños tamizados').sort_values('Niños tamizados', ascending=False)
        st.dataframe(ne, use_container_width=True, hide_index=True)

    st.markdown("**Encuestas por día y encuestadora**")
    pivot = df.groupby(['fecha_dia','encuestador']).size().reset_index(name='n')
    if not pivot.empty:
        pivot_w = pivot.pivot(index='fecha_dia', columns='encuestador', values='n').fillna(0).astype(int)
        st.dataframe(pivot_w, use_container_width=True)

    if not todos.empty and 'encuestador' in todos.columns:
        st.markdown("**Flags por encuestadora**")
        fe = todos.groupby(['encuestador','severidad']).size().unstack(fill_value=0).reset_index()
        st.dataframe(fe, use_container_width=True, hide_index=True)


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
        "Una sola hoja consolidada: cada fila es un **niño** con los datos de su entrevista al lado. "
        "Las personas sin niños (embarazadas, lactantes sin registro de niño) aparecen al final con campos de niño vacíos. "
        "Se agregan columnas `hfc_*` con los resultados de limpieza."
    )

    # ─── 1. Preparar columnas HFC desde df limpio ──────────────────────────────
    ids_corregidos = set(correcciones['_id'].tolist()) if not correcciones.empty and '_id' in correcciones.columns else set()

    hfc_lookup = pd.DataFrame(index=df['_id'] if '_id' in df.columns else [])
    if '_id' in df.columns:
        hfc_lookup = df.set_index('_id')[[c for c in [
            'nombre','encuestador','fecha_dia','Municipio','distrito_nombre','canton_nombre',
            'unidad_nombre','perfil','consejeria','referencia','duracion_min',
            'peso','talla','imc','eg_sem',
        ] if c in df.columns]].rename(columns={
            'nombre':           'hfc_nombre',
            'encuestador':      'hfc_encuestador',
            'fecha_dia':        'hfc_fecha_dia',
            'Municipio':        'hfc_municipio',
            'distrito_nombre':  'hfc_distrito',
            'canton_nombre':    'hfc_canton',
            'unidad_nombre':    'hfc_unidad_salud',
            'perfil':           'hfc_perfil',
            'consejeria':       'hfc_consejeria',
            'referencia':       'hfc_referencia',
            'duracion_min':     'hfc_duracion_min',
            'peso':             'hfc_peso_madre_kg',
            'talla':            'hfc_talla_madre_m',
            'imc':              'hfc_imc_madre',
            'eg_sem':           'hfc_eg_semanas',
        })
        hfc_lookup['hfc_geo_corregida'] = hfc_lookup.index.map(lambda x: x in ids_corregidos)
        # Flag talla madre corregida
        raw_talla_col = 'Talla (mts)'
        if raw_talla_col in df_raw.columns and '_id' in df_raw.columns:
            raw_t = df_raw.set_index('_id')[raw_talla_col]
            hfc_lookup['hfc_talla_madre_corregida'] = hfc_lookup.index.map(
                lambda x: bool(pd.notna(raw_t.get(x)) and float(raw_t.get(x) or 0) > 3)
            )
        # Flag duplicado
        if not f_dup.empty and '_id' in f_dup.columns and 'severidad' in f_dup.columns:
            dup_map = f_dup.drop_duplicates('_id').set_index('_id')['severidad']
            hfc_lookup['hfc_duplicado'] = hfc_lookup.index.map(dup_map).fillna('')
        else:
            hfc_lookup['hfc_duplicado'] = ''

    # ─── 2. Combinar hojas crudas de niños ────────────────────────────────────
    raw_ninos_all = pd.concat(
        [s for s in [df_ninos_raw, df_sec3_raw] if not s.empty], ignore_index=True
    ) if not df_ninos_raw.empty or not df_sec3_raw.empty else pd.DataFrame()

    # Agregar talla corregida desde ninos procesado
    if not raw_ninos_all.empty and not ninos.empty and len(raw_ninos_all) == len(ninos):
        raw_ninos_all['hfc_talla_nino_cm']       = ninos['talla_nino'].values
        raw_ninos_all['hfc_talla_nino_corregida'] = ninos['talla_corregida'].values if 'talla_corregida' in ninos.columns else False

    # ─── 3. JOIN: niños (raw) ← entrevista (raw + hfc) ───────────────────────
    # Clave: raw_ninos._parent_index → df_raw._index → df_raw._id → hfc_lookup
    if not raw_ninos_all.empty and '_parent_index' in raw_ninos_all.columns and '_index' in df_raw.columns:
        # Mapa _index → _id en df_raw
        idx_to_id = df_raw.set_index('_index')['_id'] if '_id' in df_raw.columns else pd.Series(dtype=int)
        raw_ninos_all['_entrevista_id'] = raw_ninos_all['_parent_index'].map(idx_to_id)

        # Join con df_raw completo (todas las cols originales de la entrevista)
        entrevista_export = df_raw.copy()
        entrevista_export = entrevista_export.join(hfc_lookup, on='_id', how='left')

        consolidado = raw_ninos_all.merge(
            entrevista_export,
            left_on='_entrevista_id', right_on='_id',
            how='left',
            suffixes=('_nino', '_entrevista')
        )

        # Añadir personas sin niños (embarazadas solas, lactantes sin registro de niño)
        ids_con_ninos = set(raw_ninos_all['_entrevista_id'].dropna().unique())
        sin_ninos = entrevista_export[~entrevista_export['_id'].isin(ids_con_ninos)].copy()
        consolidado = pd.concat([consolidado, sin_ninos], ignore_index=True)

    elif not raw_ninos_all.empty:
        # Fallback: solo niños con hfc cols pegadas por posición
        consolidado = raw_ninos_all.copy()
        consolidado = consolidado.join(hfc_lookup.reset_index(drop=True), how='left')
    else:
        # Solo entrevistas, sin niños
        consolidado = df_raw.copy().join(hfc_lookup, on='_id', how='left')

    # ─── 4. Botón de descarga ─────────────────────────────────────────────────
    st.markdown("### 📋 Base consolidada (niños + entrevista) con limpieza HFC")
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
        # Mostrar solo columnas hfc_* + identificadores para no saturar
        preview_cols = ['_id'] + [c for c in consolidado.columns if c.startswith('hfc_')]
        st.dataframe(consolidado[[c for c in preview_cols if c in consolidado.columns]].head(10),
                     use_container_width=True, hide_index=True)

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
