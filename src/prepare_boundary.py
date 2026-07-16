import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import requests
import truststore

truststore.inject_into_ssl()

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_FONTE = PASTA_PROJETO / "data" / "geographic" / "ibge_dhn250_2021"
ARQUIVO_ZIP = PASTA_FONTE / "macro_RH.zip"
ARQUIVO_FONTE = PASTA_FONTE / "macro_RH.shp"
ARQUIVO_LIMITE = PASTA_PROJETO / "data" / "geographic" / "bacia_parana_brasil.gpkg"

URL_BASE = (
    "https://geoftp.ibge.gov.br/informacoes_ambientais/estudos_ambientais/"
    "bacias_e_divisoes_hidrograficas_do_brasil/2021/"
    "Divisao_Hidrografica_Nacional_DHN250/vetores"
)
URL_FONTE = f"{URL_BASE}/macro_RH.zip"
URL_DOCUMENTACAO = f"{URL_BASE}/Documentacao_Tecnica_DHN250.pdf"
CODIGO_PARANA = "111"


def baixar_arquivo(url: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(f"{destino.suffix}.part")

    try:
        with requests.get(url, stream=True, timeout=120) as resposta:
            resposta.raise_for_status()
            with temporario.open("wb") as arquivo:
                for bloco in resposta.iter_content(chunk_size=1024 * 1024):
                    if bloco:
                        arquivo.write(bloco)
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)


def garantir_fonte(forcar_download: bool = False) -> Path:
    if forcar_download or not ARQUIVO_ZIP.exists():
        print(f"Baixando camada oficial do IBGE: {URL_FONTE}")
        baixar_arquivo(URL_FONTE, ARQUIVO_ZIP)

    if forcar_download or not ARQUIVO_FONTE.exists():
        with zipfile.ZipFile(ARQUIVO_ZIP) as arquivo_zip:
            arquivo_zip.extractall(PASTA_FONTE)

    if not ARQUIVO_FONTE.exists():
        raise FileNotFoundError(
            f"O shapefile esperado não foi encontrado: {ARQUIVO_FONTE}"
        )

    return ARQUIVO_FONTE


def selecionar_regiao(
    regioes: gpd.GeoDataFrame,
    codigo: str = CODIGO_PARANA,
) -> gpd.GeoDataFrame:
    if regioes.crs is None:
        raise ValueError("A camada de regiões hidrográficas não possui CRS.")
    if "cd_macroRH" not in regioes.columns:
        raise ValueError("A camada não possui a coluna 'cd_macroRH'.")

    selecionada = regioes[regioes["cd_macroRH"].astype("string") == codigo].copy()

    if len(selecionada) != 1:
        raise ValueError(
            f"Era esperada uma região com código {codigo}; "
            f"foram encontradas {len(selecionada)}."
        )
    if not selecionada.geometry.is_valid.all():
        raise ValueError("A geometria selecionada para a região é inválida.")

    return selecionada


def preparar_limite(caminho_fonte: Path, caminho_saida: Path) -> gpd.GeoDataFrame:
    regioes = gpd.read_file(caminho_fonte, engine="fiona")
    parana = selecionar_regiao(regioes)
    parana = parana.to_crs("EPSG:4326")
    colunas = ["cd_macroRH", "nm_macroRH", "area", "geometry"]
    parana = parana[colunas]

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    caminho_saida.unlink(missing_ok=True)
    parana.to_file(
        caminho_saida,
        layer="bacia_parana_brasil",
        driver="GPKG",
        engine="fiona",
    )

    metadados = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "title": "Região Hidrográfica do Paraná - porção brasileira",
        "sourceInstitution": "IBGE",
        "sourceDataset": "Divisão Hidrográfica Nacional DHN250",
        "sourceVersion": 2021,
        "sourceScale": "1:250000",
        "sourceUrl": URL_FONTE,
        "documentationUrl": URL_DOCUMENTACAO,
        "sourceCrs": str(regioes.crs),
        "outputCrs": str(parana.crs),
        "regionCode": CODIGO_PARANA,
        "regionName": parana.iloc[0]["nm_macroRH"],
        "areaSquareKilometers": float(parana.iloc[0]["area"]),
        "license": (
            "Dados abertos do IBGE. Reutilização com atribuição da fonte, "
            "conforme a Política de Dados Abertos do Governo Federal."
        ),
    }
    caminho_metadados = caminho_saida.with_name(f"{caminho_saida.stem}_metadata.json")
    caminho_metadados.write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return parana


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara o limite brasileiro da Região Hidrográfica Paraná."
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=ARQUIVO_LIMITE,
        help="Caminho do GeoPackage derivado.",
    )
    parser.add_argument(
        "--forcar-download",
        action="store_true",
        help="Baixa novamente a camada oficial mesmo se ela já existir.",
    )
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    fonte = garantir_fonte(argumentos.forcar_download)
    parana = preparar_limite(fonte, argumentos.saida)

    print(f"Limite preparado em: {argumentos.saida}")
    print(f"CRS de saída: {parana.crs}")
    print(f"Área informada pelo IBGE: {parana.iloc[0]['area']:.2f} km²")


if __name__ == "__main__":
    main()
