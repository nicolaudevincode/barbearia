@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Barbearia - Criar repo + Conectar GitHub e Vercel
color 0E

rem ============================================================
rem  BARBEARIA - cria o repositorio e conecta GitHub + Vercel
rem  Fica em: D:\Sites\barbearia\CONECTAR-GITHUB-VERCEL.cmd
rem  Duplo clique = menu.  Ou por parametro:
rem    CONECTAR-GITHUB-VERCEL.cmd github
rem    CONECTAR-GITHUB-VERCEL.cmd vercel
rem    CONECTAR-GITHUB-VERCEL.cmd tudo
rem    CONECTAR-GITHUB-VERCEL.cmd publicar
rem    CONECTAR-GITHUB-VERCEL.cmd paineis
rem    CONECTAR-GITHUB-VERCEL.cmd teste
rem ============================================================

rem ---- dados do projeto (troque aqui se mudar o nome) ----
set "NOMEREPO=barbearia"
set "CONTA=nicolaudevincode"
set "DESCRICAO=Site da barbearia - HTML/CSS/JS estatico (projeto novo)"
set "DOMINIO=[A CONFIRMAR]"

set "SLUG=%CONTA%/%NOMEREPO%"
set "REPO=https://github.com/%CONTA%/%NOMEREPO%.git"
set "SITE=https://%CONTA%.github.io/%NOMEREPO%/"
set "VPROJ=%NOMEREPO%"

set "PROJETO=%~dp0"
pushd "%PROJETO%"
set "PROJETO=%CD%"
popd

set "TOKEN_FILE=%PROJETO%\vercel-token.txt"
set "GHBIN=%LOCALAPPDATA%\GitHubCLI\bin"
if exist "%GHBIN%\gh.exe" set "PATH=%GHBIN%;%PATH%"

set "MODO=MENU"
if /i "%~1"=="github"   set "MODO=UNICO" & goto github
if /i "%~1"=="vercel"   set "MODO=UNICO" & goto vercel
if /i "%~1"=="tudo"     set "MODO=UNICO" & goto tudo
if /i "%~1"=="publicar" set "MODO=UNICO" & goto publicar
if /i "%~1"=="paineis"  set "MODO=UNICO" & goto paineis
if /i "%~1"=="teste"    set "MODO=UNICO" & goto testes
if /i "%~1"=="dominio"  set "MODO=UNICO" & goto dominio

:menu
cls
echo.
echo  ==============================================================
echo    BARBEARIA  -  REPOSITORIO + GITHUB + VERCEL
echo  ==============================================================
echo    Pasta do site : %PROJETO%
echo    Repositorio   : %SLUG%
echo    Site          : %SITE%
echo  --------------------------------------------------------------
echo    [1] Criar/conectar o GITHUB  (repo, login, push, Pages)
echo    [2] Conectar a VERCEL        (API com token ou CLI)
echo    [3] Fazer as duas conexoes   (recomendado)
echo    [4] Publicar agora           (git add -A, commit e push)
echo    [5] Abrir paineis no navegador
echo    [6] Ver minha configuracao atual (diagnostico)
echo    [7] Dominio novo - registros de DNS (Vercel / Pages)
echo    [0] Sair
echo  ==============================================================
echo.
if not exist "%PROJETO%\index.html" (
  echo  AVISO: ainda nao existe index.html nesta pasta.
  echo         O site da barbearia nao foi criado ainda.
  echo.
)
set "OP="
set /p "OP=Escolha uma opcao: "
if "!OP!"=="1" goto github
if "!OP!"=="2" goto vercel
if "!OP!"=="3" goto tudo
if "!OP!"=="4" goto publicar
if "!OP!"=="5" goto paineis
if "!OP!"=="6" goto testes
if "!OP!"=="7" goto dominio
if "!OP!"=="0" goto fim
goto menu

rem ============================================================
:esperar
if /i "%MODO%"=="UNICO" goto fim
pause
goto menu

rem ============================================================
:github
cls
echo.
echo  ============  GITHUB (criar repo + conectar)  ==============
echo.
echo  [1/7] Verificando o git...
where git >nul 2>nul
if errorlevel 1 (
  echo        ERRO: git nao encontrado.
  start "" "https://git-scm.com/download/win"
  goto esperar
)
for /f "delims=" %%V in ('git --version') do echo        OK: %%V

