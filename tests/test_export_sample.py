import unittest

import pandas as pd

from src.export_sample import selecionar_amostra


def criar_registro(chave, especie, dataset, licenca):
    return {
        "gbifID": chave,
        "canonicalName": especie,
        "eventDate": "2024-01-01",
        "stateProvince": "Parana",
        "basisOfRecord": "OBSERVATION",
        "decimalLatitude": -23,
        "decimalLongitude": -51,
        "datasetKey": dataset,
        "datasetName": f"Dataset {dataset}",
        "publishingOrgKey": f"Org {dataset}",
        "institutionCode": dataset,
        "license": licenca,
        "references": f"https://example.org/{chave}",
    }


class TestExportarAmostra(unittest.TestCase):
    def test_exclui_by_nc_e_preserva_atribuicao(self):
        dados = pd.DataFrame(
            [
                criar_registro(
                    1,
                    "Species alpha",
                    "A",
                    "http://creativecommons.org/licenses/by/4.0/legalcode",
                ),
                criar_registro(
                    2,
                    "Species beta",
                    "B",
                    "http://creativecommons.org/licenses/by-nc/4.0/legalcode",
                ),
                criar_registro(
                    3,
                    "Species gamma",
                    "C",
                    "http://creativecommons.org/publicdomain/zero/1.0/legalcode",
                ),
            ]
        )

        amostra = selecionar_amostra(dados)

        self.assertEqual(amostra["gbifID"].tolist(), [1, 3])
        self.assertEqual(set(amostra["licenseName"]), {"CC BY 4.0", "CC0 1.0"})
        self.assertTrue(
            amostra["gbifUrl"].str.startswith("https://www.gbif.org/").all()
        )

    def test_limita_especie_e_dataset(self):
        licenca = "http://creativecommons.org/licenses/by/4.0/legalcode"
        dados = pd.DataFrame(
            [
                criar_registro(1, "Species alpha", "A", licenca),
                criar_registro(2, "Species alpha", "A", licenca),
                criar_registro(3, "Species beta", "A", licenca),
                criar_registro(4, "Species gamma", "A", licenca),
                criar_registro(5, "Species delta", "B", licenca),
            ]
        )

        amostra = selecionar_amostra(dados, limite=10, maximo_por_dataset=2)

        self.assertEqual(amostra["canonicalName"].nunique(), len(amostra))
        self.assertLessEqual(amostra["datasetKey"].value_counts().max(), 2)


if __name__ == "__main__":
    unittest.main()
