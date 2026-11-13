/* Menu do site + detalhes gerais (roda nas páginas públicas e no painel) */
(function () {
  "use strict";

  var botao = document.getElementById("menuBotao");
  var menu = document.getElementById("menuPrincipal") || document.getElementById("menuAdmin");

  if (botao && menu) {
    var fechar = function () {
      menu.classList.remove("aberto");
      botao.setAttribute("aria-expanded", "false");
      botao.querySelector(".sr-only").textContent = "Abrir menu";
    };

    botao.addEventListener("click", function () {
      var aberto = menu.classList.toggle("aberto");
      botao.setAttribute("aria-expanded", String(aberto));
      botao.querySelector(".sr-only").textContent = aberto ? "Fechar menu" : "Abrir menu";
    });

    menu.addEventListener("click", function (evento) {
      if (evento.target.closest("a")) fechar();
    });

    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") fechar();
    });

    document.addEventListener("click", function (evento) {
      if (!menu.contains(evento.target) && !botao.contains(evento.target)) fechar();
    });
  }

  // Bloqueios: esconder os campos de hora quando for o dia inteiro
  var diaInteiro = document.getElementById("dia_inteiro");
  var camposHorario = document.getElementById("camposHorario");
  if (diaInteiro && camposHorario) {
    var alternar = function () {
      camposHorario.style.display = diaInteiro.checked ? "none" : "";
    };
    diaInteiro.addEventListener("change", alternar);
    alternar();
  }

  // Marcar no formulário de novo agendamento a data/hora vindas da grade
  var dataInput = document.getElementById("data");
  if (dataInput && !dataInput.value) {
    var hoje = new Date();
    var iso = new Date(hoje.getTime() - hoje.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 10);
    if (dataInput.type === "date") dataInput.value = iso;
  }
})();