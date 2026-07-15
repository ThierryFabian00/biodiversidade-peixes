import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import psycopg

from src.load import (
    carregar_registros,
    criar_comandos_schema,
    preparar_especies,
    preparar_ocorrencias,
    validar_referencias,
    validar_schema,
    verificar_carga,
)
from src.query_db import criar_consultas, executar_consulta


def tabela_especies():
    return pd.DataFrame(
        [
            {
                "speciesKey": "SP1",
                "acceptedScientificName": "Species alpha Author, 1900",
                "canonicalName": "Species alpha",
                "fishGroup": "Actinopterygii",
                "class": "Teleostei",
                "order": "Testiformes",
                "family": "Testidae",
                "genus": "Species",
                "iucnCategory": pd.NA,
                "occurrenceCount": 1,
                "firstYear": 2020,
                "lastYear": 2020,
                "originStatus": "UNKNOWN",
                "originEvidence": pd.NA,
                "originSource": pd.NA,
                "originSourceUrl": pd.NA,
                "originScope": pd.NA,
                "taxonomicIssueCount": 0,
            }
        ]
    )


def tabela_ocorrencias(species_key="SP1"):
    return pd.DataFrame(
        [
            {
                "gbifID": 10,
                "speciesKey": species_key,
                "scientificName": "Species alpha Author, 1900",
                "taxonomicStatus": "ACCEPTED",
                "decimalLatitude": -23.5,
                "decimalLongitude": -51.5,
                "eventDate": "2020-02-03T10:30:00Z",
                "eventDateOriginal": "2020-02-03T10:30:00",
                "year": 2020,
                "month": 2,
                "stateProvince": "Parana",
                "locality": pd.NA,
                "basisOfRecord": "PRESERVED_SPECIMEN",
                "datasetKey": "dataset-1",
                "occurrenceStatus": "PRESENT",
                "establishmentMeans": pd.NA,
                "degreeOfEstablishment": pd.NA,
                "taxonomicIssues": pd.NA,
                "occurrenceIssues": "TEST_ISSUE",
                "insideBasin": "true",
            }
        ]
    )


class CursorFalso:
    def __init__(self, resultados=None):
        self.executados = []
        self.lotes = []
        self.resultados = resultados or []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, comando, parametros=None):
        self.executados.append((str(comando), parametros))

    def executemany(self, comando, parametros):
        self.lotes.append((str(comando), list(parametros)))

    def fetchall(self):
        return self.resultados


class ConexaoFalsa:
    def __init__(self):
        self.cursores = []

    def cursor(self):
        cursor = CursorFalso()
        self.cursores.append(cursor)
        return cursor


class TestModeloPostgreSQL(unittest.TestCase):
    def test_valida_schema_e_cria_restricoes(self):
        comandos = "\n".join(criar_comandos_schema("biodiversity"))

        self.assertEqual(validar_schema("biodiversity_2"), "biodiversity_2")
        self.assertIn("PRIMARY KEY", comandos)
        self.assertIn("REFERENCES biodiversity.species", comandos)
        self.assertIn("CREATE OR REPLACE VIEW", comandos)
        with self.assertRaises(ValueError):
            validar_schema("biodiversity; DROP TABLE species")

    def test_prepara_tipos_nulos_data_e_booleano(self):
        especie = preparar_especies(tabela_especies())[0]
        ocorrencia = preparar_ocorrencias(tabela_ocorrencias())[0]

        self.assertIsNone(especie["iucn_category"])
        self.assertIsNone(ocorrencia["locality"])
        self.assertTrue(ocorrencia["inside_basin"])
        self.assertEqual(ocorrencia["event_date"].year, 2020)
        self.assertIsNotNone(ocorrencia["event_date"].tzinfo)

    def test_rejeita_referencia_orfa(self):
        especies = preparar_especies(tabela_especies())
        ocorrencias = preparar_ocorrencias(tabela_ocorrencias("SP2"))

        with self.assertRaisesRegex(ValueError, "especies ausentes"):
            validar_referencias(especies, ocorrencias)

    def test_rejeita_coordenada_nula_antes_do_banco(self):
        dados = tabela_ocorrencias()
        dados.loc[0, "decimalLatitude"] = pd.NA

        with self.assertRaisesRegex(ValueError, "decimalLatitude"):
            preparar_ocorrencias(dados)

    def test_carrega_em_lotes_e_registra_auditoria(self):
        conexao = ConexaoFalsa()
        especies = preparar_especies(tabela_especies())
        ocorrencias = preparar_ocorrencias(tabela_ocorrencias())
        with tempfile.TemporaryDirectory() as pasta:
            caminho_especies = Path(pasta) / "species.csv"
            caminho_ocorrencias = Path(pasta) / "occurrences.csv"
            caminho_especies.write_text("species", encoding="utf-8")
            caminho_ocorrencias.write_text("occurrences", encoding="utf-8")

            resultado = carregar_registros(
                conexao,
                especies,
                ocorrencias,
                "biodiversity",
                1,
                caminho_especies,
                caminho_ocorrencias,
            )

        self.assertEqual(resultado, {"species": 1, "occurrences": 1})
        self.assertEqual(len(conexao.cursores[1].lotes), 2)
        self.assertIn("ON CONFLICT (species_key)", conexao.cursores[1].lotes[0][0])
        self.assertIn("load_runs", conexao.cursores[1].executados[-1][0])


class TestConsultasPostgreSQL(unittest.TestCase):
    def test_catalogo_contem_consultas_principais(self):
        consultas = criar_consultas("biodiversity")

        self.assertEqual(
            set(consultas), {"resumo", "ranking", "anos", "meses", "origens", "especie"}
        )
        self.assertIn("ILIKE %s", consultas["especie"])

    def test_consulta_especie_parametriza_termo_e_limite(self):
        cursor = CursorFalso([{"gbif_id": 10}])

        resultado = executar_consulta(
            cursor, "especie", "biodiversity", limite=5, termo="alpha"
        )

        self.assertEqual(resultado, [{"gbif_id": 10}])
        self.assertEqual(cursor.executados[0][1], ("%alpha%", 5))


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL nao definida; teste PostgreSQL real ignorado.",
)
class TestIntegracaoPostgreSQL(unittest.TestCase):
    def test_carga_real_em_transacao_reversivel(self):
        conexao = psycopg.connect(os.environ["TEST_DATABASE_URL"])
        try:
            especies = preparar_especies(tabela_especies())
            ocorrencias = preparar_ocorrencias(tabela_ocorrencias())
            with tempfile.TemporaryDirectory() as pasta:
                caminho_especies = Path(pasta) / "species.csv"
                caminho_ocorrencias = Path(pasta) / "occurrences.csv"
                caminho_especies.write_text("species", encoding="utf-8")
                caminho_ocorrencias.write_text("occurrences", encoding="utf-8")
                carregar_registros(
                    conexao,
                    especies,
                    ocorrencias,
                    "biodiversity_test",
                    100,
                    caminho_especies,
                    caminho_ocorrencias,
                )
            verificacao = verificar_carga(conexao, "biodiversity_test")
            self.assertEqual(verificacao["orphans"], 0)
            self.assertGreaterEqual(verificacao["occurrences"], 1)
        finally:
            conexao.rollback()
            conexao.close()


if __name__ == "__main__":
    unittest.main()
