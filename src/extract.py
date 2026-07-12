import requests
import pandas as pd

GBIF_API = "https://api.gbif.org/v1"


def buscar_especie(nome_cientifico):
    url = f"{GBIF_API}/species/match"
    parametros = {"name": nome_cientifico}

    resposta = requests.get(url, params=parametros, timeout=30)
    resposta.raise_for_status()

    return resposta.json()


def buscar_ocorrencias(taxon_key, limite=20):
    url = f"{GBIF_API}/occurrence/search"

    parametros = {
        "taxon_key": taxon_key,
        "country": "BR",
        "has_coordinate": "true",
        "limit": limite,
    }

    resposta = requests.get(url, params=parametros, timeout=30)
    resposta.raise_for_status()

    return resposta.json()


def main():
    especie = buscar_especie("Oreochromis niloticus")

    taxon_key = especie["usageKey"]

    print("Espécie encontrada:", especie["scientificName"])
    print("Taxon key:", taxon_key)

    dados = buscar_ocorrencias(taxon_key)

    registros = dados["results"]

    colunas = [
        "key",
        "scientificName",
        "decimalLatitude",
        "decimalLongitude",
        "eventDate",
        "stateProvince",
        "locality",
        "basisOfRecord",
    ]

    tabela = pd.DataFrame(registros)
    tabela = tabela.reindex(columns=colunas)

    tabela.to_csv(
        "data/raw/ocorrencias_tilapia.csv",
        index=False,
        encoding="utf-8",
    )

    print(f"\nForam coletados {len(tabela)} registros.")
    print(tabela.head())


if __name__ == "__main__":
    main()