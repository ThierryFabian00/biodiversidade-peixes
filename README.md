# Biodiversidade de peixes

Pipeline de dados para coleta, tratamento e análise de registros de ocorrência de espécies de peixes disponibilizados pelo GBIF.

## Objetivo

Analisar a distribuição geográfica e temporal de espécies de peixes, com foco futuro na bacia do rio Paraná e usando inicialmente registros brasileiros de *Oreochromis niloticus*.

## Tecnologias

- Python
- Pandas
- Requests
- API do GBIF

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

Execute os testes com:

```powershell
python -m unittest discover -s tests -v
```

## Situação do projeto

- Extração paginada e configurável implementada.
- Limpeza e transformação inicial implementadas.
- Próxima etapa: definir e aplicar a delimitação geográfica da bacia do rio Paraná.
