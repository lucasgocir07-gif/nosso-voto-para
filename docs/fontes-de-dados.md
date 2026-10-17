# Levantamento de fontes de dados: Câmara Municipal de Belém

> **Atualização em 16/10/2026:** o foco do projeto mudou para o **Senado e a Câmara dos Deputados** (bancada do Pará). Veja [fontes-federais.md](fontes-federais.md). Este documento fica como referência para uma fase futura.

**Fase 0 do Nosso Voto Belém** · feito em 15–16/10/2026 · cerca de 50 requisições, uma por vez e a maioria com 6 s de intervalo.

## Resumo

| Dado | Existe? | Formato | Dificuldade |
|---|---|---|---|
| Lista dos 35 vereadores | ✅ | API JSON oficial | Fácil |
| Projetos apresentados (ementa, autor, partido) | ✅ | Exportação JSON/CSV/XML | Fácil |
| Texto integral dos projetos | ⚠️ | PDF **escaneado** (sem texto) | Média (OCR) |
| Pauta de cada sessão (o que vai a voto) | ✅ | PDF **com texto**, em tabela | Média |
| Resultado das votações (aprovado/rejeitado) | ❌ estruturado | Atas escaneadas, ~1 mês de atraso | Difícil |
| Votações nominais (quem votou o quê) | ⚠️ raro | 43 registros desde 2023, escaneados | Difícil |
| Presença em plenário | ✅ | PDF mensal **com texto**, desde 2019 | Fácil–média |
| Gastos de gabinete (cota parlamentar) | ❌ | Declarações mensais de "não houve" | Inviável |
| Folha de pagamento | ⚠️ | Visualizador fora do ar (404) | Bloqueado hoje |
| Diário Oficial da Câmara | ✅ | PDF semanal com texto | Média |
| Diário Oficial do Município | ⚠️ | Querido Diário, mas parado em 05/2025 | Média |

**Em uma frase:** dá para montar projetos e presença desde já. Aprovação é o ponto fraco, e gasto de gabinete como foi imaginado não existe.

---

## 1. Vereadores

**API oficial de dados abertos.** `GET https://www.cmb.pa.gov.br/api/v1/dados-abertos/vereadores?page=&per_page=`

- Traz 35 registros com `id`, `nome` (civil), `nome_parlamentar`, `foto_url`, `perfil_url` e `atualizado_em`.
- `partido`, `email`, `telefone`, `biografia` e `redes_sociais` vêm **vazios**.
- Licença declarada no `meta`: *"Dados de uso livre, desde que citada a fonte. Sujeito a LGPD e hipóteses de sigilo legal."*

**Complementos:**
- **Partido, cargo na Mesa e situação** ("Em Atividade"): portal do fornecedor em `https://belem.n2gov.com.br/parlamentares?legislatura=20`. É um app React, então precisa de navegador ou da API interna dele, que não é documentada.
- **Perfil no site da Câmara** (`/vereador/{slug}`): partido, mandato, votos em 2024, naturalidade, biografia e comissões. É HTML, fácil de raspar.

> ⚠️ **Os nomes não batem entre as fontes.** A lista de presença usa nome parlamentar, às vezes com erro de digitação (ex.: "Jonh Wayne"). As exportações usam nome civil ("Ver. John Wayne Holanda Parente"). E há pelo menos três IDs diferentes: o da API da CMB (ex.: 11), o do n2gov (ex.: 100329) e o slug da URL. Precisamos de uma **tabela de correspondência manual** com os 35, feita uma vez e revisada a cada mudança de mandato ou suplência.

## 2. Projetos (proposições)

**Lista geral:** `https://www.cmb.pa.gov.br/processos/exportar?export=json` (também `csv` e `xml`)
- Campos: `numero` (número do processo), `tipo`, `ano`, `ementa`, `proponente` (texto com o partido) e `status`.
- `status` vem **vazio**.
- A página `/processos` filtra por número, ano, espécie (PDL, PLC-E, PLC-L, PLL, PLO, PR), palavra-chave e autor. Ainda **não testei se os filtros valem para a exportação**. A exportação completa não foi baixada, por ser grande.

**Por vereador (mais rica):** `https://www.cmb.pa.gov.br/vereador/proposicoes/exportar?id={id}&formato=json`
- Campos: `id_legiflow`, `numero`, `ano`, `ementa`, `especie`, `sigla_especie`, `proponentes[]` (ID, nome, partido, foto), `url_externa`, `expediente` e `updated_at`.
- `data_entrada`, `data_publicacao`, `fase_atual`, `nome_tramitacao` e `resumo` vieram **todos nulos** nos 78 itens testados.
- `updated_at` serve para buscar **só o que mudou** no dia.
- A lista inclui projetos de coautoria. É preciso deduplicar pelo `id_legiflow`.

**Detalhe:** `https://www.cmb.pa.gov.br/legislativo/proposicao/{id_legiflow}`
- Mostra espécie, ementa, autor, partido e tramitação com datas.
- Nas duas amostras (uma de 2026 e outra de 2025), a tramitação só tinha **"Cadastrado no Sistema"**. Ou seja, a tramitação não está sendo atualizada.

