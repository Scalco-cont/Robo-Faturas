# -*- coding: utf-8 -*-
"""
MOTOR GENÉRICO DE LEITURA DE FATURA
====================================
Antes, cada banco tinha uma expressão regular própria e MUITO rígida — se a
fatura viesse com uma coluna a mais, sem a sigla do estado, ou com o valor em
outro lugar, o robô simplesmente não achava nada.

Agora existe um motor único que trabalha por REGRA e não por "molde":

  1. A linha precisa começar com uma data (05/02, 05/02/26, 05 FEV...).
  2. O último valor em dinheiro da linha é o valor do lançamento.
  3. O que sobra no meio é a descrição (vai pro COMPLEMENTO do TXT).
  4. Linhas de pagamento/saldo/total/encargo são descartadas.
  5. Parcelas: "PARC 01/03", "01/03", "1 DE 3", "PARCELA 1/3" etc.
     - 1ª parcela  -> lança valor x quantidade de parcelas
     - 2ª em diante -> ignora

Cada banco (banco_do_brasil.py, bradesco.py...) só informa seus detalhes:
palavras a ignorar e página inicial padrão. O resto é compartilhado, então
corrigir aqui conserta todos os bancos de uma vez.
"""

import re
import unicodedata
from datetime import date
from decimal import Decimal

import pdfplumber

# ── padrões ────────────────────────────────────────────────────────────────

# Data no começo da linha: 05/02, 05/02/26, 05/02/2026, 05.02, 05-02
RE_DATA_NUM = re.compile(r"^(\d{2})[/.\-](\d{2})(?:[/.\-](\d{2,4}))?\b")

# Data por extenso: "05 FEV", "05 FEV 26"
MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
         "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}
RE_DATA_EXT = re.compile(r"^(\d{1,2})\s*[/ ]\s*([A-Z]{3})(?:\s*[/ ]\s*(\d{2,4}))?\b")

# Valor em dinheiro no padrão brasileiro: 1.270,00 / 72,00 / -50,00 / R$ 12,34
RE_VALOR = re.compile(r"(-)?\s*(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})(?!\d)")

# Parcelas — do jeito mais explícito para o mais solto
RE_PARC_EXPLICITA = re.compile(
    r"\b(?:PARC(?:ELA)?\.?|PCL|P)\s*[:\-]?\s*(\d{1,3})\s*(?:/|\s+DE\s+)\s*(\d{1,3})\b"
)
RE_PARC_SOLTA = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")

# Datas completas usadas para descobrir o ANO dos lançamentos
RE_DATA_COMPLETA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
RE_FECHAMENTO = re.compile(
    r"(?:FATURA FECHADA EM|FECHADA EM|DATA DE FECHAMENTO|FECHAMENTO)"
    r"\s*[:\-]?\s*(\d{2})/(\d{2})/(\d{2,4})"
)
RE_REFERENCIA = re.compile(
    r"(?:DATA DE VENCIMENTO|VENCIMENTO|VENCE EM|EMISSAO)"
    r"\s*[:\-]?\s*(\d{2})/(\d{2})/(\d{2,4})"
)

# Razão social do titular — serve para conferir se o PDF é da empresa certa
RE_TITULAR = re.compile(
    r"^([A-Z0-9][A-Z0-9 &.\-/']{3,58}\s(?:LTDA|EIRELI|MEI|EPP|ME|S/A|S\.A\.?|SA))\b"
)
RE_TITULAR_ROTULO = re.compile(
    r"(?:EMPRESA|RAZAO SOCIAL|CLIENTE|TITULAR)\s*:\s*"
    r"([A-Z0-9][A-Z0-9 &.\-/']{3,58}\s(?:LTDA|EIRELI|MEI|EPP|ME|S/A|S\.A\.?|SA))\b"
)

