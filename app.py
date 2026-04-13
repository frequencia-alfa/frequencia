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
    html += '<a href="/nova_turma">Nova Turma</a><br><br>'

    for t in turmas:
        html += f"""
        {t[1]} 
        <a href="/importar/{t[0]}">Importar</a> | 
        <a href="/iniciar/{t[0]}">Iniciar Aula</a><br>
        """

    return html

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
        try:
            file = request.files["file"]
            df = pd.read_excel(file, header=6)

            total = 0

            for _, row in df.iterrows():
                nome = str(row["Nome do Aluno"]).strip()
                codigo = str(row["Código"]).strip()

                if nome == "nan" or codigo == "nan":
                    continue

                cursor.execute(
                    "INSERT INTO alunos (codigo, nome, turma_id) VALUES (?, ?, ?)",
                    (codigo, nome, turma_id)
                )
                total += 1

            conn.commit()
            return f"Importado com sucesso! {total} alunos <br><a href='/'>Voltar</a>"

        except Exception as e:
            return f"Erro: {str(e)}"

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

# -------- BUSCAR ALUNO --------
@app.route("/buscar_aluno/<int:turma_id>")
def buscar_aluno(turma_id):

    termo = request.args.get("q", "").upper()

    dados = cursor.execute("""
    SELECT codigo, nome
    FROM alunos
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

# -------- AULA (ALUNO) --------
@app.route("/aula/<aula_id>", methods=["GET", "POST"])
def aula(aula_id):

    cursor.execute("SELECT turma_id FROM aulas WHERE id=?", (aula_id,))
    turma_id = cursor.fetchone()[0]

    dispositivo = request.cookies.get("device_id") or str(uuid.uuid4())
    codigo_salvo = request.cookies.get("codigo_aluno")

    # AUTO LOGIN
    if codigo_salvo:
        cursor.execute("SELECT 1 FROM alunos WHERE codigo=? AND turma_id=?", (codigo_salvo, turma_id))
        if cursor.fetchone():
            cursor.execute("SELECT 1 FROM presenca WHERE codigo=? AND aula_id=?", (codigo_salvo, aula_id))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO presenca VALUES (?, ?, ?)", (codigo_salvo, aula_id, dispositivo))
                conn.commit()

            return f"<h2>Presença automática ✅</h2><p>{codigo_salvo}</p>"

    # PRIMEIRO ACESSO
    if request.method == "POST":
        codigo = request.form["codigo"]

        cursor.execute("INSERT INTO presenca VALUES (?, ?, ?)", (codigo, aula_id, dispositivo))
        conn.commit()

        resp = make_response(f"<h2>Presença confirmada ✅</h2><p>{codigo}</p>")
        resp.set_cookie("codigo_aluno", codigo, max_age=60*60*24*365)

        return resp

    return f"""
    <h2>Confirmar Presença</h2>

    <input type="text" id="busca" placeholder="Digite seu nome..." onkeyup="buscar()"><br><br>

    <ul id="lista"></ul>

    <form method="post">
        Matrícula: <input name="codigo" id="codigo"><br><br>
        <button>Confirmar</button>
    </form>

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
    """

# -------- FALTANTES --------
@app.route("/faltantes/<aula_id>")
def faltantes(aula_id):

    query = """
    SELECT a.codigo, a.nome
    FROM alunos a
    JOIN aulas au ON au.turma_id = a.turma_id
    WHERE au.id = ?
    AND a.codigo NOT IN (
        SELECT codigo FROM presenca WHERE aula_id = ?
    )
    ORDER BY a.nome
    """

    df = pd.read_sql(query, conn, params=(aula_id, aula_id))
    df["Status"] = "FALTA"

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name="faltantes.xlsx", as_attachment=True)

# -------- RODAR --------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