**Texto integral:** `https://cdn-belem.n2gov.com.br/uploads/{n}.pdf`
- Nas 2 amostras de 2, o PDF é **escaneado: 0 caracteres de texto** (só imagens).
- Para o MVP, usar só a ementa. O texto integral fica para depois, com OCR (Tesseract, gratuito) ou mandando o PDF direto ao Gemini, que aceita PDF.

> ⚠️ **As fontes divergem.** Para a mesma vereadora, a exportação da CMB tem 78 proposições e as estatísticas do portal n2gov contam 85. Antes de publicar qualquer número, precisamos definir **qual fonte é a oficial**.

### Teste rápido de classificação por regras

Rodei 5 regex simples sobre as 214 ementas mais recentes (amostra parcial e não revisada à mão):

| Categoria | Qtde | % |
|---|---|---|
| Título, diploma, medalha, comenda | 82 | 38,3% |
| Patrimônio cultural imaterial | 13 | 6,1% |
| Data comemorativa / calendário | 11 | 5,1% |
| Denominação de logradouro / próprio | 7 | 3,3% |
| Utilidade pública | 3 | 1,4% |
| **Outros** (vão para análise da IA) | 98 | 45,8% |

Cerca de **54% caem em categorias simbólicas só com regras**. A IA só precisaria olhar perto da metade. Ainda falta medir falsos positivos (ex.: "Institui... dia" pode pegar uma política pública).

## 3. Sessões e pautas

**Lista:** `https://www.cmb.pa.gov.br/legislativo/sessoes`
- 704 sessões, com exportação CSV/XML/JSON.
- Detalhe em `/legislativo/sessao/{id}`, que leva a um PDF no CDN.
- As sessões ordinárias são às **quartas-feiras**, às vezes duas no mesmo dia.

**PDF da pauta: tem texto** (17 mil caracteres em 6 páginas na 47ª sessão).
- **Expediente:** ofícios do Prefeito comunicando **sanção ou veto** (ex.: *"foi vetado em sua íntegra, encaminhado pelo Veto nº 09/2026"*, *"foi sancionado na Lei nº 10.382"*) e respostas a requerimentos.
- **1ª e 2ª parte:** itens que vão a voto (*"Discussão única e votação com dispensa"*), com autor e número.
- O layout é uma tabela, e na extração simples as linhas se quebram. Vai precisar de extração de tabela (PyMuPDF `find_tables`) ou da IA para estruturar.
- **A pauta diz o que vai a voto, não o resultado.**

> ⚠️ **Não há pauta publicada depois de 30/09/2026** (consulta em 16/10). Pode ser recesso do Círio ou atraso. Precisa confirmar.

## 4. Resultado das votações: o ponto fraco

Não encontrei **nenhuma fonte estruturada** que diga se um projeto foi aprovado. Estas são as opções:

1. **Atas** (`/legislativo/sessoes/atas`, 740 registros, com exportação). O PDF é **escaneado**. A ata da sessão de 02/09 só foi cadastrada em 01/10, cerca de **1 mês de atraso**.
2. **Expediente das pautas.** Ali aparecem sanções e vetos do Prefeito, o que confirma aprovação de forma indireta e com atraso.
3. **Votações nominais** (`/transparencia/item/votacoes-nominais`). São só **43 registros desde 2023**, em geral "votação em bloco", e o PDF é **escaneado**.
4. **Leis municipais** (`/legislacao/leis-municipais`). A listagem voltou com **0 resultados**, embora tenha botão de exportação.
5. **API** `/api/v1/dados-abertos/sessoes`, `/proposicoes` e `/legislacao`: existem, mas retornam **`total: 0`**.

**Recomendação:** na Fase 1, falar em **"apresentado"** e **"pautado para votação"**, e usar sanção e veto do Expediente. "Aprovado" entra depois, com OCR das atas, ou se a CMB passar a preencher a API. Vale também um **pedido via LAI** (e-SIC da CMB) pedindo o resultado das votações em formato aberto.

## 5. Presença

**Fonte:** `https://www.cmb.pa.gov.br/transparencia/item/lista-de-presenca`
- 270 arquivos mensais desde 2019, com exportação CSV da listagem.
- Cada item leva a um PDF no CDN, por exemplo `cdn-belem.n2gov.com.br/uploads/6561.pdf`.

**O PDF tem texto.** É uma tabela vereador × sessão, com valores **Presente**, **Justificado(a)** e **Licenciado(a)**.
- Setembro/2026: 6 sessões, uma página, cerca de 2.700 caracteres.
- O mês de setembro foi publicado em 05/10, cerca de **5 dias depois** do fim do mês.
- As datas da presença não batem com as da lista de sessões. Pela ordem das colunas, a 45ª aparece em 16/09 na presença e em 09/09 na lista de sessões. É preciso cruzar pelo **número da sessão**, não pela data.

