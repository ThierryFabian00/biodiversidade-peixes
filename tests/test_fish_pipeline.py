import unittest
from unittest.mock import Mock

import geopandas as gpd
import pandas as pd
from shapely import from_wkt
from shapely.geometry import Polygon

from src.config import ConfiguracaoAplicacao
from src.extract_fish import (
    buscar_ocorrencias_peixes,
    criar_parser,
    criar_prefiltro_wkt,
    selecionar_grupo_taxonomico,
)
from src.transform_fish import (
    classificar_origem,
    normalizar_registro,
    transformar_registros,
)


def criar_resposta(dados):
    resposta = Mock()
    resposta.json.return_value = dados
    resposta.raise_for_status.return_value = None
    return resposta


def registro_especie(chave, longitude=5, latitude=5, rank="SPECIES"):
    classificacao = [
        {"key": "8VR36", "name": "Actinopterygii", "rank": "GIGACLASS"},
        {"key": "8V4VD", "name": "Teleostei", "rank": "CLASS"},
        {"key": "ORD", "name": "Siluriformes", "rank": "ORDER"},
        {"key": "FAM", "name": "Pimelodidae", "rank": "FAMILY"},
        {"key": "GEN", "name": "Pimelodus", "rank": "GENUS"},
        {"key": "SP1", "name": "Pimelodus maculatus", "rank": "SPECIES"},
    ]
    return {
        "key": chave,
        "scientificName": "Pimelodus maculatus Lacépède, 1803",
        "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
        "datasetName": "Dataset de teste",
        "decimalLongitude": longitude,
        "decimalLatitude": latitude,
        "eventDate": "2020-01-02",
        "occurrenceStatus": "PRESENT",
        "classifications": {
            "7ddf754f-d193-4cc9-b351-99906754a03b": {
                "usage": {
                    "key": "SP1",
                    "name": "Pimelodus maculatus Lacépède, 1803",
                    "rank": rank,
                },
                "acceptedUsage": {
                    "key": "SP1",
                    "name": "Pimelodus maculatus Lacépède, 1803",
                    "rank": "SPECIES",
                },
                "taxonomicStatus": "ACCEPTED",
                "classification": classificacao,
            }
        },
    }


class TestExtracaoPeixes(unittest.TestCase):
    def test_prefiltro_cobre_poligono_original(self):
        poligono = Polygon([(0, 0), (10, 0), (5, 5), (10, 10), (0, 10)])
        limite = gpd.GeoDataFrame(geometry=[poligono], crs="EPSG:4326")

        prefiltro = from_wkt(criar_prefiltro_wkt(limite))

        self.assertTrue(prefiltro.covers(poligono))

    def test_paginacao_respeita_limite_da_amostra(self):
        sessao = Mock()
        sessao.get.side_effect = [
            criar_resposta(
                {
                    "count": 100,
                    "endOfRecords": False,
                    "results": [{"key": 1}, {"key": 2}],
                }
            ),
            criar_resposta(
                {
                    "count": 100,
                    "endOfRecords": False,
                    "results": [{"key": 3}],
                }
            ),
        ]

        resultado = buscar_ocorrencias_peixes(
            "POLYGON ((0 0, 1 0, 1 1, 0 0))",
            max_registros=3,
            tamanho_pagina=2,
            sessao=sessao,
        )

        self.assertEqual(len(resultado.registros), 3)
        self.assertEqual(sessao.get.call_count, 2)

    def test_aplica_somente_grupo_taxonomico_informado(self):
        sessao = Mock()
        sessao.get.return_value = criar_resposta(
            {
                "count": 1,
                "endOfRecords": True,
                "results": [{"key": 1}],
            }
        )

        buscar_ocorrencias_peixes(
            "POLYGON ((0 0, 1 0, 1 1, 0 0))",
            max_registros=1,
            sessao=sessao,
            grupos_taxonomicos={"Actinopterygii": "8VR36"},
        )

        parametros = sessao.get.call_args.kwargs["params"]
        self.assertEqual(
            [valor for nome, valor in parametros if nome == "taxonKey"],
            ["8VR36"],
        )

    def test_normaliza_grupo_e_rejeita_desconhecido(self):
        self.assertEqual(
            selecionar_grupo_taxonomico(" actinopterygii "),
            {"Actinopterygii": "8VR36"},
        )
        with self.assertRaisesRegex(ValueError, "desconhecido"):
            selecionar_grupo_taxonomico("Peixes imaginários")

    def test_parser_usa_grupo_e_tamanho_de_pagina_configurados(self):
        configuracao = ConfiguracaoAplicacao(
            grupo_taxonomico="Elasmobranchii",
            tamanho_pagina_padrao=80,
        )

        argumentos = criar_parser(configuracao).parse_args([])

        self.assertEqual(argumentos.grupo_taxonomico, "Elasmobranchii")
        self.assertEqual(argumentos.tamanho_pagina, 80)


