# Robô de Cartão Empresarial — versão site interno

Site local: o colaborador arrasta a(s) fatura(s) em PDF, confirma a empresa e
clica em **Processar Arquivos**. O robô lê os PDFs e devolve um `.txt` por
fatura (mais um `.zip` com todos) pronto pra importar no Questor.

Regras do chamado, mantidas:

- Sequência do TXT: **DATA - DEBITO - CREDITO - HISTORICO - VALOR - COMPLEMENTO**
- COMPLEMENTO = descrição do lançamento no PDF
- DATA e VALOR = os mesmos do PDF
- Compra parcelada: lança o **valor cheio (parcela × qtd de parcelas)** só na
  **1ª parcela**; da 2ª em diante o robô **ignora**
- Débito/Crédito definidos por empresa (`config_empresas.py`)

## O que foi corrigido nesta versão

| Problema | O que era | Como ficou |
|---|---|---|
| Sempre caía na mesma empresa, qualquer PDF | O banco era descoberto pelo **nome do arquivo**, e como só havia uma empresa cadastrada no BB, tudo virava empresa 70 | O banco é descoberto pelo **conteúdo do PDF**; e existe um seletor de empresa na tela, que manda em tudo |
| Só saía um TXT ao arrastar várias faturas | Cada arquivo era enviado numa requisição separada e o ZIP era regravado do zero a cada uma — sobrava só a última | Todos os arquivos vão num envio só; o ZIP sai com todos os TXT |
| Baixava o TXT antigo | Todos os TXT iam pra mesma pasta com o mesmo nome, e o navegador servia do cache | Cada processamento tem sua própria pasta + downloads com `no-cache` |
| Fatura não reconhecida | A regra de leitura era rígida demais (exigia sigla de estado antes do valor e o texto "Fatura fechada em") | Motor genérico: data no início da linha + último valor da linha; funciona com layouts diferentes |
| Só Banco do Brasil | — | **Bradesco** incluído (validado com fatura real), mais leitura genérica de reserva para Itaú/Santander/Caixa/Sicredi/Sicoob |
| Cobranças repetidas sumiam | O robô descartava linhas idênticas achando que era repetição de página | Linhas iguais são mantidas (pedágio no mesmo dia, mesmo valor, é real) |
| Coluna US$ entrava no complemento | A descrição ia até o último número da linha | A descrição vai até o **primeiro** número; o valor é o **último** (coluna R$) |
| Parcela "002/003" não era reconhecida | Só aceitava 1 ou 2 dígitos | Aceita até 3 dígitos, com ou sem a palavra PARC |
| Linhas sumiam sem explicação | Créditos, tarifas e parcelas descartadas sumiam caladas | Tudo que é descartado aparece como aviso na tela, com nome e valor |

## Como instalar (uma vez por computador)

1. Ter o **Python** instalado (python.org, marcar "Add to PATH").
2. Extrair esta pasta em um lugar fixo.
3. Dois cliques no `Iniciar.bat` — ele instala o que falta e abre
   `http://localhost:5000`.

## Como o colaborador usa