echo.
echo  [2/7] Verificando o GitHub CLI ^(gh^)...
where gh >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if errorlevel 1 (
    start "" "https://cli.github.com/"
    goto esperar
  )
  winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
  if exist "%GHBIN%\gh.exe" set "PATH=%GHBIN%;%PATH%"
  where gh >nul 2>nul
  if errorlevel 1 (
    echo        Feche esta janela e rode de novo.
    goto esperar
  )
)
for /f "delims=" %%V in ('gh --version') do (
  echo        OK: %%V
  goto :gh_ok
)
:gh_ok

echo.
echo  [3/7] Login no GitHub...
call gh auth status >nul 2>nul
if errorlevel 1 (
  echo        Abrindo o navegador para autorizar a conta %CONTA%...
  call gh auth login --hostname github.com --git-protocol https --web --scopes repo,workflow,gist,read:org
  call gh auth status >nul 2>nul
  if errorlevel 1 (
    echo        ERRO: login nao concluido.
    goto esperar
  )
)
call gh auth status
call gh auth setup-git

echo.
echo  [4/7] Preparando o repositorio local...
pushd "%PROJETO%"
if not exist ".git" (
  echo        git init -b main
  git init -b main >nul
)
git config user.name "%CONTA%"
git config user.email "%CONTA%@users.noreply.github.com"
git rev-parse --verify HEAD >nul 2>nul
if errorlevel 1 (
  echo        Criando o primeiro commit...
  git add -A
  git commit -m "Base inicial do site da barbearia" >nul
  if errorlevel 1 echo        Nada para commitar ^(pasta vazia^).
)

echo.
echo  [5/7] O repositorio %SLUG% existe no GitHub?
call gh repo view "%SLUG%" >nul 2>nul
if errorlevel 1 (
  echo        Nao existe. Criando agora...
  call gh repo create "%SLUG%" --public --description "%DESCRICAO%"
  if errorlevel 1 (
    echo        ERRO ao criar. Pode ser nome ja usado ou falta de permissao.
    popd
    goto esperar
  )
  echo        Criado: https://github.com/%SLUG%
) else (
  echo        Sim, ja existe: https://github.com/%SLUG%
)

echo.
echo  [6/7] Conectando e enviando o codigo...
git remote get-url origin >nul 2>nul
if errorlevel 1 (
  git remote add origin "%REPO%"
) else (
  set "ATUAL="
  for /f "delims=" %%R in ('git remote get-url origin') do set "ATUAL=%%R"
  if /i not "!ATUAL!"=="%REPO%" git remote set-url origin "%REPO%"
)
git rev-parse --verify HEAD >nul 2>nul
if errorlevel 1 (
  echo        Sem commit local: nada para enviar ainda.
) else (
  git push -u origin main
  if errorlevel 1 (
    echo        ERRO no push. Confira o login e o nome do repositorio.
    popd
    goto esperar
  )
)
git status -sb 2>nul | findstr /b "##"

echo.
echo  [7/7] GitHub Pages...
set "PGSTATUS="
for /f "delims=" %%L in ('gh api "repos/%SLUG%/pages" --jq ".status" 2^>nul') do set "PGSTATUS=%%L"
if defined PGSTATUS (
  echo        Pages ativo ^(status: !PGSTATUS!^) - %SITE%
) else (
  if exist "%PROJETO%\index.html" (
    echo        Ativando Pages na branch main, raiz / ...
    call gh api -X POST "repos/%SLUG%/pages" -f "source[branch]=main" -f "source[path]=/" >nul 2>nul
    if errorlevel 1 (
      echo        Nao consegui ativar. Ative manualmente em:
      echo        https://github.com/%SLUG%/settings/pages
    ) else (
      echo        Pages ativado. O site fica em %SITE%
    )
  ) else (
    echo        Ainda nao existe index.html - Pages sera ativado depois.
  )
)
popd
echo.
echo  --------------------------------------------------------------
echo   GITHUB OK. Site: %SITE%
echo  --------------------------------------------------------------
echo.
goto esperar

rem ============================================================
:vercel
cls
echo.
echo  ======================  VERCEL  ============================
echo.
where vercel >nul 2>nul
if errorlevel 1 goto vercel_escolha
call vercel whoami >nul 2>nul
if errorlevel 1 call vercel login
call vercel whoami
echo.
pushd "%PROJETO%"
if exist ".vercel" (
  call vercel --prod
) else (
  call vercel link --yes --project %VPROJ%
  call vercel --prod
)
popd
echo.
goto esperar

