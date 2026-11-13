/* =========================================================================
   Fluxo de agendamento (página pública)
   1 Serviço → 2 Data → 3 Horário → 4 Confirmação → Sucesso
   Regras de horário vêm sempre do servidor (/api/horarios).
   ========================================================================= */
(function () {
  "use strict";

  var fonte = document.getElementById("dados");
  if (!fonte) return;

  var dados;
  try {
    dados = JSON.parse(fonte.textContent);
  } catch (erro) {
    return;
  }

  var estado = { servico: null, data: null, hora: null, reservando: false };
  var intervaloAtualizacao = null;

  var paineis = {
    1: document.getElementById("painel1"),
    2: document.getElementById("painel2"),
    3: document.getElementById("painel3"),
    4: document.getElementById("painel4"),
    5: document.getElementById("painel5")
  };
  var etapas = Array.prototype.slice.call(document.querySelectorAll(".etapa"));
  var listaDias = document.getElementById("listaDias");
  var listaHorarios = document.getElementById("listaHorarios");
  var resumoData = document.getElementById("resumoData");
  var resumoFinal = document.getElementById("resumoFinal");
  var irHorarios = document.getElementById("irHorarios");
  var irConfirmar = document.getElementById("irConfirmar");
  var form = document.getElementById("formAgendar");
  var erroForm = document.getElementById("erroForm");
  var botaoConfirmar = document.getElementById("confirmar");

  // ------------------------------------------------------------- utilidades
  function escapar(texto) {
    return String(texto || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function diaLongo(iso) {
    var partes = iso.split("-");
    var data = new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]));
    var dias = ["domingo", "segunda-feira", "terça-feira", "quarta-feira",
                "quinta-feira", "sexta-feira", "sábado"];
    var meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                 "agosto", "setembro", "outubro", "novembro", "dezembro"];
    return dias[data.getDay()] + ", " + data.getDate() + " de " + meses[data.getMonth()];
  }

  function irPara(passo) {
    Object.keys(paineis).forEach(function (chave) {
      var painel = paineis[chave];
      if (painel) painel.hidden = Number(chave) !== passo;
    });

    etapas.forEach(function (etapa) {
      var numero = Number(etapa.getAttribute("data-etapa"));
      etapa.classList.toggle("etapa--ativa", numero === passo);
      etapa.classList.toggle("etapa--feita", numero < passo);
    });

    if (passo !== 3) pararAtualizacao();

    var painel = paineis[passo];
    if (painel) {
      var titulo = painel.querySelector(".painel__titulo");
      if (titulo) {
        titulo.setAttribute("tabindex", "-1");
        titulo.focus({ preventScroll: true });
      }
      painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function servicoPorId(id) {
    for (var i = 0; i < dados.servicos.length; i++) {
      if (dados.servicos[i].id === Number(id)) return dados.servicos[i];
    }
    return null;
  }

  // ------------------------------------------------------------- etapa 1
  function escolherServico(id) {
    var servico = servicoPorId(id);
    if (!servico) return;
    estado.servico = servico;
    estado.data = null;
    estado.hora = null;

    document.querySelectorAll("[data-servico]").forEach(function (botao) {
      botao.setAttribute("aria-pressed",
        String(Number(botao.getAttribute("data-servico")) === servico.id));
    });

    montarDias();
    irPara(2);
  }

  document.querySelectorAll("[data-servico]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      escolherServico(botao.getAttribute("data-servico"));
    });
  });

  document.querySelectorAll("[data-escolher-servico]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      escolherServico(botao.getAttribute("data-escolher-servico"));
    });
  });

  // ------------------------------------------------------------- etapa 2
  function montarDias() {
    if (!listaDias) return;
    listaDias.innerHTML = "";
    var abertos = 0;

    dados.dias.forEach(function (dia) {
      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "dia";
      botao.setAttribute("aria-pressed", "false");

      var fechado = !dia.aberto;
      if (fechado) botao.disabled = true;
      else abertos++;

      botao.innerHTML =
        '<span class="dia__semana">' + escapar(dia.dia_semana_curto) + "</span>" +
        '<span class="dia__numero">' + dia.dia + "</span>" +
        '<span class="dia__mes">' + escapar(dia.mes) + "</span>" +
        (dia.hoje ? '<span class="dia__hoje">hoje</span>' : "") +
        '<span class="sr-only">' + escapar(
          diaLongo(dia.iso) + (fechado ? " — fechado" : "") + (dia.hoje ? " — hoje" : "")
        ) + "</span>";

      botao.addEventListener("click", function () {
        estado.data = dia.iso;
        estado.hora = null;
        Array.prototype.forEach.call(listaDias.children, function (outro) {
          outro.setAttribute("aria-pressed", "false");
        });
        botao.setAttribute("aria-pressed", "true");
        if (irHorarios) irHorarios.disabled = false;
        carregarHorarios();
      });

      listaDias.appendChild(botao);
    });

    var vazio = document.getElementById("diasVazio");
    if (vazio) vazio.hidden = abertos > 0;
    if (irHorarios) irHorarios.disabled = !estado.data;
  }

  if (irHorarios) {
    irHorarios.addEventListener("click", carregarHorarios);
  }

  // ------------------------------------------------------------- etapa 3
  function carregarHorarios() {
    if (!estado.servico || !estado.data) return;

    irPara(3);
    resumoData.textContent = diaLongo(estado.data) + " · " + estado.servico.nome +
      " (" + estado.servico.duracao + " min)";
    listaHorarios.innerHTML = '<p class="carregando">Carregando horários…</p>';
    if (irConfirmar) irConfirmar.disabled = true;

    var url = "/api/horarios?data=" + encodeURIComponent(estado.data) +
              "&servico_id=" + encodeURIComponent(estado.servico.id);

    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (resposta) { return resposta.json(); })
      .then(function (res) {
        if (!res.ok) {
          listaHorarios.innerHTML = '<p class="carregando">' + escapar(res.erro || "Não foi possível carregar.") + "</p>";
          return;
        }
        desenharHorarios(res);
        iniciarAtualizacao();
      })
      .catch(function () {
        listaHorarios.innerHTML =
          '<p class="carregando">Sem conexão. Tente de novo ou chame no WhatsApp.</p>';
      });
  }

  function desenharHorarios(res) {
    listaHorarios.innerHTML = "";
    var visiveis = res.slots.filter(function (slot) { return slot.estado !== "nao_cabe"; });

    if (!visiveis.length) {
      listaHorarios.innerHTML = '<p class="carregando">Nenhum horário neste dia. Escolha outro dia.</p>';
      return;
    }

    var faixaInserida = false;
    var livres = 0;

    visiveis.forEach(function (slot) {
      if (!faixaInserida && res.almoco && slot.hora >= res.almoco.fim) {
        var faixa = document.createElement("p");
        faixa.className = "almoco-faixa";
        faixa.textContent = "Intervalo de almoço · " + res.almoco.inicio + " às " + res.almoco.fim;
        listaHorarios.appendChild(faixa);
        faixaInserida = true;
      }

      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "horario";
      botao.textContent = slot.hora;
      botao.setAttribute("aria-pressed", String(estado.hora === slot.hora));

      if (slot.estado === "livre") {
        livres++;
        botao.addEventListener("click", function () {
          estado.hora = slot.hora;
          Array.prototype.forEach.call(
            listaHorarios.querySelectorAll(".horario"),
            function (outro) { outro.setAttribute("aria-pressed", "false"); }
          );
          botao.setAttribute("aria-pressed", "true");
          if (irConfirmar) irConfirmar.disabled = false;
        });
      } else {
        botao.disabled = true;
        botao.classList.add("horario--bloqueado");
        botao.title = slot.estado === "passou" ? "Horário já passou" : "Horário ocupado";
        botao.setAttribute("aria-label", slot.hora + " — " +
          (slot.estado === "passou" ? "já passou" : "ocupado"));
      }

      listaHorarios.appendChild(botao);
    });

    if (!livres) {
      var soPassou = visiveis.every(function (slot) { return slot.estado === "passou"; });
      var aviso = document.createElement("p");
      aviso.className = "carregando";
      aviso.textContent = soPassou
        ? "Os horários de hoje já passaram. Escolha outro dia."
        : "Todos os horários deste dia estão ocupados. Tente outro dia.";
      listaHorarios.appendChild(aviso);
    }
  }

  function iniciarAtualizacao() {
    pararAtualizacao();
    intervaloAtualizacao = window.setInterval(function () {
      if (!estado.servico || !estado.data) return;
      var url = "/api/horarios?data=" + encodeURIComponent(estado.data) +
                "&servico_id=" + encodeURIComponent(estado.servico.id);
      fetch(url, { headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.ok) return;
          var aindaLivre = res.slots.some(function (slot) {
            return slot.hora === estado.hora && slot.estado === "livre";
          });
          if (estado.hora && !aindaLivre) {
            estado.hora = null;
            if (irConfirmar) irConfirmar.disabled = true;
            avisoRapido("Esse horário acabou de ser ocupado. Escolha outro.");
          }
          desenharHorarios(res);
        })
        .catch(function () { /* silencioso: tenta de novo depois */ });
    }, 25000);
  }

  function pararAtualizacao() {
    if (intervaloAtualizacao) {
      window.clearInterval(intervaloAtualizacao);
      intervaloAtualizacao = null;
    }
  }

  function avisoRapido(texto) {
    var aviso = document.createElement("p");
    aviso.className = "aviso aviso--erro";
    aviso.setAttribute("role", "alert");
    aviso.textContent = texto;
    listaHorarios.parentNode.insertBefore(aviso, listaHorarios);
    window.setTimeout(function () { aviso.remove(); }, 6000);
  }

  // ------------------------------------------------------------- etapa 4
  function montarResumo() {
    if (!estado.servico) return;
    resumoFinal.innerHTML =
      linhaResumo("Serviço", estado.servico.nome) +
      linhaResumo("Dia", diaLongo(estado.data)) +
      linhaResumo("Horário", estado.hora + " (" + estado.servico.duracao + " min)") +
      linhaResumo("Valor", estado.servico.preco);

    irPara(4);
  }

  function linhaResumo(rotulo, valor) {
    return "<div><dt>" + escapar(rotulo) + "</dt><dd>" + escapar(valor) + "</dd></div>";
  }

  if (irConfirmar) {
    irConfirmar.addEventListener("click", function () {
      if (!estado.hora) return;
      montarResumo();
    });
  }

  document.querySelectorAll("[data-voltar]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var destino = Number(botao.getAttribute("data-voltar"));
      if (destino === 1) {
        estado.data = null;
        estado.hora = null;
        irPara(1);
      } else if (destino === 2) {
        if (estado.servico) montarDias();
        irPara(2);
      } else {
        irPara(3);
      }
    });
  });

  // ------------------------------------------------------------- máscara
  var campoWhats = document.getElementById("whatsapp");
  if (campoWhats) {
    campoWhats.addEventListener("input", function () {
      var digitos = campoWhats.value.replace(/\D/g, "").slice(0, 11);
      var saida = digitos;
      if (digitos.length > 6) {
        saida = "(" + digitos.slice(0, 2) + ") " + digitos.slice(2, 7) + "-" + digitos.slice(7);
      } else if (digitos.length > 2) {
        saida = "(" + digitos.slice(0, 2) + ") " + digitos.slice(2);
      } else if (digitos.length > 0) {
        saida = "(" + digitos;
      }
      campoWhats.value = saida;
    });
  }

  // ------------------------------------------------------------- envio
  function mostrarErro(texto) {
    if (!erroForm) return;
    erroForm.textContent = texto;
    erroForm.hidden = false;
  }

  if (form) {
    form.addEventListener("submit", function (evento) {
      evento.preventDefault();
      if (estado.reservando) return;
      if (erroForm) erroForm.hidden = true;

      var nome = (document.getElementById("nome").value || "").trim();
      var whats = (document.getElementById("whatsapp").value || "").replace(/\D/g, "");
      var consentimento = document.getElementById("consentimento").checked;
      var honeypot = document.getElementById("site");

      if (nome.length < 3) {
        mostrarErro("Digite seu nome completo.");
        document.getElementById("nome").focus();
        return;
      }
      if (whats.length < 10) {
        mostrarErro("Digite o WhatsApp com DDD, ex.: (73) 99999-9999.");
        document.getElementById("whatsapp").focus();
        return;
      }
      if (!consentimento) {
        mostrarErro("É preciso aceitar o uso dos dados para agendar.");
        return;
      }

      estado.reservando = true;
      if (botaoConfirmar) {
        botaoConfirmar.disabled = true;
        botaoConfirmar.dataset.texto = botaoConfirmar.textContent;
        botaoConfirmar.textContent = "Reservando…";
      }

      fetch("/api/agendar", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          servico_id: estado.servico.id,
          data: estado.data,
          hora: estado.hora,
          nome: nome,
          whatsapp: whats,
          consentimento: true,
          site: honeypot ? honeypot.value : ""
        })
      })
        .then(function (resposta) { return resposta.json().then(function (corpo) { return { status: resposta.status, corpo: corpo }; }); })
        .then(function (resultado) {
          estado.reservando = false;
          if (botaoConfirmar) {
            botaoConfirmar.disabled = false;
            botaoConfirmar.textContent = botaoConfirmar.dataset.texto || "Confirmar agendamento";
          }

          if (!resultado.corpo || !resultado.corpo.ok) {
            mostrarErro(resultado.corpo && resultado.corpo.erro
              ? resultado.corpo.erro
              : "Não deu para reservar. Tente outro horário.");
            if (resultado.status === 409) {
              estado.hora = null;
              if (irConfirmar) irConfirmar.disabled = true;
              carregarHorarios();
            }
            return;
          }

          mostrarSucesso(resultado.corpo);
        })
        .catch(function () {
          estado.reservando = false;
          if (botaoConfirmar) {
            botaoConfirmar.disabled = false;
            botaoConfirmar.textContent = botaoConfirmar.dataset.texto || "Confirmar agendamento";
          }
          mostrarErro("Sem conexão com o servidor. Tente de novo.");
        });
    });
  }

  function mostrarSucesso(res) {
    pararAtualizacao();
    document.getElementById("codigoFinal").textContent = res.codigo;

    var resumo = document.getElementById("resumoSucesso");
    resumo.innerHTML =
      linhaResumo("Serviço", res.resumo.servico) +
      linhaResumo("Dia", res.resumo.data) +
      linhaResumo("Horário", res.resumo.hora) +
      linhaResumo("Nome", res.resumo.nome);

    var ics = document.getElementById("btnIcs");
    if (ics) ics.href = "/agendamento/" + res.codigo + ".ics";

    var zap = document.getElementById("btnWhats");
    if (zap) {
      var texto = "Olá! Sou " + res.resumo.nome + " e acabei de agendar " +
        res.resumo.servico + " para " + res.resumo.data + " às " + res.resumo.hora +
        ". Código " + res.codigo + ".";
      zap.href = "https://wa.me/" + dados.whatsapp + "?text=" + encodeURIComponent(texto);
    }

    irPara(5);
    var codigo = document.getElementById("codigoFinal");
    if (codigo) codigo.focus({ preventScroll: true });
  }

  var novo = document.getElementById("novoAgendamento");
  if (novo) {
    novo.addEventListener("click", function () {
      estado.servico = null;
      estado.data = null;
      estado.hora = null;
      document.querySelectorAll("[data-servico]").forEach(function (botao) {
        botao.setAttribute("aria-pressed", "false");
      });
      if (form) form.reset();
      if (erroForm) erroForm.hidden = true;
      montarDias();
      irPara(1);
    });
  }

  // ------------------------------------------------------------- galeria
  var lightbox = document.getElementById("lightbox");
  var lightboxTexto = document.getElementById("lightboxTexto");
  var lightboxFechar = document.getElementById("lightboxFechar");
  var focoAnterior = null;

  document.querySelectorAll("[data-foto]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      if (!lightbox) return;
      focoAnterior = botao;
      lightboxTexto.textContent = "Foto de corte " + botao.getAttribute("data-foto");
      lightbox.hidden = false;
      if (lightboxFechar) lightboxFechar.focus();
    });
  });

  function fecharLightbox() {
    if (!lightbox || lightbox.hidden) return;
    lightbox.hidden = true;
    if (focoAnterior) focoAnterior.focus();
  }

  if (lightboxFechar) lightboxFechar.addEventListener("click", fecharLightbox);
  if (lightbox) {
    lightbox.addEventListener("click", function (evento) {
      if (evento.target === lightbox) fecharLightbox();
    });
  }
  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") fecharLightbox();
  });
})();