#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Actualiza datos de acciones colombianas desde Yahoo Finance."""

# Sección: imports de la biblioteca estándar.
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Sección: activos incluidos en el proyecto académico.
ACCIONES: list[dict[str, str]] = [
    {
        "ticker": "ECOPETROL.CL",
        "nombre": "Ecopetrol",
        "nemotecnico": "ECOPETROL",
        "sector": "Petróleo y gas",
    },
    {
        "ticker": "PFCIBEST.CL",
        "nombre": "Grupo Cibest preferencial",
        "nemotecnico": "PFCIBEST",
        "sector": "Financiero",
    },
    {
        "ticker": "CIBEST.CL",
        "nombre": "Grupo Cibest ordinaria",
        "nemotecnico": "CIBEST",
        "sector": "Financiero",
    },
    {
        "ticker": "ISA.CL",
        "nombre": "ISA",
        "nemotecnico": "ISA",
        "sector": "Energía e infraestructura",
    },
    {
        "ticker": "EXITO.CL",
        "nombre": "Grupo Éxito",
        "nemotecnico": "EXITO",
        "sector": "Comercio",
    },
    {
        "ticker": "PFAVAL.CL",
        "nombre": "Grupo Aval preferencial",
        "nemotecnico": "PFAVAL",
        "sector": "Financiero",
    },
    # Acción de ejemplo escogida por el equipo; cámbiela si eligieron otra.
    {
        "ticker": "GEB.CL",
        "nombre": "Grupo Energía Bogotá",
        "nemotecnico": "GEB",
        "sector": "Energía",
    },
    # Acción de ejemplo escogida por el equipo; cámbiela si eligieron otra.
    {
        "ticker": "CELSIA.CL",
        "nombre": "Celsia",
        "nemotecnico": "CELSIA",
        "sector": "Energía",
    },
]

FUENTE = "Yahoo Finance (yfinance); rentabilidades con precio ajustado por dividendos"
ARCHIVO_SALIDA = Path(__file__).resolve().with_name("datos.json")


# Sección: lectura y limpieza de las series de precios.
def obtener_columna(historial: Any, nombre: str, ticker: str, pd: Any) -> Any:
    """Devuelve una serie del historial, incluso si yfinance usa columnas multinivel."""
    columnas = historial.columns
    if nombre in columnas:
        return historial[nombre]

    if isinstance(columnas, pd.MultiIndex):
        for columna in columnas:
            if nombre in columna and ticker in columna:
                return historial[columna]
        for columna in columnas:
            if nombre in columna:
                return historial[columna]

    raise ValueError(f"El historial no contiene la columna {nombre}")


def preparar_historial(historial: Any, ticker: str, pd: Any) -> Any:
    """Normaliza fechas y columnas requeridas; descarta filas sin precios ajustados."""
    if historial is None or historial.empty:
        raise ValueError("Yahoo Finance no devolvió datos")

    indice = pd.DatetimeIndex(pd.to_datetime(historial.index, errors="coerce"))
    validas = ~indice.isna()
    historial = historial.loc[validas].copy()
    indice = indice[validas]
    if indice.tz is not None:
        indice = indice.tz_localize(None)
    historial.index = indice
    historial = historial.sort_index()

    close = pd.to_numeric(obtener_columna(historial, "Close", ticker, pd), errors="coerce")
    adj_close = pd.to_numeric(obtener_columna(historial, "Adj Close", ticker, pd), errors="coerce")
    dividends = pd.to_numeric(
        obtener_columna(historial, "Dividends", ticker, pd), errors="coerce"
    ).fillna(0)

    limpio = pd.DataFrame(
        {"Close": close, "Adj Close": adj_close, "Dividends": dividends},
        index=historial.index,
    )
    limpio = limpio.dropna(subset=["Close", "Adj Close"])
    limpio = limpio[(limpio["Close"] > 0) & (limpio["Adj Close"] > 0)]
    if len(limpio) < 2:
        raise ValueError("No hay suficientes precios válidos para calcular rendimientos")
    return limpio


