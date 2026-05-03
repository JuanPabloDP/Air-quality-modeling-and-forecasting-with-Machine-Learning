
import pandas as pd
import numpy as np

class ETLProcess():
    def __init__(self, folder_url:str, file_name):
        self.folder_url = folder_url
        self.file_name = file_name
    
    def extract(self,sensors:list[str]) -> list[pd.DataFrame]:
        self.__data_sensors=[]
        self.__sensors=sensors
        data=pd.read_excel(self.folder_url+self.file_name)
        data[["sensor", "periodo"]] = data["sensor_periodo"].str.split("_", expand=True)
        cols=["sensor"]+["periodo"]+[c for c in data.columns if c!="sensor" if c !="periodo" if c!="sensor_periodo"]
        data = data[cols]
        for sensor in self.__sensors:
            self.__data_sensors.append(data[data["sensor"]==sensor].drop(columns="sensor").copy())
        return self.__data_sensors
    
    def __clean_fit(self):
        ...
    
    def __clean_transform(self):
        ...

    def __impute_fit(self):
        ...

    def __impute_transform(self):
        ...

    def __norm_std_fit(self):
        ...
    
    def __norm_std_transform(self):
        ...

    def fit(self):
        self.__clean_fit()
        self.__impute_fit()
        self.__norm_std_fit()
    
    def transform(self):
        self.__data_sensors_transf=[]

        self.__clean_transform()
        self.__impute_transform()
        self.__norm_std_transform()
    
    def fit_transform(self):
        self.fit()
        self.transform()
    
    def load(self):
        for i,sensor in enumerate(self.__sensors):
            self.__data_sensors_transf[i].to_csv(self.folder_url+"/Load/data_sensor"+sensor+".xlsx")
