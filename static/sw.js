/* Service worker — cache do básico + notificações push */
const CACHE = "barbearia-v3";
const ARQUIVOS = [
  "/static/css/estilo.css",
  "/static/js/site.js",
  "/static/img/icone.svg",
  "/static/img/icone-192.png",
  "/static/img/icone-512.png"
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ARQUIVOS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys().then((chaves) =>
      Promise.all(chaves.filter((chave) => chave !== CACHE).map((chave) => caches.delete(chave)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evento) => {
  const requisicao = evento.request;

  if (requisicao.method !== "GET") return;

  const url = new URL(requisicao.url);

  // Nunca guardar API, login ou painel
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin") ||
      url.pathname.startsWith("/login")) {
    return;
  }

  // Navegação: rede primeiro, cache como reserva
  if (requisicao.mode === "navigate") {
    evento.respondWith(
      fetch(requisicao)
        .then((resposta) => {
          const copia = resposta.clone();
          caches.open(CACHE).then((cache) => cache.put(requisicao, copia));
          return resposta;
        })
        .catch(() => caches.match(requisicao).then((cacheada) => cacheada || caches.match("/")))
    );
    return;
  }

  // Arquivos estáticos: cache primeiro
  if (url.pathname.startsWith("/static/")) {
    evento.respondWith(
      caches.match(requisicao).then((cacheada) => {
        if (cacheada) return cacheada;
        return fetch(requisicao).then((resposta) => {
          const copia = resposta.clone();
          caches.open(CACHE).then((cache) => cache.put(requisicao, copia));
          return resposta;
        });
      })
    );
  }
});

self.addEventListener("push", (evento) => {
  let dados = { titulo: "Novo agendamento", corpo: "Abra o painel para ver.", url: "/admin" };
  try {
    if (evento.data) dados = Object.assign(dados, evento.data.json());
  } catch (erro) { /* mantém o padrão */ }

  evento.waitUntil(
    self.registration.showNotification(dados.titulo, {
      body: dados.corpo,
      icon: "/static/img/icone-192.png",
      badge: "/static/img/icone-192.png",
      vibrate: [90, 60, 90],
      tag: "agendamento",
      renotify: true,
      data: { url: dados.url || "/admin" }
    })
  );
});

self.addEventListener("notificationclick", (evento) => {
  evento.notification.close();
  const destino = (evento.notification.data && evento.notification.data.url) || "/admin";
  evento.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((janelas) => {
      for (const janela of janelas) {
        if (janela.url.includes(destino) && "focus" in janela) return janela.focus();
      }
      return self.clients.openWindow(destino);
    })
  );
});