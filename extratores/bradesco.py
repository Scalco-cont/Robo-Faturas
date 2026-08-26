# -*- coding: utf-8 -*-
"""
EXTRATOR — CARTÃO BRADESCO
===========================
Mesma lógica do BB: só muda a lista de termos que não são compra e a página
onde os lançamentos costumam começar.

No Bradesco os lançamentos normalmente já aparecem na página 1 ou 2, por isso
o padrão aqui é varrer o PDF inteiro (0) — o filtro de linhas dá conta do
cabeçalho e do resumo.
"""

from extratores.base import extrair_lancamentos

IGNORAR_BRADESCO = [
    "SALDO ANTERIOR",
    "SALDO FATURA ANTERIOR",
    "PAGTO DEBITO CONTA",
    "PAGAMENTO EFETUADO",
    "PAGAMENTO REALIZADO",
    "PAGAMENTOS E CREDITOS",
    "TOTAL DESTA FATURA",
    "TOTAL A PAGAR",
    "SALDO REFINANCIADO",
    "COMPRAS PARCELADAS",
    "PROXIMAS PARCELAS",
    "DEMONSTRATIVO",
    "ANUIDADE",         # tire daqui se quiser lançar anuidade também
    "SEGURO",
]

PAGINA_PADRAO = 0   # 0 = PDF inteiro


def extrair(caminho_pdf: str, pagina_inicio: int = 0) -> dict:
    return extrair_lancamentos(
        caminho_pdf,
        pagina_inicio=pagina_inicio or PAGINA_PADRAO,
        ignorar_extra=IGNORAR_BRADESCO,
    )
