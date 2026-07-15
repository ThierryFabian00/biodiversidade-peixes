# Biodiversidade de peixes

Pipeline de dados para coleta, tratamento e análise de registros de ocorrência de espécies de peixes disponibilizados pelo GBIF.

## Objetivo

Analisar a distribuição geográfica, temporal, taxonômica e de origem de espécies de peixes na porção brasileira da Região Hidrográfica do Paraná.

## Tecnologias

- Python
- Pandas
- GeoPandas
- Matplotlib
- PostgreSQL
- Psycopg
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

### Coleta multiespécies

Com o limite geográfico preparado, execute a coleta de peixes e a normalização taxonômica da Etapa 5:

```powershell
python -m src.extract_fish
python -m src.transform_fish
```

A coleta usa cinco grupos taxonômicos de peixes, a taxonomia Catalogue of Life e um casco convexo do limite apenas como pré-filtro da API. O recorte exato da Região Hidrográfica do Paraná é aplicado localmente.

Por padrão, `extract_fish` coleta uma amostra reproduzível de até 5.000 ocorrências, pois a consulta atual possui mais de 100.000 resultados e precisa do serviço assíncrono de download do GBIF, com DOI, para ser obtida integralmente. O limite da amostra pode ser alterado com `--max-registros`.

Os principais resultados são:

- `data/processed/ocorrencias_peixes_bacia_parana.csv`: ocorrências normalizadas dentro da bacia;
- `data/processed/especies_bacia_parana.csv`: síntese por espécie, incluindo origem e evidências;
- `data/processed/problemas_taxonomicos_peixes.csv`: registros sem identificação em nível de espécie;
- `data/processed/pipeline_multiespecies_metadata.json`: filtros, contagens e indicação de completude.

As decisões taxonômicas e os critérios de origem estão descritos em [docs/TAXONOMIA_E_ORIGEM.md](docs/TAXONOMIA_E_ORIGEM.md).

### Análise exploratória

Execute a Etapa 6 depois de gerar as tabelas multiespécies:

```powershell
python -m src.analysis
```

O comando cria em `data/analysis/` rankings, séries anuais e mensais, distribuição por unidade administrativa e tipo de registro, relatório de qualidade, candidatos a duplicidade, mapa de ocorrências e grade de lacunas espaciais. A pasta é reproduzível e não é versionada.

O notebook [notebooks/01_analise_exploratoria.ipynb](notebooks/01_analise_exploratoria.ipynb) executa o mesmo módulo e apresenta os resultados em sequência. As interpretações e limitações da amostra estão documentadas em [docs/ANALISE_EXPLORATORIA.md](docs/ANALISE_EXPLORATORIA.md).

### PostgreSQL

Prepare um arquivo `.env` a partir de `.env.example` e defina uma senha local. Com um servidor PostgreSQL disponível, valide e carregue as tabelas da Etapa 7:

```powershell
python -m src.load --dry-run
python -m src.load
```

A carga usa `UPSERT`: novas execuções atualizam espécies e ocorrências com a mesma chave, sem criar duplicatas. Para consultar o banco:

```powershell
python -m src.query_db --consulta resumo
python -m src.query_db --consulta ranking --limite 10
python -m src.query_db --consulta especie --termo "Oreochromis niloticus"
```

O modelo, a configuração opcional com Docker, as restrições e as consultas estão descritos em [docs/POSTGRESQL.md](docs/POSTGRESQL.md).

Execute os testes com:

```powershell
python -m unittest discover -s tests -v
```

## Situação do projeto

- Extração paginada e configurável implementada.
- Limpeza e transformação inicial implementadas.
- Delimitação geográfica oficial da porção brasileira implementada.
- Coleta multiespécies, normalização taxonômica e classificação conservadora de origem implementadas.
- Na amostra atual de 5.000 registros, 3.792 ocorrências de 356 espécies estão dentro da Região Hidrográfica do Paraná; 555 registros sem identificação em nível de espécie foram separados para auditoria.
- Análise exploratória espacial, temporal, taxonômica e de qualidade implementada com notebook reproduzível.
- Modelagem PostgreSQL, carga idempotente, auditoria e consultas analíticas implementadas e validadas com 356 espécies e 3.792 ocorrências.
- Próxima etapa: dashboard interativo em Streamlit.
