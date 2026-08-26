# -*- coding: utf-8 -*-
"""
GERADOR DO TXT PARA O QUESTOR
==============================
Sequência dos campos (como o cliente pediu):
DATA - DEBITO - CREDITO - HISTORICO - VALOR - COMPLEMENTO

Exemplo de uma linha gerada:
    05/02/2026;4978;800;1;1421,22;POSTO IPIRANGA CUIABA BR

O formato abaixo é fixo — foi definido e conferido, e por isso saiu da tela de
configurações (era campo demais pra uma coisa que não muda no dia a dia).

Se um dia o Questor reclamar da importação, é aqui que se ajusta: são as cinco
constantes logo abaixo, uma linha cada. Nada mais no robô precisa mudar.
"""

import re
import unicodedata
from decimal import Decimal

# ── formato do arquivo ─────────────────────────────────────────────────────
SEPARADOR = ";"                 # o que separa os campos
FORMATO_DATA = "DD/MM/AAAA"     # ou "DDMMAAAA" (05022026)
FORMATO_VALOR = "VIRGULA"       # "VIRGULA" = 1421,22 | "PONTO" = 1421.22
CODIFICACAO = "utf-8"           # ou "cp1252" (ANSI/Windows), se sair acento torto
TAMANHO_COMPLEMENTO = 0         # 0 = sem limite. Ex: 40 corta em 40 caracteres
# ───────────────────────────────────────────────────────────────────────────


def _formatar_data(data_br: str) -> str:
    """Recebe 'DD/MM/AAAA' e devolve no formato configurado acima."""
    dia, mes, ano = data_br.split("/")
    return f"{dia}{mes}{ano}" if FORMATO_DATA == "DDMMAAAA" else data_br


def _formatar_valor(valor: Decimal) -> str:
    texto = f"{valor:.2f}"
    return texto.replace(".", ",") if FORMATO_VALOR == "VIRGULA" else texto


def _limpar_complemento(texto: str) -> str:
    """
    Tira o separador de dentro do texto (senão o Questor conta um campo a mais),
    colapsa espaços e remove caracteres que a codificação não aceita.
    """
    texto = (texto or "").replace(SEPARADOR, ",")
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = unicodedata.normalize("NFKC", texto)
    texto = texto.encode(CODIFICACAO, errors="ignore").decode(CODIFICACAO)
    if TAMANHO_COMPLEMENTO:
        texto = texto[:TAMANHO_COMPLEMENTO]
    return texto


def montar_linha(data, debito, credito, historico, valor, complemento) -> str:
    campos = [
        _formatar_data(data),
        str(debito),
        str(credito),
        str(historico),
        _formatar_valor(valor),
        _limpar_complemento(complemento),
    ]
    return SEPARADOR.join(campos)


def montar_linhas(lancamentos: list[dict], config_empresa: dict) -> list[str]:
    return [
        montar_linha(
            data=l["data"],
            debito=config_empresa["debito"],
            credito=config_empresa["credito"],
            historico=config_empresa["historico"],
            valor=l["valor"],
            complemento=l["descricao"],
        )
        for l in lancamentos
    ]


def gerar_conteudo(lancamentos: list[dict], config_empresa: dict) -> bytes:
    """Conteúdo do TXT já codificado, pronto pra salvar ou zipar."""
    linhas = montar_linhas(lancamentos, config_empresa)
    texto = "\r\n".join(linhas)
    if linhas:
        texto += "\r\n"
    return texto.encode(CODIFICACAO, errors="replace")


def gerar_arquivo(lancamentos: list[dict], config_empresa: dict,
                  caminho_saida: str) -> int:
    with open(caminho_saida, "wb") as f:
        f.write(gerar_conteudo(lancamentos, config_empresa))
    return len(lancamentos)
