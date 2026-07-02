"""
High Frequency Check — Línea de Base UNICEF US / FUSAL
Corre con: streamlit run hfc_app.py
Todos los archivos auxiliares deben estar en la misma carpeta:
  correcciones_geograficas.csv | distritos.csv | cantones.csv | unidadesdesalud.csv
"""

import streamlit as st
import pandas as pd
import numpy as np
import io, os
from datetime import date, timedelta

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="HFC · UNICEF US / FUSAL", page_icon="🔍", layout="wide")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

META_TAMIZAJE   = 4_000
META_REFERIDOS  = 120
META_DESNUT     = 120
FECHA_LIMITE    = date(2026, 11, 15)

st.markdown("""
<style>
.flag-high   {background:#fee2e2;border-left:4px solid #ef4444;padding:6px 10px;border-radius:4px;margin:2px 0;font-size:13px;}
.flag-medium {background:#fef3c7;border-left:4px solid #f59e0b;padding:6px 10px;border-radius:4px;margin:2px 0;font-size:13px;}
.kpi {background:white;border-radius:10px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.08);border-top:4px solid #00aeef;}
.kpi-warn {border-top-color:#f59e0b !important;}
.kpi-ok   {border-top-color:#10b981 !important;}
.kpi-bad  {border-top-color:#ef4444 !important;}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CATÁLOGOS GEOGRÁFICOS
# ─────────────────────────────────────────────
@st.cache_data
def cargar_catalogos():
    def _load(fname, sep=';'):
        p = os.path.join(SCRIPT_DIR, fname)
        return pd.read_csv(p, sep=sep) if os.path.exists(p) else pd.DataFrame()

    distritos = _load('distritos.csv')
    cantones  = _load('cantones.csv')
    unidades  = _load('unidadesdesalud.csv')

    dist_map = distritos.set_index('adm3_pcode')['adm3_name'].to_dict()  if not distritos.empty else {}
    cant_map = cantones.set_index('adm4_pcode')['adm4_name'].to_dict()   if not cantones.empty  else {}
    us_map   = unidades.set_index('u_code')['u_name'].to_dict()          if not unidades.empty   else {}
    return dist_map, cant_map, us_map


@st.cache_data
def cargar_correcciones():
    p = os.path.join(SCRIPT_DIR, 'correcciones_geograficas.csv')
    return pd.read_csv(p, dtype={'_id': int}) if os.path.exists(p) else pd.DataFrame()


# ─────────────────────────────────────────────
# CARGA Y LIMPIEZA
# ─────────────────────────────────────────────
@st.cache_data
def cargar_raw(archivo):
    xl = pd.ExcelFile(archivo)
    main  = pd.read_excel(xl, sheet_name=0)
    ninos = pd.read_excel(xl, sheet_name='group_sr9jz33')      if 'group_sr9jz33'       in xl.sheet_names else pd.DataFrame()
    sec3  = pd.read_excel(xl, sheet_name='sec3_salud_nutricion') if 'sec3_salud_nutricion' in xl.sheet_names else pd.DataFrame()
    return main, ninos, sec3


def unificar(df, dist_map, cant_map, us_map):
    pares = {
        'nombre':       ('Nombre de la persona entrevistada',                    'Nombre de la persona entrevistada.1'),
        'fecha_ent':    ('Fecha de la entrevista',                               'Fecha de la entrevista.1'),
        'encuestador':  ('Encuestador',                                          'Encuestador.1'),
        'sexo':         ('Sexo',                                                 'Sexo.1'),
        'perfil':       ('Perfil de la persona entrevistada',                    'Perfil de la persona entrevistada.1'),
        'unidad_cod':   ('Unidad de Salud a la que pertenece/asiste su familia', 'Unidad de Salud a la que pertenece/asiste su familia.1'),
        'telefono':     ('Número de teléfono',                                   'Número de teléfono.1'),
        'sabe_leer':    ('¿Sabe leer y escribir?',                               '¿Sabe leer y escribir?.1'),
        'peso':         ('Peso (kg)',                                             'Peso (kg)'),
        'talla':        ('Talla (mts)',                                          'Talla (mts)'),
        'imc':          ('imc_embarazada',                                       'IMC'),
        'eg_sem':       ('Edad gestacional: Semanas',                            'Edad gestacional: Semanas.1'),
        'diag_nutri':   ('Diagnóstico nutricional',                              'Diagnóstico nutricional.1'),
        'referencia':   ('¿Se brindó referencia?',                               '¿Se brindó referencia?.1'),
        'consejeria':   ('¿Se le brindó consejería?',                            '¿Se le brindó consejería?.1'),
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

    # Numéricos
    df['talla'] = pd.to_numeric(df['talla'], errors='coerce')
    df.loc[df['talla'] > 3, 'talla'] /= 100
    for c in ['peso', 'imc', 'eg_sem']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    # Decodificar geografía
    df['distrito_cod'] = df['Distrito'].astype(str).where(df['Distrito'].notna())
    df['canton_cod']   = df['Cantón'].astype(str).where(df['Cantón'].notna())
    df['distrito_nombre'] = df['distrito_cod'].map(dist_map)
    df['canton_nombre']   = df['canton_cod'].map(cant_map)
    df['unidad_cod_int']  = pd.to_numeric(df['unidad_cod'], errors='coerce')
    df['unidad_nombre']   = df['unidad_cod_int'].map(us_map)

    return df


def aplicar_correcciones(df, corr):
    if corr.empty:
        return df, 0
    df = df.copy()
    # Asegurar columnas texto
    for col in ['Municipio', 'distrito_nombre', 'canton_nombre', 'unidad_nombre']:
        df[col] = df[col].astype(object)
    n = 0
    for _, row in corr.iterrows():
        mask = df['_id'] == row['_id']
        if mask.any():
            df.loc[mask, 'Municipio']         = row['municipio_correcto']
            df.loc[mask, 'distrito_nombre']   = row['distrito_correcto']
            df.loc[mask, 'canton_nombre']     = row['canton_correcto']
            df.loc[mask, 'unidad_nombre']     = row['unidad_salud_correcta']
            n += mask.sum()
    return df, n


def construir_ninos(df_ninos, df_sec3, df_main):
    """Une las dos hojas de niños y agrega fecha/encuestador/municipio del padre."""
    ref_cols = ['_id', 'fecha_dia', 'semana', 'mes', 'encuestador', 'Municipio', 'distrito_nombre', 'canton_nombre']
    ref = df_main[[c for c in ref_cols if c in df_main.columns]].copy()

    frames = []
    for sheet, id_col in [(df_ninos, '_submission__id'), (df_sec3, '_submission__id')]:
        if sheet.empty:
            continue
        s = sheet.copy()
        # edad: unificar columna
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
    return ninos


# ─────────────────────────────────────────────
# CHECKS HFC
# ─────────────────────────────────────────────
def check_duplicados(df):
    mask = df.duplicated(subset=['nombre', 'fecha_ent'], keep=False) & df['nombre'].notna()
    out = df[mask][['_id','nombre','fecha_dia','encuestador','Municipio']].copy()
    out['flag'] = '🔴 Posible duplicado (misma mamá + misma fecha — verificar si son hijos distintos)'
    out['severidad'] = 'Alta'
    return out

def check_duracion(df):
    rows = []
    dur = df['duracion_min']
    for cond, fn, sev in [
        (dur < 5,                   lambda x: f'🔴 Muy corta ({x:.1f} min)',           'Alta'),
        ((dur>90)&(dur<1000),       lambda x: f'🟡 Larga ({x:.1f} min > 90)',          'Media'),
        (dur >= 1000,               lambda x: f'🔴 Formulario no cerrado ({x/60:.0f}h)','Alta'),
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
        mask0 = df['imc']==0
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
        mask = df[col].isna()|(df[col].astype(str).str.strip()=='')
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
        'Encuestas':         g.size(),
        'Días campo':        g['fecha_dia'].nunique(),
        'Dur. mediana (min)':g['duracion_min'].median().round(1),
        '% < 5 min':        g['duracion_min'].apply(lambda x:(x<5).mean()*100).round(1),
        '% > 90 min':       g['duracion_min'].apply(lambda x:(x>90).mean()*100).round(1),
        'Enc./día':         (g.size()/g['fecha_dia'].nunique()).round(1),
    }).reset_index()
    s.columns = ['Encuestador/a','Encuestas','Días campo','Dur. mediana (min)','% < 5 min','% > 90 min','Enc./día']
    return s.sort_values('Encuestas', ascending=False)


# ─────────────────────────────────────────────
# PROYECCIÓN
# ─────────────────────────────────────────────
def calcular_proyeccion(actual, meta, tasa_dia, dias_sem, n_equipos, fecha_inicio=None):
    """
    Devuelve dict con fechas proyectadas para C1 y C3 bajo los parámetros dados.
    tasa_dia: tamizajes por día de campo por equipo
    dias_sem: días de campo por semana
    n_equipos: número de equipos paralelos
    """
    hoy = date.today()
    if fecha_inicio is None:
        fecha_inicio = hoy

    cap_dia_total = tasa_dia * n_equipos          # capacidad diaria total
    cap_sem       = cap_dia_total * dias_sem       # capacidad semanal

    restante_c1 = max(meta - actual, 0)
    dias_campo_necesarios = restante_c1 / cap_dia_total if cap_dia_total > 0 else float('inf')
    # Convertir días de campo a días calendario
    semanas_necesarias = dias_campo_necesarios / dias_sem if dias_sem > 0 else float('inf')
    dias_cal_c1 = semanas_necesarias * 7

    fecha_fin_c1 = fecha_inicio + timedelta(days=int(dias_cal_c1)) if dias_cal_c1 < 3650 else None

    # C2 virtual: se puede hacer en paralelo con C1 (asumimos mismo lapso que C1)
    # C3 campo: empieza después de C1, misma duración
    dias_cal_c3 = (meta / cap_dia_total) / dias_sem * 7 if cap_dia_total > 0 and dias_sem > 0 else float('inf')
    fecha_fin_c3 = fecha_fin_c1 + timedelta(days=int(dias_cal_c3)) if fecha_fin_c1 and dias_cal_c3 < 3650 else None

    cumple = fecha_fin_c3 is not None and fecha_fin_c3 <= FECHA_LIMITE

    return {
        'cap_dia':       cap_dia_total,
        'cap_sem':       cap_sem,
        'dias_c1':       round(dias_cal_c1),
        'fecha_fin_c1':  fecha_fin_c1,
        'dias_c3':       round(dias_cal_c3),
        'fecha_fin_c3':  fecha_fin_c3,
        'cumple':        cumple,
    }


# ─────────────────────────────────────────────
# INTERFAZ PRINCIPAL
# ─────────────────────────────────────────────
st.title("🔍 HFC · Línea de Base UNICEF US / FUSAL")
st.caption("El Salvador · Meta: 4,000 personas tamizadas · Cierre: 15 noviembre 2026")

dist_map, cant_map, us_map = cargar_catalogos()
correcciones = cargar_correcciones()

# ── SIDEBAR ──
with st.sidebar:
    st.header("📂 Datos")
    archivo = st.file_uploader("Export KoboToolbox (.xlsx)", type=['xlsx'])
    st.markdown("---")

    n_corr_total = len(correcciones)
    if n_corr_total:
        st.success(f"✅ {n_corr_total} correcciones geo cargadas")
    else:
        st.warning("⚠️ Sin correcciones_geograficas.csv")

    if archivo:
        df_raw, df_ninos_raw, df_sec3_raw = cargar_raw(archivo)
        df = unificar(df_raw.copy(), dist_map, cant_map, us_map)
        df, n_corr = aplicar_correcciones(df, correcciones)
        ninos = construir_ninos(df_ninos_raw, df_sec3_raw, df)

        st.markdown("**Filtros**")
        municipios = ['Todos'] + sorted(df['Municipio'].dropna().unique().tolist())
        sel_mun = st.selectbox("Municipio", municipios)

        distritos_disp = ['Todos'] + sorted(df['distrito_nombre'].dropna().unique().tolist())
        sel_dist = st.selectbox("Distrito", distritos_disp)

        cantones_disp = ['Todos'] + sorted(df['canton_nombre'].dropna().unique().tolist())
        sel_cant = st.selectbox("Cantón", cantones_disp)

        encuestadores = ['Todos'] + sorted(df['encuestador'].dropna().unique().tolist())
        sel_enc = st.selectbox("Encuestador/a", encuestadores)

        fechas = sorted(df['fecha_dia'].dropna().unique())
        if fechas:
            rango = st.date_input("Rango fechas", value=(fechas[0], fechas[-1]),
                                  min_value=fechas[0], max_value=fechas[-1])

        # Aplicar filtros
        mask = pd.Series(True, index=df.index)
        if sel_mun  != 'Todos': mask &= df['Municipio']        == sel_mun
        if sel_dist != 'Todos': mask &= df['distrito_nombre']  == sel_dist
        if sel_cant != 'Todos': mask &= df['canton_nombre']    == sel_cant
        if sel_enc  != 'Todos': mask &= df['encuestador']      == sel_enc
        if fechas and len(rango)==2:
            mask &= (df['fecha_dia'] >= rango[0]) & (df['fecha_dia'] <= rango[1])
        df = df[mask].copy()

        # Filtrar niños también
        if not ninos.empty and 'encuestador' in ninos.columns:
            n_mask = pd.Series(True, index=ninos.index)
            if sel_mun  != 'Todos' and 'Municipio'       in ninos.columns: n_mask &= ninos['Municipio']       == sel_mun
            if sel_dist != 'Todos' and 'distrito_nombre' in ninos.columns: n_mask &= ninos['distrito_nombre'] == sel_dist
            if sel_enc  != 'Todos' and 'encuestador'     in ninos.columns: n_mask &= ninos['encuestador']     == sel_enc
            ninos = ninos[n_mask].copy()

        st.markdown("---")
        st.metric("Entrevistas en vista", len(df))
        st.metric("Niños en vista", len(ninos))
        if n_corr: st.caption(f"📍 {n_corr} corregidos geo")

    st.markdown("---")
    st.caption("Coloca todos los CSV auxiliares junto a hfc_app.py")


if not archivo:
    st.info("👈 Sube el export de KoboToolbox para comenzar.")
    with st.expander("Archivos necesarios en la misma carpeta"):
        st.code("hfc_app.py\ncorrecciones_geograficas.csv\ndistritos.csv\ncantones.csv\nunidadesdesalud.csv")
    st.stop()


# Checks
f_dup  = check_duplicados(df)
f_dur  = check_duracion(df)
f_out  = check_outliers(df)
f_nul  = check_nulos(df)
f_geo  = check_geo(df)
todos  = pd.concat([f for f in [f_dup,f_dur,f_out,f_nul,f_geo] if not f.empty], ignore_index=True)

n_alta  = int((todos['severidad']=='Alta').sum())  if not todos.empty else 0
n_media = int((todos['severidad']=='Media').sum()) if not todos.empty else 0

# Datos para avance
total_ninos    = len(ninos)
total_personas = len(df)           # entrevistas (incluye madres/cuidadores)
# Personas tamizadas = niños + embarazadas + lactantes con datos
perfiles_tami  = ['Mujer embarazada','Madre lactante','Madre de niño/a menor a 5 años y mujer embarazada']
madres_tami    = df[df['perfil'].isin(perfiles_tami)] if 'perfil' in df.columns else pd.DataFrame()
total_tamizados = total_ninos + len(madres_tami)

pct_meta = total_tamizados / META_TAMIZAJE * 100
dias_restantes = (FECHA_LIMITE - date.today()).days

# Tasa actual
dias_campo = df['fecha_dia'].nunique()
tasa_actual = total_tamizados / dias_campo if dias_campo > 0 else 0


# ── TABS ──
tab_avance, tab_escenarios, tab_flags, tab_dur, tab_dups, tab_out, tab_enc, tab_geo_tab, tab_export = st.tabs([
    "📊 Avance General",
    "🎯 Proyección & Escenarios",
    "🚦 Flags HFC",
    "⏱️ Duración",
    "👥 Duplicados",
    "📈 Outliers",
    "👩‍💼 Por Encuestadora",
    "📍 Geo / Correcciones",
    "📥 Exportar",
])


# ══════════════════════════════════════════════
# TAB 1: AVANCE GENERAL
# ══════════════════════════════════════════════
with tab_avance:
    st.subheader("📊 Avance General del Proyecto")

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Personas tamizadas (C1)", f"{total_tamizados:,}", help="Niños + embarazadas + lactantes medidas")
    c2.metric("Meta", f"{META_TAMIZAJE:,}")
    c3.metric("Avance", f"{pct_meta:.1f}%")
    c4.metric("Días restantes", dias_restantes, help=f"Al {FECHA_LIMITE.strftime('%d/%m/%Y')}")
    c5.metric("Ritmo actual", f"{tasa_actual:.1f}/día campo")

    # Barra de progreso
    st.progress(min(pct_meta/100, 1.0))
    st.caption(f"**{total_tamizados:,}** de **{META_TAMIZAJE:,}** personas tamizadas — falta **{META_TAMIZAJE - total_tamizados:,}**")

    st.markdown("---")
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.markdown("**Niños tamizados por semana**")
        if not ninos.empty and 'semana' in ninos.columns:
            por_sem = ninos.groupby('semana').size().reset_index(name='Niños')
            por_sem['semana'] = por_sem['semana'].astype(str)
            st.bar_chart(por_sem.set_index('semana'))
        else:
            st.info("Sin datos de semana disponibles.")

    with col_der:
        st.markdown("**Niños tamizados por mes**")
        if not ninos.empty and 'mes' in ninos.columns:
            por_mes = ninos.groupby('mes').size().reset_index(name='Niños')
            st.bar_chart(por_mes.set_index('mes'))
        else:
            st.info("Sin datos de mes disponibles.")

    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Avance por municipio**")
        mun_ninos = ninos.groupby('Municipio').size().reset_index(name='Niños tamizados') if not ninos.empty else pd.DataFrame()
        if not mun_ninos.empty:
            mun_ninos['% de meta'] = (mun_ninos['Niños tamizados'] / META_TAMIZAJE * 100).round(1)
            st.dataframe(mun_ninos.sort_values('Niños tamizados', ascending=False),
                         use_container_width=True, hide_index=True)

    with col_b:
        st.markdown("**Otros indicadores del proyecto**")
        ind_data = {
            'Indicador':  ['Personas tamizadas (C1)', 'Personas referidas', 'Con desnutrición aguda'],
            'Meta':       [4000, 120, 120],
            'Actual':     [total_tamizados,
                           int(df['referencia'].str.contains('Sí', na=False).sum()) if 'referencia' in df.columns else 0,
                           0],
        }
        ind_df = pd.DataFrame(ind_data)
        ind_df['Avance %'] = (ind_df['Actual'] / ind_df['Meta'] * 100).round(1)
        st.dataframe(ind_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Progreso acumulado de niños tamizados**")
    if not ninos.empty and 'fecha_dia' in ninos.columns:
        cum = ninos.groupby('fecha_dia').size().reset_index(name='n')
        cum = cum.sort_values('fecha_dia')
        cum['acumulado'] = cum['n'].cumsum()
        st.line_chart(cum.set_index('fecha_dia')['acumulado'])


# ══════════════════════════════════════════════
# TAB 2: PROYECCIÓN & ESCENARIOS
# ══════════════════════════════════════════════
with tab_escenarios:
    st.subheader("🎯 Proyección a Meta — Modelo de 3 Contactos")

    st.markdown("""
    **Modelo de contactos:**
    - **Contacto 1 (C1)** 🏥 Tamizaje en campo — medición antropométrica (peso, talla, MUAC)
    - **Contacto 2 (C2)** 📱 Seguimiento virtual — llamada/WhatsApp para verificar evolución
    - **Contacto 3 (C3)** 🏥 Retamizaje en campo — segunda medición para evaluar cambios

    > Fecha límite: **15 noviembre 2026** · Meta: **4,000 personas** por cada contacto
    """)

    st.info(f"**Estado actual C1:** {total_tamizados:,} tamizados · {META_TAMIZAJE - total_tamizados:,} pendientes · {pct_meta:.1f}% completado · {dias_campo} días de campo realizados")

    st.markdown("---")
    st.markdown("### ⚙️ Ajusta los escenarios")

    # Escenario base (tasa actual)
    tasa_base = round(tasa_actual, 0) if tasa_actual > 0 else 20

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**🟡 Escenario Conservador**")
        tam_dia_A = st.slider("Tamizajes/día campo (A)", 10, 100, int(tasa_base), 5, key='A1')
        dias_sem_A = st.slider("Días campo/semana (A)",   1, 6,  3, 1,               key='A2')
        equipos_A  = st.slider("Equipos en campo (A)",    1, 5,  1, 1,               key='A3')
    with col2:
        st.markdown("**🟠 Escenario Moderado**")
        tam_dia_B = st.slider("Tamizajes/día campo (B)", 10, 100, int(tasa_base*1.5), 5, key='B1')
        dias_sem_B = st.slider("Días campo/semana (B)",   1, 6,  4,                    1, key='B2')
        equipos_B  = st.slider("Equipos en campo (B)",    1, 5,  2,                    1, key='B3')
    with col3:
        st.markdown("**🔴 Escenario Intensivo**")
        tam_dia_C = st.slider("Tamizajes/día campo (C)", 10, 100, int(tasa_base*2), 5, key='C1')
        dias_sem_C = st.slider("Días campo/semana (C)",   1, 6,  5,                  1, key='C2')
        equipos_C  = st.slider("Equipos en campo (C)",    1, 5,  3,                  1, key='C3')

    st.markdown("---")

    escenarios = {
        '🟡 Conservador': calcular_proyeccion(total_tamizados, META_TAMIZAJE, tam_dia_A, dias_sem_A, equipos_A),
        '🟠 Moderado':    calcular_proyeccion(total_tamizados, META_TAMIZAJE, tam_dia_B, dias_sem_B, equipos_B),
        '🔴 Intensivo':   calcular_proyeccion(total_tamizados, META_TAMIZAJE, tam_dia_C, dias_sem_C, equipos_C),
    }

    # Tabla comparativa
    filas = []
    for nombre, e in escenarios.items():
        filas.append({
            'Escenario':            nombre,
            'Cap. diaria total':    int(e['cap_dia']),
            'Cap. semanal':         int(e['cap_sem']),
            'Fin C1 (Tamizaje 1)':  e['fecha_fin_c1'].strftime('%d/%m/%Y') if e['fecha_fin_c1'] else '⚠️ No alcanza',
            'Fin C3 (Tamizaje 2)':  e['fecha_fin_c3'].strftime('%d/%m/%Y') if e['fecha_fin_c3'] else '⚠️ No alcanza',
            '✅ Cumple Nov 15':      '✅ Sí' if e['cumple'] else '❌ No',
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    st.markdown("---")

    # Detalle por escenario
    for nombre, e in escenarios.items():
        color = "#d1fae5" if e['cumple'] else "#fee2e2"
        icono = "✅" if e['cumple'] else "❌"
        st.markdown(f"""
        <div style="background:{color};border-radius:8px;padding:14px 18px;margin:8px 0;">
        <strong>{nombre}</strong> &nbsp;|&nbsp; {icono} {'Cumple deadline' if e['cumple'] else 'NO cumple deadline'}
        <br><small>
        📍 C1 termina: <b>{e['fecha_fin_c1'].strftime('%d %b %Y') if e['fecha_fin_c1'] else 'fuera de rango'}</b>
        &nbsp;·&nbsp;
        🏁 C3 termina: <b>{e['fecha_fin_c3'].strftime('%d %b %Y') if e['fecha_fin_c3'] else 'fuera de rango'}</b>
        &nbsp;·&nbsp;
        Capacidad: <b>{int(e['cap_dia'])} tamizajes/día · {int(e['cap_sem'])}/semana</b>
        </small></div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📅 Timeline de los 3 contactos")

    # Mostrar línea de tiempo para el escenario seleccionado
    sel_esc = st.selectbox("Escenario para el timeline", list(escenarios.keys()))
    e = escenarios[sel_esc]

    hoy = date.today()
    eventos = {
        'Hoy': hoy,
        'Fin C1 (Tamizaje 1)': e['fecha_fin_c1'],
        'C2 virtual (en paralelo con C1)': e['fecha_fin_c1'],  # se puede empezar desde primer tamizado
        'Inicio C3': e['fecha_fin_c1'],
        'Fin C3 (Tamizaje 2)': e['fecha_fin_c3'],
        'Deadline Nov 15': FECHA_LIMITE,
    }

    tl_rows = []
    for ev, fecha in eventos.items():
        if fecha:
            dias_desde_hoy = (fecha - hoy).days
            tl_rows.append({'Evento': ev, 'Fecha': fecha.strftime('%d/%m/%Y'),
                            'Días desde hoy': dias_desde_hoy})
    st.dataframe(pd.DataFrame(tl_rows), use_container_width=True, hide_index=True)

    st.markdown("""
    > **Nota sobre C2 (seguimiento virtual):** puede iniciarse desde los primeros tamizados de C1 en paralelo al trabajo de campo.
    > No requiere días de campo adicionales pero sí capacidad de equipo para llamadas/WhatsApp.
    """)

    # Necesidad de ritmo para cumplir
    if not escenarios['🟡 Conservador']['cumple']:
        dias_disp = dias_restantes
        # Días campo disponibles asumiendo X días/semana
        dias_campo_disp = dias_disp / 7 * dias_sem_A
        # Para completar C1 + C3 en los días disponibles
        tamizajes_totales_necesarios = META_TAMIZAJE - total_tamizados + META_TAMIZAJE  # C1 pendiente + C3 completo
        ritmo_necesario = tamizajes_totales_necesarios / (dias_campo_disp * equipos_A) if dias_campo_disp > 0 else float('inf')
        st.warning(f"⚠️ Para cumplir el deadline con {equipos_A} equipo(s) y {dias_sem_A} días/semana, se necesitan **{ritmo_necesario:.0f} tamizajes/día de campo**.")


# ══════════════════════════════════════════════
# TAB 3: FLAGS HFC
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
# TAB 4: DURACIÓN
# ══════════════════════════════════════════════
with tab_dur:
    st.subheader("⏱️ Duración de Entrevistas")
    dur = df['duracion_min'].dropna()
    dur_v = dur[dur < 1000]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Mediana", f"{dur_v.median():.1f} min")
    c2.metric("< 5 min", int((dur_v<5).sum()))
    c3.metric("> 90 min", int((dur_v>90).sum()))
    c4.metric("No cerrados (>1000 min)", int((dur>=1000).sum()))
    hist, edges = np.histogram(dur_v.clip(upper=120), bins=range(0,125,5))
    hdf = pd.DataFrame({'Rango': [f"{edges[i]}-{edges[i+1]}" for i in range(len(hist))], 'n': hist})
    st.bar_chart(hdf.set_index('Rango'))
    if not f_dur.empty:
        st.dataframe(f_dur[[c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','duracion_min','flag'] if c in f_dur.columns]],
                     use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# TAB 5: DUPLICADOS
# ══════════════════════════════════════════════
with tab_dups:
    st.subheader("👥 Posibles Duplicados")
    st.info("Recuerda: una misma mamá puede aparecer dos veces si tiene dos hijos y la encuestadora hizo submissions separadas. Verifica siempre el nombre del niño antes de eliminar.")
    if f_dup.empty:
        st.success("✅ Sin duplicados detectados.")
    else:
        st.dataframe(f_dup[[c for c in ['_id','nombre','fecha_dia','encuestador','Municipio'] if c in f_dup.columns]],
                     use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# TAB 6: OUTLIERS
# ══════════════════════════════════════════════
with tab_out:
    st.subheader("📈 Valores Fuera de Rango")
    num_cols = {'peso':'Peso (kg)','talla':'Talla (m)','imc':'IMC','eg_sem':'Sem. gestación'}
    resumen_n = []
    for col, lbl in num_cols.items():
        if col in df.columns and df[col].notna().any():
            resumen_n.append({'Variable':lbl,'N':int(df[col].notna().sum()),
                              'Mín':round(float(df[col].min()),2),'Mediana':round(float(df[col].median()),2),
                              'Máx':round(float(df[col].max()),2)})
    if resumen_n:
        st.dataframe(pd.DataFrame(resumen_n), use_container_width=True, hide_index=True)

    st.markdown("**Niños con outliers (peso/talla/MUAC)**")
    if not ninos.empty:
        ninos_out = ninos[
            ninos['peso_nino'].notna() & ((ninos['peso_nino']<3)|(ninos['peso_nino']>35)) |
            ninos['talla_nino'].notna() & ((ninos['talla_nino']<40)|(ninos['talla_nino']>130)) |
            ninos['muac'].notna() & ((ninos['muac']<8)|(ninos['muac']>22))
        ] if not ninos.empty else pd.DataFrame()
        if not ninos_out.empty:
            st.warning(f"{len(ninos_out)} niños con medidas fuera de rango")
            cols_n = [c for c in ['¿Cuál es el nombre del niño/a?','fecha_dia','encuestador','Municipio','peso_nino','talla_nino','muac'] if c in ninos_out.columns]
            st.dataframe(ninos_out[cols_n], use_container_width=True, hide_index=True)
        else:
            st.success("✅ Sin outliers en medidas de niños.")

    if f_out.empty:
        st.success("✅ Sin outliers en madres.")
    else:
        st.dataframe(f_out[[c for c in ['_id','nombre','fecha_dia','encuestador','flag'] if c in f_out.columns]],
                     use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# TAB 7: POR ENCUESTADORA
# ══════════════════════════════════════════════
with tab_enc:
    st.subheader("👩‍💼 Métricas por Encuestadora")
    st.dataframe(stats_enc(df), use_container_width=True, hide_index=True)
    st.markdown("---")
    st.markdown("**Niños tamizados por encuestadora**")
    if not ninos.empty and 'encuestador' in ninos.columns:
        ninos_enc = ninos.groupby('encuestador').size().reset_index(name='Niños tamizados').sort_values('Niños tamizados', ascending=False)
        st.dataframe(ninos_enc, use_container_width=True, hide_index=True)
    st.markdown("**Encuestas por día y encuestadora**")
    pivot = df.groupby(['fecha_dia','encuestador']).size().reset_index(name='n')
    if not pivot.empty:
        pivot_w = pivot.pivot(index='fecha_dia', columns='encuestador', values='n').fillna(0).astype(int)
        st.dataframe(pivot_w, use_container_width=True)
    if not todos.empty and 'encuestador' in todos.columns:
        st.markdown("**Flags por encuestadora**")
        fe = todos.groupby(['encuestador','severidad']).size().unstack(fill_value=0).reset_index()
        st.dataframe(fe, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# TAB 8: GEO / CORRECCIONES
# ══════════════════════════════════════════════
with tab_geo_tab:
    st.subheader("📍 Geográfico y Correcciones")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Distribución por municipio (corregida)**")
        mun_dist = df.groupby('Municipio').size().reset_index(name='Encuestas')
        st.dataframe(mun_dist, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Por distrito**")
        dist_dist = df.groupby('distrito_nombre', dropna=True).size().reset_index(name='Encuestas')
        st.dataframe(dist_dist, use_container_width=True, hide_index=True)

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
        st.dataframe(ids_presentes[['_id','nombre_referencia','municipio_correcto','distrito_correcto','canton_correcto','unidad_salud_correcta','nota']],
                     use_container_width=True, hide_index=True)
        st.markdown("**Para agregar una corrección:** abre `correcciones_geograficas.csv` en Excel y agrega una fila con el `_id` del submission.")


# ══════════════════════════════════════════════
# TAB 9: EXPORTAR
# ══════════════════════════════════════════════
with tab_export:
    st.subheader("📥 Exportar")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Base de entrevistas limpia (con correcciones)**")
        df_lim = df.sort_values('_id').drop_duplicates(subset=['nombre','fecha_ent'], keep='first')
        cols_exp = [c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','distrito_nombre',
                                 'canton_nombre','unidad_nombre','perfil','sexo','telefono','sabe_leer',
                                 'duracion_min','referencia'] if c in df_lim.columns]
        buf1 = io.BytesIO()
        df_lim[cols_exp].to_excel(buf1, index=False); buf1.seek(0)
        st.download_button("⬇️ Entrevistas limpias (.xlsx)", buf1, "entrevistas_limpio.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.metric("Registros", len(df_lim))

    with col2:
        st.markdown("**Base de niños tamizados**")
        if not ninos.empty:
            cols_n = [c for c in ['_submission_id','¿Cuál es el nombre del niño/a?','Sexo',
                                   'Fecha de nacimiento del niño a evaluar','edad_txt',
                                   'fecha_dia','encuestador','Municipio','distrito_nombre','canton_nombre',
                                   'peso_nino','talla_nino','muac',
                                   '¿Cuál es el diagnóstico nutricional de la talla y edad?',
                                   '¿Cuál es el diagnóstico nutricional de peso edad?',
                                   'Diagnóstico nutricional según perímetro braquial',
                                   '¿Se brindó referencia?'] if c in ninos.columns]
            buf2 = io.BytesIO()
            ninos[cols_n].to_excel(buf2, index=False); buf2.seek(0)
            st.download_button("⬇️ Niños tamizados (.xlsx)", buf2, "ninos_tamizados.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.metric("Niños", len(ninos))

    st.markdown("---")
    st.markdown("**Reporte de flags**")
    if not todos.empty:
        cols_f = [c for c in ['_id','nombre','fecha_dia','encuestador','Municipio','distrito_nombre','flag','severidad'] if c in todos.columns]
        buf3 = io.BytesIO()
        with pd.ExcelWriter(buf3, engine='openpyxl') as w:
            todos[cols_f].to_excel(w, sheet_name='Flags', index=False)
            stats_enc(df).to_excel(w, sheet_name='Por encuestadora', index=False)
        buf3.seek(0)
        st.download_button("⬇️ Reporte de flags (.xlsx)", buf3, "hfc_flags.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
