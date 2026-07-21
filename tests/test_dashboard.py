import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.dashboard_data import (
    calcular_indicadores,
    carregar_csv,
    carregar_dados_dashboard,
    consulta_dashboard,
    distribuicao_origem,
    filtrar_ocorrencias,
    frequencia_alertas,
    indicadores_qualidade,
    normalizar_dados,
    ranking_especies,
    serie_temporal,
)


def dados_dashboard():
    return pd.DataFrame(
        [
            {
                "gbif_id": 1,
                "species_key": "A",
                "canonical_name": "Species alpha",
                "family": "Alphaidae",
                "order_name": "Alphaformes",
                "origin_status": "NATIVE",
                "iucn_category": "LC",
                "event_date": "2020-01-02T00:00:00Z",
                "event_year": 2020,
                "event_month": 1,
                "decimal_latitude": -23.0,
                "decimal_longitude": -51.0,
                "state_province": "ParanÃ¡",
                "locality": "Local A",
                "basis_of_record": "PRESERVED_SPECIMEN",
                "taxonomic_issues": "",
                "occurrence_issues": "COORDINATE_ROUNDED",
            },
            {
                "gbif_id": 2,
                "species_key": "B",
                "canonical_name": "Species beta",
                "family": "Betaidae",
                "order_name": "Betaformes",
                "origin_status": "INTRODUCED",
                "iucn_category": "LC",
                "event_date": "2021-03-04T00:00:00Z",
                "event_year": 2021,
                "event_month": 3,
                "decimal_latitude": -22.0,
                "decimal_longitude": -50.0,
                "state_province": "SP",
                "locality": pd.NA,
                "basis_of_record": "HUMAN_OBSERVATION",
                "taxonomic_issues": "TAXON_ID_NOT_FOUND",
                "occurrence_issues": "COORDINATE_ROUNDED|TAXON_ID_NOT_FOUND",
            },
            {
                "gbif_id": 3,
                "species_key": "A",
                "canonical_name": "Species alpha",
                "family": "Alphaidae",
                "order_name": "Alphaformes",
                "origin_status": "NATIVE",
                "iucn_category": "LC",
                "event_date": "2021-04-05T00:00:00Z",
                "event_year": 2021,
                "event_month": 4,
                "decimal_latitude": -21.0,
                "decimal_longitude": -49.0,
                "state_province": "Misiones",
                "locality": "Local C",
                "basis_of_record": "PRESERVED_SPECIMEN",
                "taxonomic_issues": "",
                "occurrence_issues": "",
            },
        ]
    )


