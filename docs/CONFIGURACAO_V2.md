# Configuração e refatoração da versão 2

## Objetivo

A Etapa 2 centraliza parâmetros que antes estavam espalhados pelos comandos.
País, espécie, limites e grupo taxonômico possuem valores padrão, mas podem ser
substituídos por variáveis de ambiente ou argumentos de linha de comando.

## Módulos

| Módulo | Responsabilidade |
| --- | --- |
| `src.config` | Caminhos, valores padrão, limites técnicos e leitura do ambiente |
| `src.database` | Configuração do PostgreSQL e validação do schema |
| `src.gbif_client` | Sessão HTTP, retentativas, timeout e validação da resposta GBIF |
| `src.services.country_service` | Normalização do código ISO do país |
| `src.services.occurrence_service` | Validação e montagem dos parâmetros de ocorrências |
| `src.extract` | Orquestra a extração de uma espécie |
| `src.extract_fish` | Orquestra a extração por grupo taxonômico |

Transformação, análise, carga e apresentação continuam em módulos separados.
Os imports públicos usados pela versão 1 foram preservados quando necessários
para evitar regressões.

## Parâmetros

| Variável | Padrão | Uso |
| --- | --- | --- |
| `PAIS_PADRAO` | `BR` | País usado quando nenhum código é informado |
| `ESPECIE_PADRAO` | `Oreochromis niloticus` | Consulta inicial de uma espécie |
| `LIMITE_CONSULTA_PADRAO` | `10000` | Teto total de registros por consulta do MVP |
| `TAMANHO_PAGINA_PADRAO` | `300` | Registros solicitados por página da API |
| `GRUPO_TAXONOMICO` | `Actinopterygii` | Grupo inicial de peixes |
| `GBIF_API` | `https://api.gbif.org/v1` | Endpoint base do GBIF |
| `DATABASE_URL` | sem valor seguro | Conexão PostgreSQL da aplicação |
| `DB_SCHEMA` | `biodiversity` | Schema validado do banco |

O tamanho máximo de uma página GBIF permanece em 300, o teto interativo padrão
é de 10.000 registros e o limite técnico da API de busca permanece em 100.000.
`LIMITE_PADRAO` continua aceito como variável de ambiente de compatibilidade,
mas novos ambientes devem usar `LIMITE_CONSULTA_PADRAO`.

A linha de comando multiespécies usa `GRUPO_TAXONOMICO` e registra no
metadado exatamente o grupo consultado. Chamadas programáticas que não
informam grupos preservam o conjunto legado de grupos de peixes.

## Seleção de países

O catálogo inicial da V2 é imutável durante a execução e associa nomes aos
códigos ISO usados pelo parâmetro `country` da API GBIF:

| País | Código |
| --- | --- |
| Brasil | `BR` |
| Suíça | `CH` |
| Alemanha | `DE` |
| França | `FR` |

O dashboard apresenta esse catálogo em um seletor, exibe o nome e o código do
país escolhido e repassa o código validado ao carregamento. A mesma validação é
usada por `ParametrosConsultaOcorrencia`, que envia o código no parâmetro
`country` das consultas GBIF. Códigos malformados ou fora do catálogo são
rejeitados.

Para ampliar a lista, basta adicionar uma entrada a `PAISES` em `src.config`;
a interface e a validação consomem o catálogo sem condicionais por país.

Os CSVs processados e o schema da versão 1 não possuem coluna de país e são
identificados como dados legados do Brasil. Assim, selecionar outro país não
mistura registros brasileiros: o dashboard mostra um conjunto vazio e informa
que os dados ainda não foram importados. A persistência mult país será tratada
na etapa de evolução do modelo de dados.

## Logging

Os comandos de extração, preparação geográfica, filtro, transformação, análise,
carga e exportação usam `src.logging_config`. Comandos que aceitam
`--verbose` habilitam mensagens de depuração. `query_db` mantém `print`
somente para emitir o JSON solicitado pelo usuário.

## Credenciais

O repositório contém somente `.env.example`, com valores ilustrativos. O
arquivo `.env` é ignorado pelo Git e deve guardar as credenciais locais. Em
produção, as variáveis devem ser fornecidas pela plataforma de hospedagem.

`TEST_DATABASE_URL` é opcional e deve apontar para um banco exclusivo de
testes. Ela não é necessária para executar os testes unitários.

## Dependências

`requirements.txt` contém apenas dependências importadas diretamente em
produção. Dependências transitivas são resolvidas pelo instalador. Ferramentas
de desenvolvimento e notebook ficam em `requirements-dev.txt`.

## Compatibilidade

As funções públicas usadas pela versão 1 mantêm parâmetros compatíveis. Na
linha de comando da V2, país, espécie, grupo, limite total e tamanho da página
são resolvidos pela configuração central.
