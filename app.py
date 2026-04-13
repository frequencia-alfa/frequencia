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

cursor.execute("CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY, codigo TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS disciplinas (id INTEGER PRIMARY KEY, codigo TEXT, nome TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS alunos (codigo TEXT, nome TEXT, turma_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS aulas (id TEXT, turma_id INTEGER, data TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS presenca (codigo TEXT, aula_id TEXT, dispositivo TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS dispositivos (dispositivo TEXT PRIMARY KEY, codigo TEXT)")
conn.commit()

# -------- HOME --------
@app.route("/")
def home():
    turmas = cursor.execute("SELECT * FROM turmas").fetchall()

    html = "<h2>Turmas</h2>"
    html += '<a href="/nova_turma">Nova Turma</a> | '
    html += '<a href="/nova_disciplina">Nova Disciplina</a><br><br>'

    for t in turmas:
        html += f"""
        <b>{t[1]}</b><br>
        <a href="/importar/{t[0]}">Importar</a> | 
        <a href="/iniciar/{t[0]}">Iniciar Aula</a><br><br>
        """

    return html

# -------- DISCIPLINA --------
@app.route("/nova_disciplina", methods=["GET", "POST"])
def nova_disciplina():
    if request.method == "POST":
        codigo = request.form["codigo"]
        nome = request.form["nome"]

        cursor.execute(
            "INSERT INTO disciplinas (codigo, nome) VALUES (?, ?)",
            (codigo, nome)
        )
        conn.commit()

        return redirect("/")

    return """
    <h2>Nova Disciplina</h2>
    <form method="post">
        Código: <input name="codigo"><br><br>
        Nome: <input name="nome"><br><br>
        <button>Cadastrar</button>
    </form>
    """

# -------- NOVA TURMA --------
@app.route("/nova_turma", methods=["GET", "POST"])
def nova_turma():
    if request.method == "POST":
        codigo = request.form["codigo"]
        cursor.execute("INSERT INTO turmas (codigo) VALUES (?)", (codigo,))
        conn.commit()
        return redirect("/")

    return """
    <h2>Nova Turma</h2>
    <form method="post">
        Código: <input name="codigo">
        <button>Criar</button>
    </form>
    """

# -------- IMPORTAR --------
@app.route("/importar/<int:turma_id>", methods=["GET", "POST"])
def importar(turma_id):

    if request.method == "POST":
        file = request.files["file"]
        df = pd.read_excel(file, header=6)

        for _, row in df.iterrows():
            nome = str(row["Nome do Aluno"]).strip()
            codigo = str(row["Código"]).strip()

            if nome == "nan" or codigo == "nan":
                continue

            cursor.execute(
                "INSERT INTO alunos VALUES (?, ?, ?)",
                (codigo, nome, turma_id)
            )

        conn.commit()
        return "Importado com sucesso! <br><a href='/'>Voltar</a>"

    return """
    <h2>Importar Alunos</h2>
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <button>Importar</button>
    </form>
    """

# -------- INICIAR AULA --------
@app.route("/iniciar/<int:turma_id>")
def iniciar(turma_id):

    aula_id = str(uuid.uuid4())
    data = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("INSERT INTO aulas VALUES (?, ?, ?)", (aula_id, turma_id, data))
    conn.commit()

    link = request.host_url + "aula/" + aula_id

    qr = qrcode.make(link)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return f"""
    <h2>Aula iniciada</h2>

    <img src="data:image/png;base64,{img_str}" width="250"><br><br>

    <p><a href="{link}">{link}</a></p>

    <p><a href="/faltantes/{aula_id}">📥 Exportar Faltantes</a></p>

    <h3>Presentes:</h3>
    <ul id="lista"></ul>

    <script>
    async function atualizar() {{
        let res = await fetch('/presencas/{aula_id}');
        let data = await res.json();

        let lista = document.getElementById("lista");
        lista.innerHTML = "";

        data.dados.forEach(item => {{
            let li = document.createElement("li");
            li.innerText = item[0] + " - " + item[1];
            lista.appendChild(li);
        }});
    }}

    setInterval(atualizar, 3000);
    atualizar();
    </script>
    """

# -------- BUSCAR --------
@app.route("/buscar_aluno/<int:turma_id>")
def buscar_aluno(turma_id):
    termo = request.args.get("q", "").upper()

    dados = cursor.execute("""
    SELECT codigo, nome FROM alunos
    WHERE turma_id = ?
    AND nome LIKE ?
    LIMIT 10
    """, (turma_id, f"%{termo}%")).fetchall()

    return {"dados": dados}

# -------- PRESENÇAS --------
@app.route("/presencas/<aula_id>")
def presencas(aula_id):
    dados = cursor.execute("""
    SELECT p.codigo, a.nome
    FROM presenca p
    JOIN alunos a ON a.codigo = p.codigo
    WHERE p.aula_id = ?
    """, (aula_id,)).fetchall()

    return {"dados": dados}

# -------- AULA --------
@app.route("/aula/<aula_id>", methods=["GET", "POST"])
def aula(aula_id):

    cursor.execute("SELECT turma_id FROM aulas WHERE id=?", (aula_id,))
    turma_id = cursor.fetchone()[0]

    codigo_salvo = request.cookies.get("codigo_aluno")

    if codigo_salvo:
        cursor.execute("INSERT INTO presenca VALUES (?, ?, ?)", (codigo_salvo, aula_id, "auto"))
        conn.commit()
        return "<h2 style='text-align:center;color:#b30000;'>Presença automática ✅</h2>"

    if request.method == "POST":
        codigo = request.form["codigo"]
        cursor.execute("INSERT INTO presenca VALUES (?, ?, ?)", (codigo, aula_id, "manual"))
        conn.commit()

        resp = make_response("<h2 style='text-align:center;color:#b30000;'>Presença confirmada ✅</h2>")
        resp.set_cookie("codigo_aluno", codigo)
        return resp

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{
    font-family: Arial;
    background: #b30000;
    text-align: center;
    padding: 20px;
}}

.card {{
    background: white;
    padding: 25px;
    border-radius: 15px;
}}

h2 {{
    color: #b30000;
}}

button {{
    background: #b30000;
    color: white;
    padding: 15px;
    width: 90%;
    font-size: 18px;
    border: none;
    border-radius: 10px;
}}

input {{
    width: 90%;
    padding: 15px;
    margin: 10px;
}}

li {{
    background: #eee;
    padding: 10px;
    margin: 5px;
}}
</style>
</head>

<body>

<div class="card">

<h2>📚 Presença UNIALFA</h2>

<input id="busca" placeholder="Digite seu nome..." onkeyup="buscar()">

<ul id="lista"></ul>

<form method="post">
    <input name="codigo" id="codigo" placeholder="Matrícula">
    <button>Confirmar</button>
</form>

</div>

<script>
async function buscar() {{
    let termo = document.getElementById("busca").value;

    if (termo.length < 2) return;

    let res = await fetch('/buscar_aluno/{turma_id}?q=' + termo);
    let data = await res.json();

    let lista = document.getElementById("lista");
    lista.innerHTML = "";

    data.dados.forEach(item => {{
        let li = document.createElement("li");
        li.innerText = item[1];

        li.onclick = function() {{
            document.getElementById("codigo").value = item[0];
            lista.innerHTML = "";
        }}

        lista.appendChild(li);
    }});
}}
</script>

</body>
</html>
"""

# -------- RODAR --------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
