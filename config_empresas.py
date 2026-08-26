# -*- coding: utf-8 -*-
"""
EMPRESAS E BANCOS
==================
O cadastro de empresas NÃO fica mais aqui dentro — ele é feito pela tela do
site, no botão "⚙ Empresas cadastradas", e guardado em `dados/config.json`.

Este arquivo só cuida da lógica: procurar empresa, reconhecer banco, validar
o que veio da tela. Mexer aqui só é necessário pra ensinar o robô a reconhecer
um banco novo (listas PALAVRAS_BANCO_* e NOMES_BANCOS logo abaixo).
"""

import uuid

import armazenamento

# Palavras que identificam cada banco DENTRO DO PDF (é assim que o robô
# descobre o banco de verdade — o nome do arquivo é só um reforço).
PALAVRAS_BANCO_NO_PDF = {
    "bb":        ["BANCO DO BRASIL", "OUROCARD", "BB.COM.BR", "00000000000191"],
    "bradesco":  ["BRADESCO", "BRADESCARD", "60746948000112"],
    "itau":      ["ITAU", "ITAUCARD", "60701190000104"],
    "santander": ["SANTANDER", "90400888000142"],
    "caixa":     ["CAIXA ECONOMICA", "00360305000104"],
    "sicredi":   ["SICREDI"],
    "sicoob":    ["SICOOB", "BANCOOB"],
}

PALAVRAS_BANCO_NO_NOME = {
    "bb":        ["banco do brasil", "bancodobrasil", "bb ", "_bb", "-bb", "ourocard"],
    "bradesco":  ["bradesco"],
    "itau":      ["itau", "itaú"],
    "santander": ["santander"],
    "caixa":     ["caixa"],
    "sicredi":   ["sicredi"],
    "sicoob":    ["sicoob"],
}

NOMES_BANCOS = {
    "bb":        "Banco do Brasil",
    "bradesco":  "Bradesco",
    "itau":      "Itaú",
    "santander": "Santander",
    "caixa":     "Caixa",
    "sicredi":   "Sicredi",
    "sicoob":    "Sicoob",
}


def nome_banco(banco: str) -> str:
    return NOMES_BANCOS.get(banco, (banco or "?").upper())


def bancos_para_tela() -> list[dict]:
    return [{"valor": k, "label": v} for k, v in NOMES_BANCOS.items()]


def so_digitos(texto) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


def rotulo(e: dict) -> str:
    """'70 - Maranata Med' quando há código; só 'Maranata Med' quando não há."""
    codigo = str(e.get("codigo") or "").strip()
    return f"{codigo} - {e['nome']}" if codigo else e["nome"]


def _chave_nome(e: dict) -> str:
    """Nome+banco normalizados — é o que impede cadastrar a mesma duas vezes."""
    return f"{' '.join(str(e.get('nome','')).upper().split())}|{e.get('banco','')}"


# ── leitura do cadastro ────────────────────────────────────────────────────

def todas_empresas() -> list[dict]:
    """
    Devolve o cadastro garantindo que toda empresa tenha um `id` interno.
    Cadastros antigos (feitos quando a identidade era o código) ganham um id
    na primeira leitura, sem que ninguém precise fazer nada.
    """
    dados = armazenamento.carregar()
    faltando = [e for e in dados["empresas"] if not e.get("id")]
    if faltando:
        for e in faltando:
            e["id"] = uuid.uuid4().hex[:8]
        armazenamento.salvar(dados)
    return dados["empresas"]


def detectar_banco_pelo_nome(nome_arquivo: str):
    """'Banco do Brasil cartão março.pdf' -> 'bb'. None se não reconhecer."""
    nome_lower = " " + (nome_arquivo or "").lower() + " "
    for banco, palavras in PALAVRAS_BANCO_NO_NOME.items():
        if any(p in nome_lower for p in palavras):
            return banco
    return None


def empresas_do_banco(banco: str) -> list[dict]:
    return [e for e in todas_empresas() if e["banco"] == banco]


def buscar_por_cnpj(texto_pdf: str):
    """Se algum CNPJ cadastrado aparecer no texto do PDF, devolve a empresa."""
    if not texto_pdf:
        return None
    digitos = so_digitos(texto_pdf)
    for e in todas_empresas():
        cnpj = so_digitos(e.get("cnpj"))
        if cnpj and cnpj in digitos:
            return e
    return None


def listar_empresas_para_tela() -> list[dict]:
    opcoes = []
    for e in todas_empresas():
        opcoes.append({
            "valor": e["id"],
            "banco": e["banco"],
            "label": f"{rotulo(e)} — {nome_banco(e['banco'])}",
        })
    return opcoes


