import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

st.set_page_config(
    page_title="Robot de noticias Forex",
    page_icon=":material/monitoring:",
    layout="wide",
)

FMP_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"
IMPACT_ES = {"High": "Alto", "Medium": "Medio", "Low": "Bajo", "Holiday": "Feriado"}
IMPACT_COLOR = {"Alto": "#e05252", "Medio": "#d99a3d", "Bajo": "#8a8f98", "Feriado": "#5b8def"}


@st.cache_data(ttl="10m")  # el plan gratuito de FMP tiene cupo diario limitado de llamadas
def obtener_calendario():
    api_key = st.secrets.get("FMP_API_KEY")
    if not api_key:
        return None

    hoy = datetime.now(timezone.utc).date()
    params = {
        "from": hoy.isoformat(),
        "to": (hoy + timedelta(days=6)).isoformat(),
        "apikey": api_key,
    }
    respuesta = requests.get(FMP_URL, params=params, timeout=10)
    respuesta.raise_for_status()

    filas = []
    for item in respuesta.json():
        fecha_raw = item.get("date")
        if not fecha_raw:
            continue
        try:
            fecha_dt = (
                datetime.strptime(fecha_raw, "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc)
                .astimezone()
            )
        except ValueError:
            continue

        filas.append({
            "Moneda": item.get("currency") or item.get("country", "—"),
            "Evento": item.get("event", "Evento económico"),
            "Fecha y hora": fecha_dt,
            "Previo": item.get("previous") if item.get("previous") is not None else "—",
            "Previsión": item.get("estimate") if item.get("estimate") is not None else "—",
            "Actual": item.get("actual") if item.get("actual") is not None else "—",
            "Impacto": IMPACT_ES.get(item.get("impact"), "Bajo"),
        })

    return pd.DataFrame(filas)


def calcular_estrategia(df):
    df = df.copy()
    df["Hora entrada"] = df["Fecha y hora"] + pd.Timedelta(minutes=2)

    def tendencia(row):
        try:
            previo, prevision = float(row["Previo"]), float(row["Previsión"])
        except (TypeError, ValueError):
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


@st.fragment(run_every="60s")
def panel_noticias():
    ahora = datetime.now().astimezone()

    try:
        with st.spinner("Actualizando calendario económico..."):
            datos = obtener_calendario()
    except requests.RequestException as e:
        st.error(f"No se pudo conectar con Financial Modeling Prep: {e}", icon=":material/error:")
        return

    if datos is None:
        st.error(
            "Falta configurar la API key de Financial Modeling Prep. Agrega `FMP_API_KEY` en "
            "`.streamlit/secrets.toml` (local) o en Settings → Secrets de tu app en Streamlit "
            "Cloud.",
            icon=":material/key_off:",
        )
        return

    if datos.empty:
        st.warning("El calendario no devolvió eventos para esta semana.", icon=":material/warning:")
        return

    df = calcular_estrategia(datos)

    st.sidebar.header("Filtros")
    monedas = sorted(df["Moneda"].unique())
    impacto_elegido = st.sidebar.multiselect(
        "Impacto", ["Alto", "Medio", "Bajo", "Feriado"], default=["Alto", "Medio"]
    )
    moneda_elegida = st.sidebar.multiselect("Moneda", monedas, default=monedas)

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

    st.caption(f"Última actualización: {ahora.strftime('%H:%M:%S')} · datos del calendario se refrescan cada ~10 min")

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

    st.caption("Fuente: Financial Modeling Prep (calendario económico).")


st.title(":material/monitoring: Robot analizador de noticias económicas")
st.caption("Planificación de trading en tiempo real a partir del calendario económico")

panel_noticias()

st.sidebar.warning(
    "Entra al mercado únicamente en la 'Hora de entrada' indicada, para evitar el spread "
    "salvaje del primer segundo tras la noticia.",
    icon=":material/warning:",
)
