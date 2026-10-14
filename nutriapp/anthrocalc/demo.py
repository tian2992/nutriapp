import os
import logging

import numpy
import pandas as pd
import pygrowup

logger = logging.getLogger(__name__)


def extract_fechas_tablas_index(tabla, tipo, expand_i=False):
    if tipo not in ["Peso", "Talla"]:
        raise Exception("not implemented")
    return tabla.columns.str.extract(rf"{tipo}_(\d*-\d*)", expand=expand_i).dropna()


def sweet_toast_melt(melty_df, vname="z-val", tabla_source=None):
    """Melt Hfaz or wfaz to plotty"""
    if tabla_source is not None and "Codigo" in tabla_source:
        melty_df["Codigo"] = tabla_source["Codigo"]
    _melted = melty_df.melt(id_vars="Codigo", var_name="fecha", value_name=vname)
    _melted["fecha"] = pd.DatetimeIndex(_melted["fecha"])
    return _melted


def run_demo(file_path=None):
    if file_path is None:
        file_path = os.path.join(os.path.dirname(__file__), "ej_nim.xls")
    if not os.path.exists(file_path):
        logger.error("Demo spreadsheet not found: %s", file_path)
        raise FileNotFoundError(f"Demo spreadsheet not found: {file_path}")

    tabla_nimacabaj = pd.read_excel(file_path)

    calculator = pygrowup.Calculator(
        adjust_height_data=False, adjust_weight_scores=True, include_cdc=False, logger_name="pygrowup", log_level="INFO"
    )

    """Col index between weights columns and weight-height sets."""
    OFFSET_DATOS_P = 5

    datos_personales = tabla_nimacabaj.iloc[:, :5:]
    pesos = tabla_nimacabaj.iloc[:, OFFSET_DATOS_P::4]
    talla = tabla_nimacabaj.iloc[:, (OFFSET_DATOS_P + 1) :: 4]
    fechas = tabla_nimacabaj.iloc[:, (OFFSET_DATOS_P + 2) :: 4]
    acostados = (tabla_nimacabaj.iloc[:, (OFFSET_DATOS_P - 1) :: 4]).iloc[:, 1::]

    jornadas_peso = extract_fechas_tablas_index(tabla_nimacabaj, "Peso")
    jornadas_talla = extract_fechas_tablas_index(tabla_nimacabaj, "Talla")
    if (jornadas_peso == jornadas_talla).all():
        logger.debug("Tallas y Pesos match!")
    else:
        logger.error("No hay match en pesos y tallas")

    for i, c in enumerate(jornadas_peso):
        print(f"Jornadas detectadas: {c}")  ## TODO: maek logging

    valores = pd.DataFrame(index=datos_personales.index)
    listado_wfaz = []
    listado_hfaz = []
    for j, c in enumerate(jornadas_peso):
        jornal = c
        wfas = []
        hfas = []
        for i, nin in datos_personales.iterrows():
            try:
                dnac = nin["FechaNacimiento"]
                dmet = fechas.loc[i][j]

                logger.debug("Calculating days for measurement date: %s", dmet)

                if isinstance(dmet, numpy.float64) or isinstance(dmet, type(pd.NaT)):
                    wfa_val = numpy.NaN
                    hfa_val = numpy.NaN
                else:
                    days = (dmet - dnac).days / 30.4375
                    wfa_val = float(calculator.wfa(pesos.loc[i][j], days, nin["Sexo"], height=talla.loc[i][0]))
                    hfa_val = float(calculator.lhfa(talla.loc[i][j], days, nin["Sexo"]))
            except Exception as e:
                logger.warning("invalid date: %s", e, exc_info=True)
                wfa_val = numpy.NaN
                hfa_val = numpy.NaN
            wfas.append(wfa_val)
            hfas.append(hfa_val)
        wfaz_s = pd.Series(wfas, index=datos_personales.index)
        hfaz_s = pd.Series(hfas, index=datos_personales.index)
        valores[f"wfaz_{jornal}"] = wfaz_s
        valores[f"hfaz_{jornal}"] = hfaz_s
        listado_wfaz.append(wfaz_s)
        listado_hfaz.append(hfaz_s)

    wfaz = pd.DataFrame(dict(zip(jornadas_peso, listado_wfaz)))
    hfaz = pd.DataFrame(dict(zip(jornadas_peso, listado_hfaz)))

    hfaz_melted = sweet_toast_melt(hfaz, "hfaz", tabla_source=tabla_nimacabaj)
    wfaz_melted = sweet_toast_melt(wfaz, "wfaz", tabla_source=tabla_nimacabaj)
    return wfaz, hfaz, hfaz_melted, wfaz_melted


if __name__ == "__main__":
    run_demo()
