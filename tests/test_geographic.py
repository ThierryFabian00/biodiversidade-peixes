import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.filter_basin import classificar_ocorrencias, filtrar_por_poligono
from src.prepare_boundary import selecionar_regiao


class TestPrepararLimite(unittest.TestCase):
    def test_seleciona_regiao_pelo_codigo_oficial(self):
        regioes = gpd.GeoDataFrame(
            {
                "cd_macroRH": ["110", "111"],
                "nm_macroRH": ["URUGUAI", "PARANÁ"],
            },
            geometry=[
                Polygon([(20, 20), (21, 20), (21, 21), (20, 21)]),
                Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
            ],
            crs="EPSG:4326",
        )

        selecionada = selecionar_regiao(regioes)

        self.assertEqual(len(selecionada), 1)
        self.assertEqual(selecionada.iloc[0]["nm_macroRH"], "PARANÁ")


class TestFiltroEspacial(unittest.TestCase):
    def setUp(self):
        self.limite = gpd.GeoDataFrame(
            {"cd_macroRH": ["111"]},
            geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
            crs="EPSG:4326",
        )
        self.dados = pd.DataFrame(
            {
                "key": [1, 2, 3],
                "decimalLongitude": [5, 0, 11],
                "decimalLatitude": [5, 5, 5],
            }
        )

    def test_mantem_pontos_internos_e_sobre_o_limite(self):
        filtrados = filtrar_por_poligono(self.dados, self.limite)

        self.assertEqual(filtrados["key"].tolist(), [1, 2])
        self.assertTrue(filtrados["insideBasin"].all())
        self.assertEqual(filtrados["basinCode"].unique().tolist(), ["111"])

    def test_classifica_ponto_externo(self):
        classificados = classificar_ocorrencias(self.dados, self.limite)

        self.assertEqual(classificados["insideBasin"].tolist(), [True, True, False])

    def test_reprojeta_limite_antes_de_classificar(self):
        limite_projetado = self.limite.to_crs("EPSG:3857")

        filtrados = filtrar_por_poligono(self.dados, limite_projetado)

        self.assertEqual(filtrados["key"].tolist(), [1, 2])

    def test_rejeita_limite_sem_crs(self):
        limite_sem_crs = self.limite.copy().set_crs(None, allow_override=True)

        with self.assertRaisesRegex(ValueError, "não possui CRS"):
            classificar_ocorrencias(self.dados, limite_sem_crs)


if __name__ == "__main__":
    unittest.main()
