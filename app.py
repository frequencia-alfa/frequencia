from flask import Flask, request, redirect, send_file, make_response, session
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
app.secret_key = "123456"

conn = sqlite3.connect("banco.db", check_same_thread=False)
cursor = conn.cursor()

# -------- TABELAS --------
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

# -------- LOGIN --------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form["nome"]
        prof = cursor.execute("SELECT id FROM professores WHERE nome=?", (nome,)).fetchone()

        if prof:
            session["professor"] = prof[0]
            return redirect("/dashboard")

        return "Professor não encontrado"

    return """
    <h2>Login Professor</h2>
    <form method="post">
        Nome: <input name="nome">
        <button>Entrar</button>
    </form>
    """

# -------- DASHBOARD --------
@app.route("/dashboard")
def dashboard():
    if "professor" not in session:
        return redirect("/login")

    prof_id = session["professor"]

    aulas = cursor.execute("""
    SELECT au.id, t.codigo, d.nome, au.data
    FROM aulas au
    JOIN turmas t ON t.id = au.turma_id
    JOIN disciplinas d ON d.id = au.disciplina_id
    WHERE au.professor_id=?
    ORDER BY au.data DESC
    """, (prof_id,)).fetchall()

    html = "<h2>Dashboard</h2><a href='/'>Home</a><br><br>"

    for a in aulas:
        html += f"""
        Turma: {a[1]} | Disciplina: {a[2]} | Data: {a[3]}<br>
        <a href='/relatorio/{a[0]}'>Relatório</a><br><br>
        """

    return html

# -------- RELATORIO --------
@app.route("/relatorio/<aula_id>")
def relatorio(aula_id):

    presentes = cursor.execute("""
    SELECT a.nome FROM presenca p
    JOIN alunos a ON a.codigo = p.codigo
    WHERE p.aula_id=?
    """, (aula_id,)).fetchall()

    total = cursor.execute("""
    SELECT COUNT(*) FROM alunos a
    JOIN aulas au ON au.turma_id = a.turma_id
    WHERE au.id=?
    """, (aula_id,)).fetchone()[0]

    qtd = len(presentes)
    faltas = total - qtd
    perc = int((qtd / total) * 100) if total else 0

    html = f"""
    <h2>Relatório</h2>
    Total: {total}<br>
    Presentes: {qtd}<br>
    Faltantes: {faltas}<br>
    Presença: {perc}%<br><br>
    """

    return html

# -------- HOME --------
@app.route("/")
def home():
    turmas = cursor.execute("SELECT * FROM turmas").fetchall()

    html = """
    <h2>Controle UNIALFA</h2>
    <a href="/login">Login</a> |
    <a href="/novo_professor">Professor</a> |
    <a href="/nova_disciplina">Disciplina</a> |
    <a href="/nova_turma">Turma</a> |
    <a href="/desvincular">Desvincular</a>
    <br><br>
    """

    for t in turmas:
        html += f"""
        <b>{t[1]}</b><br>
        <a href="/importar/{t[0]}">Importar</a> |
        <a href="/iniciar/{t[0]}">Iniciar Aula</a><br><br>
        """

    return html

# -------- DESVINCULAR --------
@app.route("/desvincular", methods=["GET", "POST"])
def desvincular():
    if request.method == "POST":
        cursor.execute("DELETE FROM dispositivos WHERE codigo=?", (request.form["codigo"],))
        conn.commit()
        return "Removido!"

    return """
    <h2>Desvincular</h2>
    <form method="post">
        Matrícula: <input name="codigo">
        <button>Remover</button>
    </form>
    """

# -------- IMPORTAR --------
@app.route("/importar/<int:turma_id>", methods=["GET", "POST"])
def importar(turma_id):
    if request.method == "POST":
        df = pd.read_excel(request.files["file"], header=6)
        for _, row in df.iterrows():
            cursor.execute("INSERT INTO alunos VALUES (?, ?, ?)",
                           (row["Código"], row["Nome do Aluno"], turma_id))
        conn.commit()
        return "Importado!"
    return '<form method="post" enctype="multipart/form-data"><input type="file" name="file"><button>Importar</button></form>'

# -------- INICIAR --------
@app.route("/iniciar/<int:turma_id>", methods=["GET", "POST"])
def iniciar(turma_id):
    if request.method == "POST":
        aula_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO aulas VALUES (?, ?, ?, ?, ?)",
                       (aula_id, turma_id, request.form["disciplina"],
                        request.form["professor"], datetime.now().strftime("%Y-%m-%d")))
        conn.commit()

        link = request.host_url + "aula/" + aula_id
        qr = qrcode.make(link)
        buffer = BytesIO()
        qr.save(buffer)
        img = base64.b64encode(buffer.getvalue()).decode()

        return f"""
        <h2>Aula iniciada</h2>
        <img src="data:image/png;base64,{img}" width="250"><br>
        <a href="/faltantes/{aula_id}">Exportar Faltantes</a>
        """

    d = cursor.execute("SELECT id,nome FROM disciplinas").fetchall()
    p = cursor.execute("SELECT id,nome FROM professores").fetchall()

    form = "<form method='post'>Disciplina:<select name='disciplina'>"
    for x in d: form += f"<option value='{x[0]}'>{x[1]}</option>"
    form += "</select><br>Professor:<select name='professor'>"
    for x in p: form += f"<option value='{x[0]}'>{x[1]}</option>"
    form += "</select><button>Iniciar</button></form>"

    return form

# -------- EXPORTAR --------
@app.route("/faltantes/<aula_id>")
def faltantes(aula_id):
    df = pd.read_sql("""
    SELECT pr.nome,d.codigo,d.nome,a.codigo,a.nome
    FROM alunos a
    JOIN aulas au ON au.turma_id=a.turma_id
    JOIN disciplinas d ON d.id=au.disciplina_id
    JOIN professores pr ON pr.id=au.professor_id
    WHERE au.id=? AND a.codigo NOT IN
    (SELECT codigo FROM presenca WHERE aula_id=?)
    ORDER BY a.nome
    """, conn, params=(aula_id,aula_id))

    df["Status"] = "FALTA"
    out = io.BytesIO()
    df.to_excel(out,index=False)
    out.seek(0)
    return send_file(out,download_name="faltantes.xlsx",as_attachment=True)

# -------- PRESENÇA --------
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

        cursor.execute("INSERT OR IGNORE INTO dispositivos VALUES (?, ?)", (dispositivo, codigo))
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
    SELECT codigo,nome FROM alunos WHERE turma_id=? AND nome LIKE ?
    """,(turma_id,f"%{termo}%")).fetchall()
    return {"dados":dados}

# -------- RODAR --------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
