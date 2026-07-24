import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.extract_fish import ResultadoPeixes
from src.sync_data import StatusCache, sincronizar_dados_pais


class TestSincronizacao(unittest.TestCase):
    @patch("src.sync_data.buscar_ocorrencias_peixes")
    @patch("src.sync_data._consultar_cache_com_estrutura")
    @patch("src.sync_data.psycopg.connect")
    def test_reutiliza_postgresql_sem_consultar_gbif(
        self, conectar, consultar_cache, buscar_gbif
    ):
        atualizado_em = datetime(2026, 7, 24, tzinfo=timezone.utc)
        consultar_cache.return_value = StatusCache("BR", 3764, 352, atualizado_em)

        resultado = sincronizar_dados_pais("postgresql://teste", "bio", "BR")

        self.assertEqual(resultado.fonte, "PostgreSQL")
        self.assertEqual(resultado.status_cache.atualizado_em, atualizado_em)
        buscar_gbif.assert_not_called()
        conectar.assert_called_once_with("postgresql://teste")

    @patch("src.sync_data.consultar_status_cache")
    @patch("src.sync_data.carregar_registros")
    @patch("src.sync_data.preparar_ocorrencias", return_value=[{"gbif_key": 1}])
    @patch("src.sync_data.preparar_taxa", return_value=[{"taxon_key": 10}])
    @patch("src.sync_data.salvar_tabelas")
    @patch("src.sync_data.transformar_registros")
    @patch("src.sync_data.buscar_ocorrencias_peixes")
    @patch("src.sync_data._consultar_cache_com_estrutura")
    @patch("src.sync_data.psycopg.connect")
    def test_atualizacao_forcada_coleta_e_recarrega_cache(
        self,
        conectar,
        consultar_cache_inicial,
        buscar_gbif,
        transformar,
        salvar_tabelas,
        preparar_taxa,
        preparar_ocorrencias,
        carregar,
        consultar_cache_final,
    ):
        vazio = StatusCache("CH", 0, 0, None)
        atualizado = StatusCache("CH", 1, 1, datetime(2026, 7, 24, tzinfo=timezone.utc))
        consultar_cache_inicial.return_value = vazio
        consultar_cache_final.return_value = atualizado
        buscar_gbif.return_value = ResultadoPeixes([{"key": 1}], 2, 100)
        transformar.return_value = (
            pd.DataFrame([{"gbifID": 1}]),
            pd.DataFrame([{"taxonKey": 10}]),
            pd.DataFrame(),
            {"normalized": 1},
        )
        eventos = []

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            caminhos = (
                raiz / "raw" / "ocorrencias.jsonl",
                raiz / "processed" / "ocorrencias.csv",
                raiz / "processed" / "taxa.csv",
                raiz / "processed" / "problemas.csv",
            )

            def salvar_resultado(*args):
                bruto = args[1]
                bruto.parent.mkdir(parents=True, exist_ok=True)
                bruto.with_name(f"{bruto.stem}_metadata.json").write_text(
                    json.dumps({"source": "GBIF"}), encoding="utf-8"
                )

            with (
                patch("src.sync_data._caminhos_pais", return_value=caminhos),
                patch("src.sync_data.salvar_resultado", side_effect=salvar_resultado),
                patch("src.sync_data._carregar_referencia", return_value=None),
            ):
                resultado = sincronizar_dados_pais(
                    "postgresql://teste",
                    "bio",
                    "CH",
                    forcar_atualizacao=True,
                    callback=eventos.append,
                )

        self.assertEqual(resultado.fonte, "GBIF")
        self.assertEqual(resultado.paginas_consultadas, 2)
        self.assertEqual(resultado.registros_salvos, 1)
        buscar_gbif.assert_called_once()
        carregar.assert_called_once()
        estatisticas = carregar.call_args.args[7]["CH"]
        self.assertEqual(estatisticas["records_received"], 1)
        self.assertEqual(estatisticas["records_rejected"], 0)
        self.assertEqual(estatisticas["records_rejected_taxonomy"], 0)
        salvar_tabelas.assert_called_once()
        self.assertEqual(eventos[0].etapa, "cache")
        self.assertEqual(eventos[-1].etapa, "concluido")


if __name__ == "__main__":
    unittest.main()
