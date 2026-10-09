from flask import Flask, render_template, request, redirect
import sqlite3
import random
import string
import os
from datetime import datetime, timedelta
from user_agents import parse

app = Flask(
    __name__,
    template_folder=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "templates"
    )
)

print("ARQUIVO EXECUTADO:", __file__)
print("É ARQUIVO?", os.path.isfile(__file__))
print("É PASTA?", os.path.isdir(__file__))
print("DIRETÓRIO:", os.path.dirname(os.path.abspath(__file__)))
# -------------------------
# BANCO DE DADOS
# -------------------------

def conectar_banco():
    return sqlite3.connect("links.db")



def criar_banco():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    # Tabela principal dos links
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_url TEXT NOT NULL,
            short_code TEXT NOT NULL UNIQUE
        )
    """)

    # Adiciona clicks se ainda não existir
    try:
        cursor.execute(
            "ALTER TABLE links ADD COLUMN clicks INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    # Tabela de histórico dos cliques
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS click_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL,
            clicked_at TEXT NOT NULL,
            user_agent TEXT,
            FOREIGN KEY (link_id) REFERENCES links(id)
        )
    """)

    # Adiciona navegador
    try:
        cursor.execute(
            "ALTER TABLE click_events ADD COLUMN browser TEXT"
        )
    except sqlite3.OperationalError:
        pass

    # Adiciona sistema operacional
    try:
        cursor.execute(
            "ALTER TABLE click_events ADD COLUMN os TEXT"
        )
    except sqlite3.OperationalError:
        pass

    # Adiciona dispositivo
    try:
        cursor.execute(
            "ALTER TABLE click_events ADD COLUMN device TEXT"
        )
    except sqlite3.OperationalError:
        pass

    conexao.commit()
    conexao.close()
# -------------------------
# GERAR CÓDIGO
# -------------------------

def gerar_codigo():
    caracteres = string.ascii_letters + string.digits

    codigo = ''.join(
        random.choice(caracteres)
        for _ in range(6)
    )

    return codigo


# -------------------------
# PÁGINA INICIAL
# -------------------------

@app.route("/", methods=["GET", "POST"])
def home():

    short_url = None
    clicks = 0
    codigo = None
    erro = None

    if request.method == "POST":

        original_url = request.form["url"]

        custom_code = request.form.get("custom_code", "").strip()

        if custom_code:
            codigo = custom_code
        else:
            codigo = gerar_codigo()

        conexao = conectar_banco()
        cursor = conexao.cursor()

        # Verifica se o código já existe
        cursor.execute(
            "SELECT id FROM links WHERE short_code = ?",
            (codigo,)
        )

        existente = cursor.fetchone()

        if existente:

            conexao.close()

            erro = "Esse apelido já está sendo usado."

            return render_template(
                "index.html",
                short_url=None,
                clicks=0,
                codigo=None,
                erro=erro
            )

        # Cria o link
        cursor.execute(
            """
            INSERT INTO links (original_url, short_code)
            VALUES (?, ?)
            """,
            (original_url, codigo)
        )

        conexao.commit()
        conexao.close()

        short_url = f"http://127.0.0.1:8080/{codigo}"

    return render_template(
        "index.html",
        short_url=short_url,
        clicks=clicks,
        codigo=codigo,
        erro=erro
    )

# -------------------------
# REDIRECIONAMENTO
# -------------------------

@app.route("/<codigo>")
def redirecionar(codigo):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT id, original_url
        FROM links
        WHERE short_code = ?
        """,
        (codigo,)
    )

    resultado = cursor.fetchone()

    if resultado:

        link_id = resultado[0]
        original_url = resultado[1]

        # Identifica o visitante
        user_agent_string = request.headers.get("User-Agent", "")
        user_agent = parse(user_agent_string)

        navegador = user_agent.browser.family
        sistema = user_agent.os.family
        dispositivo = user_agent.device.family

        # Aumenta o contador
        cursor.execute(
            """
            UPDATE links
            SET clicks = clicks + 1
            WHERE id = ?
            """,
            (link_id,)
        )

        # Registra o clique
        cursor.execute(
    """
    INSERT INTO click_events
    (
        link_id,
        clicked_at,
        user_agent,
        browser,
        os,
        device
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    (
        link_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_agent_string,
        navegador,
        sistema,
        dispositivo
    )
)

        conexao.commit()
        conexao.close()

        return redirect(original_url)

    conexao.close()

    return "Link não encontrado", 404

