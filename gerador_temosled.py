import json
import math
import os
import random
import tempfile
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, jsonify, request, send_from_directory


app = Flask(__name__)

EXPECTED_AUTH = os.getenv("MW_EXPECTED_AUTH", "Bearer MKV-JOB")
EXPECTED_UA = os.getenv("MW_EXPECTED_USER_AGENT", "Google-Cloud-Scheduler")
GCS_BUCKET = os.getenv("MW_GCS_BUCKET", "maso_storage_main")
MW_PUBLIC_ROOT = os.getenv("MW_PUBLIC_ROOT", "/home/makevendas/public_html")
MW_DISABLE_GCS_UPLOAD = os.getenv("MW_DISABLE_GCS_UPLOAD", "false").strip().lower() in {"1", "true", "sim", "yes", "on"}
MW_ALLOW_LOCAL_URL_ON_UPLOAD_ERROR = os.getenv("MW_ALLOW_LOCAL_URL_ON_UPLOAD_ERROR", "true").strip().lower() in {"1", "true", "sim", "yes", "on"}

# ── Assets TemosLED ──────────────────────────────────────────────────────────
LOGO_URL = "https://makevendas.com.br/img/4642/logo_leds.jpg"
AMBIENTE_RESIDENCIA_URL = "https://www.makevendas.com.br/assets/residencia.jpg"
AMBIENTE_MURO_URL = "https://www.makevendas.com.br/assets/muro.jpeg"
DEMO_PAINEL_URL = "https://www.makevendas.com.br/img/mavi/4642/demo-3.png"


# ── Helpers ──────────────────────────────────────────────────────────────────

def br_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        if isinstance(value, str):
            v = value.strip().replace(" ", "")
            if v == "":
                return float(default)
            return float(v.replace(",", "."))
        return float(value)
    except Exception:
        return float(default)


