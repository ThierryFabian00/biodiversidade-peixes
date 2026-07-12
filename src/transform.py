from pathlib import Path

import pandas as pd


# Localiza a pasta principal do projeto.
PASTA_PROJETO = Path(__file__).resolve().parent.parent

ARQUIVO_ENTRADA = (
    PASTA_PROJETO
    / "data"
    / "raw"
    / "ocorrencias_tilapia.csv"
)

ARQUIVO_SAIDA = (
    PASTA_PROJETO
    / "data"
    / "processed"
    / "ocorrencias_tilapia_limpo.csv"
)


def carregar_dados(caminho: Path) -> pd.DataFrame:
    """Carrega os registros brutos armazenados em CSV."""

    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo de entrada não encontrado: {caminho}"
        )

    return pd.read_csv(caminho)


def exibir_resumo(dados: pd.DataFrame) -> None:
    """Exibe informações gerais sobre o conjunto de dados."""

    print("\n--- RESUMO DOS DADOS BRUTOS ---")
    print(f"Quantidade de linhas: {len(dados)}")
    print(f"Quantidade de colunas: {len(dados.columns)}")

    print("\nColunas:")
    print(dados.columns.tolist())

    print("\nTipos das colunas:")
    print(dados.dtypes)

    print("\nValores ausentes:")
    print(dados.isna().sum())

    print("\nLinhas duplicadas:")
    print(dados.duplicated().sum())


def limpar_dados(dados: pd.DataFrame) -> pd.DataFrame:
    """Limpa e padroniza os registros de ocorrência."""

    dados_limpos = dados.copy()

    # Remove linhas totalmente duplicadas.
    dados_limpos = dados_limpos.drop_duplicates()

    # Remove duplicidades pelo identificador do GBIF.
    if "key" in dados_limpos.columns:
        dados_limpos = dados_limpos.drop_duplicates(
            subset=["key"],
            keep="first",
        )

    # Converte as coordenadas para valores numéricos.
    dados_limpos["decimalLatitude"] = pd.to_numeric(
        dados_limpos["decimalLatitude"],
        errors="coerce",
    )

    dados_limpos["decimalLongitude"] = pd.to_numeric(
        dados_limpos["decimalLongitude"],
        errors="coerce",
    )

    # Remove registros sem coordenadas.
    dados_limpos = dados_limpos.dropna(
        subset=["decimalLatitude", "decimalLongitude"]
    )

    # Mantém somente coordenadas possíveis.
    dados_limpos = dados_limpos[
        dados_limpos["decimalLatitude"].between(-90, 90)
        & dados_limpos["decimalLongitude"].between(-180, 180)
    ]

    # Preserva a data exatamente como veio do GBIF.
    dados_limpos["eventDateOriginal"] = dados_limpos["eventDate"]

    data_original = dados_limpos["eventDateOriginal"].astype("string")

    # Identifica a precisão da data original.
    dados_limpos["datePrecision"] = "UNKNOWN"

    dados_limpos.loc[
        data_original.str.match(r"^\d{4}-\d{2}$", na=False),
        "datePrecision",
    ] = "MONTH"

    dados_limpos.loc[
        data_original.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False),
        "datePrecision",
    ] = "DAY"

    dados_limpos.loc[
        data_original.str.contains("T", na=False),
        "datePrecision",
    ] = "TIME"

    # Converte formatos diferentes para datetime.
    dados_limpos["eventDate"] = pd.to_datetime(
        dados_limpos["eventDate"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    # Cria colunas para análises temporais.
    dados_limpos["year"] = (
        dados_limpos["eventDate"]
        .dt.year
        .astype("Int64")
    )

    dados_limpos["month"] = (
        dados_limpos["eventDate"]
        .dt.month
        .astype("Int64")
    )

    # Remove espaços extras nos campos de texto.
    colunas_texto = [
        "scientificName",
        "stateProvince",
        "locality",
        "basisOfRecord",
    ]

    for coluna in colunas_texto:
        if coluna in dados_limpos.columns:
            dados_limpos[coluna] = (
                dados_limpos[coluna]
                .astype("string")
                .str.strip()
            )

    # Organiza o índice depois das remoções.
    dados_limpos = dados_limpos.reset_index(drop=True)

    return dados_limpos


def salvar_dados(dados: pd.DataFrame, caminho: Path) -> None:
    """Salva os dados processados em CSV."""

    caminho.parent.mkdir(parents=True, exist_ok=True)

    dados.to_csv(
        caminho,
        index=False,
        encoding="utf-8",
    )


def main() -> None:
    dados_brutos = carregar_dados(ARQUIVO_ENTRADA)

    exibir_resumo(dados_brutos)

    dados_limpos = limpar_dados(dados_brutos)

    salvar_dados(dados_limpos, ARQUIVO_SAIDA)

    print("\n--- RESULTADO DA LIMPEZA ---")
    print(f"Registros antes da limpeza: {len(dados_brutos)}")
    print(f"Registros depois da limpeza: {len(dados_limpos)}")
    print(f"Registros removidos: {len(dados_brutos) - len(dados_limpos)}")
    print(f"Arquivo salvo em: {ARQUIVO_SAIDA}")

    print("\nPrimeiros registros processados:")
    print(dados_limpos.head())


if __name__ == "__main__":
    main()