:vercel_escolha
echo  Vercel CLI nao instalado ^(Node/npm ausentes^).
echo.
echo    [1] Conectar pela API da Vercel com token  ^(sem Node^)
echo    [2] Instalar Node.js + Vercel CLI pelo winget
echo    [0] Voltar
echo.
set "OPV="
set /p "OPV=Escolha: "
if "!OPV!"=="1" goto vercel_api
if "!OPV!"=="2" goto vercel_node
goto voltar

:vercel_node
echo.
winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
echo.
echo  Depois: feche esta janela, abra de novo e rode  npm install -g vercel
echo.
goto esperar

:vercel_api
echo.
set "VTOKEN="
if exist "%TOKEN_FILE%" (
  set /p VTOKEN=<"%TOKEN_FILE%"
  echo  Token salvo encontrado.

)
if "!VTOKEN!"=="" (
  echo  Gere um token em: https://vercel.com/account/tokens
  echo.
  set /p "VTOKEN=Cole o token aqui: "
)
if "!VTOKEN!"=="" (
  echo  Nenhum token informado. Cancelado.
  goto esperar
)
set "VTOK=!VTOKEN!"

echo.
echo  [1/3] Validando o token...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{$h=@{Authorization=('Bearer '+$env:VTOK)};$u=Invoke-RestMethod -Uri 'https://api.vercel.com/v2/user' -Headers $h;Write-Host ('       OK - conta Vercel: '+$u.user.username);exit 0}catch{Write-Host '       ERRO: token invalido, expirado ou sem internet.';exit 1}"
if errorlevel 1 (
  if exist "%TOKEN_FILE%" del "%TOKEN_FILE%" >nul 2>nul
  goto esperar
)

echo.
echo  [2/3] Projeto %VPROJ% na Vercel...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=@{Authorization=('Bearer '+$env:VTOK)};try{$p=Invoke-RestMethod -Uri ('https://api.vercel.com/v9/projects/'+$env:VPROJ) -Headers $h;Write-Host ('       OK - projeto ja existe: '+$p.name);exit 0}catch{$c=0;try{$c=[int]$_.Exception.Response.StatusCode}catch{};if($c -ne 404){Write-Host ('       ERRO: '+$_.Exception.Message);exit 1};Write-Host '       Projeto nao existe. Criando e ligando ao GitHub...';$b=(@{name=$env:VPROJ;gitRepository=@{type='github';repo=('nicolaudevincode/'+$env:VPROJ)}} | ConvertTo-Json);try{$n=Invoke-RestMethod -Uri 'https://api.vercel.com/v11/projects' -Method Post -Headers $h -ContentType 'application/json' -Body $b;Write-Host ('       OK - criado: '+$n.name);exit 0}catch{Write-Host ('       ERRO ao criar: '+$_.Exception.Message);Write-Host '       Dica: conecte o GitHub em https://vercel.com/account/login-connections';exit 1}}"
if errorlevel 1 goto esperar

echo.
echo  [3/3] Token...
if exist "%TOKEN_FILE%" (
  echo        Ja estava salvo.
) else (
  set "SALVAR="
  set /p "SALVAR=Salvar o token nesta pasta? (S/N): "
  if /i "!SALVAR!"=="S" >"%TOKEN_FILE%" echo !VTOKEN!
  if /i "!SALVAR!"=="S" echo        Salvo em %TOKEN_FILE%
)
echo.
echo  --------------------------------------------------------------
echo   VERCEL OK. Cada "git push" na main publica sozinho.
echo   Painel: https://vercel.com/dashboard
echo  --------------------------------------------------------------
echo.
goto esperar

rem ============================================================
:tudo
cls
echo  Conexao completa. Nao feche a janela.
call "%~f0" github
call "%~f0" vercel
cls
echo.
echo  ==============================================================
echo    TUDO PRONTO
echo  ==============================================================
echo    GitHub : https://github.com/%SLUG%
echo    Pages  : %SITE%
echo    Vercel : https://vercel.com/dashboard
echo  ==============================================================
echo.
goto esperar

