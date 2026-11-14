COMO PUBLICAR O SITE
====================

O sistema é Python + Flask. Duas hospedagens:

  A) Vercel  — desde 13/11/2026 o projeto já está PREPARADO para ela
               (api/index.py, vercel.json, Postgres opcional)
  B) PythonAnywhere — mantém o SQLite e é GRÁTIS hoje


------------------------------------------------------------------
A) VERCEL (opção do Gabriel: "azevedodocorte.vercel.app")
------------------------------------------------------------------

O que a Vercel precisa do projeto:

  • enviou GitHub → Vercel (branch main)
  • banco: PostgreSQL (nunca SQLite) — URL na variável POSTGRES_URL

PASSO A PASSO (uma vez):

1. Conta na Vercel: https://vercel.com (login com o GitHub)

2. Crie o token: https://vercel.com/account/tokens
   (escolha "Full Account" para permitir criar projetos e variáveis)

3. No painel Vercel, abra o projeto (ou crie com o nome azevedodocorte)
   e vá em  Settings → Environment Variables  e crie:

     POSTGRES_URL  (o sistema aceita isso; veja passo 4)

   e, para ter a URL automaticamente, no passo 4 o Vercel cria POSTGRES_URL
   sozinho quando você criar o banco "Postgres" no projeto.

4. No projeto:  Storage → Create Database → Postgres (Neon)
   Clicar em "Connect" no projeto: a Vercel já injeta POSTGRES_URL.

5. Variáveis extras que recomendamos (Settings → Environment Variables):

     SECRET_KEY      -> texto longo aleatório (protege o login)
     COOKIE_SECURE   -> 1
     ADMIN_USUARIO   -> gabriel
     ADMIN_SENHA     -> senha que o Gabriel escolher (mín. 8)

6. Deploy: vercel tab → "Deploy" (ou push na branch main, se o projeto
   estiver ligado ao GitHub)

7. Compartilhar: https://azevedodocorte.vercel.app
   O painel do barbeiro: /admin

NOTA: na primeira execução do banco, são criadas as tabelas e o usuário
"gabriel" com a senha de ADMIN_SENHA (ou uma aleatória impressa nos logs
da função, se ADMIN_SENHA não for definida).


------------------------------------------------------------------
B) PYTHONANYWHERE (alternativa GRÁTIS, mantém SQLite)
------------------------------------------------------------------

1. Crie a conta em https://www.pythonanywhere.com/plans/
   (plano "Beginner", gratuito).

2. Suba o código. O jeito mais fácil é pelo GitHub:
   - o projeto já está em https://github.com/nicolaudevincode/barbearia
   - no PythonAnywhere, abra um "Bash console" e rode:

     git clone https://github.com/nicolaudevincode/barbearia.git
     cd barbearia
     python3 -m venv venv
     source venv/bin/activate
     pip install -r requirements.txt

3. Crie o web app:
   - aba "Web" → "Add a new web app"
   - escolha "Manual configuration" → Python 3.10 (ou a versão mais nova)
   - em "Virtualenv", informe:  /home/SEU_USUARIO/barbearia/venv

4. Configure o arquivo WSGI:
   - clique no link do arquivo WSGI e apague tudo
   - cole (trocando SEU_USUARIO):

     import sys
     sys.path.insert(0, "/home/SEU_USUARIO/barbearia")
     from app import app as application

5. Ajuste as variáveis de ambiente (seção "Environment variables"):
   - SECRET_KEY        -> invente uma frase longa e aleatória
   - ADMIN_USUARIO     -> gabriel
   - ADMIN_SENHA       -> uma senha forte (mínimo 8 caracteres)
   - COOKIE_SECURE     -> 1
   - BARBEARIA_DB      -> /home/SEU_USUARIO/barbearia/instance/barbearia.db

6. Aponte os arquivos estáticos:
   - seção "Static files"
   - URL: /static/   →   Directory: /home/SEU_USUARIO/barbearia/static

7. Clique em "Reload" e abra https://SEU_USUARIO.pythonanywhere.com

8. O banco é criado sozinho na primeira visita. Entre em /login com o usuário e
   a senha que você definiu acima.

9. Domínio próprio (opcional):
   - aba "Web" → "Add a new domain"
   - no registro do domínio, crie o CNAME que o PythonAnywhere mostrar
   - HTTPS é gratuito (botão "Force HTTPS")

ATENÇÃO: no plano gratuito o PythonAnywhere pede para você clicar em
"Run until 3 months from today" a cada 3 meses, senão o site é pausado.


------------------------------------------------------------------
B) RENDER (pago, com disco próprio)
------------------------------------------------------------------

1. Conta em https://render.com (login com GitHub).
2. "New" → "Blueprint" → escolha o repositório barbearia.
3. O arquivo render.yaml já está pronto no projeto.
4. Preencha ADMIN_SENHA quando pedir e clique em "Apply".
5. O disco de 1 GB guarda o banco em /var/data/barbearia.db.

Sem o disco (plano gratuito do Render) os agendamentos somem a cada reinício —
por isso o render.yaml já pede o plano "starter".


------------------------------------------------------------------
TESTAR RÁPIDO NO CELULAR (LINK TEMPORÁRIO, SEM CONTA)
------------------------------------------------------------------

Serve para mostrar o site funcionando hoje, inclusive para o Gabriel,
sem contratar nada. NÃO é hospedagem definitiva: o endereço muda e o site
sai do ar quando o computador desligar.

1. Deixe o site rodando no computador:  py app.py
2. Em outro terminal (a pasta .local é criada na primeira vez):

   .local\cloudflared.exe tunnel --url http://127.0.0.1:8000 --no-autoupdate

3. Copie o endereço https://algo-algo-algo.trycloudflare.com que aparecer.
4. Abra no celular. O painel é o mesmo endereço com /admin no final.
5. Para encerrar: Ctrl+C no terminal do cloudflared.

Enquanto isso, o site também responde na rede de casa:
http://IP-DO-COMPUTADOR:8000  (ex.: http://192.168.0.108:8000)


------------------------------------------------------------------
ATUALIZAR O SITE DEPOIS DE MUDAR O CÓDIGO
------------------------------------------------------------------

No computador:

  cd /d D:\Sites\barbearia
  git add -A
  git commit -m "descrição da mudança"
  git push

Depois, no servidor:

  PythonAnywhere: Bash console → cd barbearia → git pull → aba Web → Reload
  Render: ele republica sozinho a cada push.


------------------------------------------------------------------
O QUE NÃO PODE FALTAR
------------------------------------------------------------------

- instance/  nunca vai para o GitHub (tem o banco e as chaves)
- troque a senha inicial em Configurações assim que entrar
- faça backup: copie instance/barbearia.db de vez em quando