class TestDadosDashboard(unittest.TestCase):
    def setUp(self):
        self.dados = normalizar_dados(dados_dashboard())

    def test_consulta_rejeita_schema_inseguro(self):
        self.assertIn("JOIN biodiversity.species", consulta_dashboard("biodiversity"))
        with self.assertRaises(ValueError):
            consulta_dashboard("biodiversity;drop")

    def test_normaliza_estado_e_flags_de_qualidade(self):
        self.assertEqual(
            self.dados["state_normalized"].tolist()[:2], ["Parana", "Sao Paulo"]
        )
        self.assertTrue(self.dados.loc[1, "missing_locality"])
        self.assertTrue(self.dados.loc[2, "unexpected_state"])
        self.assertEqual(self.dados["country_code"].unique().tolist(), ["BR"])
        self.assertEqual(self.dados["country_name"].unique().tolist(), ["Brasil"])

    def test_aplica_filtros_combinados(self):
        filtrados = filtrar_ocorrencias(
            self.dados,
            especies=["Species alpha"],
            origens=["NATIVE"],
            intervalo_anos=(2021, 2021),
            tipos=["PRESERVED_SPECIMEN"],
            estados=["Misiones"],
        )

        self.assertEqual(filtrados["gbif_id"].tolist(), [3])

    def test_calcula_resumos_do_recorte(self):
        indicadores = calcular_indicadores(self.dados)
        ranking = ranking_especies(self.dados)
        temporal = serie_temporal(self.dados)
        origens = distribuicao_origem(self.dados).set_index("origin_status")

        self.assertEqual(indicadores["occurrences"], 3)
        self.assertEqual(indicadores["species"], 2)
        self.assertEqual(indicadores["introduced_species"], 1)
        self.assertEqual(ranking.iloc[0]["canonical_name"], "Species alpha")
        self.assertEqual(int(temporal["occurrence_count"].sum()), 3)
        self.assertEqual(origens.loc["NATIVE", "species_count"], 1)

    def test_resume_qualidade_e_alertas(self):
        qualidade = indicadores_qualidade(self.dados)
        alertas = frequencia_alertas(self.dados, "occurrence_issues").set_index("issue")

        self.assertEqual(qualidade["missing_locality"], 1)
        self.assertEqual(qualidade["taxonomic_issue"], 1)
        self.assertEqual(alertas.loc["COORDINATE_ROUNDED", "record_count"], 2)

    def test_carrega_fallback_csv(self):
        ocorrencias = pd.DataFrame(
            [
                {
                    "gbifID": 1,
                    "speciesKey": "A",
                    "canonicalName": "Species alpha",
                    "eventDate": "2020-01-02",
                    "year": 2020,
                    "month": 1,
                    "decimalLatitude": -23,
                    "decimalLongitude": -51,
                    "stateProvince": "Parana",
                    "locality": "Local",
                    "basisOfRecord": "OBSERVATION",
                    "taxonomicIssues": "",
                    "occurrenceIssues": "",
                }
            ]
        )
        especies = pd.DataFrame(
            [
                {
                    "speciesKey": "A",
                    "family": "Alphaidae",
                    "order": "Alphaformes",
                    "originStatus": "NATIVE",
                    "iucnCategory": "LC",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho_ocorrencias = Path(pasta) / "occurrences.csv"
            caminho_especies = Path(pasta) / "species.csv"
            ocorrencias.to_csv(caminho_ocorrencias, index=False)
            especies.to_csv(caminho_especies, index=False)

            resultado = carregar_csv(caminho_ocorrencias, caminho_especies)

        self.assertEqual(resultado.loc[0, "canonical_name"], "Species alpha")
        self.assertEqual(resultado.loc[0, "origin_status"], "NATIVE")

    def test_seleciona_brasil_e_nao_mistura_base_legada_com_suica(self):
        ocorrencias = pd.DataFrame(
            [
                {
                    "gbifID": 1,
                    "speciesKey": "A",
                    "canonicalName": "Species alpha",
                    "eventDate": "2020-01-02",
                    "year": 2020,
                    "month": 1,
                    "decimalLatitude": -23,
                    "decimalLongitude": -51,
                    "stateProvince": "Parana",
                    "locality": "Local",
                    "basisOfRecord": "OBSERVATION",
                    "taxonomicIssues": "",
                    "occurrenceIssues": "",
                }
            ]
        )
        especies = pd.DataFrame(
            [
                {
                    "speciesKey": "A",
                    "family": "Alphaidae",
                    "order": "Alphaformes",
                    "originStatus": "NATIVE",
                    "iucnCategory": "LC",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho_ocorrencias = Path(pasta) / "occurrences.csv"
            caminho_especies = Path(pasta) / "species.csv"
            ocorrencias.to_csv(caminho_ocorrencias, index=False)
            especies.to_csv(caminho_especies, index=False)

            brasil = carregar_dados_dashboard(
                None,
                "biodiversity",
                caminho_ocorrencias,
                caminho_especies,
                codigo_pais="BR",
            )
            suica = carregar_dados_dashboard(
                None,
                "biodiversity",
                caminho_ocorrencias,
                caminho_especies,
                codigo_pais="CH",
            )

        self.assertEqual(brasil.pais_nome, "Brasil")
        self.assertEqual(brasil.dados["country_code"].tolist(), ["BR"])
        self.assertEqual(suica.pais_nome, "Suíça")
        self.assertTrue(suica.dados.empty)
        self.assertIn("Suíça (CH)", suica.aviso)


if __name__ == "__main__":
    unittest.main()
