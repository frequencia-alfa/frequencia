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

# -------- BANCO --------
conn = sqlite3.connect("banco.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS professores (id INTEGER PRIMARY KEY, nome TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS disciplinas (id INTEGER PRIMARY KEY, codigo TEXT, nome TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY, codigo TEXT, professor_id INTEGER)")
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

# -------- LOGO --------
@app.route("/logo")
def logo():
    return send_file("logo.png", mimetype="image/png")

def topo():
    return """
    <div style="text-align:center;">
        <img src="/logo" width="200"><br>
    </div>
    """

# -------- LOGIN --------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form["nome"]

        prof = cursor.execute("SELECT id FROM professores WHERE nome=?", (nome,)).fetchone()

        if not prof:
            cursor.execute("INSERT INTO professores (nome) VALUES (?)", (nome,))
            conn.commit()
            prof = cursor.execute("SELECT id FROM professores WHERE nome=?", (nome,)).fetchone()

        session["professor"] = prof[0]
        return redirect("/")

    return topo() + """
    <h2 style="text-align:center;">Login Professor</h2>
    <div style="text-align:center;">
    <form method="post">
        Nome: <input name="nome">
        <button>Entrar</button>
    </form>
    </div>
    """

# -------- HOME --------
@app.route("/")
def home():
    prof = session.get("professor")

    if not prof:
        return topo() + """
        <h2 style="text-align:center;">Controle UNIALFA</h2>
        <div style="text-align:center;">
            <a href="/login">🔐 Login</a>
        </div>
        """

    turmas = cursor.execute("SELECT * FROM turmas WHERE professor_id=?", (prof,)).fetchall()

    html = topo() + """
    <h2 style="text-align:center;">Controle UNIALFA</h2>

    <div style="text-align:center;">
        <a href="/nova_turma">Turma</a> |
        <a href="/nova_disciplina">Disciplina</a> |
        <a href="/desvincular">Desvincular</a>
    </div><br>
    """

    for t in turmas:
        html += f"""
        <div style="text-align:center;">
        <b>{t[1]}</b><br>
        <a href="/importar/{t[0]}">Importar</a> |
        <a href="/iniciar/{t[0]}">Iniciar Aula</a>
        <br><br>
        </div>
        """

    return html

# -------- DISCIPLINA --------
@app.route("/nova_disciplina", methods=["GET","POST"])
def nova_disciplina():
    if request.method=="POST":
        cursor.execute("INSERT INTO disciplinas VALUES (NULL,?,?)",
                       (request.form["codigo"],request.form["nome"]))
        conn.commit()
        return redirect("/")
    return topo() + '''
    <h2>Nova Disciplina</h2>
    <form method="post">
    Código:<input name="codigo"><br>
    Nome:<input name="nome"><br>
    <button>Cadastrar</button>
    </form>
    '''

# -------- TURMA --------
@app.route("/nova_turma", methods=["GET","POST"])
def nova_turma():
    if request.method=="POST":
        cursor.execute("INSERT INTO turmas (codigo, professor_id) VALUES (?,?)",
                       (request.form["codigo"], session.get("professor")))
        conn.commit()
        return redirect("/")
    return topo() + '''
    <h2>Nova Turma</h2>
    <form method="post">
    Código:<input name="codigo">
    <button>Cadastrar</button>
    </form>
    '''

# -------- DESVINCULAR --------
@app.route("/desvincular", methods=["GET","POST"])
def desvincular():
    if request.method=="POST":
        cursor.execute("DELETE FROM dispositivos WHERE codigo=?", (request.form["codigo"],))
        conn.commit()
        return topo() + "Vínculo removido!<br><a href='/'>Voltar</a>"
    return topo() + '''
    <h2>Desvincular</h2>
    <form method="post">
    Matrícula:<input name="codigo">
    <button>Remover</button>
    </form>
    '''

# -------- IMPORTAR --------
@app.route("/importar/<int:turma_id>", methods=["GET","POST"])
def importar(turma_id):
    if request.method=="POST":
        df = pd.read_excel(request.files["file"], header=6)

        for _, row in df.iterrows():
            nome = str(row["Nome do Aluno"]).strip()
            codigo = str(row["Código"]).strip()

            if nome != "nan":
                cursor.execute("INSERT INTO alunos VALUES (?,?,?)",(codigo,nome,turma_id))

        conn.commit()
        return topo() + "Importado com sucesso!<br><a href='/'>Voltar</a>"

    return topo() + '''
    <h2>Importar Alunos</h2>
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <button>Importar</button>
    </form>
    '''