def br_int(value, default=0):
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def br_bool(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sim", "yes", "on"}
    return bool(default)


def format_moeda(valor):
    formatted = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def get_moeda_payload(fx_dict, keys, fallback):
    if isinstance(fx_dict, dict):
        for key in keys:
            val = fx_dict.get(key)
            if val is not None and str(val) != "":
                return str(val)
    return format_moeda(fallback)


def fmt_decimal_br(value, decimals=2):
    """Formata número com vírgula decimal e ponto de milhar (padrão BR)."""
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── Informações Importantes ─────────────────────────────────────────────────

def build_informacoes_importantes(modalidade, linha, tipo_painel, tipo_ambiente):
    tipo_painel_esc = escape(tipo_painel)

    if modalidade == "compra":
        if linha == "acessivel":
            if tipo_ambiente == "interno":
                explica_ambiente = f"""
                <li style="margin-bottom: 4px;"><strong>•</strong> O modelo {tipo_painel_esc} é ideal para áreas internas.<br/>
                    Uma opção mais acessível e indicada para quem busca econômia.</li>
                """
            else:
                explica_ambiente = f"""
                <li style="margin-bottom: 4px;"><strong>•</strong> O modelo {tipo_painel_esc} é ideal para áreas externas: possui alta resistência à chuva, sol e poeira.<br/>
                    Pode molhar sem risco, entregando imagem nítida e brilhante em qualquer clima.<br/>
                    Uma opção mais acessível e indicada para quem busca econômia.</li>
                """

            info = f"""
            <ul style="list-style-type: none; padding-left: 5px; font-size: 9pt !important;">
                <li style="margin-bottom: 4px;"><strong>•</strong> Já incluso no valor cases para armazenamento e módulos reservas.</li>
                <li style="margin-bottom: 4px;"><strong>•</strong> Os painéis da linha custo/benefício são fornecidos apenas para venda.
                    Caso deseje a instalação, contamos com uma rede de técnicos parceiros qualificados que indicamos para realizar o serviço com segurança e qualidade.<br/></li>
                <li style="margin-bottom: 4px;"><strong>•</strong> Garantia de 3 meses de fábrica.</li>
                {explica_ambiente}
            </ul>
            """
        else:
            # Premium
            if tipo_ambiente == "interno":
                explica_ambiente = f"""
                <li style="margin-bottom: 4px;"><strong>•</strong> O modelo {tipo_painel_esc} é ideal para áreas internas.<br/>
                    Para quem deseja o que há de melhor no mercado.<br/>
                    Esse painel é fabricado com componentes de alta qualidade, garantindo maior durabilidade e desempenho.</li>
                """
            else:
                explica_ambiente = f"""
                <li style="margin-bottom: 4px;"><strong>•</strong> O modelo {tipo_painel_esc} é ideal para áreas externas: possui alta resistência à chuva, sol e poeira.<br/>
                    Pode molhar sem risco, entregando imagem nítida e brilhante em qualquer clima.<br/>
                    Para quem deseja o que há de melhor no mercado.<br/>
                    Esse painel é fabricado com componentes de alta qualidade, garantindo maior durabilidade e desempenho.</li>
                """

            info = f"""
            <ul style="list-style-type: none; padding-left: 5px; font-size: 9pt !important;">
                <li style="margin-bottom: 4px;"><strong>•</strong> Já incluso no valor cases para armazenamento, peças reservas pra trocas rápidas: fonte, receiver e módulo extra.</li>
                <li style="margin-bottom: 4px;"><strong>•</strong> Para fixação dos painéis normalmente é utilizado estrutura em metalon.<br/>
                    Caso não haja estrutura no local, oferecemos a solução completa com o apoio de um serralheiro de nossa confiança.<br/>
                    O serviço é cobrado por metro quadrado e repassado sem acréscimo de lucro da nossa parte.</li>
                <li style="margin-bottom: 4px;"><strong>•</strong> Garantia de 12 meses de fábrica.</li>
                {explica_ambiente}
            </ul>
            """
    else:
        # Locação
        if tipo_ambiente == "interno":
            explica_ambiente = ""
        else:
            explica_ambiente = """
            <li style="margin-bottom: 4px;"><strong>•</strong> Os painéis outdoor possuem alta resistência à chuva, sol e poeira.<br/>
                Pode molhar sem risco, entregando imagem nítida e brilhante em qualquer clima.</li>
            """

        info = f"""
        <ul style="list-style-type: none; padding-left: 5px; font-size: 9pt !important;">
            <li style="margin-bottom: 4px;"><strong>•</strong> Os painéis vão dentro de cases para fácil armazenamento e transporte.</li>
            <li style="margin-bottom: 4px;"><strong>•</strong> Essa proposta não inclui valores técnicos e deslocamento.</li>
            {explica_ambiente}
        </ul>
        """

    return info


# ── Cálculo dimensões mockup (px) ───────────────────────────────────────────

def calcular_dimensoes_mockup(largura_m, altura_m, local):
    """Converte metros → pixels para o overlay do painel na imagem de ambiente."""
    # Calibração base: 3m = 250px largura, 2m = 150px altura
    px_por_m_x = 250.0 / 3.0   # ~83.333
    px_por_m_y = 150.0 / 2.0   # 75

    largura_px = largura_m * px_por_m_x
    altura_px = altura_m * px_por_m_y

    if largura_px > 600:
        largura_px = 600

    # Limita para caber no container de 400px
    limite_altura = 400
    if altura_px > (limite_altura - 10):
        fator = (limite_altura - 10) / altura_px
        altura_px *= fator
        largura_px *= fator

    foto_largura_px = 600
    foto_altura_px = 400

    # Posição vertical ajustada conforme PHP original
    if altura_px > 150:
        if local == "residencia":
            top_px = 90 - (altura_px - 150)
        else:
            top_px = 90 - (altura_px - 220)
    else:
        top_px = 90 + (150 - altura_px)

    left_px = (680 - largura_px) / 2

    return round(largura_px, 2), round(altura_px, 2), round(left_px, 2), round(top_px, 2)


# ── Upload GCS ───────────────────────────────────────────────────────────────

def is_https_request(req):
    https_val = str(req.environ.get("HTTPS", "")).lower()
    forwarded = req.headers.get("X-Forwarded-Proto", "")
    forwarded_first = forwarded.split(",")[0].strip().lower() if forwarded else ""
    return req.is_secure or https_val in {"on", "1", "true"} or forwarded_first == "https"


def upload_to_gcs(local_file_path, customer_id, filename, fallback_public_url):
    from google.cloud import storage
    from datetime import timedelta

    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET)

    blob_path = f"tasks/{customer_id}/{filename}"
    blob = bucket.blob(blob_path)

    def build_bucket_url():
        if br_bool(os.getenv("MW_GCS_MAKE_PUBLIC", "false"), False):
            blob.make_public()
            return blob.public_url

        signed_seconds = br_int(os.getenv("MW_GCS_SIGNED_URL_SECONDS", 604800), 604800)
        if signed_seconds > 0:
            try:
                return blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(seconds=signed_seconds),
                    method="GET",
                )
            except Exception:
                pass

        return f"https://storage.googleapis.com/{GCS_BUCKET}/{quote(blob_path, safe='/')}"

    if not blob.exists(storage_client):
        blob.upload_from_filename(local_file_path, content_type="application/pdf")
        media_link = build_bucket_url()

        if br_bool(os.getenv("MW_DELETE_LOCAL_AFTER_UPLOAD", "true"), True):
            try:
                os.remove(local_file_path)
            except OSError:
                pass
    else:
        media_link = build_bucket_url()

    return {
        "mediaLink": media_link,
        "contentType": "application/pdf",
    }


# ── Engine de PDF ────────────────────────────────────────────────────────────

