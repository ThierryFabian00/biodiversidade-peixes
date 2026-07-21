import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEM_FONTE_LOCAL = (PROJECT_ROOT / ".env").exists() or (
    PROJECT_ROOT / "data" / "processed" / "ocorrencias_peixes_bacia_parana.csv"
).exists()


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

        app.selectbox[0].set_value("CH").run()

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Ocorrências de peixes — Suíça")
        self.assertTrue(any("Suíça (CH)" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
