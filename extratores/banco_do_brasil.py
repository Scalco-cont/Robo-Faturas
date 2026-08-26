# -*- coding: utf-8 -*-
"""
EXTRATOR — CARTÃO BANCO DO BRASIL (Ourocard)
=============================================
Só declara o que é específico do BB. Toda a leitura pesada está em base.py,
o que significa que ajuste feito lá vale pra todos os bancos.
"""

from extratores.base import extrair_lancamentos

# Termos que aparecem na fatura do BB e NÃO são compras
IGNORAR_BB = [
    "SALDO FATURA ANTERIOR",
    "PGTO DEBITO",
    "PAGAMENTO DEBITO",
    "PAGAMENTOS/CREDITOS",
    "COMPRAS PARCELADAS",
    "COMPRAS A VISTA",
    "TOTAL DA FATURA",
    "LANCAMENTOS DO PERIODO",
    "SEGURO",         # tire daqui se quiser lançar seguro/anuidade também
    "ANUIDADE DIFERENCIADA",
]

# Nas faturas do BB as compras costumam começar na página 3.
PAGINA_PADRAO = 3


def extrair(caminho_pdf: str, pagina_inicio: int = 0) -> dict:
    return extrair_lancamentos(
        caminho_pdf,
        pagina_inicio=pagina_inicio or PAGINA_PADRAO,
        ignorar_extra=IGNORAR_BB,
    )
