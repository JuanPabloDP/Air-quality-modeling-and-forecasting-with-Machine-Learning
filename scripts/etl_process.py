
import pandas as pd
import numpy as np
import os

class ETLProcess():
    #checar los topes
    corr_umbral = 0.90
    variables_correlacionadas_eliminar = ["TVOC_ppb", "PM10_ugm3"]

    umbrales_contaminantes_altos = {
        "CO_ppm":      8.0,
        "CO2_ppm":  2000.0,
        "SO2_ppm":     0.037,
        "O3_ppm":      0.025,
        "NO2_ppm":     0.040,
        "PM2_5_ugm3": 35.0,
    }

    umbral_bateria_baja = 20.0

    def __init__(self, folder_url:str, file_name):
        self.folder_url = folder_url
        self.file_name = file_name
        self.params_fit = {}

    def extract(self, sensors:list[str]) -> list[pd.DataFrame]:
        self.__data_sensors = []
        self.__sensors = sensors
        data = pd.read_excel(self.folder_url + self.file_name)
        data[["sensor", "periodo"]] = data["sensor_periodo"].str.split("_", expand=True)
        cols = ["sensor"] + ["periodo"] + [c for c in data.columns if c != "sensor" if c != "periodo" if c != "sensor_periodo"]
        data = data[cols]
        for sensor in self.__sensors:
            df_s = data[data["sensor"] == sensor].drop(columns="sensor").copy()
            # eliminar periodo si no varia dentro del sensor (fase 2: verificar si es relevante)
            if df_s["periodo"].nunique() <= 1:
                df_s = df_s.drop(columns="periodo")
            # ordenar por datetime
            df_s = df_s.sort_values("datetime").reset_index(drop=True)
            self.__data_sensors.append(df_s)
        return self.__data_sensors

    def __clean_fit(self, df:pd.DataFrame, sensor:str) -> None:
        params = {}

        # columnas a eliminar por correlacion alta (tvoc r=0.96 con co2, pm10 r=0.72 con pm2.5, fase 2 eda)
        params["cols_eliminar"] = [c for c in self.variables_correlacionadas_eliminar if c in df.columns]

        # deteccion de outliers comparando aqi vs umbrales de contaminantes 
        cols_contaminantes = [c for c in self.umbrales_contaminantes_altos if c in df.columns]
        algun_contaminante_alto = pd.Series(False, index=df.index)
        for col in cols_contaminantes:
            algun_contaminante_alto |= df[col] > self.umbrales_contaminantes_altos[col]

        # aqi alto pero ningun contaminante lo justifica
        outlier_a = (df["AQI"] >= 4) & (~algun_contaminante_alto)
        # aqi bajo pero algun contaminante supera su umbral
        outlier_b = (df["AQI"] <= 2) & algun_contaminante_alto

        mascara_outliers = outlier_a | outlier_b
        bateria_baja = df["Bat_pct"] < self.umbral_bateria_baja

        # outlier + bateria baja = error de medicion se elimina
        params["idx_error_medicion"] = df.index[mascara_outliers & bateria_baja].tolist()
        # outlier + bateria buena = se conserva para analisis de errores autorregresivos 
        params["idx_outlier_conservar"] = df.index[mascara_outliers & ~bateria_baja].tolist()

        self.params_fit[sensor]["clean"] = params

    def __clean_transform(self, df:pd.DataFrame, sensor:str) -> pd.DataFrame:
        params = self.params_fit[sensor]["clean"]
        df = df.drop(columns=params["cols_eliminar"], errors="ignore")
        df = df.drop(index=params["idx_error_medicion"], errors="ignore")
        return df.reset_index(drop=True)

    def __impute_fit(self, df:pd.DataFrame, sensor:str) -> None:
        # no hay datos faltantes 
        # si la limpieza genera nan se maneja en impute_transform con interpolacion
        self.params_fit[sensor]["impute"] = {}

    def __impute_transform(self, df:pd.DataFrame, sensor:str) -> pd.DataFrame:
        cols_numericas = df.select_dtypes(include=np.number).columns.tolist()
        if df[cols_numericas].isnull().any().any():
            df[cols_numericas] = df[cols_numericas].interpolate(method="linear", limit_direction="both")
        return df

    def __norm_std_fit(self, df:pd.DataFrame, sensor:str) -> None:
        params = {}

        # estandarizacion para contaminantes, distribucion asimetrica con valores bajos, medios y altos 
        cols_std = [c for c in ["CO2_ppm","CO_ppm","SO2_ppm","O3_ppm","NO2_ppm","PM2_5_ugm3"] if c in df.columns]
        params["cols_std"] = cols_std
        params["media"]    = df[cols_std].mean()
        params["std"]      = df[cols_std].std()

        # min-max para temp, humedad y bateria, no hay negativos en la region 
        cols_minmax = [c for c in ["temp_C","hum_pct","Bat_pct"] if c in df.columns]
        params["cols_minmax"] = cols_minmax
        params["minimo"]      = df[cols_minmax].min()
        params["maximo"]      = df[cols_minmax].max()

        self.params_fit[sensor]["scaling"] = params

    def __norm_std_transform(self, df:pd.DataFrame, sensor:str) -> pd.DataFrame:
        params = self.params_fit[sensor]["scaling"]

        cols_std = params["cols_std"]
        df[cols_std] = (df[cols_std] - params["media"]) / params["std"].replace(0, 1)

        cols_minmax = params["cols_minmax"]
        rango = (params["maximo"] - params["minimo"]).replace(0, 1)
        df[cols_minmax] = (df[cols_minmax] - params["minimo"]) / rango

        return df

    def fit(self):
        for i, sensor in enumerate(self.__sensors):
            self.params_fit[sensor] = {}
            df = self.__data_sensors[i].copy()
            self.__clean_fit(df, sensor)
            df_limpio = self.__clean_transform(df, sensor)
            df_limpio = self.__impute_transform(df_limpio, sensor)
            self.__impute_fit(df_limpio, sensor)
            self.__norm_std_fit(df_limpio, sensor)

    def transform(self):
        self.__data_sensors_transf = []
        for i, sensor in enumerate(self.__sensors):
            df = self.__data_sensors[i].copy()
            df = self.__clean_transform(df, sensor)
            df = self.__impute_transform(df, sensor)
            df = self.__norm_std_transform(df, sensor)
            self.__data_sensors_transf.append(df)

    def fit_transform(self):
        self.fit()
        self.transform()

    def load(self):
        ruta_load = self.folder_url + "Load/"
        os.makedirs(ruta_load, exist_ok=True)
        for i, sensor in enumerate(self.__sensors):
            ruta_salida = ruta_load + "data_sensor_" + sensor + ".csv"
            self.__data_sensors_transf[i].to_csv(ruta_salida, index=False)
            print(f"guardado: {ruta_salida}")


if __name__ == "__main__":
    folder = "data/"
    file   = "Datos_maestro_sensores.xlsx"

    etl = ETLProcess(folder_url=folder, file_name=file)
    etl.extract(sensors=["D"])
    etl.fit_transform()
    etl.load()
