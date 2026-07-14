# Biodiversidade de peixes

Pipeline de dados para coleta, tratamento e análise de registros de ocorrência de espécies de peixes disponibilizados pelo GBIF.

## Objetivo

Analisar a distribuição geográfica e temporal de espécies de peixes na porção brasileira da Região Hidrográfica do Paraná, usando inicialmente registros de *Oreochromis niloticus*.

## Tecnologias

- Python
- Pandas
- GeoPandas
- Matplotlib
- Requests
- API do GBIF
- Divisão Hidrográfica Nacional DHN250/IBGE

## Como executar

Ative o ambiente virtual e instale as dependências:

```powershell
pip install -r requirements.txt
```

Execute a extração completa da espécie padrão:

```powershell
python src/extract.py
```

Para testar a paginação com uma quantidade limitada de registros:

```powershell
python src/extract.py --max-registros 600
```

A extração aceita `--especie`, `--pais`, `--max-registros`, `--tamanho-pagina` e `--saida`. Ela gera um CSV em `data/raw/` e um JSON associado com os filtros, horário e quantidade da coleta.

A API de busca do GBIF permite consultar no máximo 100.000 registros. Quando uma consulta ultrapassa esse volume, o programa orienta o uso do serviço oficial de download do GBIF, que também fornece o DOI necessário para citar o conjunto de dados.

Em seguida, execute a transformação:

```powershell
python src/transform.py
```

Prepare o limite oficial da Região Hidrográfica do Paraná e aplique o filtro espacial:

```powershell
python src/prepare_boundary.py
python src/filter_basin.py
```

O filtro gera o CSV regional, um JSON com o resumo da operação e um mapa para validação visual em `data/processed/`. A fonte, o recorte adotado, a licença e os sistemas de coordenadas estão descritos em [docs/FONTE_GEOGRAFICA.md](docs/FONTE_GEOGRAFICA.md).

Execute os testes com:

```powershell
python -m unittest discover -s tests -v
```

## Situação do projeto

- Extração paginada e configurável implementada.
- Limpeza e transformação inicial implementadas.
- Delimitação geográfica oficial da porção brasileira implementada.
- Dos 590 registros atuais, 270 estão dentro da Região Hidrográfica do Paraná.
- Próxima etapa: ampliar a coleta para várias espécies de peixes.
