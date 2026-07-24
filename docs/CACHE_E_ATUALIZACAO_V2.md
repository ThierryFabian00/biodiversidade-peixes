# Cache e atualização pelo GBIF

## Fluxo de leitura

O PostgreSQL é a fonte preferencial. Ao abrir o dashboard ou trocar o país, a
aplicação consulta primeiro `occurrences`, `taxa` e `data_imports`. Se houver
ocorrências do grupo de peixes selecionado, os dados armazenados são reutilizados
e nenhuma requisição é enviada ao GBIF.

O GBIF é consultado somente em duas situações:

- não há dados do país no PostgreSQL;
- o usuário aciona **Atualizar dados do GBIF**.

Depois da coleta, os registros são normalizados e gravados por upsert. A carga
concluída registra `started_at`, `finished_at`, quantidades e checksums em
`data_imports`. Assim, a data retornada como última atualização é o maior
`finished_at` concluído para o país.

Na atualização interativa, as ocorrências anteriores do país são substituídas
pelo snapshot recém-normalizado dentro da mesma transação. Isso impede que
registros ausentes na nova amostra permaneçam como dados obsoletos. Táxons
compartilhados e dados dos demais países são preservados.

## Proteções da coleta

- paginação de até 300 registros por requisição;
- limite padrão de 5.000 e limite técnico de 100.000 registros por operação;
- progresso informado após cada página;
- timeout de 60 segundos;
- três novas tentativas para falhas de conexão, leitura, HTTP 429 e erros HTTP
  temporários 5xx;
- espera exponencial com fator de backoff de 0,5 segundo;
- mensagens controladas para timeout, indisponibilidade e erro HTTP.

Os limites evitam uma coleta integral acidental na interface. Conjuntos acima do
limite técnico devem usar o serviço de download autenticado do GBIF e preservar
o DOI resultante.

## Atualização manual

O botão **Atualizar dados do GBIF** ignora o cache para o país selecionado. A
interface mostra o avanço da coleta, normaliza os registros, atualiza o
PostgreSQL e invalida o cache de leitura do Streamlit. Se a atualização falhar,
o erro é exibido sem remover os dados anteriormente armazenados.

A atualização exige `DATABASE_URL`, pois o fluxo só considera a operação
concluída depois que os dados são persistidos. Sem conexão configurada, os CSVs
continuam disponíveis apenas como fallback de leitura.

## Verificação

Os testes automatizados comprovam que:

- um cache preenchido retorna a fonte `PostgreSQL` sem chamar o cliente GBIF;
- uma atualização forçada coleta, transforma e recarrega o banco;
- a paginação informa o progresso de cada página;
- timeout é convertido em erro controlado;
- as retentativas e o backoff são configurados no cliente HTTP.
