# Fontes de dados: Senado e Câmara dos Deputados (bancada do Pará)

**Novo foco do projeto, decidido em 16/10/2026:** os **3 senadores** e os **17 deputados federais** do Pará. A Câmara Municipal de Belém e a ALEPA ficam fora por enquanto. O levantamento da Câmara Municipal continua em [fontes-de-dados.md](fontes-de-dados.md), como referência.

Testes feitos em 16/10/2026 nas APIs oficiais. Todas responderam rápido e sem autenticação.

## Resumo

| Dado | Senado (3) | Câmara dos Deputados (17) |
|---|---|---|
| Lista de parlamentares | ✅ API | ✅ API |
| Projetos por autor, com situação atual | ✅ API | ✅ API |
| Voto de cada parlamentar | ✅ API (com motivo da ausência) | ✅ API |
| Presença | ✅ derivada dos votos (LS, MIS, P-NRV…) | ✅ página oficial de frequência (HTML) |
| Gastos (cota parlamentar) | ✅ CSV anual, atualizado diariamente | ✅ CSV anual com link para a nota fiscal |

**Diferença em relação à Câmara Municipal:** tudo que faltava lá existe aqui, em formato aberto e atualizado.

---

## 1. Parlamentares

**Senado:** `GET https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json`
- Traz os 81 senadores. Filtrar por `UfParlamentar == "PA"`.
- Os do Pará, com o código do Senado:
  - 4639 Beto Faro (PT)
  - 35 Jader Barbalho (MDB)
  - 3806 Zequinha Marinho (PODE)

**Câmara:** `GET https://dadosabertos.camara.leg.br/api/v2/deputados?siglaUf=PA&itens=100`
- Traz os 17 deputados em exercício, com `id`, `nome`, `siglaPartido` e foto.

> ⚠️ **Mudança de mandato em 1º/02/2027.** A eleição foi em 04/10/2026.
> - Os mandatos de Jader Barbalho e Zequinha Marinho terminam em 31/01/2027. O de Beto Faro vai até 2031.
> - A bancada da Câmara também muda.
>
> O sistema precisa guardar o **período de mandato** de cada parlamentar, e não só uma lista fixa.

## 2. Projetos e situação

**Câmara:** `GET /api/v2/proposicoes?idDeputadoAutor={id}&ano={ano}`
- O detalhe fica em `/api/v2/proposicoes/{id}`.
- `statusProposicao` traz data, situação, tramitação e despacho. Exemplo: *"Aguardando Despacho do Presidente da Câmara dos Deputados"*, de 28/08/2026.
- `urlInteiroTeor` aponta para o texto completo.

**Senado:** `GET https://legis.senado.leg.br/dadosabertos/processo?codigoParlamentarAutor={codigo}&ano={ano}`
- Campos: `identificacao` (ex.: "REQ 1/2026 - CRE"), `ementa`, `situacaoAtual`, `tramitando`, `dataUltimaAtualizacao` e `urlDocumento`.
- O serviço antigo (`/senador/{codigo}/autorias`) ainda responde, mas está **marcado como descontinuado**. Use o novo.

> Os números de projetos incluem muitos **requerimentos** (audiências, votos de pesar, frentes parlamentares). A classificação deve separá-los de **projetos de lei** e **PECs**.

## 3. Votos

**Senado:** `GET https://legis.senado.leg.br/dadosabertos/votacao?codigoParlamentar={codigo}&dataInicio=AAAA-MM-DD&dataFim=AAAA-MM-DD`
- Traz cada votação com descrição, matéria e o voto do senador.
- No histórico de Beto Faro (serviço antigo), são 426 registros. Os tipos são:
  - **Sim**, **Não** e **Votou** (votação secreta);
  - **P-NRV**: presente, não registrou voto;
  - **LS**: licença saúde;
  - **MIS**: missão oficial.

