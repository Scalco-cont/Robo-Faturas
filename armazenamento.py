# -*- coding: utf-8 -*-
"""
ARMAZENAMENTO DO CADASTRO
==========================
O cadastro de empresas feito pela tela (contas contábeis, banco, CNPJ) fica
guardado em `dados/config.json`.

Por que um arquivo à parte, e não mais no `config_empresas.py`?
Porque assim ninguém precisa abrir código pra cadastrar uma empresa — e,
quando o robô for atualizado, o cadastro de vocês não se perde junto.

Na primeira vez que o site roda, o arquivo é criado com a empresa 70 já
cadastrada (o que estava no código antigo). A partir daí, quem manda é a tela.

Backup: é só copiar a pasta `dados/`. Cabe num e-mail.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

PASTA_DADOS = Path("dados")
CAMINHO = PASTA_DADOS / "config.json"

# Como o robô nasce, se ainda não existir configuração salva
PADRAO = {
    "empresas": [
        {
            "codigo": 70,
            "nome": "Rodrigues S Hospitalar / Maranata Med",
            "banco": "bb",
            "debito": "4978",
            "credito": "800",
            "historico": "1",
            "pagina_pdf": 3,
            "cnpj": "",
        }
    ],
}


def _garantir_arquivo():
    PASTA_DADOS.mkdir(exist_ok=True)
    if not CAMINHO.exists():
        CAMINHO.write_text(
            json.dumps(PADRAO, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def carregar() -> dict:
    _garantir_arquivo()
    try:
        dados = json.loads(CAMINHO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # arquivo corrompido: guarda o quebrado e recomeça do padrão
        estragado = PASTA_DADOS / f"config_com_erro_{datetime.now():%Y%m%d_%H%M%S}.json"
        try:
            shutil.copy(CAMINHO, estragado)
        except OSError:
            pass
        CAMINHO.write_text(
            json.dumps(PADRAO, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return json.loads(json.dumps(PADRAO))

    dados.setdefault("empresas", [])
    return dados


def salvar(dados: dict):
    """Salva guardando uma cópia da versão anterior (segurança contra engano)."""
    _garantir_arquivo()
    try:
        shutil.copy(CAMINHO, PASTA_DADOS / "config_anterior.json")
    except OSError:
        pass
    CAMINHO.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