1. Abre o site.
2. **Escolhe a empresa/cartão** na listinha (ou deixa em "Detectar
   automaticamente").
3. Arrasta uma ou várias faturas em PDF.
4. Clica em **Processar Arquivos**.
5. Cada fatura mostra quantos lançamentos saíram, uma prévia das primeiras
   linhas e o link do `.txt`. O botão verde baixa **todos** num `.zip`.

### Sobre o "Detectar automaticamente"

O robô descobre o **banco** sozinho pelo conteúdo do PDF. A **empresa** ele só
acerta sozinho quando:

- existe uma única empresa cadastrada naquele banco; **ou**
- o CNPJ da empresa está preenchido em `config_empresas.py` e aparece no PDF.

Fora disso ele avisa e pede pra escolher na listinha — de propósito, porque
chutar a empresa errada significa lançar despesa na contabilidade errada.

### Botão "Ver o que o robô leu"

Se uma fatura vier com layout diferente e o robô não achar lançamentos, esse
botão mostra o texto cru que ele conseguiu extrair do PDF. É só copiar e
mandar pro desenvolvedor — com isso dá pra ajustar a regra em minutos.

## O que o robô descarta (e avisa na tela)

- **Créditos/estornos** (cashback, devolução): valor negativo — o TXT só traz despesa.
- **Parcelas da 2ª em diante**: conforme a regra combinada.
- **Tarifas, anuidade, seguro, pagamentos e saldos**: pela lista `IGNORAR_...`
  do extrator do banco. Se alguma dessas precisar ser lançada (a anuidade,
  por exemplo), é só tirar o termo dessa lista.

Nada some calado: cada descarte vira um aviso amarelo com nome e valor, pra
você conferir contra o total impresso na fatura.

## Cadastrar empresa — pela própria tela

Clique em **⚙ Empresas cadastradas**, na tela principal. Ninguém precisa abrir
arquivo de programa. A tela lista o que já existe, com o botão **Editar**, e
traz o formulário para incluir. Os campos:

| Campo | O que é |
|---|---|
| Código da empresa | **Opcional.** O número dela no Questor (ex: 70). Não entra no TXT — serve só pra achar a empresa na listinha |
| Banco do cartão | De qual banco é a fatura |
| Nome da empresa | Só pra você reconhecer na listinha |
| Conta de DÉBITO | A conta da despesa |
| Conta de CRÉDITO | A contrapartida (o cartão) |
| Código de histórico | O 4º campo do TXT |
| Página inicial | **0 = ler o PDF inteiro** (recomendado). BB costuma ser 3 |
| CNPJ | Opcional. Preenchido, o robô reconhece a empresa sozinho |

Não existe botão de excluir, de propósito: um cadastro errado se conserta pelo
Editar, e ninguém apaga contas contábeis sem querer. Se um dia precisar mesmo
remover uma empresa, apague a linha dela em `dados/config.json`.

Vale na hora, sem reiniciar. A mesma empresa pode ter cartão em mais de um
banco: cadastre duas vezes, mesmo código, bancos diferentes.

### Quando falta cadastro

Se você jogar um PDF de um banco sem empresa cadastrada, o robô avisa e mostra
o botão **➕ Cadastrar essa empresa agora** — que já abre o formulário com o
banco, o nome e o CNPJ lidos do próprio PDF. Faltam só o código no Questor e as
contas.

### Onde o cadastro fica salvo

Na pasta `dados/`, em `config.json`. Para fazer backup, copie essa pasta. Ao
atualizar o robô, é essa pasta que você deve preservar — o cadastro não se
perde. Toda gravação guarda a versão anterior em `config_anterior.json`.

## Adicionar outro banco

1. Copie `extratores/bradesco.py` com o nome do banco novo e ajuste a lista
   `IGNORAR_...` (termos que aparecem na fatura e **não** são compra).
2. Registre em `EXTRATORES`, no `app.py`.
3. Acrescente as palavras-chave do banco em `PALAVRAS_BANCO_NO_PDF` e
   `NOMES_BANCOS`, em `config_empresas.py`.

Enquanto isso não é feito, o banco já funciona pela leitura genérica —
o robô só avisa na tela que o resultado precisa de conferência.

## Pontos pra confirmar com quem importa no Questor

Esses itens dependem de como o Questor de vocês está configurado. Estão no
padrão mais comum, mas vale conferir antes da primeira importação de verdade:

| Item | Onde ajustar | Padrão atual |
|---|---|---|
| Código de histórico | ⚙ Empresas cadastradas, campo Histórico | `1` (placeholder) |

O código da empresa é opcional: preenchido, a listinha mostra
"70 - Maranata Med — Banco do Brasil"; em branco, mostra só
"Maranata Med — Banco do Brasil". Nos dois casos o TXT sai igual.

Internamente cada cadastro tem um identificador próprio, invisível na tela, e
é ele que amarra tudo — por isso dá pra mudar o código (ou tirá-lo) sem
quebrar nada. Duas empresas com o mesmo nome no mesmo banco continuam
bloqueadas. Cadastros feitos na versão anterior recebem esse identificador
sozinhos na primeira vez que o robô roda.

## Formato do TXT

Fixo, já definido e conferido:

```
05/02/2026;4978;800;1;1421,22;POSTO IPIRANGA CUIABA BR
```

Separador `;` · data `DD/MM/AAAA` · valor com vírgula · codificação UTF-8 ·
complemento sem corte.

Se um dia o Questor reclamar da importação, isso se ajusta nas cinco constantes
no topo do `gerador_txt.py` — uma linha cada, com o comentário do que faz.

## Estrutura do projeto

```
robo_cartao_web/
├── app.py                     -> site (Flask): recebe PDFs, devolve TXT/ZIP
├── armazenamento.py           -> lê/grava o dados/config.json
├── config_empresas.py         -> regras de empresa e banco (não é mais cadastro)
├── gerador_txt.py             -> monta o TXT no formato do Questor
├── dados/config.json          -> SEU CADASTRO (faça backup desta pasta)
├── extratores/
│   ├── base.py                -> motor de leitura (regras compartilhadas)
│   ├── banco_do_brasil.py     -> ajustes do BB
│   ├── bradesco.py            -> ajustes do Bradesco
│   └── padrao.py              -> reserva pros bancos sem regra própria
├── templates/index.html       -> a telinha
├── requirements.txt
└── Iniciar.bat
```
