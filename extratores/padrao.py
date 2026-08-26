# -*- coding: utf-8 -*-
"""
EXTRATOR PADRÃO (reserva)
==========================
Usado quando o banco da fatura ainda não tem um arquivo próprio aqui dentro
(Itaú, Santander, Caixa, Sicredi...). Aplica só as regras genéricas.

Costuma funcionar, mas o resultado precisa ser conferido na primeira vez que
você usar um banco novo. Se vier torta, copie este arquivo com o nome do
banco (ex: itau.py), ajuste a lista IGNORAR e registre no app.py.
"""

from extratores.base import extrair_lancamentos

IGNORAR = [
    "SALDO ANTERIOR",
    "PAGAMENTO",
    "PAGTO",
    "TOTAL",
    "ANUIDADE",
    "SEGURO",
]


def extrair(caminho_pdf: str, pagina_inicio: int = 0) -> dict:
    return extrair_lancamentos(
        caminho_pdf,
        pagina_inicio=pagina_inicio or 0,
        ignorar_extra=IGNORAR,
    )
