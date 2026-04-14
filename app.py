from flask import Flask, request, redirect, send_file, make_response
import sqlite3
import pandas as pd
import uuid
from datetime import datetime
import io
import qrcode
import base64
from io import BytesIO
import os

app = Flask(__name__)

# -------- BANCO --------
conn = sqlite3.connect("banco.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS professores (id INTEGER PRIMARY KEY, nome TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS disciplinas (id INTEGER PRIMARY KEY, codigo TEXT, nome TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY, codigo TEXT)")
cursor.execute("""
CREATE TABLE IF NOT EXISTS aulas (
    id TEXT,
    turma_id INTEGER,
    disciplina_id INTEGER,
    professor_id INTEGER,
    data TEXT
)
""")
cursor.execute("CREATE TABLE IF NOT EXISTS alunos (codigo TEXT, nome TEXT, turma_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS presenca (codigo TEXT, aula_id TEXT, dispositivo TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS dispositivos (dispositivo TEXT PRIMARY KEY, codigo TEXT)")
conn.commit()

# -------- HOME --------
@app.route("/")
def home():
    turmas = cursor.execute("SELECT * FROM turmas").fetchall()

    html = "<h2>Controle de Frequência</h2>"
    html += """
    <a href="/novo_professor">Professor</a> |
    <a href="/nova_disciplina">Disciplina</a> |
    <a href="/nova_turma">Turma</a><br><br>
    """

    for t in turmas:
        html += f"""
        <b>{t[1]}</b><br>
        <a href="/importar/{t[0]}">Importar</a> |
        <a href="/iniciar/{t[0]}">Iniciar Aula</a> |
        <a href="/desvincular">🔓 Desvincular aluno</a>
        <br><br>
        """

    return html

# -------- PROFESSOR --------
@app.route("/novo_professor", methods=["GET", "POST"])
def novo_professor():
    if request.method == "POST":
        cursor.execute("INSERT INTO professores (nome) VALUES (?)", (request.form["nome"],))
        conn.commit()
        return redirect("/")
    return """
    <h2>Novo Professor</h2>
    <form method="post">
        Nome: <input name="nome">
        <button>Cadastrar</button>
    </form>
    """

# -------- DISCIPLINA --------
@app.route("/nova_disciplina", methods=["GET", "POST"])
def nova_disciplina():
    if request.method == "POST":
        cursor.execute("INSERT INTO disciplinas VALUES (NULL, ?, ?)",
                       (request.form["codigo"], request.form["nome"]))
        conn.commit()
        return redirect("/")
    return """
    <h2>Nova Disciplina</h2>
    <form method="post">
        Código: <input name="codigo"><br>
        Nome: <input name="nome"><br>
        <button>Cadastrar</button>
    </form>
    """

# -------- TURMA --------
@app.route("/nova_turma", methods=["GET", "POST"])
def nova_turma():
    if request.method == "POST":
        cursor.execute("INSERT INTO turmas VALUES (NULL, ?)", (request.form["codigo"],))
        conn.commit()
        return redirect("/")
    return """
    <h2>Nova Turma</h2>
    <form method="post">
        Código: <input name="codigo">
        <button>Cadastrar</button>
    </form>
    """

# -------- DESVINCULAR --------
@app.route("/desvincular", methods=["GET", "POST"])
def desvincular():
    if request.method == "POST":
        codigo = request.form["codigo"]
        cursor.execute("DELETE FROM dispositivos WHERE codigo=?", (codigo,))
        conn.commit()
        return "Vínculo removido!"

    return """
    <h2>Desvincular Dispositivo</h2>
    <form method="post">
        Matrícula: <input name="codigo">
        <button>Remover vínculo</button>
    </form>
    """

# -------- IMPORTAR --------
@app.route("/importar/<int:turma_id>", methods=["GET", "POST"])
def importar(turma_id):
    if request.method == "POST":
        df = pd.read_excel(request.files["file"], header=6)

        for _, row in df.iterrows():
            nome = str(row["Nome do Aluno"]).strip()
            codigo = str(row["Código"]).strip()

            if nome != "nan":
                cursor.execute("INSERT INTO alunos VALUES (?, ?, ?)", (codigo, nome, turma_id))

        conn.commit()
        return "Importado!"

    return """
    <h2>Importar</h2>
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <button>Importar</button>
    </form>
    """

