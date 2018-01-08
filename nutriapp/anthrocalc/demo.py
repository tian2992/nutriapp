import os
import logging

import numpy
import pandas as pd
import pygrowup


tabla_nimacabaj = pd.read_excel(os.path.join(os.path.dirname(__file__), "ej_nim.xls"))

calculator = pygrowup.Calculator(adjust_height_data=False, adjust_weight_scores=True,
                       include_cdc=False, logger_name='pygrowup',
                       log_level='INFO')

'''Col index between weights columns and weight-height sets.'''
OFFSET_DATOS_P = 5

datos_personales = (tabla_nimacabaj.iloc[:,:5:])
pesos = (tabla_nimacabaj.iloc[:,OFFSET_DATOS_P::4])
talla = (tabla_nimacabaj.iloc[:,(OFFSET_DATOS_P + 1)::4])
fechas = (tabla_nimacabaj.iloc[:,(OFFSET_DATOS_P + 2)::4])
acostados = (tabla_nimacabaj.iloc[:,(OFFSET_DATOS_P - 1)::4]).iloc[:,1::]


def extract_fechas_tablas_index(tabla, tipo, expand_i=False):
    if tipo not in ["Peso", "Talla"]:
        raise Exception("not implemented")
    return tabla.columns.str.extract(f'{tipo}_(\d*-\d*)', expand=expand_i).dropna()
jornadas_peso = extract_fechas_tablas_index(tabla_nimacabaj, "Peso")
jornadas_talla = extract_fechas_tablas_index(tabla_nimacabaj, "Talla")
if (jornadas_peso == jornadas_talla).all():
    logging.debug("Tallas y Pesos match!")
else:
    logging.error("No hay match en pesos y tallas")

for i, c in enumerate(jornadas_peso):
    print(f"Jornadas detectadas: {c}") ## TODO: maek logging

######

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

            logging.debug(f"{dmet} - {dnac} = Days (?)")

            if (isinstance(dmet, numpy.float64) or
               isinstance(dmet, type(pd.NaT))):
                wfa_val = numpy.NaN
                hfa_val = numpy.NaN
            else:
                days = (dmet - dnac).days/ 30.4375
                wfa_val = float(calculator.wfa(pesos.loc[i][j], days, nin["Sexo"], height=talla.loc[i][0]))
                hfa_val = float(calculator.lhfa(talla.loc[i][j], days, nin["Sexo"]))
        except Exception as e:
            logging.warn("invalid date", e)
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

def sweet_toast_melt(melty_df,vname="z-val"):
    '''Melt Hfaz or wfaz to plotty'''
    melty_df["Codigo"] = tabla_nimacabaj["Codigo"]
    _melted = melty_df.melt(id_vars="Codigo", var_name="fecha", value_name=vname)
    _melted['fecha'] = pd.DatetimeIndex(_melted['fecha'])
    return _melted

hfaz_melted = sweet_toast_melt(hfaz,"hfaz")
wfaz_melted = sweet_toast_melt(wfaz,"wfaz")
