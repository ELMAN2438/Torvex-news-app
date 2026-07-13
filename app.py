import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

st.set_page_config(
    page_title="Robot de noticias Forex",
    page_icon=":material/monitoring:",
    layout="wide",
)

DATA_FILE = Path(__file__).parent / "eventos.json"
MONEDAS = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY", "Otra"]
IMPACTOS = ["Alto", "Medio", "Bajo", "Feriado"]
IMPACT_COLOR = {"Alto": "#e05252", "Medio": "#d99a3d", "Bajo": "#8a8f98", "Feriado": "#5b8def"}


def cargar_eventos():
    if DATA_FILE.exists():
        df = pd.read_json(DATA_FILE, orient="records")
        df["Fecha y hora"] = pd.to_datetime(df["Fecha y hora"])
        return df

    return pd.DataFrame({
        "Moneda": pd.Series(dtype="string"),
        "Evento": pd.Series(dtype="string"),
        "Fecha y hora": pd.Series(dtype="datetime64[ns]"),
        "Previo": pd.Series(dtype="float"),
        "Previsión": pd.Series(dtype="float"),
        "Impacto": pd.Series(dtype="string"),
    })


def guardar_eventos(df):
    DATA_FILE.write_text(df.to_json(orient="records", date_format="iso"), encoding="utf-8")


def calcular_estrategia(df):
    df = df.dropna(subset=["Fecha y hora"]).copy()
    df["Hora entrada"] = df["Fecha y hora"] + pd.Timedelta(minutes=2)

    def tendencia(row):
        previo, prevision = row["Previo"], row["Previsión"]
        if pd.isna(previo) or pd.isna(prevision):
            return "Esperar dato"
        if prevision > previo:
            return f"Alcista ({row['Moneda']})"
        if prevision < previo:
            return f"Bajista ({row['Moneda']})"
        return "Neutral / ruptura"

    df["Tendencia estimada"] = df.apply(tendencia, axis=1)
    return df.sort_values("Fecha y hora")


def color_impacto(valor):
    color = IMPACT_COLOR.get(valor, "#8a8f98")
    return f"background-color: {color}22; color: {color}; font-weight: 600;"


def color_tendencia(valor):
    if "Alcista" in valor:
        return "color: #2e7d32; font-weight: 600;"
    if "Bajista" in valor:
        return "color: #c62828; font-weight: 600;"
    return "color: #8a8f98;"


st.title(":material/monitoring: Robot analizador de noticias económicas")
st.caption("Carga tú mismo los eventos de la semana (revisa cualquier calendario económico como referencia) y el robot calcula la hora de entrada y la tendencia estimada.")

eventos_guardados = cargar_eventos()

st.subheader("Eventos de la semana", anchor=False)
eventos_editados = st.data_editor(
    eventos_guardados,
    key="editor_eventos",
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "Moneda": st.column_config.SelectboxColumn("Moneda", options=MONEDAS, required=True),
        "Evento": st.column_config.TextColumn("Evento", required=True),
        "Fecha y hora": st.column_config.DatetimeColumn("Fecha y hora", format="ddd D MMM, HH:mm", required=True),
        "Previo": st.column_config.NumberColumn("Previo"),
        "Previsión": st.column_config.NumberColumn("Previsión"),
        "Impacto": st.column_config.SelectboxColumn("Impacto", options=IMPACTOS, required=True),
    },
)

if st.button("Guardar cambios", icon=":material/save:", type="primary"):
    guardar_eventos(eventos_editados)
    st.toast("Eventos guardados", icon=":material/check_circle:")

df = calcular_estrategia(eventos_editados)

if df.empty:
    st.info("Todavía no cargaste eventos. Agrega filas arriba para empezar.", icon=":material/event_busy:")
else:
    ahora = datetime.now()

    st.sidebar.header("Filtros")
    monedas_presentes = sorted(df["Moneda"].dropna().unique())
    impacto_elegido = st.sidebar.multiselect("Impacto", IMPACTOS, default=["Alto", "Medio"])
    moneda_elegida = st.sidebar.multiselect("Moneda", monedas_presentes, default=monedas_presentes)

    df_filtrado = df[df["Impacto"].isin(impacto_elegido) & df["Moneda"].isin(moneda_elegida)]
    df_hoy = df_filtrado[df_filtrado["Fecha y hora"].dt.date == ahora.date()]

    vista = st.segmented_control("Rango", ["Hoy", "Esta semana"], default="Hoy")
    df_vista = df_filtrado if vista == "Esta semana" else df_hoy

    proximos = df_filtrado[(df_filtrado["Impacto"] == "Alto") & (df_filtrado["Fecha y hora"] >= ahora)]

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Eventos de alto impacto hoy", int((df_hoy["Impacto"] == "Alto").sum()))
    with col2:
        if proximos.empty:
            st.metric("Próximo evento de alto impacto", "Ninguno programado")
        else:
            siguiente = proximos.iloc[0]
            minutos = int((siguiente["Fecha y hora"] - ahora).total_seconds() // 60)
            st.metric("Próximo evento de alto impacto", siguiente["Evento"], delta=f"en {minutos} min")

    st.subheader("Planificación de entrada", anchor=False)

    if df_vista.empty:
        st.info("No hay eventos para este rango con los filtros seleccionados.", icon=":material/event_busy:")
    else:
        estilo = (
            df_vista.style
            .map(color_impacto, subset=["Impacto"])
            .map(color_tendencia, subset=["Tendencia estimada"])
        )
        formato_hora = "HH:mm" if vista == "Hoy" else "ddd, HH:mm"
        st.dataframe(
            estilo,
            column_config={
                "Fecha y hora": st.column_config.DatetimeColumn("Hora del evento", format=formato_hora),
                "Hora entrada": st.column_config.DatetimeColumn("Hora de entrada mínima", format=formato_hora),
            },
            hide_index=True,
        )

st.sidebar.warning(
    "Entra al mercado únicamente en la 'Hora de entrada' indicada, para evitar el spread "
    "salvaje del primer segundo tras la noticia.",
    icon=":material/warning:",
)
