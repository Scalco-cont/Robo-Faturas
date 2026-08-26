# -*- coding: utf-8 -*-
"""
ROBÔ DE CARTÃO EMPRESARIAL — SITE INTERNO
==========================================
O colaborador arrasta uma ou várias faturas em PDF, escolhe a empresa (ou
deixa no automático) e clica em Processar. O robô lê cada PDF, aplica as
regras do chamado e devolve um TXT por fatura + um ZIP com todos.

O que mudou nesta versão (correções):
  - O banco passou a ser identificado pelo CONTEÚDO do PDF, não pelo nome do
    arquivo. Antes, se o nome não tivesse "banco do brasil", nada funcionava.
  - Suporte a Bradesco (+ reserva genérica para os demais bancos).
  - Cada arquivo é processado de verdade: o ZIP do lote agora traz TODOS os
    TXT, e não só o do último arquivo.
  - Cada processamento vai pra uma pasta própria, então o navegador nunca
    mais devolve o TXT antigo em cache no lugar do novo.
  - Tela de Diagnóstico pra ver o texto que o robô leu do PDF quando algum
    layout novo não for reconhecido.

Regras de negócio (conforme o chamado):
  - Saída: DATA;DEBITO;CREDITO;HISTORICO;VALOR;COMPLEMENTO
  - COMPLEMENTO = descrição do PDF | DATA e VALOR = os mesmos do PDF
  - Parcelada 1ª parcela: lança valor × total de parcelas
  - Parcelada 2ª em diante: ignora
"""

import importlib
import io
import shutil
import uuid
import zipfile
from pathlib import Path

from flask import (Flask, request, jsonify, render_template,
                   send_file, abort, Response)

from config_empresas import (
    buscar_config, listar_empresas_para_tela, detectar_banco_pelo_nome,
    empresas_do_banco, buscar_por_cnpj, nome_banco, PALAVRAS_BANCO_NO_PDF,
    todas_empresas, bancos_para_tela, salvar_empresa, rotulo, ErroDeCadastro,
)
from extratores.base import (ler_texto_do_pdf, normalizar, mesma_empresa,
                             detectar_titular, detectar_cnpj)
from gerador_txt import gerar_conteudo

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

# Banco -> módulo do extrator. Para adicionar um banco novo, crie o arquivo
# em extratores/ e registre aqui.
EXTRATORES = {
    "bb":       "extratores.banco_do_brasil",
    "bradesco": "extratores.bradesco",
}
EXTRATOR_RESERVA = "extratores.padrao"

PASTA_SAIDA = Path("txt_gerados")
PASTA_TMP = Path("uploads_tmp")
PASTA_SAIDA.mkdir(exist_ok=True)
PASTA_TMP.mkdir(exist_ok=True)


# ── utilidades ─────────────────────────────────────────────────────────────

def carregar_extrator(banco: str):
    """Devolve a função extrair() do banco. Cai no genérico se não existir."""
    modulo = EXTRATORES.get(banco, EXTRATOR_RESERVA)
    return importlib.import_module(modulo).extrair, modulo == EXTRATOR_RESERVA


def detectar_banco_pelo_conteudo(texto_pdf: str):
    """
    Procura a marca do banco dentro do texto do PDF.
    Ganha o banco com mais ocorrências (evita falso positivo quando um banco
    é citado de passagem em letras miúdas).
    """
    texto = normalizar(texto_pdf)
    so_digitos = "".join(c for c in texto if c.isdigit())

    pontuacao = {}
    for banco, palavras in PALAVRAS_BANCO_NO_PDF.items():
        total = 0
        for p in palavras:
            alvo = normalizar(p)
            total += so_digitos.count(alvo) if alvo.isdigit() else texto.count(alvo)
        if total:
            pontuacao[banco] = total

    if not pontuacao:
        return None
    return max(pontuacao, key=pontuacao.get)


