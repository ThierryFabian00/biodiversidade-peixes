import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib
import pandas as pd

matplotlib.use("Agg")
from matplotlib import pyplot as plt

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_ENTRADA = (
    PASTA_PROJETO / "data" / "processed" / "ocorrencias_tilapia_limpo.csv"
)
ARQUIVO_LIMITE = (
    PASTA_PROJETO / "data" / "geographic" / "bacia_parana_brasil.gpkg"
)
ARQUIVO_SAIDA = (
    PASTA_PROJETO
    / "data"
    / "processed"
    / "ocorrencias_tilapia_bacia_parana.csv"
)
ARQUIVO_MAPA = (
    PASTA_PROJETO / "data" / "processed" / "validacao_bacia_parana.png"
)


def carregar_limite(caminho: Path) -> gpd.GeoDataFrame:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Limite geográfico não encontrado: {caminho}. "
            "Execute src/prepare_boundary.py primeiro."
        )
    return gpd.read_file(caminho, engine="fiona")


def criar_pontos(dados: pd.DataFrame) -> gpd.GeoDataFrame:
    colunas = {"decimalLatitude", "decimalLongitude"}
    ausentes = colunas.difference(dados.columns)
    if ausentes:
        raise ValueError(
            f"Colunas de coordenadas ausentes: {', '.join(sorted(ausentes))}"
        )

    pontos = dados.copy()
    pontos["decimalLatitude"] = pd.to_numeric(
        pontos["decimalLatitude"], errors="coerce"
    )
    pontos["decimalLongitude"] = pd.to_numeric(
        pontos["decimalLongitude"], errors="coerce"
    )
    pontos = pontos.dropna(subset=["decimalLatitude", "decimalLongitude"])
    pontos = pontos[
        pontos["decimalLatitude"].between(-90, 90)
        & pontos["decimalLongitude"].between(-180, 180)
    ].copy()

    return gpd.GeoDataFrame(
        pontos,
        geometry=gpd.points_from_xy(
            pontos["decimalLongitude"],
            pontos["decimalLatitude"],
        ),
        crs="EPSG:4326",
    )


def classificar_ocorrencias(
    dados: pd.DataFrame,
    limite: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    if limite.empty:
        raise ValueError("A camada do limite geográfico está vazia.")
    if limite.crs is None:
        raise ValueError("A camada do limite geográfico não possui CRS.")

    pontos = criar_pontos(dados)
    limite_no_crs_dos_pontos = limite.to_crs(pontos.crs)
    poligono = limite_no_crs_dos_pontos.geometry.union_all()
    pontos["insideBasin"] = pontos.geometry.intersects(poligono)
    return pontos


def filtrar_por_poligono(
    dados: pd.DataFrame,
    limite: gpd.GeoDataFrame,
) -> pd.DataFrame:
    classificados = classificar_ocorrencias(dados, limite)
    filtrados = classificados[classificados["insideBasin"]].copy()
    filtrados["basinCode"] = "111"
    filtrados["basinName"] = "Região Hidrográfica do Paraná"
    filtrados = filtrados.drop(columns="geometry")
    return pd.DataFrame(filtrados).reset_index(drop=True)


def gerar_mapa_validacao(
    classificados: gpd.GeoDataFrame,
    limite: gpd.GeoDataFrame,
    caminho_saida: Path,
) -> None:
    limite = limite.to_crs(classificados.crs)
    dentro = classificados[classificados["insideBasin"]]
    fora = classificados[~classificados["insideBasin"]]

    figura, eixo = plt.subplots(figsize=(8, 8))
    limite.plot(ax=eixo, color="#dce8d5", edgecolor="#2f5d3a", linewidth=0.8)
    if not fora.empty:
        fora.plot(
            ax=eixo,
            color="#c84b31",
            markersize=13,
            alpha=0.65,
            label="Fora do recorte",
        )
    if not dentro.empty:
        dentro.plot(
            ax=eixo,
            color="#176b87",
            markersize=16,
            alpha=0.8,
            label="Dentro do recorte",
        )

    eixo.set_title("Validação espacial - Região Hidrográfica do Paraná")
    eixo.set_xlabel("Longitude")
    eixo.set_ylabel("Latitude")
    eixo.legend(loc="lower left")
    eixo.set_aspect("equal")
    figura.tight_layout()

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(caminho_saida, dpi=160)
    plt.close(figura)


def salvar_resultados(
    filtrados: pd.DataFrame,
    classificados: gpd.GeoDataFrame,
    caminho_saida: Path,
    caminho_entrada: Path,
    caminho_limite: Path,
) -> None:
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    filtrados.to_csv(caminho_saida, index=False, encoding="utf-8")

    metadados = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputFile": str(caminho_entrada),
        "boundaryFile": str(caminho_limite),
        "outputFile": str(caminho_saida),
        "pointCrs": "EPSG:4326",
        "spatialPredicate": "intersects",
        "recordsEvaluated": len(classificados),
        "recordsInside": int(classificados["insideBasin"].sum()),
        "recordsOutside": int((~classificados["insideBasin"]).sum()),
    }
    caminho_metadados = caminho_saida.with_name(
        f"{caminho_saida.stem}_metadata.json"
    )
    caminho_metadados.write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filtra ocorrências pela Região Hidrográfica do Paraná."
    )
    parser.add_argument("--entrada", type=Path, default=ARQUIVO_ENTRADA)
    parser.add_argument("--limite", type=Path, default=ARQUIVO_LIMITE)
    parser.add_argument("--saida", type=Path, default=ARQUIVO_SAIDA)
    parser.add_argument("--mapa", type=Path, default=ARQUIVO_MAPA)
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    if not argumentos.entrada.exists():
        raise FileNotFoundError(
            f"Arquivo processado não encontrado: {argumentos.entrada}"
        )

    dados = pd.read_csv(argumentos.entrada)
    limite = carregar_limite(argumentos.limite)
    classificados = classificar_ocorrencias(dados, limite)
    filtrados = filtrar_por_poligono(dados, limite)

    salvar_resultados(
        filtrados,
        classificados,
        argumentos.saida,
        argumentos.entrada,
        argumentos.limite,
    )
    gerar_mapa_validacao(classificados, limite, argumentos.mapa)

    print(f"Registros avaliados: {len(classificados)}")
    print(f"Registros dentro da bacia: {len(filtrados)}")
    print(f"Registros fora da bacia: {len(classificados) - len(filtrados)}")
    print(f"CSV salvo em: {argumentos.saida}")
    print(f"Mapa de validação salvo em: {argumentos.mapa}")


if __name__ == "__main__":
    main()
