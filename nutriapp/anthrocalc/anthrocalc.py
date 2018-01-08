import os
import logging

import numpy
import pandas as pd
import pygrowup

WEIGHT_CONST = "Peso" ##TODO(tian): make tipo not locale dependent.
HEIGHT_CONST = "Talla"

class AnthroLoader():

    '''Creates AnthroCalc on DataFrame with personal info'''
    def __init__(self, base_df, offset=5):
        self.df_data = base_df
        self.calculator = pygrowup.Calculator(adjust_height_data=False, adjust_weight_scores=True,
                               include_cdc=False, logger_name='pygrowup',
                               log_level='INFO')
        self.OFFSET_DATOS_P = offset

    def load_segments(self):
        ## assume data is in
        ## PERSONAL DATA, weight_1, height_1, date_1, laydown_1
        # format
         self.personal_data = (self.df_data.iloc[:,:self.OFFSET_DATOS_P:])
        self.weights = (self.df_data.iloc[:,self.OFFSET_DATOS_P::4])
        self.heights = (self.df_data.iloc[:,(self.OFFSET_DATOS_P + 1)::4])
        self.dates = (self.df_data.iloc[:,(self.OFFSET_DATOS_P + 2)::4])
        self.laydown = (self.df_data.iloc[:,(self.OFFSET_DATOS_P - 1)::4]).iloc[:,1::]

        def extract_fechas_tablas_index(tabla, tipo, expand_i=False):
            if tipo not in [WEIGHT_CONST, HEIGHT_CONST]:
                raise Exception("not implemented")
            return tabla.columns.str.extract(f'{tipo}_(\d*-\d*)', expand=expand_i).dropna()
        self.jornadas_peso = extract_fechas_tablas_index(self.df_data, WEIGHT_CONST)
        self.jornadas_talla = extract_fechas_tablas_index(self.df_data, HEIGHT_CONST)
        if (self.jornadas_peso == self.jornadas_talla).all():
            logging.debug("Sets of Measures of Weight and Height match.")
        else:
            logging.error("No Match on Weight-Height Columns!")

        for i, c in enumerate(self.jornadas_peso):
            print(f"Jornadas detectadas: {c}") ## TODO: maek logging

    def calculate_indexes(self):

        valores = pd.DataFrame(index=self.personal_data.index)
        listado_wfaz = []
        listado_hfaz = []
        for j, c in enumerate(self.jornadas_peso):
            jornal = c
            wfas = []
            hfas = []
            for i, nin in self.personal_data.iterrows():
                try:
                    dnac = nin["FechaNacimiento"]
                    dmet = self.dates.loc[i][j]

                    logging.debug(f"{dmet} - {dnac} = Days (?)")

                    if (isinstance(dmet, numpy.float64) or
                       isinstance(dmet, type(pd.NaT))):
                        wfa_val = numpy.NaN
                        hfa_val = numpy.NaN
                    else:
                        days = (dmet - dnac).days/ 30.4375
                        wfa_val = float(self.calculator.wfa(self.weights.loc[i][j], days, nin["Sexo"], height=self.heights.loc[i][0]))
                        hfa_val = float(self.calculator.lhfa(self.heights.loc[i][j], days, nin["Sexo"]))
                except Exception as e:
                    logging.warn("invalid date", e)
                    wfa_val = numpy.NaN
                    hfa_val = numpy.NaN
                wfas.append(wfa_val)
                hfas.append(hfa_val)
            wfaz_s = pd.Series(wfas, index=self.personal_data.index)
            hfaz_s = pd.Series(hfas, index=self.personal_data.index)
            valores[f"wfaz_{jornal}"] = wfaz_s
            valores[f"hfaz_{jornal}"] = hfaz_s
            listado_wfaz.append(wfaz_s)
            listado_hfaz.append(hfaz_s)

        self.wfaz = pd.DataFrame(dict(zip(self.jornadas_peso, listado_wfaz)))
        self.hfaz = pd.DataFrame(dict(zip(self.jornadas_peso, listado_hfaz)))

    def melty():
        def sweet_toast_melt(melty_df,vname="z-val"):
            '''Melt Hfaz or wfaz to plotty'''
            melty_df["Codigo"] = tabla_nimacabaj["Codigo"]
            _melted = melty_df.melt(id_vars="Codigo", var_name="fecha", value_name=vname)
            _melted['fecha'] = pd.DatetimeIndex(_melted['fecha'])
            return _melted

        hfaz_melted = sweet_toast_melt(self.hfaz,"hfaz")
        wfaz_melted = sweet_toast_melt(self.wfaz,"wfaz")