# Linhas que começam com esses termos NÃO são compras
IGNORAR_PADRAO = [
    "SALDO FATURA ANTERIOR", "SALDO ANTERIOR", "SALDO EM", "SALDO ATUAL",
    "PAGAMENTO", "PGTO", "PAGTO", "PAGAMENTOS", "CREDITOS", "PAGAMENTO EFETUADO",
    "TOTAL", "SUBTOTAL", "TOTAIS", "LIMITE", "ENCARGOS", "JUROS", "MULTA",
    "MORA", "CET ", "IOF FINANCIAMENTO", "SALDO FINANCIADO", "PARCELAMENTO DE FATURA",
    "DEMAIS LANCAMENTOS", "LANCAMENTOS DO CARTAO", "DATA HISTORICO",
    "DATA DESCRICAO", "DATA ESTABELECIMENTO", "PROXIMAS FATURAS", "RESUMO",
]


def sem_acento(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """MAIÚSCULA, sem acento, espaços colapsados — pra comparar palavras."""
    return re.sub(r"\s+", " ", sem_acento(texto or "").upper()).strip()


def converter_valor(inteiro: str, centavos: str, negativo: bool) -> Decimal:
    """('1.270','00') -> Decimal('1270.00'). Decimal, nunca float (é dinheiro)."""
    limpo = inteiro.replace(".", "").replace(" ", "")
    valor = Decimal(f"{limpo}.{centavos}")
    return -valor if negativo else valor


def ler_texto_do_pdf(caminho_pdf: str) -> list[str]:
    """Devolve o texto de cada página do PDF (índice 0 = página 1)."""
    paginas = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            paginas.append(pagina.extract_text() or "")
    return paginas


RE_CNPJ = re.compile(r"\b(\d{2,3}\.\d{3}\.\d{3}/\d{4}-\d{2})\b")


def detectar_cnpj(texto_pdf: str) -> str:
    """
    Primeiro CNPJ do PDF que NÃO seja o do próprio banco — serve pra
    pré-preencher o cadastro da empresa na tela de configurações.
    """
    bancos = {"00000000000191", "60746948000112", "60701190000104",
              "90400888000142", "00360305000104"}
    for achado in RE_CNPJ.findall(texto_pdf or ""):
        digitos = "".join(c for c in achado if c.isdigit())
        if digitos.lstrip("0").zfill(14) not in bancos and digitos[-14:] not in bancos:
            return achado
    return ""


def detectar_titular(texto_pdf: str) -> str:
    """
    Tenta achar a razão social do titular do cartão (a empresa dona da fatura).
    Serve pra avisar quando o PDF é de uma empresa e o colaborador selecionou
    outra na tela — evita lançar a despesa na contabilidade errada.
    """
    bancos = ("BANCO DO BRASIL", "BRADESCO", "ITAU", "SANTANDER", "CAIXA",
              "SICREDI", "SICOOB", "VISA", "MASTERCARD", "ELO")
    for linha in (texto_pdf or "").split("\n")[:60]:
        norm = normalizar(linha)
        m = RE_TITULAR_ROTULO.search(norm) or RE_TITULAR.match(norm)
        if m:
            candidato = m.group(1).strip()
            if any(b in candidato for b in bancos):
                continue      # é o nome do banco/bandeira, não do cliente
            return candidato
    return ""


def _palavras_uteis(nome: str) -> set:
    """Tokens comparáveis de uma razão social (sem LTDA, ME, artigos etc.)."""
    lixo = {"LTDA", "EIRELI", "MEI", "EPP", "ME", "SA", "S/A", "S.A", "DE", "DA",
            "DO", "DAS", "DOS", "E", "COMERCIO", "SERVICOS", "SERVICO",
            "INDUSTRIA", "EMPRESA", "CIA"}
    return {p for p in re.split(r"[^A-Z0-9]+", normalizar(nome))
            if len(p) >= 3 and p not in lixo}


def mesma_empresa(nome_cadastrado: str, titular_do_pdf: str) -> bool:
    """
    True se os dois nomes parecem ser da mesma empresa (compartilham alguma
    palavra significativa). Se não der pra concluir, devolve True — o objetivo
    é avisar em caso claro de divergência, não travar por diferença de grafia.
    """
    a, b = _palavras_uteis(nome_cadastrado), _palavras_uteis(titular_do_pdf)
    if not a or not b:
        return True
    return bool(a & b)


def descobrir_ano_referencia(texto_completo: str) -> tuple[int, int]:
    """
    Descobre (mes, ano) de referência da fatura, usado pra completar o ano dos
    lançamentos que só trazem DD/MM.

    Ordem de tentativa:
      1. "Fatura fechada em / Fechamento: DD/MM/AAAA"
      2. "Vencimento / Emissão: DD/MM/AAAA"
      3. Qualquer data completa DD/MM/AAAA que apareça no PDF (usa a maior)
      4. Data de hoje (último recurso — nesse caso o robô avisa na tela)
    """
    texto = normalizar(texto_completo)

    for regex in (RE_FECHAMENTO, RE_REFERENCIA):
        m = regex.search(texto)
        if m:
            _, mes, ano = m.groups()
            ano = int(ano)
            if ano < 100:
                ano += 2000
            return int(mes), ano

    datas = []
    for d, mes, ano in RE_DATA_COMPLETA.findall(texto):
        try:
            datas.append(date(int(ano), int(mes), int(d)))
        except ValueError:
            continue
    if datas:
        maior = max(datas)
        return maior.month, maior.year

    hoje = date.today()
    return hoje.month, hoje.year


def _extrair_data(linha: str):
    """Devolve (dia, mes, ano_ou_None, resto_da_linha) ou None."""
    m = RE_DATA_NUM.match(linha)
    if m:
        dia, mes, ano = m.group(1), m.group(2), m.group(3)
        if 1 <= int(mes) <= 12 and 1 <= int(dia) <= 31:
            return int(dia), int(mes), (int(ano) if ano else None), linha[m.end():]

    m = RE_DATA_EXT.match(normalizar(linha))
    if m and m.group(2) in MESES:
        dia, mes_txt, ano = m.group(1), m.group(2), m.group(3)
        # corta o mesmo tamanho na linha original
        return int(dia), MESES[mes_txt], (int(ano) if ano else None), linha[m.end():]

    return None


def _detectar_parcela(descricao: str):
    """Devolve (parcela_atual, total_parcelas) ou (None, None)."""
    texto = normalizar(descricao)

    m = RE_PARC_EXPLICITA.search(texto)
    if m:
        atual, total = int(m.group(1)), int(m.group(2))
        if 1 <= atual <= total <= 999:
            return atual, total

    # sem a palavra "PARC": aceita algo como "MERCADO X 01/06" no fim do texto
    for m in RE_PARC_SOLTA.finditer(texto):
        atual, total = int(m.group(1)), int(m.group(2))
        if 2 <= total <= 48 and 1 <= atual <= total:
            return atual, total

    return None, None


def _linha_ignorada(descricao_normalizada: str, ignorar_extra: list[str]) -> bool:
    for termo in IGNORAR_PADRAO + list(ignorar_extra or []):
        if descricao_normalizada.startswith(normalizar(termo)):
            return True
    return False


def _montar_data(dia: int, mes: int, ano_linha, mes_ref: int, ano_ref: int) -> str:
    """
    Se a linha já traz o ano, usa ele. Senão: o ano é o da referência da fatura,
    a não ser que o mês do lançamento seja MAIOR que o mês da fatura — aí a
    compra é do ano anterior (parcela antiga de dez/2025 numa fatura de fev/2026).
    """
    if ano_linha:
        ano = ano_linha + 2000 if ano_linha < 100 else ano_linha
    else:
        ano = ano_ref - 1 if mes > mes_ref else ano_ref
    return f"{dia:02d}/{mes:02d}/{ano}"


def extrair_lancamentos(caminho_pdf: str,
                        pagina_inicio: int = 0,
                        ignorar_extra: list[str] | None = None,
                        aceitar_negativos: bool = False) -> dict:
    """
    Lê o PDF e devolve:
      {
        "lancamentos": [ {data, descricao, valor, parcela_atual, parcela_total}, ...],
        "avisos":      ["...", ...],
        "paginas":     quantidade de páginas do PDF,
        "linhas_lidas": quantas linhas viraram lançamento,
      }

    pagina_inicio = 0  -> varre o PDF inteiro (recomendado)
    pagina_inicio = 3  -> começa na página 3 (padrão antigo do BB)
    """
    avisos = []
    paginas = ler_texto_do_pdf(caminho_pdf)

    if not any(p.strip() for p in paginas):
        raise ValueError(
            "Este PDF não tem texto selecionável (provavelmente é um PDF "
            "escaneado, uma imagem). O robô não consegue ler faturas "
            "digitalizadas — peça o PDF original ao cliente."
        )

    texto_completo = "\n".join(paginas)
    mes_ref, ano_ref = descobrir_ano_referencia(texto_completo)

    texto_normalizado = normalizar(texto_completo)
    if not RE_FECHAMENTO.search(texto_normalizado) and \
       not RE_REFERENCIA.search(texto_normalizado) and \
       not RE_DATA_COMPLETA.search(texto_completo):
        avisos.append(
            f"Não achei a data de fechamento/vencimento no PDF, então assumi o "
            f"ano {ano_ref} para os lançamentos. Confira as datas no TXT."
        )

    inicio = max(0, (pagina_inicio or 1) - 1)
    if inicio >= len(paginas):
        avisos.append(
            f"A empresa está configurada para começar na página {pagina_inicio}, "
            f"mas o PDF só tem {len(paginas)} página(s). Li o PDF inteiro."
        )
        inicio = 0

    lancamentos = []
    creditos_ignorados = 0
    parcelas_ignoradas = 0
    descartados = []

    for pagina_texto in paginas[inicio:]:
        for linha_bruta in pagina_texto.split("\n"):
            linha = linha_bruta.strip()
            if not linha:
                continue

            achou_data = _extrair_data(linha)
            if not achou_data:
                continue
            dia, mes, ano_linha, resto = achou_data

            valores = list(RE_VALOR.finditer(resto))
            if not valores:
                continue

            # O valor do lançamento é o ÚLTIMO número da linha (a coluna R$).
            # A descrição termina no PRIMEIRO número — assim colunas extras,
            # como a coluna US$ "0,00" do Bradesco, não sujam o complemento.
            ultimo = valores[-1]
            negativo = bool(ultimo.group(1)) or resto.rstrip().endswith("-")
            valor = converter_valor(ultimo.group(2), ultimo.group(3), negativo)

            descricao = resto[:valores[0].start()].strip(" ,.-\t")
            descricao = re.sub(r"\s{2,}", " ", descricao).strip()
            if not descricao:
                continue

            desc_norm = normalizar(descricao)
            if _linha_ignorada(desc_norm, ignorar_extra or []):
                if valor > 0:
                    descartados.append(f"{descricao} ({valor:.2f})")
                continue
            if len(desc_norm) < 3:
                continue

            if valor < 0 and not aceitar_negativos:
                creditos_ignorados += 1     # cashback, estorno, crédito
                continue
            if valor == 0:
                continue

            parcela_atual, parcela_total = _detectar_parcela(descricao)
            if parcela_atual is not None:
                if parcela_atual != 1:
                    parcelas_ignoradas += 1   # 2ª em diante: já foi lançada
                    continue
                valor = valor * parcela_total   # 1ª parcela -> valor cheio

            data = _montar_data(dia, mes, ano_linha, mes_ref, ano_ref)

            lancamentos.append({
                "data": data,
                "descricao": descricao,
                "valor": valor,
                "parcela_atual": parcela_atual,
                "parcela_total": parcela_total,
            })

    if creditos_ignorados:
        avisos.append(
            f"{creditos_ignorados} lançamento(s) de crédito/estorno "
            f"(cashback, devolução) foram descartados — o TXT só traz despesa."
        )
    if descartados:
        avisos.append(
            "Linha(s) descartada(s) por serem tarifa/anuidade/seguro/pagamento "
            "e não compra: " + "; ".join(descartados[:10])
            + (" ..." if len(descartados) > 10 else "")
            + ". Se alguma dessas precisa ser lançada, tire o termo da lista "
              "IGNORAR do extrator do banco."
        )
    if parcelas_ignoradas:
        avisos.append(
            f"{parcelas_ignoradas} parcela(s) de 2ª em diante foram ignoradas, "
            f"conforme a regra combinada."
        )

    return {
        "lancamentos": lancamentos,
        "avisos": avisos,
        "creditos_ignorados": creditos_ignorados,
        "descartados": descartados,
        "parcelas_ignoradas": parcelas_ignoradas,
        "titular": detectar_titular(texto_completo),
        "paginas": len(paginas),
        "linhas_lidas": len(lancamentos),
    }