@app.route("/stats/<codigo>")
def estatisticas(codigo):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT short_code, original_url, clicks
        FROM links
        WHERE short_code = ?
        """,
        (codigo,)
    )

    link = cursor.fetchone()

    conexao.close()

    if not link:
        return "Link não encontrado", 404

    return render_template(
        "stats.html",
        link=link
    )

@app.route("/dashboard")
def dashboard():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    # Total de links
    cursor.execute("SELECT COUNT(*) FROM links")
    total_links = cursor.fetchone()[0]

    # Total de cliques
    cursor.execute("SELECT SUM(clicks) FROM links")
    total_clicks = cursor.fetchone()[0] or 0

    # Cliques hoje
    cursor.execute("""
        SELECT COUNT(*)
        FROM click_events
        WHERE DATE(clicked_at) = DATE('now', 'localtime')
    """)
    clicks_today = cursor.fetchone()[0]

    # Links
    cursor.execute("""
        SELECT short_code, original_url, clicks
        FROM links
        ORDER BY clicks DESC
    """)
    links = cursor.fetchall()

    # Histórico dos últimos cliques
    cursor.execute("""
    SELECT
        click_events.clicked_at,
        links.short_code,
        links.original_url,
        click_events.browser,
        click_events.os,
        click_events.device
    FROM click_events
    JOIN links
    ON click_events.link_id = links.id
    ORDER BY click_events.id DESC
    LIMIT 20
""")

    historico = cursor.fetchall()
    # Cliques dos últimos 7 dias
    cursor.execute("""
        SELECT DATE(clicked_at) AS dia, COUNT(*) AS total
        FROM click_events
        WHERE DATE(clicked_at) >= DATE('now', 'localtime', '-6 days')
        GROUP BY DATE(clicked_at)
        ORDER BY dia
    """)

    dados_grafico = cursor.fetchall()

    # Cria os 7 dias, mesmo quando não houve cliques
    hoje = datetime.now().date()

    dias = []
    cliques = []

    for i in range(6, -1, -1):

        dia = hoje - timedelta(days=i)
        dia_texto = dia.strftime("%Y-%m-%d")

        dias.append(dia.strftime("%d/%m"))

        total = 0

        for registro in dados_grafico:
            if registro[0] == dia_texto:
                total = registro[1]

        cliques.append(total)
            # Estatísticas de navegadores
    cursor.execute("""
        SELECT browser, COUNT(*)
        FROM click_events
        WHERE browser IS NOT NULL
        GROUP BY browser
        ORDER BY COUNT(*) DESC
    """)
    navegadores = cursor.fetchall()

    # Estatísticas de sistemas
    cursor.execute("""
        SELECT os, COUNT(*)
        FROM click_events
        WHERE os IS NOT NULL
        GROUP BY os
        ORDER BY COUNT(*) DESC
    """)
    sistemas = cursor.fetchall()

    # Estatísticas de dispositivos
    cursor.execute("""
        SELECT device, COUNT(*)
        FROM click_events
        WHERE device IS NOT NULL
        GROUP BY device
        ORDER BY COUNT(*) DESC
    """)
    dispositivos = cursor.fetchall()
    conexao.close()

    return render_template(
    "dashboard.html",
    total_links=total_links,
    total_clicks=total_clicks,
    clicks_today=clicks_today,
    links=links,
    historico=historico,
    dias=dias,
    cliques=cliques,
    navegadores=navegadores,
    sistemas=sistemas,
    dispositivos=dispositivos
)
    

# -------------------------
# INICIAR
# -------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        debug=False
    )
    
    