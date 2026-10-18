# Nosso Voto Pará

Acompanha a bancada do Pará no Congresso (3 senadores e 17 deputados federais) com dados oficiais do Senado e da Câmara dos Deputados.

## Como rodar

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # no Linux/Mac: .venv/bin/python
.venv/Scripts/python -m nossovoto.coletar --dias 7
```

Isso coleta os **votos nominais** e as **proposições apresentadas** pela bancada no período e gera:

- `relatorios/coleta_<inicio>_a_<fim>.md`: relatório legível em português;
- `dados/processado/<inicio>_a_<fim>/`: os mesmos dados em JSON;
- `dados/bruto/<inicio>_a_<fim>/`: cópia exata das respostas das APIs (não vai para o Git).

Outros períodos: `--dias 30`, ou `--inicio 2026-10-01 --fim 2026-10-15`.

## Classificação e resumos

```bash
.venv/Scripts/python -m nossovoto.analisar
```

Classifica cada proposição por **natureza** (política pública, homenagem, fiscalização...) e **tema**, e escreve resumos em linguagem simples das votações e dos projetos de lei. O relatório da coleta mais recente é refeito com essas informações, e a análise fica em `dados/processado/<periodo>/analise.json`.

- **Regras primeiro:** casos simples (licenças, votos de pesar, nomes de rodovia, pedidos de informação...) são resolvidos por regras, sem IA.
- **Gemini para o resto:** precisa da chave em `GEMINI_API_KEY`, no arquivo `.env` (veja `.env.example`). Sem a chave, roda só com as regras. As respostas ficam em cache em `dados/cache_ia.json`, para não gastar a cota com o mesmo texto duas vezes.
- `--sem-ia` força o uso só das regras. `--periodo 2026-10-09_a_2026-10-16` escolhe outra coleta.

## Artes para o Instagram

```bash
.venv/Scripts/python -m nossovoto.artes
```

Gera, em `artes/<periodo>/`, imagens de 1080 × 1350 px (retrato do Instagram) com a identidade do projeto:

- **Votações de mérito:** um slide com o resumo e os votos da bancada. Na Câmara, um segundo slide traz os nomes.
- **Projetos de lei:** um slide com autor, classificação e resumo.

As artes usam a letra Poppins nos textos e Montserrat no nome do projeto (`marca/fontes/`, licença OFL), o símbolo `marca/simbolo-transparente.png` e as fotos oficiais dos parlamentares, guardadas em `dados/fotos/`.

Posts de apresentação do perfil, para postar à mão nos primeiros dias:

```bash
.venv/Scripts/python -m nossovoto.apresentacao   # gera em artes/apresentacao/, com legendas.txt
```

O slide da bancada usa a coleta mais recente. Gere de novo quando a bancada mudar, em 1º/02/2027.

## Envio pelo Telegram

```bash
.venv/Scripts/python -m nossovoto.enviar --previa   # mostra as mensagens sem enviar
.venv/Scripts/python -m nossovoto.enviar            # envia o que ainda não foi enviado
```

Cada votação nominal e cada projeto de lei viram uma mensagem pronta para revisar. Votações de procedimento e outros documentos (requerimentos, pareceres) chegam agrupados. O que já foi enviado fica registrado em `dados/telegram_enviados.json` e não se repete; `--reenviar` força o envio de novo.

Votações de mérito e projetos de lei chegam como **cartão para aprovação**: a arte, a legenda pronta para o Instagram e os botões **✅ Postar**, **✏️ Editar legenda** e **🗑️ Descartar**. `--so-posts` manda só os cartões.

## Aprovar e postar no Instagram

```bash
.venv/Scripts/python -m nossovoto.aprovacao                   # lê os botões apertados e faz o que foi pedido
.venv/Scripts/python -m nossovoto.aprovacao --apresentacao 1  # manda um post de apresentação (1, 2 ou 3)
.venv/Scripts/python -m nossovoto.instagram --verificar       # confere a conexão com o Instagram (não publica)
```

**Comandos no Telegram:** a rotina de aprovação lê a conversa de tempos em tempos (o GitHub agenda a cada 10 minutos, mas na prática roda a cada 20 ou 30).

| Comando | O que faz |
|---|---|
| `/post PL 1234/2026` | Cartão de um projeto ou votação da bancada já coletado. Aceita `câmara` ou `senado` para escolher a Casa |
| `/aviso Seu texto` | Cartão com uma arte de aviso. Com mais de uma linha, a primeira vira o título |
| `/gastos julho` | Cartão com os gastos da cota parlamentar no mês. Sem o mês, usa o de três meses atrás |
| `/presenca setembro` | Cartão com a presença da bancada no mês. Sem o mês, usa o mês passado |
| `/serie` | Lista a série explicativa. `/serie 3` manda o post 3; `/serie todos`, os que ainda não foram enviados |
| `/fila` | Posts esperando aprovação e os últimos publicados |
| `/ajuda` | Lista os comandos |

O menu que aparece ao digitar "/" é registrado com `python -m nossovoto.aprovacao --configurar-comandos`.

Ao apertar **Postar**, a arte é convertida para JPEG e enviada ao GitHub (pasta `publicar/`), onde ganha um endereço público. Depois é publicada pela API oficial do Instagram, e o robô devolve o link do post. O robô só obedece à conversa de `TELEGRAM_CHAT_ID`. A fila de posts fica em `dados/fila_instagram.json`.

Configuração (uma vez só), no `.env`:

1. Crie um robô com o [@BotFather](https://t.me/BotFather) e cole o token em `TELEGRAM_BOT_TOKEN`.
2. Mande um "oi" para o seu robô no Telegram.
3. Rode `.venv/Scripts/python -m nossovoto.enviar --descobrir-chat`: ele grava o `TELEGRAM_CHAT_ID` no `.env`.

## Gastos e presença (resumos do mês)

```bash
.venv/Scripts/python -m nossovoto.mensal                                # manda o que já estiver na hora
.venv/Scripts/python -m nossovoto.mensal --gastos 2026-07 --previa      # só gera as artes em artes/mensal
.venv/Scripts/python -m nossovoto.mensal --presenca setembro            # cartão de presença de setembro
```

Uma vez por mês chegam dois cartões para aprovação, cada um com arte em carrossel e legenda:

- **Presença** (do mês anterior, a partir do dia 10): dias de sessão deliberativa na Câmara (presenças, faltas justificadas e faltas não justificadas, pela página oficial de cada deputado) e participação nas votações nominais do Senado. O dia 10 dá tempo de as faltas serem justificadas.
- **Gastos da cota parlamentar** (de três meses atrás, a partir do dia 15): total da bancada, onde foi o dinheiro e quanto cada um gastou, a partir dos arquivos oficiais da Câmara (CEAP) e do Senado (CEAPS). São três meses porque as notas podem ser apresentadas em até 90 dias. Quem ainda não apresentou nenhuma nota aparece como "sem notas até agora".

Cada mês sai uma vez só. Um cartão descartado não volta sozinho, mas pode ser pedido de novo com `/gastos` ou `/presenca`. Os números de cada resumo ficam em `dados/resumos/`, e é deles que a arte é refeita na hora de publicar. A comparação é só com a média da bancada, sem ranking de "bom" ou "ruim": usar a cota é permitido.

## Série explicativa

```bash
.venv/Scripts/python -m nossovoto.explicativos --atualizar   # busca cargos e comissões (Câmara/Senado) e o resultado do TSE
.venv/Scripts/python -m nossovoto.explicativos --previa      # gera as artes em artes/explicativos e mostra as legendas
```

Seis posts para explicar sobre quem o projeto fala:

1. **O que faz um deputado federal**
2. **O que faz um senador**
3. **Como uma lei é feita**
4. **Por que acompanhar o Congresso**
5. **Quem é quem**: cargos (presidência de comissão, liderança) e comissões em que cada parlamentar é titular
6. **Eleições 2026**: senadores e deputados federais eleitos pelo Pará (resultado oficial do TSE), quem é reeleito e quem deixa o cargo

Os textos sobre os cargos seguem a Constituição, com os artigos no rodapé de cada slide. Os posts 5 e 6 usam os dados guardados em `dados/explicativos/`. Para atualizar, rode `--atualizar` e envie os arquivos ao GitHub. No post 5 só entram cargos em comissões permanentes, iniciados no biênio atual e sem data de fim, porque os dados abertos às vezes deixam cargos antigos sem data de fim. O post 6 reconhece quem já está no cargo pelo nome completo.

Os cartões são pedidos pelo Telegram com `/serie`.

## Robô automático (GitHub Actions)

Três rotinas em `.github/workflows/` rodam sozinhas no GitHub:

| Rotina | Quando | O que faz |
|---|---|---|
| **Robô diário** | Todo dia, às 7h de Belém | Coleta, analisa e manda as novidades e os cartões de post ao Telegram. Uma vez por mês, também os resumos de presença e gastos |
| **Aprovação dos posts** | A cada 10 a 30 minutos | Lê os botões apertados no Telegram e publica o que foi aprovado |
| **Renovar token do Instagram** | Segundas, às 9h | Renova o token do Instagram, que vence em 60 dias |

Os dados (coletas, análises, fila de posts) são guardados de volta no repositório a cada rodada. Se algo falhar, chega um aviso no Telegram com o link do erro. Todas as rotinas também podem ser rodadas na hora, pelo botão **Run workflow** na aba **Actions**.

**Segredos** (Settings → Secrets and variables → Actions → New repository secret):

- `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`: os mesmos valores do `.env`.
- `GH_PAT`: token do GitHub com permissão **Secrets: Read and write** só neste repositório. Ele permite que a renovação guarde o token novo do Instagram.

> ⚠️ Com o robô rodando no GitHub, **não rode os comandos no computador ao mesmo tempo**: os dois mexeriam na mesma fila. Para rodar algo localmente, faça `git pull` antes.

## Testes

```bash
.venv/Scripts/python -m pytest
```

## Documentação

- [docs/fontes-federais.md](docs/fontes-federais.md): de onde vêm os dados.
- [marca/identidade-visual.md](marca/identidade-visual.md): nome, cores e logo.
- [docs/fontes-de-dados.md](docs/fontes-de-dados.md): levantamento da Câmara Municipal de Belém, para uma fase futura.