class TestTransformacaoPeixes(unittest.TestCase):
    def setUp(self):
        self.limite = gpd.GeoDataFrame(
            geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
            crs="EPSG:4326",
        )

    def test_normaliza_nome_aceito_e_hierarquia(self):
        normalizado, problema = normalizar_registro(registro_especie(1))

        self.assertIsNone(problema)
        self.assertEqual(normalizado["speciesKey"], "SP1")
        self.assertEqual(normalizado["family"], "Pimelodidae")
        self.assertEqual(normalizado["fishGroup"], "Actinopterygii")
        self.assertEqual(normalizado["datasetName"], "Dataset de teste")
        self.assertIn("creativecommons.org/licenses/by/4.0", normalizado["license"])

    def test_rejeita_identificacao_acima_de_especie(self):
        _, problema = normalizar_registro(registro_especie(1, rank="GENUS"))

        self.assertEqual(problema, "NOT_SPECIES_LEVEL:GENUS")

    def test_filtra_geografia_e_cria_tabela_de_especies(self):
        registros = [
            registro_especie(1, longitude=5),
            registro_especie(2, longitude=15),
        ]

        ocorrencias, especies, problemas, resumo = transformar_registros(
            registros, self.limite
        )

        self.assertEqual(ocorrencias["gbifID"].tolist(), [1])
        self.assertEqual(len(especies), 1)
        self.assertEqual(resumo["outside"], 1)
        self.assertTrue(problemas.empty)

    def test_converte_datas_com_formatos_mistos(self):
        primeiro = registro_especie(1)
        segundo = registro_especie(2)
        primeiro["eventDate"] = "2020-01-02"
        segundo["eventDate"] = "2021-03-04T12:30:00"

        ocorrencias, _, _, _ = transformar_registros([primeiro, segundo], self.limite)

        self.assertEqual(ocorrencias["year"].tolist(), [2020, 2021])
        self.assertEqual(ocorrencias["month"].tolist(), [1, 3])

    def test_classifica_origem_sem_inferir_ausencia(self):
        self.assertEqual(classificar_origem([]), "UNKNOWN")
        self.assertEqual(classificar_origem(["NATIVE"]), "NATIVE")
        self.assertEqual(classificar_origem(["INTRODUCED"]), "INTRODUCED")

    def test_referencia_oficial_complementa_status_de_origem(self):
        registro = registro_especie(1)
        referencia = pd.DataFrame(
            [
                {
                    "canonicalName": "Pimelodus maculatus",
                    "originStatus": "INTRODUCED",
                    "source": "Fonte oficial",
                    "sourceUrl": "https://example.org",
                    "scope": "Test",
                    "note": "Evidência de teste",
                }
            ]
        )

        _, especies, _, _ = transformar_registros([registro], self.limite, referencia)

        self.assertEqual(especies.iloc[0]["originStatus"], "INTRODUCED")
        self.assertEqual(especies.iloc[0]["originSource"], "Fonte oficial")

    def test_referencia_sem_nota_usa_nome_como_evidencia(self):
        registro = registro_especie(1)
        referencia = pd.DataFrame(
            [
                {
                    "canonicalName": "Pimelodus maculatus",
                    "originStatus": "INTRODUCED",
                    "source": "Fonte oficial",
                    "sourceUrl": "https://example.org",
                    "scope": "Test",
                    "note": pd.NA,
                }
            ]
        )

        _, especies, _, _ = transformar_registros([registro], self.limite, referencia)

        self.assertEqual(especies.iloc[0]["originEvidence"], "Pimelodus maculatus")


if __name__ == "__main__":
    unittest.main()
