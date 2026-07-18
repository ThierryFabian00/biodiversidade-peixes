import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import (
    ESPECIE_PADRAO,
    GRUPO_TAXONOMICO,
    LIMITE_PADRAO,
    PAIS_PADRAO,
    ConfiguracaoAplicacao,
)
from src.database import ConfiguracaoBanco, validar_schema
from src.extract import criar_parser
from src.services.country_service import normalizar_codigo_pais
from src.services.occurrence_service import ParametrosConsultaOcorrencia

ENV_INEXISTENTE = Path("arquivo-inexistente.env")


class TestConfiguracaoAplicacao(unittest.TestCase):
    def test_mantem_valores_padrao_sem_ambiente(self):
        with patch.dict(os.environ, {}, clear=True):
            configuracao = ConfiguracaoAplicacao.do_ambiente(ENV_INEXISTENTE)

        self.assertEqual(configuracao.pais_padrao, PAIS_PADRAO)
        self.assertEqual(configuracao.especie_padrao, ESPECIE_PADRAO)
        self.assertEqual(configuracao.limite_padrao, LIMITE_PADRAO)
        self.assertEqual(configuracao.grupo_taxonomico, GRUPO_TAXONOMICO)

    def test_le_parametros_do_ambiente(self):
        ambiente = {
            "PAIS_PADRAO": "CH",
            "ESPECIE_PADRAO": "Salmo trutta",
            "LIMITE_PADRAO": "120",
            "GRUPO_TAXONOMICO": "Actinopterygii",
            "GBIF_API": "https://example.test/v1/",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            configuracao = ConfiguracaoAplicacao.do_ambiente(ENV_INEXISTENTE)

        self.assertEqual(configuracao.pais_padrao, "CH")
        self.assertEqual(configuracao.especie_padrao, "Salmo trutta")
        self.assertEqual(configuracao.limite_padrao, 120)
        self.assertEqual(configuracao.gbif_api, "https://example.test/v1")

    def test_parser_usa_pais_especie_e_limite_configurados(self):
        configuracao = ConfiguracaoAplicacao(
            pais_padrao="CH",
            especie_padrao="Salmo trutta",
            limite_padrao=120,
        )
        argumentos = criar_parser(configuracao).parse_args([])

        self.assertEqual(argumentos.pais, "CH")
        self.assertEqual(argumentos.especie, "Salmo trutta")
        self.assertEqual(argumentos.tamanho_pagina, 120)

    def test_rejeita_limite_invalido(self):
        with patch.dict(os.environ, {"LIMITE_PADRAO": "zero"}, clear=True):
            with self.assertRaisesRegex(ValueError, "inteiro"):
                ConfiguracaoAplicacao.do_ambiente(ENV_INEXISTENTE)


class TestConfiguracaoBanco(unittest.TestCase):
    def test_carrega_url_e_valida_schema(self):
        ambiente = {
            "DATABASE_URL": "postgresql://localhost/teste",
            "DB_SCHEMA": "biodiversity_v2",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            configuracao = ConfiguracaoBanco.do_ambiente(ENV_INEXISTENTE)

        self.assertEqual(configuracao.exigir_url(), ambiente["DATABASE_URL"])
        self.assertEqual(configuracao.schema, "biodiversity_v2")

    def test_exige_url(self):
        with patch.dict(os.environ, {}, clear=True):
            configuracao = ConfiguracaoBanco.do_ambiente(ENV_INEXISTENTE)

        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            configuracao.exigir_url()

    def test_rejeita_schema_inseguro(self):
        with self.assertRaises(ValueError):
            validar_schema("public; DROP TABLE taxa")


class TestServicosConsulta(unittest.TestCase):
    def test_normaliza_codigo_iso(self):
        self.assertEqual(normalizar_codigo_pais(" ch "), "CH")

    def test_rejeita_codigo_iso_invalido(self):
        with self.assertRaisesRegex(ValueError, "ISO"):
            normalizar_codigo_pais("Brasil")

    def test_monta_parametros_da_api(self):
        consulta = ParametrosConsultaOcorrencia(
            taxon_key=123,
            pais=" ch ",
            tamanho_pagina=100,
            max_registros=200,
        )

        self.assertEqual(
            consulta.parametros_api(offset=50, limite=100),
            {
                "taxon_key": 123,
                "country": "CH",
                "has_coordinate": "true",
                "limit": 100,
                "offset": 50,
            },
        )

    def test_rejeita_limites_fora_da_api(self):
        with self.assertRaisesRegex(ValueError, "100000"):
            ParametrosConsultaOcorrencia(123, max_registros=100_001)


if __name__ == "__main__":
    unittest.main()
