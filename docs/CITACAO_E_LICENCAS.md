# Citação, licenças e proveniência

## Ocorrências GBIF

O GBIF oferece dados sob CC0, CC BY ou CC BY-NC. A licença de cada publicador prevalece e deve permanecer associada ao registro. Consulte os [termos de uso](https://www.gbif.org/terms) e o [acordo para usuários de dados](https://www.gbif.org/terms/data-user).

A consulta de busca usada nesta versão é uma amostra técnica e não possui DOI próprio. Para pesquisa, política pública ou publicação, gere um GBIF Occurrence Download autenticado e cite o DOI fornecido, conforme as [diretrizes oficiais de citação](https://www.gbif.org/citation-guidelines).

Quando um registro individual for citado, use a página indicada por `gbifUrl` e a citação recomendada pelo GBIF. O identificador do dataset e a organização publicadora devem permanecer associados ao registro.

## Licenças observadas

Nos 5.000 registros brutos da execução atual:

| Licença | Registros | Regra aplicada |
|---|---:|---|
| CC BY 4.0 | 2.493 | Uso permitido com atribuição. |
| CC BY-NC 4.0 | 2.427 | Mantido localmente; excluído da amostra versionada. |
| CC0 1.0 | 80 | Uso sem restrição, com citação científica recomendada. |

`data/sample/occurrences_sample.csv` contém somente CC0 e CC BY. `datasetName` pode estar ausente quando a resposta de ocorrência não o fornece; nesses casos, `datasetKey` e `gbifUrl` preservam a rastreabilidade até a página oficial.

## Limite geográfico

O limite deriva da Divisão Hidrográfica Nacional DHN250 publicada pelo IBGE. Fonte, licença e procedimento estão em [FONTE_GEOGRAFICA.md](FONTE_GEOGRAFICA.md).

## Origem das espécies

A referência oficial de espécies introduzidas é a lista do MAPA associada à IN 16/2019. Ausência na lista não é interpretada como natividade. Consulte [TAXONOMIA_E_ORIGEM.md](TAXONOMIA_E_ORIGEM.md).

## Código e documentação

O repositório ainda não declara uma licença de software. Isso não altera as licenças dos dados de terceiros. Até que o autor escolha uma licença para o código, reutilização e redistribuição do software exigem autorização do titular.

## Citação do projeto

Os metadados de citação estão em `CITATION.cff`. A versão preparada é 1.0.0. Quando houver uma release com DOI, atualize o arquivo com o identificador persistente.
