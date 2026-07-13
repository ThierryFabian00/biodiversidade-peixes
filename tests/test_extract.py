import unittest
from unittest.mock import Mock

from src.extract import buscar_especie, buscar_ocorrencias


def criar_resposta(dados):
    resposta = Mock()
    resposta.json.return_value = dados
    resposta.raise_for_status.return_value = None
    return resposta


class TestBuscarEspecie(unittest.TestCase):
    def test_retorna_especie_correspondente(self):
        sessao = Mock()
        sessao.get.return_value = criar_resposta(
            {"usageKey": 2, "scientificName": "Oreochromis niloticus"}
        )

        especie = buscar_especie("Oreochromis niloticus", sessao)

        self.assertEqual(especie["usageKey"], 2)
        sessao.get.assert_called_once()

    def test_rejeita_especie_sem_usage_key(self):
        sessao = Mock()
        sessao.get.return_value = criar_resposta({"matchType": "NONE"})

        with self.assertRaisesRegex(ValueError, "não encontrada"):
            buscar_especie("Especie inexistente", sessao)


class TestBuscarOcorrencias(unittest.TestCase):
    def test_percorre_paginas_ate_o_fim(self):
        sessao = Mock()
        sessao.get.side_effect = [
            criar_resposta(
                {
                    "count": 3,
                    "endOfRecords": False,
                    "results": [{"key": 1}, {"key": 2}],
                }
            ),
            criar_resposta(
                {
                    "count": 3,
                    "endOfRecords": True,
                    "results": [{"key": 3}],
                }
            ),
        ]

        resultado = buscar_ocorrencias(2, tamanho_pagina=2, sessao=sessao)

        self.assertEqual([item["key"] for item in resultado.registros], [1, 2, 3])
        self.assertEqual(resultado.paginas_consultadas, 2)
        self.assertEqual(resultado.total_disponivel, 3)
        self.assertEqual(sessao.get.call_args_list[1].kwargs["params"]["offset"], 2)

    def test_respeita_limite_total_sem_chamada_extra(self):
        sessao = Mock()
        sessao.get.side_effect = [
            criar_resposta(
                {
                    "count": 10,
                    "endOfRecords": False,
                    "results": [{"key": 1}, {"key": 2}],
                }
            ),
            criar_resposta(
                {
                    "count": 10,
                    "endOfRecords": False,
                    "results": [{"key": 3}],
                }
            ),
        ]

        resultado = buscar_ocorrencias(
            2,
            tamanho_pagina=2,
            max_registros=3,
            sessao=sessao,
        )

        self.assertEqual(len(resultado.registros), 3)
        self.assertEqual(sessao.get.call_count, 2)
        self.assertEqual(sessao.get.call_args_list[1].kwargs["params"]["limit"], 1)

    def test_rejeita_resposta_sem_lista_de_resultados(self):
        sessao = Mock()
        sessao.get.return_value = criar_resposta({"count": 1})

        with self.assertRaisesRegex(ValueError, "results"):
            buscar_ocorrencias(2, sessao=sessao)

    def test_valida_tamanho_da_pagina(self):
        with self.assertRaisesRegex(ValueError, "entre 1 e 300"):
            buscar_ocorrencias(2, tamanho_pagina=301)

    def test_orienta_download_quando_resultado_excede_limite_da_busca(self):
        sessao = Mock()
        sessao.get.return_value = criar_resposta(
            {
                "count": 100_001,
                "endOfRecords": False,
                "results": [{"key": 1}],
            }
        )

        with self.assertRaisesRegex(ValueError, "serviço de download"):
            buscar_ocorrencias(2, sessao=sessao)


if __name__ == "__main__":
    unittest.main()
