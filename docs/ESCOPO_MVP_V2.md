# Escopo do MVP da versão 2

## Objetivo

Transformar o dashboard em uma plataforma para consultar ocorrências de peixes
por país, espécie e período, reutilizando dados persistidos no PostgreSQL. A
versão 1 permanece preservada em `main`; a V2 é desenvolvida em
`develop-v2`.

## Jornada mínima

O MVP está concluído quando o usuário consegue:

1. escolher Brasil ou Suíça;
2. ver as espécies de peixes com ocorrências no país;
3. selecionar uma ou várias espécies;
4. filtrar período e qualidade dos registros;
5. explorar indicadores, mapa e distribuição temporal;
6. reutilizar dados do PostgreSQL e solicitar atualização controlada.

## Recorte inicial

| Dimensão | Decisão |
| --- | --- |
| Países de teste | Brasil (`BR`) e Suíça (`CH`) |
| Grupo | Classe `Actinopterygii`, segundo a taxonomia interpretada pelo GBIF |
| Unidade | Registro de ocorrência publicado no GBIF |
| Persistência | PostgreSQL; GBIF para carga e atualização |
| Interface | Streamlit responsivo |
| Comparação | Espécies, ocorrências e tempo, sem inferir abundância |

Os códigos ISO são enviados à API e os nomes dos países são exibidos na
interface. Novos países devem poder ser adicionados sem alterar a lógica.

## Limites de consulta

- No máximo **300 registros por requisição**, limite de página da busca GBIF.
- No máximo **10.000 ocorrências por combinação de país e espécie** em uma
  atualização interativa do MVP. O valor deve ser configurável.
- A interface informa quando houver truncamento; uma amostra não pode ser
  apresentada como inventário completo.
- Acima do teto operacional, a carga deve ser controlada. Acima do limite
  técnico de 100.000 resultados da busca, deve ser usado o GBIF Occurrence
  Download com autenticação e DOI.
- Dados persistidos são reutilizados. Uma chamada ao GBIF só ocorre por
  ausência de dados ou atualização manual explícita.

## Filtros do MVP

- país: Brasil ou Suíça;
- uma ou várias espécies no nível taxonômico de espécie;
- intervalo de anos, preservando data original e precisão temporal;
- tipo de evidência (`basisOfRecord`);
- presença de coordenadas válidas;
- presença de alertas de qualidade (`issues`) do GBIF.

O recorte filtrado alimenta o mapa, os totais de ocorrências e espécies, o
período coberto, a data da última atualização, as séries anual e mensal, o
ranking taxonômico e os indicadores de qualidade.

## Fora do MVP

- inferência de abundância, tamanho populacional ou riqueza real;
- modelagem de distribuição e previsão temporal;
- edição colaborativa e aplicativo móvel nativo;
- cobertura garantida de todos os países;
- relatório PDF e comparação normalizada entre países.

## Limitações dos dados do GBIF

As limitações devem permanecer visíveis na documentação e no dashboard:

- uma ocorrência é evidência de um registro publicado, não uma medida de
  abundância nem necessariamente um indivíduo distinto;
- a cobertura varia entre países, regiões, períodos, táxons, métodos,
  instituições e projetos. Mais registros não significam mais biodiversidade;
- ausência de registros não comprova ausência da espécie, pois esforço
  amostral e não detecções geralmente não estão descritos;
- coordenadas podem estar ausentes, arredondadas, generalizadas, inválidas ou
  incompatíveis com o país;
- datas podem estar ausentes, ser intervalos, ter só ano ou mês ou resultar da
  interpretação do valor original;
- identificações podem estar incompletas ou incorretas e nomes mudam. Nome
  original, aceito, chave e status taxonômico devem ser preservados;
- a chave GBIF evita duplicação técnica, mas não resolve duplicações biológicas
  ou o mesmo evento publicado por fontes diferentes;
- alertas (`issues`) indicam problemas potenciais e não justificam exclusão
  automática sem regra documentada;
- resultados mudam com atualizações dos publicadores. Cada carga deve guardar
  data, parâmetros, quantidade recebida e salva;
- licença, dataset, publicador e link da ocorrência devem acompanhar registros
  redistribuídos;
- a API de busca serve a consultas interativas e amostras controladas. Análises
  integrais e publicações devem usar download com DOI.

Referências oficiais:

- [API de ocorrências](https://techdocs.gbif.org/en/openapi/v1/occurrence);
- [alertas de ocorrências](https://techdocs.gbif.org/en/data-use/occurrence-issues-and-flags);
- [interpretação de datas](https://techdocs.gbif.org/en/data-processing/temporal-interpretation);
- [qualidade dos dados](https://docs.gbif.org/course-introduction-to-gbif/en/handling-data-quality.html).

## Critérios de aceite

- `BR` e `CH` produzem consultas válidas e entradas inválidas são rejeitadas;
- uma ou várias espécies podem ser selecionadas;
- indicadores, gráficos, mapa e tabela respeitam os mesmos filtros;
- paginação respeita 300 registros e o teto operacional;
- consultas repetidas reutilizam o PostgreSQL;
- atualizações não duplicam a chave GBIF;
- truncamento, data da carga e qualidade são comunicados;
- testes cobrem seleção, paginação, filtros, persistência e falha da API;
- o fluxo e os testes da versão 1 permanecem funcionando em `main`.

## Decisões posteriores

Política de validade do cache, conjunto final de países, normalização das
comparações, agregação de mapas grandes e infraestrutura de produção serão
definidos nas etapas correspondentes.

Última atualização: 17 de julho de 2026.
