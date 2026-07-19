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