**Câmara:**
- Votações do plenário: `GET /api/v2/votacoes?idOrgao=180&dataInicio=...&dataFim=...`. Foram 57 em setembro/2026.
- Votos de uma votação: `GET /api/v2/votacoes/{id}/votos`.
- Só as **votações nominais** têm votos. As simbólicas voltam vazias.
- No teste, a votação de 03/09 teve 396 votos, sendo 12 de deputados do Pará.

## 4. Presença

**Senado:** dá para tirar dos códigos de voto (P-NRV, LS, MIS etc.). Não procurei uma página de frequência separada.

**Câmara:** a API **não serve**. `/eventos/{id}/deputados` devolveu 500 nomes, praticamente a Câmara inteira. A fonte é a página oficial:
`https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}`
- Mostra cada dia de sessão marcado como presença ou ausência. No teste: 52 presenças e 8 ausências em 2026.
- Traz os totais: dias com presença, **ausências justificadas** e **ausências não justificadas**.
- É HTML, mas organizado: são 17 páginas por ano.

> Mostrar sempre **justificadas e não justificadas separadas**, como na Câmara Municipal.

## 5. Gastos (cota parlamentar)

**Câmara:** `https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip`
- O arquivo de 2026 tem 4,3 MB e foi atualizado em 16/10/2026.
- São 115.927 linhas no país. Filtrar por `sgUF == "PA"`.
- Em 2026 (janeiro a outubro), aparecem **os 17 deputados do Pará, somando R$ 3.902.902,51**.
- Os maiores tipos de gasto:
  - divulgação da atividade parlamentar: R$ 1,77 mi;
  - fretamento de aeronaves: R$ 843 mil;
  - locação de veículos: R$ 592 mil.
- `urlDocumento` aponta para o **PDF da nota fiscal**.
- ⚠️ O serviço `/api/v2/deputados/{id}/despesas` voltou **vazio** em 16/10 para dois deputados, em 2025 e 2026. **Usar o arquivo anual.**

**Senado:** `https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv`
- O arquivo de 2026 tem 3,7 MB e foi atualizado em 16/10/2026.
- Está em latin-1, separado por `;`, com uma linha de título antes do cabeçalho.
- Colunas: `ANO`, `MES`, `SENADOR`, `TIPO_DESPESA`, `CNPJ_CPF`, `FORNECEDOR`, `DOCUMENTO`, `DATA`, `DETALHAMENTO`, `VALOR_REEMBOLSADO`, `COD_DOCUMENTO`.
- Em 2026 (janeiro a outubro):
  - Beto Faro: R$ 478.995,58
  - Zequinha Marinho: R$ 363.541,25
  - Jader Barbalho: R$ 138.309,17
- Não tem o ID do senador. É preciso **casar pelo nome**.

> ⚠️ **LGPD.** Os arquivos trazem **CPF** (do deputado e de fornecedores pessoa física). Nunca publicar CPF. Mostrar só o nome do fornecedor e o CNPJ de empresas.

> ⚠️ **Gasto alto não é irregularidade.** A cota é legal e tem limites por estado. O conteúdo deve comparar com o limite e com a média da bancada, nunca insinuar desvio sem prova.

## 6. Ritmo de atualização

- **Votações:** de terça a quinta, em semanas de sessão.
- **Projetos e situação:** atualizados continuamente.
- **Gastos:** os arquivos anuais são regenerados todos os dias.

Ao contrário da Câmara Municipal, aqui **um resumo diário faz sentido**.

## 7. Pendências

- [ ] Confirmar o limite mensal da cota para o Pará (Câmara e Senado), para comparar os gastos.
- [ ] Ver se o Senado tem uma página de frequência própria, além dos códigos de voto.
- [ ] Definir a classificação para o nível federal: requerimento, homenagem ou voto de pesar, data comemorativa, denominação (rodovias, viadutos), projeto de lei, PEC.
- [x] Novo nome: **Nosso Voto Pará** (16/10/2026). Veja [../marca/identidade-visual.md](../marca/identidade-visual.md).
