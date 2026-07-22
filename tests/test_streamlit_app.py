import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEM_FONTE_LOCAL = (PROJECT_ROOT / ".env").exists() or (
    PROJECT_ROOT / "data" / "processed" / "ocorrencias_peixes_bacia_parana.csv"
).exists()
TEM_DADOS_SUICA = (
    PROJECT_ROOT / "data" / "processed" / "ocorrencias_peixes_ch.csv"
).exists() and (PROJECT_ROOT / "data" / "processed" / "especies_peixes_ch.csv").exists()


@unittest.skipUnless(
    TEM_FONTE_LOCAL,
    "Dashboard exige PostgreSQL configurado ou CSVs processados.",
)
class TestStreamlitApp(unittest.TestCase):
    def test_renderiza_dashboard_sem_excecoes(self):
        app = AppTest.from_file(
            str(PROJECT_ROOT / "app" / "app.py"), default_timeout=90
        )

        app.run()

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Peixes da Bacia do Paraná")
        self.assertEqual(
            [aba.label for aba in app.tabs],
            ["Visão geral", "Distribuição", "Qualidade", "Dados"],
        )
        metricas = {metrica.label: metrica.value for metrica in app.metric}
        self.assertEqual(metricas["Ocorrências"], "3.792")
        self.assertEqual(metricas["Espécies"], "356")
        self.assertEqual(app.selectbox[0].label, "País")
        self.assertEqual(app.selectbox[0].value, "BR")

        opcoes_especies = app.multiselect[0].options
        self.assertGreaterEqual(len(opcoes_especies), 2)
        app.multiselect[0].set_value(opcoes_especies[:2]).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.multiselect[0].value), 2)
        app.selectbox[0].set_value("CH").run()

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Ocorrências de peixes — Suíça")
        if TEM_DADOS_SUICA:
            metricas_suica = {metrica.label: metrica.value for metrica in app.metric}
            self.assertEqual(metricas_suica["Ocorrências"], "4.802")
            self.assertEqual(metricas_suica["Espécies"], "61")
            self.assertEqual(len(app.multiselect[0].options), 61)
            self.assertFalse(app.info)
        else:
            self.assertTrue(any("Suíça (CH)" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
