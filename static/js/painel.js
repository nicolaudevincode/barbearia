/* Painel: aviso de novo agendamento + notificações no celular (PWA) */
(function () {
  "use strict";

  // ------------------------------------------------ aviso de novidade
  var faixa = document.getElementById("novidade");
  var textoFaixa = document.getElementById("novidadeTexto");
  var botaoRecarregar = document.getElementById("novidadeRecarregar");
  var desde = null;

  function verificar() {
    var url = "/api/admin/novidades" + (desde ? "?desde=" + encodeURIComponent(desde) : "");
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (resposta) { return resposta.json(); })
      .then(function (res) {
        if (!res || !res.ok) return;
        if (!desde) {
          desde = res.agora;
          return;
        }
        if (res.novos > 0) {
          desde = res.agora;
          if (faixa) {
            textoFaixa.textContent = res.novos === 1
              ? "1 novo agendamento chegou."
              : res.novos + " novos agendamentos chegaram.";
            faixa.hidden = false;
          }
          tocarAviso();
        }
      })
      .catch(function () { /* sem internet: tenta depois */ });
  }

  if (document.querySelector(".adm__conteudo")) {
    verificar();
    window.setInterval(verificar, 20000);
  }

  if (botaoRecarregar) {
    botaoRecarregar.addEventListener("click", function () {
      window.location.reload();
    });
  }

  function tocarAviso() {
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      var ctx = new AudioCtx();
      var osc = ctx.createOscillator();
      var ganho = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 880;
      ganho.gain.value = 0.06;
      osc.connect(ganho);
      ganho.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.16);
    } catch (erro) { /* silêncio */ }
  }

  // ------------------------------------------------ PWA + push
  var status = document.getElementById("pushStatus");
  var ativar = document.getElementById("ativarPush");
  var testar = document.getElementById("testarPush");

  function avisar(msg, erro) {
    if (!status) return;
    status.textContent = msg;
    status.className = "nota" + (erro ? " erro-push" : "");
  }

  function base64ParaBytes(texto) {
    var preenchimento = "=".repeat((4 - (texto.length % 4)) % 4);
    var base64 = (texto + preenchimento).replace(/-/g, "+").replace(/_/g, "/");
    var bruto = window.atob(base64);
    var bytes = new Uint8Array(bruto.length);
    for (var i = 0; i < bruto.length; i++) bytes[i] = bruto.charCodeAt(i);
    return bytes;
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () { /* ignora */ });
  }

  function inscrever() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      avisar("Este navegador não suporta notificações. No iPhone, instale pelo Safari " +
             "(Compartilhar → Adicionar à Tela de Início) e abra pelo ícone.", true);
      return Promise.reject(new Error("sem suporte"));
    }

    return Notification.requestPermission().then(function (permissao) {
      if (permissao !== "granted") {
        avisar("Permissão de notificação negada. Ative nas configurações do navegador.", true);
        throw new Error("negado");
      }
      return fetch("/api/push/chave").then(function (r) { return r.json(); });
    }).then(function (res) {
      if (!res.ok || !res.chave) throw new Error("chave");
      return navigator.serviceWorker.ready.then(function (registro) {
        return registro.pushManager.getSubscription().then(function (existente) {
          if (existente) return existente;
          return registro.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: base64ParaBytes(res.chave)
          });
        });
      });
    }).then(function (inscricao) {
      var dados = inscricao.toJSON();
      return fetch("/api/push/inscrever", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: dados.endpoint, keys: dados.keys })
      });
    }).then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.ok) avisar("Notificações ativadas neste aparelho. ✔");
        else avisar("Não deu para salvar o aparelho. Tente de novo.", true);
      })
      .catch(function (erro) {
        if (erro && erro.message === "negado") return;
        if (erro && erro.message === "sem suporte") return;
        avisar("Não foi possível ativar. No iPhone, instale o painel na Tela de Início primeiro.", true);
      });
  }

  if (ativar) {
    ativar.addEventListener("click", function () {
      avisar("Pedindo permissão…");
      inscrever();
    });
  }

  if (testar) {
    testar.addEventListener("click", function () {
      fetch("/api/push/teste", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.disponivel) avisar("Servidor sem suporte a notificações (pywebpush).", true);
          else if (res.enviados > 0) avisar("Teste enviado para " + res.enviados + " aparelho(s).");
          else avisar("Nenhum aparelho cadastrado ainda. Ative primeiro.", true);
        })
        .catch(function () { avisar("Falha ao enviar o teste.", true); });
    });
  }
})();