> ⚠️ **"Justificado" é muito comum.** Em setembro/2026, dois vereadores tiveram 6 de 6 faltas justificadas. Juridicamente, falta justificada não é ausência irregular. O site deve mostrar **os três números separados** (presente / justificada / licença), nunca um percentual único.

## 6. Gastos de gabinete

- **Cotas parlamentares** (`/transparencia/item/regulamentacao-e-cotas-parlamentares`): os 9 meses de 2026 têm a mesma declaração, *"no mês de [mês] de 2026, não houve Cotas Parlamentares"*. **Não existe uma verba de gabinete por vereador para mostrar.**
- **Folha de pagamento** (`/transparencia/folha-pagamento`): a página embute `telasistema-folha.php?embed=1`, que retornou **404**. Dela daria para estimar o custo de pessoal de cada gabinete (assessores lotados), mas está fora do ar.
- **"Cédula C"** (`http://201.30.93.64:90/infopublic/cmb/transparencia/cedula_c/`, linkado na home): o servidor **não respondeu** (conexão recusada após 21 s).
- **Diárias** (`/transparencia/item/diarias`): existe, mas **não inspecionei**.

**Recomendação:** tirar "gastos mensais de gabinete" do MVP. Alternativas futuras: custo de pessoal por gabinete (quando a folha voltar), diárias por vereador e um **pedido via LAI**.

## 7. Diários oficiais

**Diário Oficial da Câmara:** `https://www.cmb.pa.gov.br/diario-oficial`
- **Semanal**, com 661 edições. O PDF fica em `/diario-oficial/pdf?id={id}` e **tem texto** (28 mil caracteres em 4 páginas).
- O conteúdo é quase todo ato administrativo, como nomeações e exonerações.
- Há atos publicados meses depois. Um ato de 28/02/2026 saiu na edição de 05/10/2026.
- É útil numa fase posterior, para acompanhar nomeações em gabinetes.

**Diário Oficial do Município:**
- O **Querido Diário** (Open Knowledge Brasil) cobre Belém: `https://api.queridodiario.org.br/gazettes?territory_ids=1501402`. São 4.744 edições, com `.txt` já extraído.
- Porém **a mais recente é de 13/05/2025**, então serve para histórico, não para o dia a dia.
- A API mudou de domínio. O antigo `api.queridodiario.ok.org.br` dá erro de TLS.
- O site do DOM da Prefeitura **não foi verificado**.

## 8. Regras de acesso e boa convivência

- **robots.txt** da CMB: `Allow: /`, com `Crawl-delay: 5` para robôs em geral e `30` para robôs de IA (GPTBot, ClaudeBot etc.). Nosso coletor deve:
  - se identificar com um User-Agent próprio, com contato;
  - esperar **pelo menos 5 s** entre requisições;
  - guardar cópia local e baixar só o que mudou (`updated_at`).
- O site oscila: em 15/10 várias páginas passaram de 40 s; em 16/10 responderam em cerca de 2 s. Use **timeout longo e retry com backoff**.
- **Infraestrutura:**
  - O site da CMB é Laravel.
  - Os dados legislativos e os PDFs vêm do fornecedor **n2gov / LegiFlow** (`belem.n2gov.com.br`, `cdn-belem.n2gov.com.br`).
  - O portal n2gov tem uma API interna não documentada. **Não depender dela**, porque pode mudar sem aviso.

## 9. O que muda no plano

1. **"Resumo diário" vira "Resumo da sessão", semanal.** As sessões são às quartas e a pauta sai no dia. O que dá para fazer todo dia é "novos projetos protocolados" (via `updated_at`).
2. **"Aprovados hoje" sai da Fase 1.** Usar "pautado" + "sancionado/vetado" (Expediente).
3. **Presença pode entrar já na Fase 1.** A fonte é melhor do que o esperado. Mostrar sempre presente / justificada / licença separados.
4. **Gastos de gabinete saem do MVP.** Abrir pedido via LAI.
5. **Classificação:** regras primeiro (cerca de 54% resolvidos), IA para o resto. Adicionar a categoria "Patrimônio cultural imaterial", que é frequente.
6. **Criar a tabela de correspondência** dos 35 vereadores (nome civil, nome parlamentar, IDs CMB e n2gov, slug).

## 10. Pendências

- [ ] Testar se os filtros (`?ano=2026` etc.) funcionam na exportação de `/processos`.
- [ ] Confirmar se houve sessões em outubro/2026.
- [ ] Testar OCR (Tesseract e Gemini) numa ata escaneada: dá para extrair resultado de votação e presença?
- [ ] Inspecionar `/transparencia/item/diarias`.
- [ ] Verificar o DOM da Prefeitura de Belém.
- [ ] Redigir pedido via LAI (e-SIC): resultados de votação em formato aberto, custo de pessoal por gabinete, previsão de a API passar a preencher sessões e proposições.
- [ ] Decidir qual fonte é a "oficial" para a contagem de proposições (CMB ou n2gov).
