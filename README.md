# frequencia

Aplicativo Flask para controle de frequencia em turmas de faculdade com:

- cadastro e login de professor
- cadastro de disciplinas e turmas
- vinculacao professor-disciplina-turma
- importacao de alunos por planilha Excel
- abertura de aula com QR code temporario
- confirmacao de presenca por matricula no celular
- relatorio de presentes e exportacao de faltantes

## Execucao local

```bash
pip install -r requirements.txt
python app.py
```

## Variaveis de ambiente

- `SECRET_KEY`: chave da sessao Flask
- `DATABASE_URL`: URL do PostgreSQL no Render
- `DATABASE_PATH`: caminho do banco SQLite
- `AULA_EXPIRATION_MINUTES`: validade do QR da aula

## Fluxo sugerido

1. Cadastre o professor.
2. Cadastre disciplina e turma.
3. Faca login como professor.
4. Crie a alocacao da disciplina na turma.
5. Importe a planilha de alunos.
6. Inicie a aula para gerar o QR code.
7. Acompanhe o relatorio e exporte os faltantes.

## Observacoes

- Professores antigos sem e-mail/senha recebem migracao automatica para login local.
- Se `DATABASE_URL` estiver definida, o app usa PostgreSQL. Sem ela, continua usando SQLite local.

## Render com PostgreSQL

1. Crie um banco PostgreSQL no Render.
2. Copie a `External Database URL`.
3. No servico web, configure `DATABASE_URL` com essa URL.
4. Configure tambem `SECRET_KEY`.
5. O app cria as tabelas automaticamente na primeira inicializacao.
