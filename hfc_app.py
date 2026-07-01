"""
High Frequency Check — Línea de Base UNICEF US
Corre con: streamlit run hfc_app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import io

# ─────────────────────────────────────────────
# Configuración general
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="HFC · Línea de Base UNICEF US",
    page_icon="🔍",
    layout="wide",
)

st.markdown("""
<style>
    .flag-high   { background:#fee2e2; border-left:4px solid #ef4444; padding:6px 10px; border-radius:4px; margin:2px 0; font-size:13px; }
    .flag-medium { background:#fef3c7; border-left:4px solid #f59e0b; padding:6px 10px; border-radius:4px; margin:2px 0; font-size:13px; }
    .flag-low    { background:#dbeafe; border-left:4px solid #3b82f6; padding:6px 10px; border-radius:4px; margin:2px 0; font-size:13px; }
    .metric-box  { background:white; border-radius:8px; padding:16px 20px; box-shadow:0 1px 3px rgba(0,0,0,0.08); }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Funciones de limpieza y checks
# ─────────────────────────────────────────────

@st.cache_data
def cargar_datos(archivo):
    df = pd.read_excel(archivo, sheet_name=0)
    return df


def unificar_columnas(df):
    """Fusiona columnas duplicadas de v1 y v2 del formulario KoboToolbox."""
    pares = {
        'nombre':        ('Nombre de la persona entrevistada', 'Nombre de la persona entrevistada.1'),
        'fecha':         ('Fecha de la entrevista',            'Fecha de la entrevista.1'),
        'encuestador':   ('Encuestador',                       'Encuestador.1'),
        'sexo':          ('Sexo',                              'Sexo.1'),
        'perfil':        ('Perfil de la persona entrevistada', 'Perfil de la persona entrevistada.1'),
        'unidad_salud':  ('Unidad de Salud a la que pertenece/asiste su familia',
                          'Unidad de Salud a la que pertenece/asiste su familia.1'),
        'telefono':      ('Número de teléfono',                'Número de teléfono.1'),
        'sabe_leer':     ('¿Sabe leer y escribir?',            '¿Sabe leer y escribir?.1'),
        'peso':          ('Peso (kg)',                          'Peso (kg)'),           # solo v1
        'talla':         ('Talla (mts)',                        'Talla (mts)'),         # solo v1
        'imc':           ('imc_embarazada',                    'IMC'),
        'eg_semanas':    ('Edad gestacional: Semanas',         'Edad gestacional: Semanas.1'),
        'diag_nutri':    ('Diagnóstico nutricional',           'Diagnóstico nutricional.1'),
        'control_pre':   ('¿Ha asistido o está en control prenatal?',
                          '¿Ha asistido o está en control prenatal?.1'),
        'consejeria':    ('¿Se le brindó consejería?',         '¿Se le brindó consejería?.1'),
        'referencia':    ('¿Se brindó referencia?',            '¿Se brindó referencia?.1'),
        'lactancia_act': ('¿Actualmente está amamantando a su bebé?',
                          '¿Actualmente está amamantando a su bebé?.1'),
    }

    for nuevo, (col1, col2) in pares.items():
        c1 = df[col1] if col1 in df.columns else pd.Series(dtype='object')
        c2 = df[col2] if col2 in df.columns else pd.Series(dtype='object')
        df[nuevo] = c1.fillna(c2)

    # Nombre limpio
    df['nombre'] = df['nombre'].astype(str).str.strip().str.title().replace('Nan', pd.NA)
    df['encuestador'] = df['encuestador'].astype(str).str.strip().replace('nan', pd.NA)

    # Fechas
    df['start'] = pd.to_datetime(df['start'], errors='coerce')
    df['end']   = pd.to_datetime(df['end'],   errors='coerce')
    df['fecha'] = pd.to_datetime(df['fecha'],  errors='coerce')
    df['fecha_dia'] = df['start'].dt.date

    # Duración en minutos
    df['duracion_min'] = (df['end'] - df['start']).dt.total_seconds() / 60

    # Talla: corregir si está en cm en lugar de metros
    if 'talla' in df.columns:
        df['talla'] = pd.to_numeric(df['talla'], errors='coerce')
        df.loc[df['talla'] > 3, 'talla'] = df.loc[df['talla'] > 3, 'talla'] / 100

    df['peso']       = pd.to_numeric(df['peso'],       errors='coerce')
    df['imc']        = pd.to_numeric(df['imc'],        errors='coerce')
    df['eg_semanas'] = pd.to_numeric(df['eg_semanas'], errors='coerce')

    return df


def check_duplicados(df):
    """Detecta registros duplicados por nombre + fecha."""
    mask = df.duplicated(subset=['nombre', 'fecha'], keep=False) & df['nombre'].notna()
    flagged = df[mask][['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio']].copy()
    flagged['flag'] = '🔴 Duplicado (mismo nombre + fecha)'
    flagged['severidad'] = 'Alta'
    return flagged


def check_duracion(df):
    """Flaggea entrevistas muy cortas (<5 min) o muy largas (>90 min, excluyendo formularios abiertos)."""
    flags = []

    # Cortas
    mask_corta = df['duracion_min'] < 5
    sub = df[mask_corta][['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio', 'duracion_min']].copy()
    sub['flag'] = sub['duracion_min'].apply(lambda x: f'🔴 Duración muy corta ({x:.1f} min < 5 min)')
    sub['severidad'] = 'Alta'
    flags.append(sub)

    # Largas (excluye outliers extremos >1000 min = formulario no cerrado)
    mask_larga = (df['duracion_min'] > 90) & (df['duracion_min'] < 1000)
    sub2 = df[mask_larga][['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio', 'duracion_min']].copy()
    sub2['flag'] = sub2['duracion_min'].apply(lambda x: f'🟡 Duración larga ({x:.1f} min > 90 min)')
    sub2['severidad'] = 'Media'
    flags.append(sub2)

    # Formulario no cerrado (>1000 min)
    mask_nc = df['duracion_min'] >= 1000
    sub3 = df[mask_nc][['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio', 'duracion_min']].copy()
    sub3['flag'] = sub3['duracion_min'].apply(lambda x: f'🔴 Formulario no cerrado ({x/60:.0f} horas)')
    sub3['severidad'] = 'Alta'
    flags.append(sub3)

    return pd.concat(flags, ignore_index=True) if flags else pd.DataFrame()


def check_outliers(df):
    """Detecta valores fuera de rango en variables numéricas clave."""
    flags = []

    rangos = {
        'peso':       (30, 120,  'Peso fuera de rango ({:.1f} kg)'),
        'talla':      (1.30, 2.00, 'Talla fuera de rango ({:.2f} m)'),
        'imc':        (10, 50,   'IMC fuera de rango ({:.1f})'),
        'eg_semanas': (4, 44,    'Semanas gestación fuera de rango ({:.0f} sem)'),
    }

    for col, (lo, hi, msg_tmpl) in rangos.items():
        if col not in df.columns:
            continue
        mask = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
        if mask.any():
            sub = df[mask][['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio', col]].copy()
            sub['flag'] = sub[col].apply(lambda x: f'🟡 {msg_tmpl.format(x)}')
            sub['severidad'] = 'Media'
            flags.append(sub.drop(columns=[col]))

    # IMC = 0 explícito (error de captura)
    if 'imc' in df.columns:
        mask0 = df['imc'] == 0
        if mask0.any():
            sub = df[mask0][['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio']].copy()
            sub['flag'] = '🔴 IMC = 0 (error de captura)'
            sub['severidad'] = 'Alta'
            flags.append(sub)

    return pd.concat(flags, ignore_index=True) if flags else pd.DataFrame()


def check_nulos_clave(df):
    """Registros con campos obligatorios vacíos."""
    flags = []
    campos = {
        'nombre':      'Nombre del entrevistado',
        'encuestador': 'Encuestador',
        'fecha':       'Fecha de entrevista',
        'Municipio':   'Municipio',
        'perfil':      'Perfil del entrevistado',
    }
    for col, etiqueta in campos.items():
        if col not in df.columns:
            continue
        mask = df[col].isna() | (df[col].astype(str).str.strip() == '')
        if mask.any():
            sub = df[mask][['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio']].copy()
            sub['flag'] = f'🟡 Campo vacío: {etiqueta}'
            sub['severidad'] = 'Media'
            flags.append(sub)

    return pd.concat(flags, ignore_index=True) if flags else pd.DataFrame()


def check_productividad(df):
    """Calcula métricas de calidad y productividad por encuestadora."""
    grp = df.groupby('encuestador', dropna=True)
    stats = pd.DataFrame({
        'encuestas':       grp.size(),
        'dias_campo':      grp['fecha_dia'].nunique(),
        'dur_mediana_min': grp['duracion_min'].median().round(1),
        'dur_min_min':     grp['duracion_min'].min().round(1),
        'pct_cortas':      grp['duracion_min'].apply(lambda g: (g < 5).mean() * 100).round(1),
        'pct_largas':      grp['duracion_min'].apply(lambda g: (g > 90).mean() * 100).round(1),
        'enc_por_dia':     (grp.size() / grp['fecha_dia'].nunique()).round(1),
    }).reset_index()

    stats.columns = ['Encuestador/a', 'Encuestas', 'Días campo',
                     'Duración mediana (min)', 'Duración mínima (min)',
                     '% entrevistas cortas (<5min)', '% entrevistas largas (>90min)',
                     'Encuestas/día']
    return stats.sort_values('Encuestas', ascending=False)


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────

st.title("🔍 High Frequency Check")
st.caption("Línea de Base · UNICEF US · El Salvador")

# Sidebar
with st.sidebar:
    st.header("📂 Datos")
    archivo = st.file_uploader(
        "Sube el export de KoboToolbox (.xlsx)",
        type=["xlsx"],
        help="Descarga el export con etiquetas desde KoboToolbox y súbelo aquí"
    )

    st.markdown("---")
    st.markdown("**Filtros**")

    if archivo:
        df_raw = cargar_datos(archivo)
        df = unificar_columnas(df_raw.copy())

        municipios = ['Todos'] + sorted(df['Municipio'].dropna().unique().tolist())
        sel_mun = st.selectbox("Municipio", municipios)

        encuestadores = ['Todos'] + sorted(df['encuestador'].dropna().unique().tolist())
        sel_enc = st.selectbox("Encuestador/a", encuestadores)

        fechas = sorted(df['fecha_dia'].dropna().unique())
        if fechas:
            rango = st.date_input("Rango de fechas",
                                  value=(fechas[0], fechas[-1]),
                                  min_value=fechas[0],
                                  max_value=fechas[-1])

        # Aplicar filtros
        mask = pd.Series(True, index=df.index)
        if sel_mun != 'Todos':
            mask &= df['Municipio'] == sel_mun
        if sel_enc != 'Todos':
            mask &= df['encuestador'] == sel_enc
        if fechas and len(rango) == 2:
            mask &= (df['fecha_dia'] >= rango[0]) & (df['fecha_dia'] <= rango[1])
        df = df[mask].copy()

        st.markdown("---")
        st.metric("Registros en vista", len(df))

    st.markdown("---")
    st.caption("Actualiza subiendo un nuevo export de KoboToolbox")


# ─────────────────────────────────────────────
# Contenido principal
# ─────────────────────────────────────────────

if not archivo:
    st.info("👈 Sube el export de KoboToolbox para comenzar el análisis.")
    st.markdown("""
    **¿Cómo descargar el export de KoboToolbox?**
    1. Entra a tu proyecto en KoboToolbox
    2. Ve a **Descargas** (Downloads)
    3. Selecciona **Excel** y activa **Usar etiquetas en lugar de nombres XML**
    4. Descarga y súbelo aquí
    """)
    st.stop()


# Correr todos los checks
flags_dup  = check_duplicados(df)
flags_dur  = check_duracion(df)
flags_out  = check_outliers(df)
flags_nul  = check_nulos_clave(df)
stats_enc  = check_productividad(df)

# Consolidar todos los flags
todos_flags = pd.concat(
    [f for f in [flags_dup, flags_dur, flags_out, flags_nul] if not f.empty],
    ignore_index=True
)

n_alta   = (todos_flags['severidad'] == 'Alta').sum()   if not todos_flags.empty else 0
n_media  = (todos_flags['severidad'] == 'Media').sum()  if not todos_flags.empty else 0
n_total  = len(todos_flags)


# ── KPIs de calidad ──
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total encuestas", len(df))
c2.metric("🔴 Flags críticos",  n_alta,  delta=None)
c3.metric("🟡 Flags medios",   n_media, delta=None)
c4.metric("Registros con flag", todos_flags['_id'].nunique() if not todos_flags.empty else 0)
c5.metric("% con algún flag",
          f"{todos_flags['_id'].nunique() / len(df) * 100:.1f}%" if len(df) > 0 else "—")

st.markdown("---")


# ── Tabs ──
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🚦 Resumen flags",
    "⏱️ Duración",
    "👥 Duplicados",
    "📊 Outliers",
    "👩‍💼 Por encuestadora",
    "📥 Exportar"
])


# ─── Tab 1: Resumen ───
with tab1:
    if todos_flags.empty:
        st.success("✅ No se encontraron problemas en los datos.")
    else:
        st.subheader(f"{n_total} flags encontrados en {todos_flags['_id'].nunique()} registros")

        # Resumen por tipo de flag
        resumen = todos_flags.groupby(['flag', 'severidad']).size().reset_index(name='n')
        resumen = resumen.sort_values(['severidad', 'n'], ascending=[True, False])

        for _, row in resumen.iterrows():
            cls = 'flag-high' if row['severidad'] == 'Alta' else 'flag-medium'
            st.markdown(
                f'<div class="{cls}"><strong>{row["flag"]}</strong> — {row["n"]} registro(s)</div>',
                unsafe_allow_html=True
            )

        st.markdown("---")
        st.subheader("Detalle completo")
        cols_show = [c for c in ['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio', 'flag', 'severidad'] if c in todos_flags.columns]
        st.dataframe(todos_flags[cols_show].sort_values('severidad'), use_container_width=True, hide_index=True)


# ─── Tab 2: Duración ───
with tab2:
    st.subheader("⏱️ Duración de entrevistas")

    dur = df['duracion_min'].dropna()
    dur_valida = dur[dur < 1000]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mediana", f"{dur_valida.median():.1f} min")
    c2.metric("< 5 min (crítico)", int((dur_valida < 5).sum()))
    c3.metric("> 90 min", int((dur_valida > 90).sum()))
    c4.metric("Formulario no cerrado (>1000 min)", int((dur >= 1000).sum()))

    # Histograma con bins
    st.markdown("**Distribución de duración (excluye >1000 min)**")
    bins = list(range(0, 100, 5)) + [200]
    hist, edges = np.histogram(dur_valida.clip(upper=120), bins=range(0, 125, 5))

    hist_df = pd.DataFrame({
        'Rango (min)': [f"{edges[i]}-{edges[i+1]}" for i in range(len(hist))],
        'Encuestas': hist
    })
    st.bar_chart(hist_df.set_index('Rango (min)'))

    if not flags_dur.empty:
        st.markdown("**Registros con flags de duración**")
        cols_show = [c for c in ['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio', 'duracion_min', 'flag'] if c in flags_dur.columns]
        st.dataframe(flags_dur[cols_show], use_container_width=True, hide_index=True)


# ─── Tab 3: Duplicados ───
with tab3:
    st.subheader("👥 Duplicados")

    if flags_dup.empty:
        st.success("✅ No se detectaron duplicados.")
    else:
        st.warning(f"Se encontraron **{len(flags_dup)} registros** con el mismo nombre y fecha.")
        cols_show = [c for c in ['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio'] if c in flags_dup.columns]
        st.dataframe(flags_dup[cols_show], use_container_width=True, hide_index=True)
        st.caption("💡 Conserva el registro con el _id menor y elimina el resto.")


# ─── Tab 4: Outliers ───
with tab4:
    st.subheader("📊 Valores fuera de rango")

    # Mostrar resumen de variables numéricas disponibles
    num_cols = {'peso': 'Peso (kg)', 'talla': 'Talla (m)', 'imc': 'IMC', 'eg_semanas': 'Semanas gestación'}
    resumen_num = []
    for col, label in num_cols.items():
        if col in df.columns and df[col].notna().any():
            resumen_num.append({
                'Variable': label,
                'N con dato': int(df[col].notna().sum()),
                'Mínimo': round(float(df[col].min()), 2),
                'Mediana': round(float(df[col].median()), 2),
                'Máximo': round(float(df[col].max()), 2),
            })

    if resumen_num:
        st.dataframe(pd.DataFrame(resumen_num), use_container_width=True, hide_index=True)

    if flags_out.empty:
        st.success("✅ No se detectaron outliers en variables numéricas.")
    else:
        st.warning(f"**{len(flags_out)} registros** con valores fuera de rango.")
        cols_show = [c for c in ['_id', 'nombre', 'fecha_dia', 'encuestador', 'Municipio', 'flag'] if c in flags_out.columns]
        st.dataframe(flags_out[cols_show], use_container_width=True, hide_index=True)


# ─── Tab 5: Por encuestadora ───
with tab5:
    st.subheader("👩‍💼 Métricas por encuestadora")
    st.dataframe(stats_enc, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Encuestas por día y encuestadora**")

    pivot = df.groupby(['fecha_dia', 'encuestador']).size().reset_index(name='n')
    pivot_wide = pivot.pivot(index='fecha_dia', columns='encuestador', values='n').fillna(0).astype(int)
    st.dataframe(pivot_wide, use_container_width=True)

    # Flags críticos por encuestadora
    if not todos_flags.empty:
        st.markdown("**Flags por encuestadora**")
        flags_enc = todos_flags.groupby(['encuestador', 'severidad']).size().unstack(fill_value=0).reset_index()
        st.dataframe(flags_enc, use_container_width=True, hide_index=True)


# ─── Tab 6: Exportar ───
with tab6:
    st.subheader("📥 Exportar registros con flags")

    if todos_flags.empty:
        st.success("No hay flags que exportar.")
    else:
        # Merge con datos originales
        cols_orig = [c for c in ['_id', 'nombre', 'fecha', 'encuestador', 'Municipio',
                                  'distrito_label', 'canton_label', 'perfil', 'duracion_min'] if c in df.columns]
        df_exp = todos_flags[['_id', 'flag', 'severidad']].merge(
            df[cols_orig], on='_id', how='left'
        )

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df_exp.to_excel(writer, sheet_name='Flags', index=False)
            todos_flags.to_excel(writer, sheet_name='Detalle flags', index=False)
            stats_enc.to_excel(writer, sheet_name='Por encuestadora', index=False)
        buf.seek(0)

        st.download_button(
            label="⬇️ Descargar reporte de flags (.xlsx)",
            data=buf,
            file_name="hfc_flags.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown(f"El archivo incluye **{len(df_exp)} flags** en {df_exp['_id'].nunique()} registros únicos.")

    st.markdown("---")
    st.subheader("📋 Base limpia (sin duplicados)")
    st.caption("Se eliminan duplicados por nombre + fecha, conservando el registro con menor _id.")

    df_limpio = df.sort_values('_id').drop_duplicates(subset=['nombre', 'fecha'], keep='first')
    cols_limpio = [c for c in ['_id', 'nombre', 'fecha', 'encuestador', 'Municipio',
                                'distrito_label', 'canton_label', 'perfil', 'sexo',
                                'unidad_salud', 'telefono', 'sabe_leer', 'duracion_min'] if c in df_limpio.columns]

    buf2 = io.BytesIO()
    df_limpio[cols_limpio].to_excel(buf2, index=False)
    buf2.seek(0)

    st.download_button(
        label="⬇️ Descargar base limpia (.xlsx)",
        data=buf2,
        file_name="encuestas_limpio.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.metric("Registros en base limpia", len(df_limpio))
