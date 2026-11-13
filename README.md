# Gabriel do Corte — agendamento online

Sistema de agendamento para barbearia, feito em **Python (Flask)** com banco
**SQLite**. Uma página pública onde o cliente marca sozinho e um painel onde o
barbeiro vê e controla a agenda.

Feito do zero. Não usa código de outros projetos.

---

## O que tem

**Página pública (`/`)**
- serviços com duração e preço, galeria, apresentação e contato
- agendamento em 4 passos: serviço → dia → horário → confirmação
- grade de 30 em 30 minutos, das 08:00 às 18:00
- almoço das 11:00 às 13:00 nunca aparece como disponível
- serviço de 60 minutos ocupa dois horários seguidos
- sem cadastro: nome + WhatsApp + aceite da política
- tela de sucesso com código, arquivo `.ics` e botão de WhatsApp

**Painel (`/admin`)**
- hoje: números do dia, próximo cliente, lista com WhatsApp
- semana: grade de dias × horários
- agendamentos: busca, filtros, paginação
- detalhe: confirmar, concluir, cancelar, marcar falta, remarcar
- novo agendamento manual (cliente que chamou no WhatsApp)
- bloqueios de horário ou de dia inteiro
- configurações: horários, serviços, preços, regras, senha e notificações

**Notificações**
- PWA instalável no celular + Web Push (`pywebpush`)
- aviso a cada novo agendamento, cancelamento ou remarcação
- no iPhone funciona instalando pela Tela de Início (iOS 16.4+)

---

## Rodar no computador

```cmd
cd /d D:\Sites\barbearia
py -m pip install -r requirements.txt
py app.py
```

Abra <http://localhost:8000>. Na primeira execução o sistema cria o banco e mostra
no terminal o **usuário e a senha** do painel (também salvos em
`instance/PRIMEIRO-ACESSO.txt`). Troque a senha em Configurações.

No Windows também dá duplo clique em `servir.bat`.

---

## Publicar

Passo a passo em **[docs/COMO-PUBLICAR.md](docs/COMO-PUBLICAR.md)**
(PythonAnywhere de graça, ou Render).

Guia do dia a dia para o barbeiro: **[docs/GUIA-RAPIDO.txt](docs/GUIA-RAPIDO.txt)**.

---

## Estrutura

```
app.py                  rotas, login, painel, APIs
database.py             banco, tabelas e dados iniciais
rules.py                regras de horário (fonte única da verdade)
push.py                 notificações Web Push
wsgi.py                 entrada para servidores de produção
templates/              páginas (Jinja)
static/css/estilo.css   estilo único
static/js/              agendamento, painel e menu
ferramentas/            gerador de ícones
docs/                   guias de publicação e uso
instance/               banco e chaves (NÃO vai para o GitHub)
```

---

## Regras de negócio aplicadas

| Regra | Onde |
|---|---|
| grade de 30 min, 08:00–17:30 | `rules.horarios_do_dia` |
| almoço 11:00–13:00 indisponível | `rules.pode_agendar` |
| 60 min ocupa dois horários | `rules.horarios_do_dia` |
| antecedência mínima (1 h) | `rules.pode_agendar` |
| janela de 30 dias | `rules.pode_agendar` |
| sem reserva dupla | `pode_agendar` + índice único `(data, hora_inicio)` |
| validação no servidor | todas as rotas de escrita |

---

## Segurança

- senha com hash (`werkzeug.security`)
- sessão em cookie `httpOnly`, expira em 12 h
- limite de 5 tentativas de login por 15 min e de 15 agendamentos por 10 min
- CSRF nos formulários, honeypot e checagem de origem na API pública
- `/admin/*` sempre protegido por login
- página pública nunca mostra nome ou WhatsApp de clientes
- chaves e senhas em variáveis de ambiente / `instance/`

---

## Personalizar

Tudo que é texto, preço e horário se troca **dentro do painel**
(Configurações), sem mexer no código.

Para trocar fotos: coloque os arquivos em `static/img/` e substitua os blocos
marcados com `TROCAR` em `templates/index.html`.

Ícones: `py ferramentas/gerar-icones.py` (ou substitua os PNGs pela logo oficial).