def nome_txt_seguro(nome_pdf: str) -> str:
    base = Path(nome_pdf).stem.strip() or "fatura"
    base = "".join(c for c in base if c.isalnum() or c in " -_.()").strip()
    return (base or "fatura") + ".txt"


def limpar_lotes_antigos(manter: int = 20):
    """Mantém só os últimos lotes na pasta de saída, pra não acumular lixo."""
    lotes = sorted(
        [p for p in PASTA_SAIDA.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for velho in lotes[manter:]:
        shutil.rmtree(velho, ignore_errors=True)


def sem_cache(resposta):
    resposta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resposta.headers["Pragma"] = "no-cache"
    return resposta


# ── telas ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html",
                           empresas=listar_empresas_para_tela(),
                           bancos=bancos_para_tela())


# ── processamento ──────────────────────────────────────────────────────────

@app.route("/processar", methods=["POST"])
def processar():
    """
    Recebe TODOS os arquivos de uma vez.
    Campo 'empresa': "auto" ou "CODIGO|BANCO" (ex: "70|bb").
    """
    escolha = (request.form.get("empresa") or "auto").strip()
    arquivos = request.files.getlist("arquivos")

    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo foi enviado."}), 400

    empresa_fixa = banco_fixo = None
    if escolha and escolha != "auto":
        empresa_fixa = escolha
        for e in todas_empresas():
            if e["id"] == empresa_fixa:
                banco_fixo = e["banco"]
                break
        if banco_fixo is None:
            return jsonify({"erro": "A empresa escolhida não está mais no "
                                    "cadastro. Recarregue a página."}), 400

    lote = uuid.uuid4().hex[:10]
    pasta_lote = PASTA_SAIDA / lote
    pasta_lote.mkdir(parents=True, exist_ok=True)

    resultados = []
    gerados = []
    nomes_usados = set()

    for arquivo in arquivos:
        nome_original = arquivo.filename or "arquivo.pdf"
        caminho_tmp = None
        sugestao = {}    # dados pra pré-preencher o cadastro quando dá erro

        try:
            if not nome_original.lower().endswith(".pdf"):
                raise ValueError("Não é um arquivo PDF.")

            caminho_tmp = PASTA_TMP / f"{lote}_{Path(nome_original).name}"
            arquivo.save(caminho_tmp)

            # 1) lê o texto uma vez só e reaproveita para tudo
            paginas = ler_texto_do_pdf(str(caminho_tmp))
            texto_pdf = "\n".join(paginas)

            # 2) descobre o banco: conteúdo do PDF > nome do arquivo > escolha
            banco = (detectar_banco_pelo_conteudo(texto_pdf)
                     or detectar_banco_pelo_nome(nome_original)
                     or banco_fixo)
            if not banco:
                raise ValueError(
                    "Não consegui identificar o banco desta fatura, nem pelo "
                    "conteúdo nem pelo nome do arquivo. Escolha a empresa/banco "
                    "na listinha acima e envie de novo."
                )

            # dados pra oferecer o cadastro na hora, se faltar empresa
            sugestao = {
                "banco":   banco,
                "titular": detectar_titular(texto_pdf),
                "cnpj":    detectar_cnpj(texto_pdf),
            }

            # 3) descobre a empresa
            avisos_arquivo = []
            if empresa_fixa is not None:
                config = buscar_config(empresa_fixa, banco)
            else:
                por_cnpj = buscar_por_cnpj(texto_pdf)
                if por_cnpj:
                    config = buscar_config(por_cnpj["id"], banco)
                else:
                    candidatas = empresas_do_banco(banco)
                    if not candidatas:
                        sugestao["oferecer_cadastro"] = True
                        raise ValueError(
                            f"Reconheci a fatura como {nome_banco(banco)}, mas "
                            f"nenhuma empresa está cadastrada nesse banco."
                        )

                    escolhida = candidatas[0]
                    if len(candidatas) > 1:
                        # tenta casar pela razão social impressa na fatura
                        titular_pdf = sugestao["titular"]
                        compativeis = [
                            c for c in candidatas
                            if titular_pdf and mesma_empresa(c["nome"], titular_pdf)
                        ] if titular_pdf else []

                        if len(compativeis) == 1:
                            escolhida = compativeis[0]
                            avisos_arquivo.append(
                                f"Identifiquei a empresa pelo nome impresso na "
                                f"fatura (\"{titular_pdf}\"). Se não for essa, "
                                f"escolha na listinha e envie de novo."
                            )
                        else:
                            nomes = ", ".join(
                                rotulo(c) for c in candidatas
                            )
                            raise ValueError(
                                f"Mais de uma empresa usa {nome_banco(banco)} "
                                f"({nomes}) e não consegui saber qual é pelo PDF. "
                                f"Escolha a empresa na listinha acima e envie de novo."
                            )
                    config = buscar_config(escolhida["id"], banco)

            if config.get("aviso"):
                avisos_arquivo.append(config["aviso"])

            # 4) extrai os lançamentos
            extrair, e_reserva = carregar_extrator(banco)
            if e_reserva:
                avisos_arquivo.append(
                    f"{nome_banco(banco)} ainda não tem regra própria — usei a "
                    f"leitura genérica. Confira o TXT antes de importar."
                )

            # A "página inicial" é uma característica do layout do banco.
            # Se o PDF é de outro banco (empresa escolhida na mão), ignoramos
            # esse número e deixamos o extrator do banco certo decidir.
            pagina = config["pagina_inicio"] if config["banco"] == banco else 0

            saida = extrair(str(caminho_tmp), pagina)
            lancamentos = saida["lancamentos"]
            avisos_arquivo.extend(saida.get("avisos", []))

            # Trava de segurança: o PDF está em nome de outra empresa?
            titular = saida.get("titular", "")
            if titular and not mesma_empresa(config["nome_empresa"], titular):
                avisos_arquivo.append(
                    f"Esta fatura está em nome de \"{titular}\", mas o TXT foi "
                    f"gerado para {config['rotulo']}. Confira antes de importar — "
                    f"se for outra empresa, cadastre-a em config_empresas.py "
                    f"com as contas dela."
                )

            if not lancamentos:
                resultados.append({
                    "arquivo": nome_original,
                    "status": "aviso",
                    "mensagem": (
                        f"Reconheci como {nome_banco(banco)} ({saida['paginas']} "
                        f"páginas), mas não encontrei nenhuma linha de compra. "
                        f"Use o botão 'Ver o que o robô leu' pra conferir o "
                        f"layout desta fatura."
                    ),
                    "avisos": avisos_arquivo,
                })
                continue

            # 5) gera o TXT
            nome_txt = nome_txt_seguro(nome_original)
            contador = 2
            while nome_txt in nomes_usados:
                nome_txt = f"{Path(nome_txt).stem}_{contador}.txt"
                contador += 1
            nomes_usados.add(nome_txt)

            conteudo = gerar_conteudo(lancamentos, config)
            (pasta_lote / nome_txt).write_bytes(conteudo)
            gerados.append(nome_txt)

            parceladas = sum(1 for l in lancamentos if l["parcela_total"])
            total = sum(l["valor"] for l in lancamentos)

            resultados.append({
                "arquivo": nome_original,
                "status": "ok",
                "mensagem": (
                    f"{len(lancamentos)} lançamento(s) — {nome_banco(banco)} — "
                    f"{config['rotulo']} — "
                    f"total R$ {total:,.2f}".replace(",", "X")
                                             .replace(".", ",")
                                             .replace("X", ".")
                    + (f" — {parceladas} parcelada(s)" if parceladas else "")
                ),
                "avisos": avisos_arquivo,
                "titular": titular,
                "txt": nome_txt,
                "lote": lote,
                "previa": [
                    {"data": l["data"], "descricao": l["descricao"],
                     "valor": f"{l['valor']:.2f}",
                     "parcelas": l["parcela_total"] or ""}
                    for l in lancamentos[:8]
                ],
            })

        except Exception as e:
            resultados.append({
                "arquivo": nome_original,
                "status": "erro",
                "mensagem": str(e) or e.__class__.__name__,
                "avisos": [],
                "sugestao": sugestao,
            })
        finally:
            if caminho_tmp:
                try:
                    caminho_tmp.unlink(missing_ok=True)
                except OSError:
                    pass

    resposta = {"resultados": resultados, "lote": lote}

    if gerados:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for nome_txt in gerados:
                zf.write(pasta_lote / nome_txt, arcname=nome_txt)
        (pasta_lote / "_lote.zip").write_bytes(buf.getvalue())
        resposta["zip_disponivel"] = len(gerados) > 0
        resposta["qtd_txt"] = len(gerados)

    limpar_lotes_antigos()
    return jsonify(resposta)


@app.route("/diagnostico", methods=["POST"])
def diagnostico():
    """
    Mostra o texto que o robô conseguiu ler do PDF, página por página.
    Serve pra ajustar o extrator quando um banco/layout novo não é reconhecido:
    é só copiar essa saída e mandar pro desenvolvedor.
    """
    arquivo = request.files.get("arquivo")
    if not arquivo:
        return jsonify({"erro": "Envie um PDF."}), 400

    caminho_tmp = PASTA_TMP / f"diag_{uuid.uuid4().hex[:8]}.pdf"
    try:
        arquivo.save(caminho_tmp)
        paginas = ler_texto_do_pdf(str(caminho_tmp))
        texto = "\n".join(paginas)
        return jsonify({
            "arquivo": arquivo.filename,
            "paginas": len(paginas),
            "banco_detectado": detectar_banco_pelo_conteudo(texto) or "(nenhum)",
            "conteudo": [
                {"pagina": i + 1, "linhas": p.split("\n")[:80]}
                for i, p in enumerate(paginas)
            ],
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        try:
            caminho_tmp.unlink(missing_ok=True)
        except OSError:
            pass


# ── configurações (tela do próprio site) ───────────────────────────────────

@app.route("/api/config")
def api_config():
    """Devolve tudo que a tela de configurações precisa mostrar."""
    return sem_cache(jsonify({
        "empresas": [
            {**e, "banco_label": nome_banco(e["banco"])}
            for e in todas_empresas()
        ],
        "bancos": bancos_para_tela(),
    }))


@app.route("/api/empresa", methods=["POST"])
def api_salvar_empresa():
    corpo = request.json or {}
    try:
        salva = salvar_empresa(corpo.get("empresa", {}),
                               corpo.get("id_original", ""))
    except ErroDeCadastro as e:
        return jsonify({"erro": str(e)}), 400
    return jsonify({
        "ok": True,
        "mensagem": f"{rotulo(salva)} salva.",
    })


# ── downloads ──────────────────────────────────────────────────────────────

@app.route("/download/<lote>/<nome_arquivo>")
def download(lote, nome_arquivo):
    caminho = PASTA_SAIDA / Path(lote).name / Path(nome_arquivo).name
    if not caminho.exists():
        abort(404)
    return sem_cache(send_file(caminho, as_attachment=True,
                               download_name=caminho.name))


@app.route("/download-lote/<lote>")
def download_lote(lote):
    caminho = PASTA_SAIDA / Path(lote).name / "_lote.zip"
    if not caminho.exists():
        abort(404)
    return sem_cache(send_file(caminho, as_attachment=True,
                               download_name="txt_cartao.zip"))


@app.errorhandler(413)
def arquivo_grande(_):
    return jsonify({"erro": "Arquivo muito grande (limite de 200 MB)."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
