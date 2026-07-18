# Configuração e refatoração da versão 2

## Objetivo

A Etapa 2 centraliza parâmetros que antes estavam espalhados pelos comandos,
sem modificar o fluxo funcional da versão 1. País, espécie, limite e grupo
taxonômico possuem valores padrão, mas podem ser substituídos por variáveis de
ambiente ou argumentos de linha de comando.

## Módulos

| Módulo | Responsabilidade |
| --- | --- |
| `src.config` | Caminhos, valores padrão, limites técnicos e leitura do ambiente |
| `src.database` | Configuração do PostgreSQL e validação do schema |
| `src.gbif_client` | Sessão HTTP, retentativas, timeout e validação da resposta GBIF |
| `src.services.country_service` | Normalização do código ISO do país |
| `src.services.occurrence_service` | Validação e montagem dos parâmetros de ocorrências |
| `src.extract` | Orquestra a extração legada de uma espécie |
| `src.extract_fish` | Orquestra a amostra multiespécies da versão 1 |

Transformação, análise, carga e apresentação continuam em módulos separados.
Os imports públicos usados pela versão 1 foram preservados quando necessários
para evitar regressões.

## Parâmetros

| Variável | Padrão | Uso |
| --- | --- | --- |
| `PAIS_PADRAO` | `BR` | País usado quando nenhum código é informado |
| `ESPECIE_PADRAO` | `Oreochromis niloticus` | Consulta legada de uma espécie |
| `LIMITE_PADRAO` | `300` | Limite configurável de consulta do MVP |
| `GRUPO_TAXONOMICO` | `Actinopterygii` | Grupo inicial de peixes |
| `GBIF_API` | `https://api.gbif.org/v1` | Endpoint base do GBIF |
| `DATABASE_URL` | sem valor seguro | Conexão PostgreSQL da aplicação |
| `DB_SCHEMA` | `biodiversity` | Schema validado do banco |

O tamanho máximo de uma página GBIF permanece em 300 e o limite técnico da API
de busca permanece em 100.000. A amostra multiespécies da versão 1 continua
com 5.000 registros para preservar o comportamento existente.

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

A extração de uma espécie, a coleta multiespécies da Bacia do Paraná, a carga
PostgreSQL e o dashboard mantêm seus comandos e padrões anteriores. A
refatoração muda a localização das responsabilidades, não o resultado esperado
da versão 1.