def generate_pdf_from_html(html_content, output_path, base_url):
    engine = os.getenv("MW_PDF_ENGINE", "auto").strip().lower()
    last_error = None

    if engine in {"auto", "weasyprint"}:
        try:
            from weasyprint import HTML

            HTML(string=html_content, base_url=base_url).write_pdf(output_path)
            return
        except Exception as exc:
            last_error = exc
            if engine == "weasyprint":
                raise Exception(
                    "WeasyPrint failed. Install GTK runtime on Windows or set MW_PDF_ENGINE=playwright. "
                    f"Original error: {exc}"
                )

    if engine in {"auto", "playwright"}:
        try:
            from playwright.sync_api import sync_playwright

            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as tmp:
                tmp.write(html_content)
                temp_html_path = tmp.name

            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(Path(temp_html_path).as_uri(), wait_until="networkidle")
                    page.pdf(
                        path=output_path,
                        format="A4",
                        print_background=True,
                        margin={"top": "20mm", "right": "15mm", "bottom": "15mm", "left": "15mm"},
                    )
                    browser.close()
                return
            finally:
                try:
                    os.remove(temp_html_path)
                except OSError:
                    pass
        except Exception as exc:
            msg = "Playwright PDF failed. Run 'pip install playwright' and 'python -m playwright install chromium'."
            if last_error is not None:
                raise Exception(f"{msg} WeasyPrint error: {last_error}. Playwright error: {exc}")
            raise Exception(f"{msg} Error: {exc}")

    raise Exception("Unsupported MW_PDF_ENGINE. Use auto, weasyprint, or playwright.")


# ── CSS Compartilhado ────────────────────────────────────────────────────────