def _para_config(e: dict) -> dict:
    return {
        "id":            e["id"],
        "codigo":        str(e.get("codigo") or ""),
        "debito":        str(e["debito"]),
        "credito":       str(e["credito"]),
        "historico":     str(e["historico"]),
        "pagina_inicio": int(e.get("pagina_pdf") or 0),
        "nome_empresa":  e["nome"],
        "rotulo":        rotulo(e),
        "banco":         e["banco"],
        "aviso":         "",
    }


def buscar_config(id_empresa: str, banco: str) -> dict:
    """Config de um cadastro (pelo id interno), já checando se o banco bate."""
    for e in todas_empresas():
        if e["id"] == id_empresa:
            cfg = _para_config(e)
            if banco and e["banco"] != banco:
                cfg["aviso"] = (
                    f"{rotulo(e)} está cadastrada no banco "
                    f"{nome_banco(e['banco'])}, mas este PDF é do "
                    f"{nome_banco(banco)}. Usei as contas cadastradas mesmo "
                    f"assim — confira antes de importar."
                )
            return cfg

    raise ValueError(
        "Empresa não encontrada no cadastro. Abra \"⚙ Empresas cadastradas\" "
        "e confira — ela pode ter sido renomeada ou removida."
    )


# ── gravação do cadastro (vem da tela) ─────────────────────────────────────

class ErroDeCadastro(Exception):
    """Erro de preenchimento, com mensagem pronta pra mostrar na tela."""


def _validar(empresa: dict) -> dict:
    obrigatorios = {
        "nome":    "Nome da empresa",
        "banco":   "Banco",
        "debito":  "Conta de débito",
        "credito": "Conta de crédito",
    }
    for campo, rotulo in obrigatorios.items():
        if not str(empresa.get(campo, "")).strip():
            raise ErroDeCadastro(f"Preencha o campo \"{rotulo}\".")

    # Código é OPCIONAL — serve só pra você achar a empresa na listinha.
    codigo = str(empresa.get("codigo") or "").strip()
    if codigo and not codigo.isdigit():
        raise ErroDeCadastro(
            "O código da empresa deve ser só números (ex: 70), "
            "ou pode ficar em branco."
        )

    banco = str(empresa["banco"]).strip().lower()
    if banco not in NOMES_BANCOS:
        raise ErroDeCadastro(f"Banco desconhecido: {banco}.")

    try:
        pagina = int(str(empresa.get("pagina_pdf") or 0).strip() or 0)
    except ValueError:
        raise ErroDeCadastro("A página inicial deve ser um número (0 = PDF inteiro).")

    cnpj = so_digitos(empresa.get("cnpj"))
    if cnpj and len(cnpj) not in (14, 15):
        raise ErroDeCadastro(
            "CNPJ inválido — devem ser 14 dígitos (ex: 12.345.678/0001-99). "
            "Se não quiser usar, deixe em branco."
        )

    return {
        "id":         str(empresa.get("id") or "").strip() or uuid.uuid4().hex[:8],
        "codigo":     codigo,
        "nome":       str(empresa["nome"]).strip(),
        "banco":      banco,
        "debito":     str(empresa["debito"]).strip(),
        "credito":    str(empresa["credito"]).strip(),
        "historico":  str(empresa.get("historico") or "1").strip(),
        "pagina_pdf": pagina,
        "cnpj":       cnpj,
    }


def salvar_empresa(empresa: dict, id_original: str = "") -> dict:
    """
    Cria ou atualiza um cadastro. `id_original` vem preenchido quando é edição.
    """
    nova = _validar(empresa)
    if id_original:
        nova["id"] = id_original

    dados = armazenamento.carregar()
    lista = dados["empresas"]

    # não deixa cadastrar a mesma empresa duas vezes no mesmo banco
    for e in lista:
        if _chave_nome(e) == _chave_nome(nova) and e.get("id") != nova["id"]:
            raise ErroDeCadastro(
                f"\"{nova['nome']}\" já está cadastrada no "
                f"{nome_banco(nova['banco'])}. Use o Editar da que já existe."
            )

    for i, e in enumerate(lista):
        if e.get("id") == nova["id"]:
            lista[i] = nova
            break
    else:
        lista.append(nova)

    lista.sort(key=lambda e: (str(e.get("nome", "")).upper(), e["banco"]))
    armazenamento.salvar(dados)
    return nova


def excluir_empresa(chave: str):
    """
    Remove uma empresa. NÃO é oferecido na tela de propósito — pra ninguém
    apagar um cadastro sem querer. Um cadastro errado se conserta pelo
    "Editar". Se um dia precisar mesmo remover, apague a linha correspondente
    em `dados/config.json` (a versão anterior fica em config_anterior.json).
    """
    dados = armazenamento.carregar()
    antes = len(dados["empresas"])
    dados["empresas"] = [e for e in dados["empresas"] if e.get("id") != chave]
    if len(dados["empresas"]) == antes:
        raise ErroDeCadastro("Empresa não encontrada para excluir.")
    armazenamento.salvar(dados)