# -------- INICIAR AULA --------
@app.route("/iniciar/<int:turma_id>", methods=["GET","POST"])
def iniciar(turma_id):

    if request.method=="POST":
        aula_id=str(uuid.uuid4())

        cursor.execute("INSERT INTO aulas VALUES (?,?,?,?,?)",
                       (aula_id,turma_id,request.form["disciplina"],
                        session.get("professor"),
                        datetime.now().strftime("%Y-%m-%d")))
        conn.commit()

        link=request.host_url+"aula/"+aula_id

        qr=qrcode.make(link)
        buf=BytesIO()
        qr.save(buf)
        img=base64.b64encode(buf.getvalue()).decode()

        disc = cursor.execute("SELECT nome FROM disciplinas WHERE id=?",
                              (request.form["disciplina"],)).fetchone()[0]

        prof = cursor.execute("SELECT nome FROM professores WHERE id=?",
                              (session.get("professor"),)).fetchone()[0]

        return topo() + f"""
        <h2>Aula em andamento</h2>
        <b>Professor:</b> {prof}<br>
        <b>Disciplina:</b> {disc}<br><br>

        <img src='data:image/png;base64,{img}' width="250"><br><br>

        <a href="/faltantes/{aula_id}">📥 Exportar Faltantes</a><br><br>

        <h3>Presentes:</h3>
        <ul id="lista"></ul>

        <script>
        async function atualizar(){{
            let r=await fetch('/presencas/{aula_id}');
            let d=await r.json();
            let l=document.getElementById("lista");
            l.innerHTML="";
            d.dados.forEach(x=>{{
                let li=document.createElement("li");
                li.innerText=x[1];
                l.appendChild(li);
            }});
        }}
        setInterval(atualizar,2000);
        </script>

        <br><a href="/">🏠 Home</a>
        """

    disciplinas = cursor.execute("SELECT id,nome FROM disciplinas").fetchall()

    form = topo() + "<h2>Iniciar Aula</h2><form method='post'>Disciplina:<select name='disciplina'>"
    for d in disciplinas:
        form += f"<option value='{d[0]}'>{d[1]}</option>"
    form += "</select><br><button>Iniciar</button></form>"

    return form

# -------- PRESENÇAS --------
@app.route("/presencas/<aula_id>")
def presencas(aula_id):
    dados = cursor.execute("""
    SELECT p.codigo, a.nome
    FROM presenca p
    JOIN alunos a ON a.codigo = p.codigo
    WHERE p.aula_id=?
    """,(aula_id,)).fetchall()

    return {"dados": dados}

# -------- AULA ALUNO --------
@app.route("/aula/<aula_id>", methods=["GET","POST"])
def aula(aula_id):

    cursor.execute("SELECT turma_id FROM aulas WHERE id=?", (aula_id,))
    turma_id = cursor.fetchone()[0]

    dispositivo = request.cookies.get("device") or str(uuid.uuid4())
    codigo_salvo = request.cookies.get("codigo")

    if codigo_salvo:
        cursor.execute("INSERT INTO presenca VALUES (?,?,?)",(codigo_salvo,aula_id,dispositivo))
        conn.commit()
        return "<h2 style='color:red;text-align:center'>Presença automática</h2>"

    if request.method=="POST":
        codigo=request.form["codigo"]

        cursor.execute("INSERT OR IGNORE INTO dispositivos VALUES (?,?)",(dispositivo,codigo))
        cursor.execute("INSERT INTO presenca VALUES (?,?,?)",(codigo,aula_id,dispositivo))
        conn.commit()

        resp=make_response("<h2 style='color:red;text-align:center'>Confirmado</h2>")
        resp.set_cookie("codigo",codigo)
        resp.set_cookie("device",dispositivo)
        return resp

    return f"""
    <body style="background:#b30000;color:white;text-align:center;font-family:Arial">

    {topo()}

    <h2>Presença UNIALFA</h2>

    <input id="busca" onkeyup="buscar()" placeholder="Digite seu nome"
    style="padding:10px;width:80%;border-radius:8px;border:none"><br><br>

    <ul id="lista" style="list-style:none;padding:0;"></ul>

    <form method="post">
        <input id="codigo" name="codigo" style="padding:10px;width:80%;border-radius:8px;border:none"><br><br>
        <button style="padding:15px;width:80%;background:white;color:#b30000;border:none;border-radius:10px;font-size:18px;">
            Confirmar Presença
        </button>
    </form>

    <script>
    async function buscar() {{
        let t=document.getElementById("busca").value;
        let r=await fetch('/buscar_aluno/{turma_id}?q='+t);
        let d=await r.json();

        let l=document.getElementById("lista");
        l.innerHTML="";
        d.dados.forEach(x=>{{
            let li=document.createElement("li");
            li.innerText=x[1];
            li.style="padding:10px;background:white;color:#b30000;margin:5px;border-radius:8px;";
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
    termo=request.args.get("q","")
    dados=cursor.execute("""
    SELECT codigo,nome FROM alunos WHERE turma_id=? AND nome LIKE ?
    """,(turma_id,f"%{termo}%")).fetchall()
    return {"dados":dados}

# -------- EXPORTAR --------
@app.route("/faltantes/<aula_id>")
def faltantes(aula_id):
    df=pd.read_sql("""
    SELECT pr.nome as Professor,
           d.codigo as Cod_Disciplina,
           d.nome as Disciplina,
           a.codigo as Matricula,
           a.nome as Aluno
    FROM alunos a
    JOIN aulas au ON au.turma_id=a.turma_id
    JOIN disciplinas d ON d.id=au.disciplina_id
    JOIN professores pr ON pr.id=au.professor_id
    WHERE au.id=? AND a.codigo NOT IN
    (SELECT codigo FROM presenca WHERE aula_id=?)
    ORDER BY a.nome
    """,conn,params=(aula_id,aula_id))

    df["Status"]="FALTA"

    out=io.BytesIO()
    df.to_excel(out,index=False)
    out.seek(0)

    return send_file(out,download_name="faltantes.xlsx",as_attachment=True)

# -------- RODAR --------
if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
