import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import psycopg

from src.load import (
    ARQUIVO_SCHEMA,
    carregar_registros,
    criar_comandos_schema,
    preparar_ocorrencias,
    preparar_paises,
    preparar_taxa,
    validar_referencias,
    validar_schema,
    verificar_carga,
)
from src.query_db import criar_consultas, executar_consulta


def tabela_taxa():
    return pd.DataFrame(
        [
            {
                "speciesKey": "SP1",
                "scientificName": "Species alpha Author, 1900",
                "acceptedScientificName": "Species alpha Author, 1900",
                "canonicalName": "Species alpha",
                "taxonomicStatus": "ACCEPTED",
                "kingdom": "Animalia",
                "phylum": "Chordata",
                "fishGroup": "Actinopterygii",
                "class": "Teleostei",
                "order": "Testiformes",
                "family": "Testidae",
                "genus": "Species",
                "species": "Species alpha",
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


def tabela_ocorrencias(taxon_key="SP1", country_code="BR", gbif_key=10):
    return pd.DataFrame(
        [
            {
                "gbifID": gbif_key,
                "speciesKey": taxon_key,
                "countryCode": country_code,
                "scientificName": "Species alpha Author, 1900",
                "taxonomicStatus": "ACCEPTED",
                "decimalLatitude": -23.5,
                "decimalLongitude": -51.5,
                "eventDate": "2020-02-03T10:30:00Z",
                "eventDateOriginal": "2020-02-03",
                "year": 2020,
                "month": 2,
                "stateProvince": "Parana",
                "locality": pd.NA,
                "basisOfRecord": "PRESERVED_SPECIMEN",
                "datasetKey": "dataset-1",
                "datasetName": "Dataset de teste",
                "publishingOrgKey": "org-1",
                "institutionCode": "TEST",
                "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
                "references": "https://example.org/occurrence/10",
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
    def test_cria_modelo_multicountry_com_chaves_relacionamentos_e_indices(self):
        comandos = "\n".join(criar_comandos_schema("biodiversity"))

        self.assertTrue(ARQUIVO_SCHEMA.exists())
        self.assertEqual(validar_schema("biodiversity_2"), "biodiversity_2")
        for tabela in ("countries", "taxa", "occurrences", "data_imports"):
            self.assertIn(f"biodiversity.{tabela}", comandos)
        self.assertIn("taxon_key TEXT PRIMARY KEY", comandos)
        self.assertIn("gbif_key BIGINT PRIMARY KEY", comandos)
        self.assertIn("REFERENCES biodiversity.taxa(taxon_key)", comandos)
        self.assertIn("REFERENCES biodiversity.countries(iso_code)", comandos)
        self.assertIn("idx_occurrences_country", comandos)
        self.assertIn("idx_occurrences_taxon", comandos)
        self.assertIn("idx_occurrences_year", comandos)
        self.assertIn("RENAME TO taxa", comandos)
        with self.assertRaises(ValueError):
            validar_schema("biodiversity; DROP TABLE taxa")

    def test_prepara_taxa_ocorrencia_pais_data_e_booleano(self):
        taxon = preparar_taxa(tabela_taxa())[0]
        ocorrencia = preparar_ocorrencias(tabela_ocorrencias())[0]
        paises = preparar_paises([ocorrencia])

        self.assertEqual(taxon["taxon_key"], "SP1")
        self.assertEqual(taxon["kingdom"], "Animalia")
        self.assertIsNone(taxon["iucn_category"])
        self.assertEqual(ocorrencia["gbif_key"], 10)
        self.assertEqual(ocorrencia["taxon_key"], "SP1")
        self.assertEqual(ocorrencia["country_code"], "BR")
        self.assertEqual(ocorrencia["date_precision"], "DAY")
        self.assertIsNone(ocorrencia["locality"])
        self.assertTrue(ocorrencia["inside_basin"])
        self.assertEqual(ocorrencia["dataset_name"], "Dataset de teste")
        self.assertIsNotNone(ocorrencia["event_date"].tzinfo)
        self.assertEqual(paises, [{"iso_code": "BR", "name": "Brasil"}])

    def test_rejeita_referencia_orfa(self):
        taxa = preparar_taxa(tabela_taxa())
        ocorrencias = preparar_ocorrencias(tabela_ocorrencias("SP2"))

        with self.assertRaisesRegex(ValueError, "taxa ausentes"):
            validar_referencias(taxa, ocorrencias)

    def test_aceita_coordenada_nula_e_rejeita_gbif_duplicada(self):
        sem_coordenada = tabela_ocorrencias()
        sem_coordenada.loc[0, "decimalLatitude"] = pd.NA
        ocorrencia = preparar_ocorrencias(sem_coordenada)[0]
        self.assertIsNone(ocorrencia["latitude"])

        duplicadas = pd.concat(
            [tabela_ocorrencias(), tabela_ocorrencias()], ignore_index=True
        )
        with self.assertRaisesRegex(ValueError, "gbif_key duplicada"):
            preparar_ocorrencias(duplicadas)

    def test_carrega_upserts_e_registra_importacao(self):
        conexao = ConexaoFalsa()
        taxa = preparar_taxa(tabela_taxa())
        ocorrencias = preparar_ocorrencias(tabela_ocorrencias())
        with tempfile.TemporaryDirectory() as pasta:
            caminho_taxa = Path(pasta) / "taxa.csv"
            caminho_ocorrencias = Path(pasta) / "occurrences.csv"
            caminho_taxa.write_text("taxa", encoding="utf-8")
            caminho_ocorrencias.write_text("occurrences", encoding="utf-8")

            resultado = carregar_registros(
                conexao,
                taxa,
                ocorrencias,
                "biodiversity",
                1,
                caminho_taxa,
                caminho_ocorrencias,
            )

        self.assertEqual(
            resultado,
            {"countries": 1, "taxa": 1, "occurrences": 1, "imports": 1},
        )
        lotes = conexao.cursores[1].lotes
        self.assertEqual(len(lotes), 4)
        self.assertIn("ON CONFLICT (iso_code)", lotes[0][0])
        self.assertIn("ON CONFLICT (taxon_key)", lotes[1][0])
        self.assertIn("ON CONFLICT (gbif_key)", lotes[2][0])
        self.assertIn("data_imports", lotes[3][0])
        self.assertEqual(lotes[3][1][0]["country_code"], "BR")
        self.assertEqual(lotes[3][1][0]["taxon_key"], "SP1")
        self.assertEqual(lotes[3][1][0]["status"], "COMPLETED")

    def test_registra_uma_importacao_por_pais(self):
        ocorrencias = preparar_ocorrencias(
            pd.concat(
                [
                    tabela_ocorrencias(country_code="BR", gbif_key=10),
                    tabela_ocorrencias(country_code="CH", gbif_key=11),
                ],
                ignore_index=True,
            )
        )
        paises = preparar_paises(ocorrencias)

        self.assertEqual(
            paises,
            [
                {"iso_code": "BR", "name": "Brasil"},
                {"iso_code": "CH", "name": "Suíça"},
            ],
        )


class TestConsultasPostgreSQL(unittest.TestCase):
    def test_catalogo_usa_tabelas_e_colunas_novas(self):
        consultas = criar_consultas("biodiversity")

        self.assertEqual(
            set(consultas), {"resumo", "ranking", "anos", "meses", "origens", "especie"}
        )
        self.assertIn("biodiversity.taxa", consultas["resumo"])
        self.assertIn("taxon_key", consultas["ranking"])
        self.assertIn("country_code", consultas["ranking"])
        self.assertIn("country_code", consultas["anos"])
        self.assertIn("gbif_key", consultas["especie"])
        self.assertIn("ILIKE %s", consultas["especie"])

    def test_consulta_especie_parametriza_termo_e_limite(self):
        cursor = CursorFalso([{"gbif_key": 10}])

        resultado = executar_consulta(
            cursor, "especie", "biodiversity", limite=5, termo="alpha"
        )

        self.assertEqual(resultado, [{"gbif_key": 10}])
        self.assertEqual(cursor.executados[0][1], ("%alpha%", 5))


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL nao definida; teste PostgreSQL real ignorado.",
)
class TestIntegracaoPostgreSQL(unittest.TestCase):
    def test_carga_real_em_transacao_reversivel(self):
        conexao = psycopg.connect(os.environ["TEST_DATABASE_URL"])
        try:
            taxa = preparar_taxa(tabela_taxa())
            ocorrencias = preparar_ocorrencias(tabela_ocorrencias())
            with tempfile.TemporaryDirectory() as pasta:
                caminho_taxa = Path(pasta) / "taxa.csv"
                caminho_ocorrencias = Path(pasta) / "occurrences.csv"
                caminho_taxa.write_text("taxa", encoding="utf-8")
                caminho_ocorrencias.write_text("occurrences", encoding="utf-8")
                carregar_registros(
                    conexao,
                    taxa,
                    ocorrencias,
                    "biodiversity_test",
                    100,
                    caminho_taxa,
                    caminho_ocorrencias,
                )
            verificacao = verificar_carga(conexao, "biodiversity_test")
            self.assertEqual(verificacao["orphans"], 0)
            self.assertGreaterEqual(verificacao["countries"], 1)
            self.assertGreaterEqual(verificacao["taxa"], 1)
            self.assertGreaterEqual(verificacao["occurrences"], 1)
            self.assertGreaterEqual(verificacao["imports"], 1)
        finally:
            conexao.rollback()
            conexao.close()


if __name__ == "__main__":
    unittest.main()