# -------- INICIAR AULA --------
@app.route("/iniciar/<int:turma_id>", methods=["GET", "POST"])
def iniciar(turma_id):

    if request.method == "POST":
        aula_id = str(uuid.uuid4())

        cursor.execute("""
        INSERT INTO aulas VALUES (?, ?, ?, ?, ?)
        """, (aula_id, turma_id, request.form["disciplina"],
              request.form["professor"], datetime.now().strftime("%Y-%m-%d")))
        conn.commit()

        link = request.host_url + "aula/" + aula_id

        qr = qrcode.make(link)
        buffer = BytesIO()
        qr.save(buffer)
        img = base64.b64encode(buffer.getvalue()).decode()

        return f"""
        <h2>Aula iniciada</h2>
        <img src="data:image/png;base64,{img}" width="250"><br><br>

        <a href="/faltantes/{aula_id}">📥 Exportar Faltantes</a>

        <h3>Presentes:</h3>
        <ul id="lista"></ul>

        <script>
        async function atualizar() {{
            let r = await fetch('/presencas/{aula_id}');
            let d = await r.json();
            let lista = document.getElementById("lista");
            lista.innerHTML = "";
            d.dados.forEach(x => {{
                let li = document.createElement("li");
                li.innerText = x[1];
                lista.appendChild(li);
            }});
        }}
        setInterval(atualizar, 3000);
        </script>
        """

    disciplinas = cursor.execute("SELECT id, nome FROM disciplinas").fetchall()
    professores = cursor.execute("SELECT id, nome FROM professores").fetchall()

    form = "<h2>Iniciar Aula</h2><form method='post'>"

    form += "Disciplina: <select name='disciplina'>"
    for d in disciplinas:
        form += f"<option value='{d[0]}'>{d[1]}</option>"
    form += "</select><br><br>"

    form += "Professor: <select name='professor'>"
    for p in professores:
        form += f"<option value='{p[0]}'>{p[1]}</option>"
    form += "</select><br><br>"

    form += "<button>Iniciar</button></form>"
    return form

# -------- PRESENÇA --------
@app.route("/presencas/<aula_id>")
def presencas(aula_id):
    dados = cursor.execute("""
    SELECT p.codigo, a.nome
    FROM presenca p
    JOIN alunos a ON a.codigo = p.codigo
    WHERE aula_id = ?
    """, (aula_id,)).fetchall()

    return {"dados": dados}

# -------- EXPORTAR --------
@app.route("/faltantes/<aula_id>")
def faltantes(aula_id):
    query = """
    SELECT pr.nome, d.codigo, d.nome, a.codigo, a.nome
    FROM alunos a
    JOIN aulas au ON au.turma_id = a.turma_id
    JOIN disciplinas d ON d.id = au.disciplina_id
    JOIN professores pr ON pr.id = au.professor_id
    WHERE au.id = ?
    AND a.codigo NOT IN (SELECT codigo FROM presenca WHERE aula_id = ?)
    ORDER BY a.nome
    """
    df = pd.read_sql(query, conn, params=(aula_id, aula_id))
    df["Status"] = "FALTA"

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name="faltantes.xlsx", as_attachment=True)

# -------- AULA ALUNO --------
@app.route("/aula/<aula_id>", methods=["GET", "POST"])
def aula(aula_id):

    cursor.execute("SELECT turma_id FROM aulas WHERE id=?", (aula_id,))
    turma_id = cursor.fetchone()[0]

    dispositivo = request.cookies.get("device") or str(uuid.uuid4())
    codigo_salvo = request.cookies.get("codigo")

    if codigo_salvo:
        cursor.execute("INSERT INTO presenca VALUES (?, ?, ?)", (codigo_salvo, aula_id, dispositivo))
        conn.commit()
        return "<h2 style='color:#b30000'>Presença automática</h2>"

    if request.method == "POST":
        codigo = request.form["codigo"]

        cursor.execute("INSERT INTO dispositivos VALUES (?, ?)", (dispositivo, codigo))
        cursor.execute("INSERT INTO presenca VALUES (?, ?, ?)", (codigo, aula_id, dispositivo))
        conn.commit()

        resp = make_response("<h2 style='color:#b30000'>Confirmado</h2>")
        resp.set_cookie("codigo", codigo)
        resp.set_cookie("device", dispositivo)
        return resp

    return f"""
    <body style="background:#b30000;color:white;text-align:center">
    <h2>Presença UNIALFA</h2>
    <input id="busca" onkeyup="buscar()" placeholder="Digite seu nome">
    <ul id="lista"></ul>
    <form method="post">
        <input id="codigo" name="codigo">
        <button>Confirmar</button>
    </form>

    <script>
    async function buscar() {{
        let t = document.getElementById("busca").value;
        let r = await fetch('/buscar_aluno/{turma_id}?q=' + t);
        let d = await r.json();

        let l = document.getElementById("lista");
        l.innerHTML="";
        d.dados.forEach(x=>{{
            let li=document.createElement("li");
            li.innerText=x[1];
            li.onclick=()=>document.getElementById("codigo").value=x[0];
            l.appendChild(li);
        }});
    }}
    </script>
    </body>
    """

# -------- BUSCA --------
@app.route("/buscar_aluno/<int:turma_id>")
def buscar_aluno(turma_id):
    termo = request.args.get("q", "")
    dados = cursor.execute("""
    SELECT codigo, nome FROM alunos
    WHERE turma_id=? AND nome LIKE ?
    """, (turma_id, f"%{termo}%")).fetchall()

    return {"dados": dados}

# -------- RODAR --------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