SHARED_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: Arial, sans-serif;
        font-size: 11pt;
        color: #333;
        background: #fff;
        padding: 15mm;
    }
    .header {
        text-align: center;
        margin-bottom: 25px;
        padding-bottom: 15px;
    }
    h1 {
        font-size: 12pt;
        font-weight: bold;
        color: #222;
        margin-bottom: 5px;
    }
    h2 {
        font-size: 12pt;
        font-weight: normal;
        color: #666;
        margin-top: 25px;
        margin-bottom: 12px;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    th, td {
        padding: 8px;
        text-align: left;
        border: 1px solid #ddd;
    }
    th {
        background: #f5f5f5;
        font-weight: bold;
        color: #333;
    }
    .desc { width: 50%; }
    .ref { width: 25%; }
    .valor { width: 40%; }
    .total { width: 25%; }

    .total-row {
        background: #000;
        color: #fff;
        font-weight: bold;
        font-size: 12pt;
    }
    .total-row td {
        border-color: #000;
        padding: 10px;
    }

    .destaque {
        color: #c00;
        font-size: 10pt;
        font-style: italic;
        margin-top: 5px;
    }

    .desconto-info {
        text-align: right;
        margin: 15px 0;
        font-size: 11pt;
    }
    .desconto-info .label {
        font-style: italic;
        color: #666;
    }
    .desconto-info .valor-final {
        font-weight: bold;
        font-size: 13pt;
        color: #000;
        margin-top: 5px;
    }

    ul {
        margin: 10px 0 10px 5px;
        line-height: 1.7;
        list-style-type: none;
        padding-left: 0;
    }
    ul li {
        margin-bottom: 12px;
    }

    .footer {
        margin-top: 30px;
        padding-top: 15px;
        border-top: 1px solid #ddd;
        font-size: 10pt;
        color: #666;
    }
    .footer strong {
        color: #000;
    }
"""


# ── Build HTML: Modo Completa ────────────────────────────────────────────────

def build_html_completa(content, largura, altura, area_m2, diagonal_pol, tipo_painel,
                        modalidade, diarias, preco_m2, subtotal_painel, desconto_percent,
                        desconto_valor, estrutura_valor, preco_estrutura_m2, completa_valor,
                        total_geral, saida_minima, usa_lojas, tipo_operacao,
                        informacoes_importantes, data_atual):
    linhas_tabela = ""

    # Preço Total (Painel)
    linhas_tabela += f"""<tr>
        <td class="desc">Preço Total (Painel)</td>
        <td class="ref">{format_moeda(subtotal_painel)}</td>
        <td class="total">{format_moeda(subtotal_painel)}</td>
    </tr>"""

    # Metragem
    linhas_tabela += f"""<tr>
        <td class="desc">Metragem</td>
        <td class="ref">{fmt_decimal_br(largura)}m x {fmt_decimal_br(altura)}m</td>
        <td class="total">--</td>
    </tr>"""

    # Total m²
    linhas_tabela += f"""<tr>
        <td class="desc">Total de m²</td>
        <td class="ref">{fmt_decimal_br(area_m2)} m²</td>
        <td class="total">--</td>
    </tr>"""

    # Polegadas
    linhas_tabela += f"""<tr>
        <td class="desc">Polegadas</td>
        <td class="ref">{round(diagonal_pol)}"</td>
        <td class="total">--</td>
    </tr>"""

    # Preço por m²
    label_preco_m2 = "Preço por m²"
    if modalidade == "locacao" and diarias > 1:
        label_preco_m2 += " / dia"
    linhas_tabela += f"""<tr>
        <td class="desc">{label_preco_m2}</td>
        <td class="ref">{format_moeda(preco_m2)}</td>
        <td class="total">--</td>
    </tr>"""

    # Diárias (locação)
    if modalidade == "locacao":
        linhas_tabela += f"""<tr>
            <td class="desc">Diárias</td>
            <td class="ref">{diarias}</td>
            <td class="total">--</td>
        </tr>"""

    # Painel
    linhas_tabela += f"""<tr>
        <td class="desc">Painel</td>
        <td class="ref">{escape(tipo_painel)}</td>
        <td class="total">--</td>
    </tr>"""

    # Linhas extras COMPRA: processadora + estrutura
    if modalidade == "compra":
        if usa_lojas:
            proc_desc = "Controladora TB"
            proc_ref = "Vídeos em Loop"
            proc_total = 2000
        else:
            proc_desc = "Processadora (AMS-MVP 300 + SC)"
            proc_ref = "TV, Youtube, Netflix etc"
            proc_total = 3500

        linhas_tabela += f"""<tr>
            <td class="desc">{proc_desc}</td>
            <td class="ref">{proc_ref}</td>
            <td class="total">{format_moeda(proc_total)}</td>
        </tr>"""

        linhas_tabela += f"""<tr>
            <td class="desc">Estrutura em Metalon</td>
            <td class="ref">R$ {fmt_decimal_br(preco_estrutura_m2)} m²</td>
            <td class="total">{format_moeda(estrutura_valor)}</td>
        </tr>"""

    # Instalação e Logística
    instalacao_txt = format_moeda(completa_valor) if completa_valor > 0 else "--"
    linhas_tabela += f"""<tr>
        <td class="desc">Instalação e Logística</td>
        <td class="ref">--</td>
        <td class="total">{instalacao_txt}</td>
    </tr>"""

    # Total
    total_row = f"""<table style="margin-top: 0; margin-bottom: 15px;">
        <tr class="total-row">
          <td colspan="2" style="text-align: right; padding-right: 15px;">Total =</td>
          <td>{format_moeda(total_geral)}</td>
        </tr>
    </table>"""

    destaque_minima = '<p class="destaque">* Valor de saída mínima aplicado</p>' if saida_minima else ""

    bloco_desconto = ""
    if desconto_valor > 0:
        total_com_desconto = total_geral - desconto_valor
        bloco_desconto = f"""
        <div class="desconto-info">
            <p class="label">Desconto aplicado: {format_moeda(desconto_valor)}</p>
            <p class="valor-final">Total à vista: {format_moeda(total_com_desconto)}</p>
        </div>"""

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
      <meta charset="UTF-8">
      <style>
        {SHARED_CSS}
      </style>
    </head>
    <body>
      <div class="header">
        <h1>Pré Proposta Orçamentária - LED</h1>
        <p style="color: #999; font-size: 10pt;">www.temosled.com.br</p>
      </div>

      <h2>Detalhamento da Proposta</h2>

      <table>
        <thead>
          <tr>
            <th class="desc">Descrição</th>
            <th class="ref">Referência</th>
            <th class="total">Total</th>
          </tr>
        </thead>
        <tbody>
          {linhas_tabela}
        </tbody>
      </table>

      {total_row}
      {destaque_minima}
      {bloco_desconto}
      <h2>Informações Importantes para {tipo_operacao} dos Painéis</h2>

      <ul style="list-style-type: none; padding-left: 5px;">
        <li style="margin-bottom: 12px;"><strong>•</strong> Já incluso no valor: Cases de transporte e peças de backup para trocas rápidas (fonte, receiver e módulos extras)</li>
        <li style="margin-bottom: 12px;"><strong>•</strong> Para fixação dos painéis normalmente é utilizado estrutura em metalon.<br/>
          Caso não haja estrutura no local, oferecemos a solução completa com o apoio de um serralheiro de nossa confiança.<br/>
          O serviço é cobrado por metro quadrado e repassado sem acréscimo de lucro da nossa parte.</li>
        <li style="margin-bottom: 12px;"><strong>•</strong> O modelo P3.9 é ideal para áreas externas: possui alta resistência à chuva, sol e poeira.<br/>
          Pode molhar sem risco, entregando imagem nítida e brilhante em qualquer clima.<br/>
          Durável, seguro e feito para quem busca impacto com confiança.</li>
      </ul>

      <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">

      <p style="font-size: 10pt; line-height: 1.6; margin-bottom: 15px;">
        <strong>Obs:</strong> Para instalação dos equipamentos cobramos R$ 4,50 por km rodado, partindo de nosso depósito na Vila Maria - SP.
      </p>

      <div class="footer">
        <p><strong>Data de envio:</strong> {data_atual} | <strong>Validade:</strong> 10 dias</p>
        <p><strong>Contato:</strong> Molina (11) 91120-5678</p>
        <p><strong>E-mail:</strong> contato@temosled.com.br</p>
        <p style="margin-top: 12px; text-align: center; font-weight: bold;">
          Conte com a nossa equipe para um atendimento ágil, entrega segura<br>
          e suporte especializado em todas as etapas do seu projeto.
        </p>
      </div>
    </body>
    </html>
    """
    return html


# ── Build HTML: Modo Básico ──────────────────────────────────────────────────

def build_html_basica(content, largura, altura, area_m2, diagonal_pol, tipo_painel,
                      modalidade, diarias, preco_m2, subtotal_painel, desconto_percent,
                      desconto_valor, total_geral, tipo_operacao, informacoes_importantes,
                      data_atual, local, gabinete_data):
    tipo_painel_esc = escape(tipo_painel)
    tipo_operacao_esc = escape(tipo_operacao)

    # ── Tabela básica (sem "Linha") ──────────────────────────────────────
    linhas_basica = ""
    linhas_basica += f'<tr><td class="desc">Preço Total (Painel)</td><td class="valor">{format_moeda(subtotal_painel)}</td></tr>'
    linhas_basica += f'<tr><td class="desc">Metragem</td><td class="valor">{fmt_decimal_br(largura)}m x {fmt_decimal_br(altura)}m</td></tr>'
    linhas_basica += f'<tr><td class="desc">Total de m²</td><td class="valor">{fmt_decimal_br(area_m2)} m²</td></tr>'
    linhas_basica += f'<tr><td class="desc">Polegadas</td><td class="valor">{round(diagonal_pol)}"</td></tr>'
    linhas_basica += f'<tr><td class="desc">Painel</td><td class="valor">{tipo_painel_esc}</td></tr>'
    linhas_basica += f'<tr><td class="desc">Modalidade</td><td class="valor">{tipo_operacao_esc}</td></tr>'
    # NOTA: "Linha" removida conforme solicitado

    if modalidade == "locacao":
        linhas_basica += f'<tr><td class="desc">Diárias</td><td class="valor">{diarias}</td></tr>'

    # ── Seção de Gabinetes ───────────────────────────────────────────────
    gabinetes_html = ""
    if isinstance(gabinete_data, list) and len(gabinete_data) > 0:
        has_opcoes = any(
            isinstance(g, dict) and (g.get("opcao_cima") or g.get("opcao_baixo"))
            for g in gabinete_data
        )

        for gi, gab in enumerate(gabinete_data):
            if not isinstance(gab, dict):
                continue
            gab_type = escape(str(gab.get("gabinete_type", "64x48cm")))
            preco_gab = br_float(gab.get("preco_gabinete", 0), 0)
            opcao_cima = gab.get("opcao_cima", {})
            opcao_baixo = gab.get("opcao_baixo", {})

            gab_label = f"Gabinete {gi + 1}" if len(gabinete_data) > 1 else "Configuração de Gabinetes"
            gabinetes_html += f'<h2 style="margin-top:25px; margin-bottom:8px; font-weight:bold; color:#333;">{gab_label} ({gab_type})</h2>'
            gabinetes_html += f'<p style="font-size:9pt; margin-bottom:10px; color:#555;">Preço por gabinete: {format_moeda(preco_gab)}</p>'

            # Opção para cima
            if isinstance(opcao_cima, dict) and opcao_cima:
                oc_orient = escape(str(opcao_cima.get("orient", "-")))
                oc_gabs = br_int(opcao_cima.get("gabinetes", 0), 0)
                oc_larg = br_float(opcao_cima.get("largura", 0), 0)
                oc_alt = br_float(opcao_cima.get("altura", 0), 0)
                oc_valor = escape(str(opcao_cima.get("valor_brl", format_moeda(opcao_cima.get("valor", 0)))))

                gabinetes_html += '<h3 style="margin-top:12px; margin-bottom:6px; font-size:10pt; color:#1a7f37;">🔼 Opção mais próxima para cima</h3>'
                gabinetes_html += '<table><tbody>'
                gabinetes_html += '<tr><th class="desc">Descrição</th><th class="valor">Detalhe</th></tr>'
                gabinetes_html += f'<tr><td class="desc">Orientação</td><td class="valor">{oc_orient}</td></tr>'
                gabinetes_html += f'<tr><td class="desc">Quantidade de Gabinetes</td><td class="valor">{oc_gabs}</td></tr>'
                gabinetes_html += f'<tr><td class="desc">Tamanho Final</td><td class="valor">{fmt_decimal_br(oc_larg)}m x {fmt_decimal_br(oc_alt)}m</td></tr>'
                gabinetes_html += f'<tr class="total-row"><td class="desc"><strong>Valor</strong></td><td class="valor"><strong>{oc_valor}</strong></td></tr>'
                gabinetes_html += '</tbody></table>'

            # Opção para baixo
            if isinstance(opcao_baixo, dict) and opcao_baixo:
                ob_orient = escape(str(opcao_baixo.get("orient", "-")))
                ob_gabs = br_int(opcao_baixo.get("gabinetes", 0), 0)
                ob_larg = br_float(opcao_baixo.get("largura", 0), 0)
                ob_alt = br_float(opcao_baixo.get("altura", 0), 0)
                ob_valor = escape(str(opcao_baixo.get("valor_brl", format_moeda(opcao_baixo.get("valor", 0)))))

                gabinetes_html += '<h3 style="margin-top:12px; margin-bottom:6px; font-size:10pt; color:#cf222e;">🔽 Opção mais próxima para baixo</h3>'
                gabinetes_html += '<table><tbody>'
                gabinetes_html += '<tr><th class="desc">Descrição</th><th class="valor">Detalhe</th></tr>'
                gabinetes_html += f'<tr><td class="desc">Orientação</td><td class="valor">{ob_orient}</td></tr>'
                gabinetes_html += f'<tr><td class="desc">Quantidade de Gabinetes</td><td class="valor">{ob_gabs}</td></tr>'
                gabinetes_html += f'<tr><td class="desc">Tamanho Final</td><td class="valor">{fmt_decimal_br(ob_larg)}m x {fmt_decimal_br(ob_alt)}m</td></tr>'
                gabinetes_html += f'<tr class="total-row"><td class="desc"><strong>Valor</strong></td><td class="valor"><strong>{ob_valor}</strong></td></tr>'
                gabinetes_html += '</tbody></table>'

    # ── Decide imagem de ambiente ────────────────────────────────────────
    ambiente_img = AMBIENTE_RESIDENCIA_URL if local == "residencia" else AMBIENTE_MURO_URL

    # ── Calcula dimensões do mockup ──────────────────────────────────────
    largura_px, altura_px, left_px, top_px = calcular_dimensoes_mockup(largura, altura, local)

    largura_fmt = fmt_decimal_br(largura)
    altura_fmt = fmt_decimal_br(altura)

    # ── Página do mockup (apenas compra) ─────────────────────────────────
    mockup_page = ""
    if modalidade == "compra":
        label_h_left = left_px - 65
        label_h_top = altura_px / 2
        label_w_left = (largura_px / 2) - 24

        mockup_page = f"""
        <div style="position: relative; width: 100%; height: 1020px;">
            <div style="position: relative; display: inline-block; width: 100%; text-align: center; padding: 0px;">
                <img src="{LOGO_URL}" border="0" width="130px" />
            </div>
            <p style="font-size: 11pt; font-weight: bold; text-align: left; margin-top: 20px;">
                A representação abaixo demonstra como um painel de {largura_fmt}m x {altura_fmt}m se aplica no ambiente.
            </p>
            <div style="position: relative; width: 100%; height: 400px; background: url('{ambiente_img}') no-repeat center center; background-size: cover;">
                <div style="position: absolute; width: {largura_px}px; height: {altura_px}px; background: black; z-index: 9; margin-left: {left_px}px; margin-top: {top_px}px; border: solid 5px #57fcfa; background: url('{DEMO_PAINEL_URL}') no-repeat center center; background-size: 100% 100%;">
                    <div style="position: absolute; width: 48px; padding: 5px; background-color: black; color: white; z-index: 9; margin-top: -40px; margin-left: {label_w_left}px; text-align: center; font-size: 9pt;">{largura_fmt}m</div>
                    <div style="position: absolute; width: 40px; padding: 5px; background-color: black; color: white; z-index: 9; margin-top: {label_h_top}px; margin-left: -65px; text-align: center; font-size: 9pt;">{altura_fmt}m</div>
                </div>
            </div>
            <p style="font-size: 9pt; font-weight: bold; text-align: left; margin-top: 20px;">
                Conte com a nossa equipe para um atendimento ágil e suporte especializado em todas as etapas do seu projeto.
            </p>
            <p></p><p></p><p></p><p></p><p></p><p></p><p></p>
            <p style="font-size: 9pt; text-align: left; margin: 0px; padding: 0px;"><strong>Data envio: {data_atual}</strong> - Validade da proposta 10 dias</p>
            <p style="font-size: 9pt; text-align: left; margin: 0px; padding: 0px;"><strong>Molina</strong> (11) 91120-5678</p>
            <p style="font-size: 9pt; text-align: left; margin: 0px; padding: 0px;">E-mail: contato@temosled.com.br</p>
        </div>
        <div style="position: absolute; width: 100%; left: 0px; bottom: 0px; padding: 20px 0px;">
            <p style="font-size: 9pt; text-align: center;">www.temosled.com.br</p>
        </div>
        """

    # ── Monta HTML final ─────────────────────────────────────────────────
    if modalidade == "compra":
        html = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <style>
                {SHARED_CSS}
            </style>
        </head>
        <body>
            <div style="position: relative; width: 100%; height: 1020px;">
                <div style="position: relative; display: inline-block; width: 100%; text-align: center; padding: 0px;">
                    <img src="{LOGO_URL}" border="0" width="130px" />
                </div>
                <div class="header">
                    <h1>Pré Proposta Orçamentária - LED</h1>
                </div>
                <table border="1" cellpadding="6" cellspacing="0" width="100%">
                    <tr><th width="60%">Descrição</th><th>Valor</th></tr>
                    {linhas_basica}
                </table>
                <p style="font-size: 11pt; font-weight: bold; text-align: left; margin-top: 20px;">
                    Informações importantes para {tipo_operacao_esc} do painel:
                </p>
                {informacoes_importantes}
                {gabinetes_html}
            </div>
            <div style="position: absolute; width: 100%; left: 0px; bottom: 0px; padding: 20px 0px;">
                <p style="font-size: 9pt; text-align: center;">www.temosled.com.br</p>
            </div>

            {mockup_page}
        </body>
        </html>
        """
    else:
        # Locação: apenas uma página
        html = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <style>
                {SHARED_CSS}
            </style>
        </head>
        <body>
            <div style="position: relative; width: 100%; height: 1020px;">
                <div style="position: relative; display: inline-block; width: 100%; text-align: center; padding: 0px;">
                    <img src="{LOGO_URL}" border="0" width="130px" />
                </div>
                <div class="header">
                    <h1>Pré Proposta Orçamentária - LED</h1>
                </div>
                <table border="1" cellpadding="6" cellspacing="0" width="100%">
                    <tr><th width="60%">Descrição</th><th>Valor</th></tr>
                    {linhas_basica}
                </table>
                <p style="font-size: 11pt; font-weight: bold; text-align: left; margin-top: 20px;">
                    Informações importantes para {tipo_operacao_esc} do painel:
                </p>
                {informacoes_importantes}
                {gabinetes_html}
                <p style="font-size: 9pt; font-weight: bold; text-align: left; margin-top: 20px;">
                    Conte com a nossa equipe para um atendimento ágil e suporte especializado em todas as etapas do seu projeto.
                </p>
                <p></p>
                <p style="font-size: 9pt; text-align: left; margin: 0px; padding: 0px;"><strong>Data envio: {data_atual}</strong> - Validade da proposta 10 dias</p>
                <p style="font-size: 9pt; text-align: left; margin: 0px; padding: 0px;"><strong>Molina</strong> (11) 91120-5678</p>
                <p style="font-size: 9pt; text-align: left; margin: 0px; padding: 0px;">E-mail: contato@temosled.com.br</p>
            </div>
            <div style="position: absolute; width: 100%; left: 0px; bottom: 0px; padding: 20px 0px;">
                <p style="font-size: 9pt; text-align: center;">www.temosled.com.br</p>
            </div>
        </body>
        </html>
        """

    return html


# ══════════════════════════════════════════════════════════════════════════════
# ── ENDPOINT PRINCIPAL ────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

@app.after_request
def add_default_headers(response):
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/pdf-generator-temosled.php", methods=["POST", "GET"])
@app.route("/pdf-generator-temosled", methods=["POST", "GET"])
def pdf_generator_temosled():
    try:
        if request.method not in {"POST", "GET"}:
            return jsonify({"error": {"message": "Request method not allowed."}}), 405

        if not is_https_request(request):
            return jsonify({"error": {"message": "HTTPS not allowed."}}), 405

        auth_header = request.headers.get("Authorization") or request.environ.get("HTTP_AUTHORIZATION") or ""
        if auth_header != EXPECTED_AUTH:
            return jsonify({"error": {"message": "Unauthorized."}}), 401

        if request.headers.get("User-Agent", "") != EXPECTED_UA:
            return jsonify({"error": {"message": "Bad request.", "code": 1}}), 400

        payload = request.get_json(silent=True)
        if not isinstance(payload, (list, dict)):
            raise Exception("Invalid JSON payload.")

        # Suporta array ou dict
        if isinstance(payload, list):
            if len(payload) == 0 or not isinstance(payload[0], dict):
                raise Exception("Invalid JSON payload.")
            content = payload[0]
        else:
            content = payload

        # ── Extrai variáveis ─────────────────────────────────────────────
        customer_id = content.get("customer_id", 0)
        if not customer_id:
            raise Exception("Failed to get customer ID.")

        linha = str(content.get("linha", "acessivel"))
        local = str(content.get("local", "residencia"))
        largura = br_float(content.get("width_m", 0), 0)
        altura = br_float(content.get("height_m", 0), 0)
        area_m2 = br_float(content.get("area_m2", largura * altura), largura * altura)
        diagonal_pol = br_float(content.get("diagonal_in", 0), 0)
        tipo_painel = str(content.get("panel_type", "N/D"))
        modalidade = str(content.get("modality", "compra"))
        diarias = br_int(content.get("diarias", 1), 1)

        preco_m2 = br_float(content.get("preco_m2_tabela", 0), 0)
        subtotal_painel = br_float(content.get("subtotal_painel", 0), 0)
        desconto_percent = br_float(content.get("desconto_percent", 0), 0)
        desconto_valor = br_float(content.get("desconto_aplicado", 0), 0)

        estrutura_ativa = br_bool(content.get("estrutura_ativa", False), False)
        estrutura_valor = br_float(content.get("estrutura_m2", 0), 0)
        preco_estrutura_m2 = br_float(content.get("estrutura_total", 1100), 1100)

        completa_valor = br_float(content.get("total_cheio", 0), 0)
        total_geral = br_float(content.get("total_a_vista", 0), 0)

        saida_minima = br_bool(content.get("saida_minima", False), False)
        modo_completa = br_bool(content.get("completa", False), False)
        usa_lojas = br_bool(content.get("usa_lojas", False), False)

        gabinete_data = content.get("gabinete")

        data_atual = datetime.now().strftime("%d/%m/%Y")
        tipo_operacao = "Compra" if modalidade == "compra" else "Locação"
        tipo_ambiente = "interno" if "indoor" in tipo_painel.lower() else "externo"

        informacoes_importantes = build_informacoes_importantes(modalidade, linha, tipo_painel, tipo_ambiente)

        # ── Gera HTML ────────────────────────────────────────────────────
        if modo_completa:
            html = build_html_completa(
                content, largura, altura, area_m2, diagonal_pol, tipo_painel,
                modalidade, diarias, preco_m2, subtotal_painel, desconto_percent,
                desconto_valor, estrutura_valor, preco_estrutura_m2, completa_valor,
                total_geral, saida_minima, usa_lojas, tipo_operacao,
                informacoes_importantes, data_atual,
            )
        else:
            html = build_html_basica(
                content, largura, altura, area_m2, diagonal_pol, tipo_painel,
                modalidade, diarias, preco_m2, subtotal_painel, desconto_percent,
                desconto_valor, total_geral, tipo_operacao, informacoes_importantes,
                data_atual, local, gabinete_data,
            )

        # ── Gera PDF ─────────────────────────────────────────────────────
        uploads_rel = f"assets/uploads/{customer_id}/pdfs"
        uploads_abs = os.path.join(MW_PUBLIC_ROOT, uploads_rel)

        try:
            os.makedirs(uploads_abs, exist_ok=True)
        except OSError:
            fallback_root = os.path.join(os.getcwd(), "public_html")
            uploads_abs = os.path.join(fallback_root, uploads_rel)
            os.makedirs(uploads_abs, exist_ok=True)

        rand_suffix = random.randint(1000, 9999)
        largura_fn = f"{largura:.2f}".replace(",", ".") + "m"
        altura_fn = f"{altura:.2f}".replace(",", ".") + "m"
        filename = f"proposta-temosled-{largura_fn}_x_{altura_fn}_{rand_suffix}.pdf"

        file_path = os.path.join(uploads_abs, filename)
        generate_pdf_from_html(html, file_path, request.url_root)

        scheme = "https" if is_https_request(request) else "http"
        host = request.host
        public_url = f"{scheme}://{host}/{uploads_rel}/{quote(filename)}"

        if MW_DISABLE_GCS_UPLOAD:
            upload_result = {
                "mediaLink": public_url,
                "contentType": "application/pdf",
            }
        else:
            try:
                upload_result = upload_to_gcs(file_path, customer_id, filename, public_url)
            except Exception:
                if not MW_ALLOW_LOCAL_URL_ON_UPLOAD_ERROR:
                    raise
                upload_result = {
                    "mediaLink": public_url,
                    "contentType": "application/pdf",
                }

        return jsonify(
            {
                "success": True,
                "data": {
                    "url": upload_result["mediaLink"],
                    "type": upload_result["contentType"],
                    "filename": filename,
                    "modo": "completa" if modo_completa else "basica",
                },
            }
        )

    except Exception as exc:
        return jsonify({"error": str(exc)}), 200


@app.route("/assets/uploads/<path:filepath>", methods=["GET"])
def local_uploaded_file(filepath):
    base_dir = MW_PUBLIC_ROOT if os.path.isdir(MW_PUBLIC_ROOT) else os.path.join(os.getcwd(), "public_html")
    assets_root = os.path.join(base_dir, "assets", "uploads")
    if not os.path.isdir(assets_root):
        abort(404)
    return send_from_directory(assets_root, filepath)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