# Sección: cálculo de indicadores y datos mensuales.
def calcular_accion(definicion: dict[str, str], historial: Any, pd: Any) -> dict[str, Any]:
    """Calcula los datos de una acción usando cierres y fechas reales."""
    ticker = definicion["ticker"]
    historial = preparar_historial(historial, ticker, pd)

    cierre = historial["Close"]
    ajustado = historial["Adj Close"]
    dividendos = historial["Dividends"]
    ultima_fecha = cierre.index[-1]
    fecha_corte = ultima_fecha - pd.DateOffset(years=1)

    precio = float(cierre.iloc[-1])
    cierre_anterior = float(cierre.iloc[-2])
    variacion_dia_pct = (precio / cierre_anterior - 1) * 100

    fecha_mas_cercana = min(ajustado.index, key=lambda fecha: abs(fecha - fecha_corte))
    ajustado_hace_un_ano = float(ajustado.loc[fecha_mas_cercana])
    rent_1a_pct = (float(ajustado.iloc[-1]) / ajustado_hace_un_ano - 1) * 100

    primera_fecha = ajustado.index[0]
    anos_transcurridos = (ultima_fecha - primera_fecha).total_seconds() / (365.2425 * 24 * 60 * 60)
    if anos_transcurridos <= 0:
        raise ValueError("El historial no cubre un periodo suficiente para anualizar")
    rent_anual_3a_pct = (
        (float(ajustado.iloc[-1]) / float(ajustado.iloc[0])) ** (1 / anos_transcurridos) - 1
    ) * 100

    log_precios = ajustado[ajustado > 0].map(math.log)
    rendimientos_log = log_precios.diff().dropna()
    rendimientos_ultimo_ano = rendimientos_log.loc[rendimientos_log.index >= fecha_corte]
    if len(rendimientos_ultimo_ano) < 2:
        raise ValueError("No hay suficientes rendimientos diarios del último año")
    volatilidad_anual_pct = float(rendimientos_ultimo_ano.std(ddof=1)) * math.sqrt(252) * 100

    ajustado_ultimo_ano = ajustado.loc[ajustado.index >= fecha_corte]
    caidas_ultimo_ano = ajustado_ultimo_ano / ajustado_ultimo_ano.cummax() - 1
    caida_maxima_1a_pct = float(caidas_ultimo_ano.min()) * 100

    corte_dividendos = ultima_fecha - pd.Timedelta(days=365)
    suma_dividendos = float(dividendos.loc[dividendos.index >= corte_dividendos].sum())
    dividendo_rend_pct = suma_dividendos / precio * 100

    historico_mensual = cierre.groupby(cierre.index.to_period("M")).last()
    historico = [
        {"mes": str(mes), "cierre": round(float(valor), 2)}
        for mes, valor in historico_mensual.items()
    ]

    return {
        "ticker": ticker,
        "nombre": definicion["nombre"],
        "nemotecnico": definicion["nemotecnico"],
        "sector": definicion["sector"],
        "moneda": "COP",
        "precio": round(precio, 2),
        "fecha": ultima_fecha.strftime("%Y-%m-%d"),
        "variacion_dia_pct": round(variacion_dia_pct, 2),
        "rent_1a_pct": round(rent_1a_pct, 2),
        "rent_anual_3a_pct": round(rent_anual_3a_pct, 2),
        "volatilidad_anual_pct": round(volatilidad_anual_pct, 2),
        "caida_maxima_1a_pct": round(caida_maxima_1a_pct, 2),
        "dividendo_rend_pct": round(dividendo_rend_pct, 2),
        "historico": historico,
    }


# Sección: consulta de la TRM. Si Yahoo Finance no responde, se conserva como null.
def obtener_trm(yf: Any, pd: Any) -> dict[str, Any] | None:
    """Obtiene el último cierre de USDCOP=X o devuelve null si no está disponible."""
    try:
        historial = yf.Ticker("USDCOP=X").history(period="5d", auto_adjust=False)
        if historial is None or historial.empty:
            raise ValueError("Yahoo Finance no devolvió la serie de TRM")
        cierre = pd.to_numeric(historial["Close"], errors="coerce").dropna()
        if cierre.empty:
            raise ValueError("La serie de TRM no contiene cierres válidos")

        fecha = pd.Timestamp(cierre.index[-1])
        if fecha.tzinfo is not None:
            fecha = fecha.tz_localize(None)
        return {"valor": round(float(cierre.iloc[-1]), 2), "fecha": fecha.strftime("%Y-%m-%d")}
    except Exception as error:
        print(f"Aviso: no se pudo actualizar la TRM: {error}")
        return None


# Sección: escritura segura del JSON y resumen de actualización.
def guardar_json(datos: dict[str, Any], ruta: Path) -> None:
    """Escribe el archivo de forma atómica para conservar el anterior ante fallos."""
    ruta_temporal: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=ruta.parent,
            prefix=f".{ruta.name}.",
            suffix=".tmp",
            delete=False,
        ) as archivo:
            ruta_temporal = archivo.name
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
        os.replace(ruta_temporal, ruta)
    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            os.unlink(ruta_temporal)


def ejecutar() -> None:
    """Consulta los activos, guarda los resultados disponibles y reporta errores."""
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError as error:
        print(f"No se pudo iniciar la actualización: falta una dependencia ({error}).")
        print("Instale las dependencias con: python -m pip install yfinance pandas")
        return

    acciones_actualizadas: list[dict[str, Any]] = []
    errores: list[dict[str, str]] = []

    for definicion in ACCIONES:
        ticker = definicion["ticker"]
        try:
            historial = yf.Ticker(ticker).history(period="3y", auto_adjust=False)
            acciones_actualizadas.append(calcular_accion(definicion, historial, pd))
            print(f"Actualizada: {ticker}")
        except Exception as error:
            motivo = f"{type(error).__name__}: {error}"
            errores.append({"ticker": ticker, "motivo": motivo})
            print(f"Error en {ticker}: {motivo}")

    if not acciones_actualizadas:
        print("Aviso: todas las acciones fallaron; no se modificó datos.json.")
        imprimir_resumen(acciones_actualizadas, errores)
        return

    datos = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "fuente": FUENTE,
        "trm": obtener_trm(yf, pd),
        "acciones": acciones_actualizadas,
        "errores": errores,
    }

    try:
        guardar_json(datos, ARCHIVO_SALIDA)
        print(f"Archivo actualizado: {ARCHIVO_SALIDA}")
    except Exception as error:
        print(f"No se pudo guardar datos.json: {error}")

    imprimir_resumen(acciones_actualizadas, errores)


def imprimir_resumen(acciones: list[dict[str, Any]], errores: list[dict[str, str]]) -> None:
    """Muestra cuántas acciones se actualizaron y los tickers que fallaron."""
    print(f"\nResumen: {len(acciones)} de {len(ACCIONES)} acciones actualizadas.")
    if errores:
        print("Acciones fallidas:")
        for error in errores:
            print(f"- {error['ticker']}: {error['motivo']}")
    else:
        print("Acciones fallidas: ninguna.")


# Sección: punto de entrada. Los errores se informan sin finalizar con código distinto de cero.
if __name__ == "__main__":
    try:
        ejecutar()
    except Exception as error:
        print(f"Aviso: la actualización no pudo completarse: {type(error).__name__}: {error}")
