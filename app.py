from flask import Flask, request, redirect, render_template_string, send_file
import sqlite3
import pandas as pd
import uuid
from datetime import datetime
import io

app = Flask(__name__)

conn = sqlite3.connect("banco.db", check_same_thread=False)
cursor = conn.cursor()

# -------- BANCO --------
cursor.execute("CREATE TABLE IF NOT EXISTS professores (id INTEGER PRIMARY KEY, nome TEXT)")
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
        <a href="/importar/{t[0]}">Importar Alunos</a> | 
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

# -------- IMPORTAR EXCEL --------
@app.route("/importar/<int:turma_id>", methods=["GET", "POST"])
def importar(turma_id):

    if request.method == "POST":
        try:
            file = request.files["file"]

            # Linha 7 vira cabeçalho (index 6)
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

            return f"Importado com sucesso! Total: {total} alunos <br><a href='/'>Voltar</a>"

        except Exception as e:
            return f"Erro ao importar:<br><br>{str(e)}"

    return """
    <h2>Importar Alunos</h2>
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <button>Importar</button>
    </form>
    """

# -------- INICIAR AULA --------
import qrcode
import base64
from io import BytesIO

@app.route("/iniciar/<int:turma_id>")
def iniciar(turma_id):
    aula_id = str(uuid.uuid4())
    data = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("INSERT INTO aulas VALUES (?, ?, ?)", (aula_id, turma_id, data))
    conn.commit()

    link = request.host_url + "aula/" + aula_id

    import qrcode, base64
    from io import BytesIO

    qr = qrcode.make(link)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return f"""
    <h2>Aula iniciada</h2>

    <img src="data:image/png;base64,{img_str}" width="250"><br><br>

    <p><b>Link:</b> <a href="{link}">{link}</a></p>

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

# -------- ALUNO --------
@app.route("/aula/<aula_id>", methods=["GET", "POST"])
def aula(aula_id):

    cursor.execute("SELECT turma_id FROM aulas WHERE id=?", (aula_id,))
    turma_id = cursor.fetchone()[0]

    dispositivo = request.cookies.get("device_id") or str(uuid.uuid4())

    if request.method == "POST":
        codigo = request.form["codigo"]

        # valida turma
        cursor.execute("SELECT 1 FROM alunos WHERE codigo=? AND turma_id=?", (codigo, turma_id))
        if not cursor.fetchone():
            return "Aluno não pertence à turma!"

        # bloqueio dispositivo
        cursor.execute("SELECT codigo FROM dispositivos WHERE dispositivo=?", (dispositivo,))
        r = cursor.fetchone()

        if r and r[0] != codigo:
            return "Dispositivo já vinculado a outro aluno!"

        cursor.execute("INSERT OR IGNORE INTO dispositivos VALUES (?, ?)", (dispositivo, codigo))

        cursor.execute("INSERT INTO presenca VALUES (?, ?, ?)", (codigo, aula_id, dispositivo))
        conn.commit()

        return "Presença confirmada!"

    return """
    <h2>Confirmar Presença</h2>
    <form method="post">
        Matrícula: <input name="codigo">
        <button>Confirmar</button>
    </form>
    """

# -------- EXPORTAR FALTANTES --------
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
app.run(host="0.0.0.0", port=10000)


# -----------CRIAR ROTA DE DADOS -------------#
@app.route("/presencas/<aula_id>")
def presencas(aula_id):

    dados = cursor.execute("""
    SELECT p.codigo, a.nome
    FROM presenca p
    JOIN alunos a ON a.codigo = p.codigo
    WHERE p.aula_id = ?
    """, (aula_id,)).fetchall()

    return {"dados": dados}
