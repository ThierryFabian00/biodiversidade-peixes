import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.analysis import (
    criar_grade_espacial,
    criar_resumos,
    identificar_duplicados_potenciais,
    normalizar_estado,
    resumir_qualidade,
)


def criar_ocorrencias():
    return pd.DataFrame(
        [
            {
                "gbifID": 1,
                "speciesKey": "A",
                "canonicalName": "Species alpha",
                "decimalLatitude": 0.25,
                "decimalLongitude": 0.25,
                "eventDate": "2020-01-02",
                "eventDateOriginal": "2020-01-02",
                "year": 2020,
                "month": 1,
                "stateProvince": "SÃ£o Paulo",
                "locality": "Local A",
                "basisOfRecord": "OBSERVATION",
                "taxonomicIssues": "",
                "occurrenceIssues": "",
            },
            {
                "gbifID": 2,
                "speciesKey": "A",
                "canonicalName": "Species alpha",
                "decimalLatitude": 0.25,
                "decimalLongitude": 0.25,
                "eventDate": "2020-01-02",
                "eventDateOriginal": "2020-01-02",
                "year": 2020,
                "month": 1,
                "stateProvince": "SP",
                "locality": pd.NA,
                "basisOfRecord": "OBSERVATION",
                "taxonomicIssues": "ISSUE",
                "occurrenceIssues": "ISSUE",
            },
            {
                "gbifID": 3,
                "speciesKey": "B",
                "canonicalName": "Species beta",
                "decimalLatitude": 1.25,
                "decimalLongitude": 1.25,
                "eventDate": "2022-03-04",
                "eventDateOriginal": "2022-03-04",
                "year": 2022,
                "month": 3,
                "stateProvince": pd.NA,
                "locality": "Local B",
                "basisOfRecord": "SPECIMEN",
                "taxonomicIssues": "",
                "occurrenceIssues": "",
            },
        ]
    )


class TestAnaliseExploratoria(unittest.TestCase):
    def setUp(self):
        self.ocorrencias = criar_ocorrencias()
        self.especies = pd.DataFrame(
            [
                {
                    "speciesKey": "A",
                    "canonicalName": "Species alpha",
                    "occurrenceCount": 2,
                },
                {
                    "speciesKey": "B",
                    "canonicalName": "Species beta",
                    "occurrenceCount": 1,
                },
            ]
        )

    def test_normaliza_estado_e_corrige_mojibake(self):
        self.assertEqual(normalizar_estado("SÃ£o Paulo"), "Sao Paulo")
        self.assertEqual(normalizar_estado("SP"), "Sao Paulo")
        self.assertEqual(normalizar_estado(pd.NA), "Nao informado")

    def test_cria_series_temporais_com_anos_ausentes(self):
        resumos = criar_resumos(self.ocorrencias, self.especies)

        self.assertEqual(
            resumos["registros_por_ano"]["occurrenceCount"].tolist(),
            [2, 0, 1],
        )
        self.assertEqual(
            resumos["registros_por_mes"].loc[0, "occurrenceCount"], 2
        )
        self.assertEqual(
            resumos["registros_por_estado"].iloc[0]["stateProvince"],
            "Sao Paulo",
        )

    def test_identifica_duplicados_potenciais_sem_confundir_ids(self):
        duplicados = identificar_duplicados_potenciais(self.ocorrencias)
        qualidade = resumir_qualidade(self.ocorrencias).set_index("metric")

        self.assertEqual(duplicados["gbifID"].tolist(), [1, 2])
        self.assertEqual(duplicados["duplicateGroup"].nunique(), 1)
        self.assertEqual(qualidade.loc["duplicateGbifId", "recordCount"], 0)
        self.assertEqual(qualidade.loc["potentialDuplicate", "recordCount"], 2)

    def test_cria_grade_com_celulas_amostradas_e_vazias(self):
        limite = gpd.GeoDataFrame(
            geometry=[Polygon([(0, 0), (3, 0), (3, 3), (0, 3)])],
            crs="EPSG:4326",
        )

        grade = criar_grade_espacial(self.ocorrencias, limite)

        self.assertEqual(int(grade["occurrenceCount"].sum()), 3)
        self.assertGreater(int((~grade["sampled"]).sum()), 0)


if __name__ == "__main__":
    unittest.main()