rem ============================================================
:publicar
cls
echo.
echo  ======================  PUBLICAR  ==========================
echo.
pushd "%PROJETO%"
git add -A
git diff --cached --quiet
if errorlevel 1 (
  set "MSG="
  set /p "MSG=Mensagem do commit (Enter = padrao): "
  if "!MSG!"=="" set "MSG=Atualizacao do site da barbearia"
  git commit -m "!MSG!"
) else (
  echo  Nada novo para commitar.
)
git push origin main
if errorlevel 1 (
  echo  ERRO no push. Rode a opcao 1 primeiro.
  popd
  goto esperar
)
git log --oneline -3
popd
echo.
echo  Enviado. Pages e Vercel publicam em ~1 minuto.
echo  Site: %SITE%
echo.
goto esperar

rem ============================================================
:paineis
cls
start "" "https://github.com/%SLUG%"
start "" "https://github.com/%SLUG%/settings/pages"
start "" "https://github.com/%SLUG%/actions"
start "" "https://vercel.com/dashboard"
start "" "%SITE%"
echo  Paineis abertos no navegador.
echo.
goto esperar

rem ============================================================
:dominio
cls
echo.
echo  =================  DOMINIO NOVO (DNS)  =====================
echo.
echo   Dominio configurado no script : %DOMINIO%
if /i "%DOMINIO%"=="[A CONFIRMAR]" (
  echo.
  echo   Ainda nao definido. Registre um dominio novo em:
  echo      .com.br  -^> https://registro.br
  echo      .com     -^> Cloudflare Registrar / Namecheap / Porkbun
  echo   Depois edite a linha  set "DOMINIO=..."  no inicio deste CMD.
)
echo.
echo   ---- PRODUCAO NA VERCEL (recomendado) ----
echo      No painel da Vercel: projeto %VPROJ% -^> Settings -^> Domains -^> Add
echo      Depois, no registrador do dominio, crie:
echo.
echo         Tipo    Nome    Valor
echo         A       @       76.76.21.21
echo         CNAME   www     cname.vercel-dns.com
echo.
echo      O HTTPS e emitido automaticamente depois da propagacao.
echo.
echo   ---- OPCIONAL: GITHUB PAGES (espelho de teste) ----
echo         A       @       185.199.108.153
echo         A       @       185.199.109.153
echo         A       @       185.199.110.153
echo         A       @       185.199.111.153
echo         CNAME   www     %CONTA%.github.io
echo.
echo      E criar um arquivo CNAME na raiz do site com o dominio.
echo.
echo   ATENCAO: o mesmo dominio nao pode apontar para Vercel e GitHub Pages
echo            ao mesmo tempo. Padrao do projeto: Vercel = producao.
echo.
echo   Testar propagacao:  nslookup %DOMINIO%
echo.
goto esperar

rem ============================================================
:testes
cls
echo.
echo  ====================  DIAGNOSTICO  =========================
echo.
echo  Pasta do site : %PROJETO%
echo  Repositorio   : %SLUG%
echo  index.html    : 
if exist "%PROJETO%\index.html" (echo                   existe) else (echo                   NAO existe ainda)
echo.
echo  --- git ---
where git >nul 2>nul && git --version || echo  git NAO encontrado
echo.
echo  --- gh ---
where gh >nul 2>nul && gh --version || echo  gh NAO encontrado
echo.
echo  --- login GitHub ---
call gh auth status 2>&1
echo.
echo  --- repo no GitHub ---
set "REPOURL="
for /f "delims=" %%U in ('gh repo view "%SLUG%" --json url --jq ".url" 2^>nul') do set "REPOURL=%%U"
if defined REPOURL (
  echo  Existe: !REPOURL!
) else (
  echo  Repositorio %SLUG% ainda nao existe.
)
echo.
echo  --- git local ---
pushd "%PROJETO%"
git remote -v 2>nul
git status -sb 2>nul | findstr /b "##"
popd
echo.
echo  --- Node / npm / Vercel CLI ---
where node >nul 2>nul && node -v || echo  node NAO instalado
where npm  >nul 2>nul && npm -v  || echo  npm NAO instalado
where vercel >nul 2>nul && vercel --version || echo  vercel CLI NAO instalado
echo.
echo  --- token Vercel salvo ---
if exist "%TOKEN_FILE%" (echo  Sim: %TOKEN_FILE%) else (echo  Nao)
echo.
goto esperar

rem ============================================================
:fim
echo.
echo  Ate mais. Script: %~f0
echo.
endlocal
exit /b 0