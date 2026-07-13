import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

st.set_page_config(
    page_title="Robot de noticias Forex",
    page_icon=":material/monitoring:",
    layout="wide",
)

TE_URL = "https://api.tradingeconomics.com/calendar/{d1}/{d2}"
IMPORTANCE_ES = {3: "Alto", 2: "Medio", 1: "Bajo", 0: "Feriado"}
IMPACT_COLOR = {"Alto": "#e05252", "Medio": "#d99a3d", "Bajo": "#8a8f98", "Feriado": "#5b8def"}

CURRENCY_BY_COUNTRY = {
    "United States": "USD", "Euro Area": "EUR", "European Union": "EUR",
    "United Kingdom": "GBP", "Japan": "JPY", "Australia": "AUD", "Canada": "CAD",
    "Switzerland": "CHF", "New Zealand": "NZD", "China": "CNY",
    "Germany": "EUR", "France": "EUR", "Italy": "EUR", "Spain": "EUR",
}


@st.cache_data(ttl="10m")
def obtener_calendario():
    # "guest:guest" es el acceso público gratuito de Trading Economics; configura TE_API_KEY
    # en secrets con tu "client:secret" real si te registras para mejores límites.
    credenciales = st.secrets.get("TE_API_KEY", "guest:guest")

    hoy = datetime.now(timezone.utc).date()
    url = TE_URL.format(d1=hoy.isoformat(), d2=(hoy + timedelta(days=6)).isoformat())
    respuesta = requests.get(url, params={"c": credenciales, "f": "json"}, timeout=10)
    respuesta.raise_for_status()

    filas = []
    for item in respuesta.json():
        fecha_raw = item.get("Date")
        if not fecha_raw:
            continue
        try:
            fecha_dt = datetime.fromisoformat(fecha_raw.replace("Z", "+00:00"))
            if fecha_dt.tzinfo is None:
                fecha_dt = fecha_dt.replace(tzinfo=timezone.utc)
            fecha_dt = fecha_dt.astimezone()
        except ValueError:
            continue

        pais = item.get("Country", "—")
        filas.append({
            "Moneda": CURRENCY_BY_COUNTRY.get(pais, pais),
            "Evento": item.get("Event", "Evento económico"),
            "Fecha y hora": fecha_dt,
            "Previo": item.get("Previous") if item.get("Previous") not in (None, "") else "—",
            "Previsión": item.get("Forecast") if item.get("Forecast") not in (None, "") else "—",
            "Actual": item.get("Actual") if item.get("Actual") not in (None, "") else "—",
            "Impacto": IMPORTANCE_ES.get(item.get("Importance"), "Bajo"),
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
    except requests.HTTPError as e:
        codigo = e.response.status_code if e.response is not None else "?"
        st.error(
            f"Trading Economics respondió con error {codigo}. Si usas la cuenta 'guest' gratuita, "
            "puede estar limitada — considera registrar una cuenta real en tradingeconomics.com/api "
            "y agregar `TE_API_KEY` en Secrets.",
            icon=":material/error:",
        )
        return
    except requests.RequestException as e:
        st.error(f"No se pudo conectar con Trading Economics: {e}", icon=":material/error:")
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

    st.caption("Fuente: Trading Economics (calendario económico).")


st.title(":material/monitoring: Robot analizador de noticias económicas")
st.caption("Planificación de trading en tiempo real a partir del calendario económico")

panel_noticias()

st.sidebar.warning(
    "Entra al mercado únicamente en la 'Hora de entrada' indicada, para evitar el spread "
    "salvaje del primer segundo tras la noticia.",
    icon=":material/warning:",
)
