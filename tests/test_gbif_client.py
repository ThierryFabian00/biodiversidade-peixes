import unittest
from unittest.mock import Mock

import requests

from src.config import TIMEOUT_GBIF_SEGUNDOS
from src.gbif_client import ErroGBIF, criar_sessao, requisitar_json


class TestClienteGBIF(unittest.TestCase):
    def test_configura_retentativas_com_backoff(self):
        sessao = criar_sessao(tentativas=4, backoff=1.25)
        retentativas = sessao.get_adapter("https://").max_retries

        self.assertEqual(retentativas.total, 4)
        self.assertEqual(retentativas.backoff_factor, 1.25)
        self.assertIn(503, retentativas.status_forcelist)

    def test_converte_timeout_em_erro_controlado(self):
        sessao = Mock()
        sessao.get.side_effect = requests.Timeout()

        with self.assertRaisesRegex(ErroGBIF, "tempo limite"):
            requisitar_json(sessao, "https://api.gbif.org/v1/test", {})

        sessao.get.assert_called_once_with(
            "https://api.gbif.org/v1/test",
            params={},
            timeout=TIMEOUT_GBIF_SEGUNDOS,
        )


if __name__ == "__main__":
    unittest.main()
