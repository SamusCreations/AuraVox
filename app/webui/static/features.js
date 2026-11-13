"use strict";
/* global STRINGS */
// Funciones que se suman al chat sin tocar su núcleo: memoria a largo
// plazo, resumen de chats largos, recordatorios, listas y notas,
// documentos del asistente, rutinas, exportar/importar asistentes,
// plugins, servidores MCP y escucha por nombre desde el celular.
//
// Se carga ANTES que app.js y solo define cosas: usa sus utilidades ($, t,
// esc, api, S, toast, CHAT…) recién cuando se las llama. app.js engancha
// esto en cuatro lugares:
// - featureCards(lugar) / mountFeatureCards(lugar): tarjetas de Ajustes.
// - featureChatBody(clave): lo que se suma a cada petición de /api/chat.
// - FEATURE_EVENTS[tipo](ev, {key, epoch}): eventos del NDJSON del chat.

const FEATURE_EVENTS = {};
const FEATURE_CARDS = { settings: [], assistant: [], gallery: [] };
const FEATURE_BODY = [];

function featureCards(place) {
  return (FEATURE_CARDS[place] || []).filter((c) => c.when()).map((c) => `<section class="card" id="${c.id}"></section>`).join("\n");
}

// Botones del índice del panel del asistente para las tarjetas que lo piden.
function featureJumps(place, jump) {
  return (FEATURE_CARDS[place] || []).filter((c) => c.when() && c.jump).map((c) => jump(c.id, c.jump)).join("");
}

// Tarjetas que ya traen su propio HTML (las de la galería).
function featureTiles(place) {
  return (FEATURE_CARDS[place] || []).filter((c) => c.when()).map((c) => c.html()).join("");
}

function mountFeatureCards(place) {
  (FEATURE_CARDS[place] || []).filter((c) => c.when()).forEach((c) => {
    try {
      c.render();
    } catch (e) {
      console.error(e);
    }
  });
}

function featureChatBody(key) {
  return Object.assign({}, ...FEATURE_BODY.map((fn) => fn(key) || {}));
}

// Un aviso corto dentro del chat (como "Buscando en internet…").
function chatNote(text, epoch) {
  if (typeof CHAT === "undefined" || epoch !== CHAT.epoch) return;
  CHAT.messages.push({ role: "event", text });
  renderChatLog();
}

const fmtDate = (ts) => {
  try {
    return new Date(ts * 1000).toLocaleString(S.lang, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return "";
  }
};

// ── Memoria a largo plazo (ver app/skills/memory.py) ──────────────────
// Un perfil la tiene en el servidor; el invitado, en su navegador.
const MEM = { facts: null };

async function memLoad() {
  if (isGuest()) {
    MEM.facts = guestGet("memory", []);
    return MEM.facts;
  }
  MEM.facts = (await api("GET", "/api/memory")).facts;
  return MEM.facts;
}

function memGuestSave() {
  guestSet("memory", MEM.facts || []);
}

function renderMemoryCard() {
  const box = $("#memory-card");
  if (!box) return;
  const facts = MEM.facts;
  const rows = facts == null ? `<p class="note">${esc(t("loading"))}</p>`
    : facts.length ? facts.slice().reverse().map((f) => `<div class="mem-row" data-mem="${esc(f.id)}">
        <input class="text-input" data-mem-text value="${esc(f.text)}" maxlength="300" aria-label="${esc(t("mem.fact"))}">
        <small class="mem-when">${esc(f.created ? fmtDate(f.created) : "")}</small>
        <button class="icon-btn small" type="button" data-mem-act="delete" title="${esc(t("mem.forget"))}" aria-label="${esc(t("mem.forget"))}">${ICON.close}</button>
      </div>`).join("")
      : `<p class="note">${esc(t("mem.empty"))}</p>`;
  box.innerHTML = `
    <div class="card-head"><div><h2>🧠 ${esc(t("mem.title"))}</h2><p>${esc(t("mem.sub"))}</p></div>
      ${facts?.length ? `<button class="btn btn-sm btn-ghost-danger" type="button" data-mem-act="clear">${esc(t("mem.clear"))}</button>` : ""}</div>
    <div class="mem-list">${rows}</div>
    <div class="mem-row mem-add">
      <input class="text-input" data-mem-new maxlength="300" placeholder="${esc(t("mem.add_ph"))}" aria-label="${esc(t("mem.add_ph"))}">
      <button class="btn btn-sm btn-primary" type="button" data-mem-act="add">${esc(t("mem.add"))}</button>
    </div>
    ${isGuest() ? `<p class="note">${esc(t("mem.guest_note"))}</p>` : ""}`;
  box.onclick = onMemoryClick;
  box.onchange = onMemoryChange;
  box.onkeydown = (e) => {
    if (e.key === "Enter" && e.target.matches("[data-mem-new]")) {
      e.preventDefault();
      $("[data-mem-act=add]", box).click();
    }
  };
}

async function onMemoryClick(e) {
  const b = e.target.closest("[data-mem-act]");
  if (!b) return;
  const act = b.dataset.memAct;
  try {
    if (act === "add") {
      const input = $("[data-mem-new]");
      const text = input.value.trim();
      if (!text) return void toast(t("mem.add_ph"), "warn");
      if (isGuest()) {
        MEM.facts.push({ id: `m${Math.random().toString(16).slice(2, 8).padEnd(6, "0")}`, text, created: Date.now() / 1000 });
        memGuestSave();
      } else {
        MEM.facts = (await api("POST", "/api/memory", { text })).facts;
      }
      toast(t("mem.added"));
    } else if (act === "delete") {
      const id = b.closest("[data-mem]").dataset.mem;
      if (isGuest()) {
        MEM.facts = MEM.facts.filter((f) => f.id !== id);
        memGuestSave();
      } else {
        MEM.facts = (await api("DELETE", `/api/memory/${id}`, {})).facts;
      }
    } else if (act === "clear") {
      if (!(await confirmDialog(t("mem.clear_title"), t("mem.clear_text"), t("mem.clear")))) return;
      if (isGuest()) {
        MEM.facts = [];
        memGuestSave();
      } else {
        MEM.facts = (await api("DELETE", "/api/memory", {})).facts;
      }
    }
    renderMemoryCard();
  } catch (ex) {
    toast(ex.message, "error");
  }
}

async function onMemoryChange(e) {
  if (!e.target.matches("[data-mem-text]")) return;
  const id = e.target.closest("[data-mem]").dataset.mem;
  const text = e.target.value.trim();
  try {
    if (isGuest()) {
      MEM.facts = text ? MEM.facts.map((f) => (f.id === id ? { ...f, text } : f)) : MEM.facts.filter((f) => f.id !== id);
      memGuestSave();
    } else {
      MEM.facts = (await api("PUT", `/api/memory/${id}`, { text })).facts;
    }
    toast(t(text ? "mem.saved" : "mem.forgotten"));
    if (!text) renderMemoryCard();
  } catch (ex) {
    toast(ex.message, "error");
  }
}

FEATURE_CARDS.settings.push({
  id: "memory-card",
  when: () => !!ME(),
  render: () => {
    renderMemoryCard();
    memLoad().then(renderMemoryCard).catch((ex) => toast(ex.message, "error"));
  },
});

FEATURE_BODY.push(() => {
  if (!isGuest()) return {};
  return { guest_data: { memory: guestGet("memory", []) } };
});

FEATURE_EVENTS.memory = (ev, { epoch }) => {
  if (ev.action === "add" && ev.fact) {
    if (isGuest()) {
      const list = guestGet("memory", []);
      if (!list.some((f) => f.id === ev.fact.id)) list.push(ev.fact);
      guestSet("memory", list);
    }
    chatNote(t("mem.event_add", { text: ev.fact.text }), epoch);
  } else if (ev.action === "remove") {
    if (isGuest()) guestSet("memory", guestGet("memory", []).filter((f) => f.id !== ev.id));
    chatNote(t("mem.event_remove"), epoch);
  }
  MEM.facts = null; // la tarjeta se vuelve a pedir la próxima vez
};

// ── Resumen de chats largos (ver chat_runtime.summarize) ───────────────
// El servidor resumió lo más viejo: esos mensajes salen del historial que
// se manda al modelo (en pantalla siguen) y el resumen va en las próximas
// preguntas.
FEATURE_BODY.push(() => (CHAT.summary ? { summary: CHAT.summary } : {}));
FEATURE_BODY.push(() => (CHAT.bargeTurn ? { barge: true } : {}));

FEATURE_EVENTS.summary = (ev, { epoch }) => {
  if (epoch !== CHAT.epoch) return;
  const drop = Math.max(0, Math.min(Number(ev.drop) || 0, CHAT.history.length - 1));
  CHAT.history.splice(0, drop);
  CHAT.summary = String(ev.text || "");
  chatNote(t("sum.event"), epoch);
  persistChat();
};
// ── Avisos del servidor: recordatorios, alarmas y temporizadores ───────
// (ver notify.py y app/skills/reminders.py). La página pregunta con una
// consulta larga; al llegar uno: tarjeta con "posponer" y "listo",
// notificación del sistema (celular) y, en la PC, la voz del asistente (lo
// dice solo la primera página de la PC que lo reclama; si no hay ninguna,
// lo dice el servidor por los altavoces).
const FEATURE_INITS = [];
const NOTIFY = { client: "", after: null, running: false, sw: null, rem: null };

function initFeatures() {
  FEATURE_INITS.forEach((fn) => {
    try {
      fn();
    } catch (e) {
      console.error(e);
    }
  });
}

FEATURE_INITS.push(() => {
  if (!ME() || NOTIFY.running) return;
  NOTIFY.client = `n${Math.random().toString(36).slice(2, 12)}`;
  NOTIFY.running = true;
  registerServiceWorker();
  notifyLoop();
});

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  try {
    NOTIFY.sw = await navigator.serviceWorker.register("/sw.js");
  } catch {
    NOTIFY.sw = null; // p. ej. el certificado autofirmado de la red: queda la notificación simple
  }
}

async function notifyLoop() {
  let fails = 0;
  for (;;) {
    try {
      const wait = NOTIFY.after == null ? 0 : 20;
      const q = `after=${NOTIFY.after ?? 0}&wait=${wait}&client=${NOTIFY.client}`;
      const r = await api("GET", `/api/notify?${q}`);
      // La primera vez solo se toma la posición: lo viejo ya se avisó.
      if (NOTIFY.after != null) r.events.forEach(onNotifyEvent);
      NOTIFY.after = r.last;
      fails = 0;
    } catch {
      fails += 1;
      await new Promise((ok) => setTimeout(ok, Math.min(30000, 2000 * fails)));
    }
  }
}

function onNotifyEvent(ev) {
  if (ev.type === "reminder") onReminderFired(ev);
  else if (NOTIFY_HANDLERS[ev.type]) NOTIFY_HANDLERS[ev.type](ev);
}
const NOTIFY_HANDLERS = {};

const kindIcon = (k) => ({ alarm: "⏰", timer: "⏲️", routine: "☀️" }[k] || "🔔");

async function onReminderFired(ev) {
  const r = ev.reminder;
  const title = `${kindIcon(r.kind)} ${r.label || t("rem.title")}`;
  const body = ev.missed ? t("rem.missed", { text: r.text, when: fmtDate(r.due) }) : r.kind === "routine" ? speakable(r.say, ev.lang || "es") : r.text;
  showReminderAlert(r, ev.missed);
  systemNotify(title, body, `rem-${r.id}-${ev.id}`);
  if (navigator.vibrate) navigator.vibrate(r.kind === "alarm" ? [400, 200, 400, 200, 400] : [200, 100, 200]);
  if (ev.missed) return;
  let speak = false;
  if (LOCAL_PAGE) {
    try {
      speak = (await api("POST", "/api/notify/claim", { id: ev.id })).speak;
    } catch { /* lo dirá el servidor */ }
  }
  await chime(r.kind === "alarm" ? 3 : 1);
  if (!speak) return;
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-UI-Lang": S.lang },
      body: JSON.stringify({ text: speakable(r.say || r.text, ev.lang || "es"), voice: ev.voice, speed: ev.speed || 1, lang: ev.lang || "es" }),
    });
    if (!res.ok) throw new Error(res.status);
    const url = URL.createObjectURL(await res.blob());
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    await audio.play();
  } catch {
    toast(t("rem.audio_blocked"), "warn", 6000);
  }
}

// Unos tonos con WebAudio (sin archivos de sonido).
async function chime(times = 1) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    let at = ctx.currentTime + 0.05;
    for (let i = 0; i < times; i++) {
      for (const f of [880, 1175, 1568]) {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, at);
        g.gain.exponentialRampToValueAtTime(0.25, at + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, at + 0.16);
        o.connect(g).connect(ctx.destination);
        o.start(at);
        o.stop(at + 0.18);
        at += 0.17;
      }
      at += 0.3;
    }
    await new Promise((ok) => setTimeout(ok, (at - ctx.currentTime) * 1000 + 50));
    ctx.close();
  } catch { /* sin audio */ }
}

function systemNotify(title, body, tag) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const opts = { body, tag, icon: "/static/icon.svg", badge: "/static/icon.svg", requireInteraction: true, renotify: true };
  try {
    if (NOTIFY.sw?.showNotification) return void NOTIFY.sw.showNotification(title, opts);
    new Notification(title, opts); // eslint-disable-line no-new
  } catch {
    // Android sin service worker no deja crear notificaciones así: queda la tarjeta.
  }
}

function showReminderAlert(r, missed) {
  let box = $("#rem-alerts");
  if (!box) {
    box = document.createElement("div");
    box.id = "rem-alerts";
    box.className = "rem-alerts";
    box.setAttribute("aria-live", "assertive");
    document.body.append(box);
    box.onclick = onReminderAlertClick;
  }
  const el = document.createElement("div");
  el.className = `rem-alert ${r.kind}`;
  el.dataset.rem = r.id;
  const routine = r.kind === "routine";
  el.innerHTML = `<div class="rem-alert-text"><strong>${kindIcon(r.kind)} ${esc(r.text)}</strong>
      ${routine ? `<div class="rem-alert-body">${renderMarkdown(r.say || "")}</div>` : ""}
      <small>${esc(missed ? t("rem.missed_short", { when: fmtDate(r.due) }) : (r.label || ""))}</small></div>
    <div class="rem-alert-acts">
      ${routine ? "" : `<button class="btn btn-sm" type="button" data-rem-alert="snooze">${esc(t("rem.snooze"))}</button>`}
      <button class="btn btn-sm btn-primary" type="button" data-rem-alert="ok">${esc(t("rem.ok"))}</button>
    </div>`;
  box.append(el);
}

async function onReminderAlertClick(e) {
  const b = e.target.closest("[data-rem-alert]");
  if (!b) return;
  const el = b.closest("[data-rem]");
  if (b.dataset.remAlert === "snooze") {
    try {
      await api("POST", `/api/reminders/${el.dataset.rem}/snooze`, { minutes: 10 });
      toast(t("rem.snoozed"));
    } catch (ex) {
      toast(ex.message, "error");
    }
  }
  el.remove();
  if (NOTIFY.rem) renderRemindersCard();
}

// Ajustes → Recordatorios: los pendientes (cancelar) y los últimos avisados.
async function loadReminders() {
  NOTIFY.rem = (await api("GET", "/api/reminders")).reminders;
}

function renderRemindersCard() {
  const box = $("#reminders-card");
  if (!box) return;
  const list = NOTIFY.rem;
  const pending = (list || []).filter((r) => r.state === "pending");
  const past = (list || []).filter((r) => r.state !== "pending");
  const row = (r) => `<div class="rem-row ${r.state}" data-rem="${esc(r.id)}">
      <span class="rem-icon" aria-hidden="true">${kindIcon(r.kind)}</span>
      <div class="rem-main"><strong>${esc(r.text)}</strong>
        <small>${esc(fmtDate(r.state === "pending" ? r.due : (r.fired_at || r.due)))}${r.repeat && r.repeat !== "none" ? ` · ${esc(t(`rem.repeat_${r.repeat}`))}` : ""}${r.label ? ` · ${esc(r.label)}` : ""}${r.state === "missed" ? ` · ${esc(t("rem.missed_tag"))}` : ""}</small></div>
      ${r.state === "pending" ? `<button class="icon-btn small" type="button" data-rem-act="cancel" title="${esc(t("rem.cancel"))}" aria-label="${esc(t("rem.cancel"))}">${ICON.close}</button>` : ""}
    </div>`;
  const perm = "Notification" in window ? Notification.permission : "unsupported";
  box.innerHTML = `
    <div class="card-head"><div><h2>⏰ ${esc(t("rem.card_title"))}</h2><p>${esc(t("rem.card_sub"))}</p></div></div>
    ${list == null ? `<p class="note">${esc(t("loading"))}</p>` : pending.length ? `<div class="rem-list">${pending.map(row).join("")}</div>` : `<p class="note">${esc(t("rem.none"))}</p>`}
    ${past.length ? `<details class="rem-past"><summary>${esc(t("rem.past"))}</summary><div class="rem-list">${past.map(row).join("")}</div></details>` : ""}
    <div class="rem-perm">
      ${perm === "granted" ? `<span class="badge ok">${esc(t("rem.perm_on"))}</span>`
        : perm === "unsupported" ? `<small class="note">${esc(t("rem.perm_unsupported"))}</small>`
        : `<button class="btn btn-sm" type="button" data-rem-act="perm">${esc(t("rem.perm_ask"))}</button>`}
      <small class="note">${esc(t(window.isSecureContext ? "rem.perm_note" : "rem.perm_insecure"))}</small>
    </div>`;
  box.onclick = async (e) => {
    const b = e.target.closest("[data-rem-act]");
    if (!b) return;
    try {
      if (b.dataset.remAct === "perm") {
        const res = await Notification.requestPermission();
        if (res === "granted") systemNotify("AuraVox", t("rem.perm_test"), "auravox-test");
      } else if (b.dataset.remAct === "cancel") {
        NOTIFY.rem = (await api("DELETE", `/api/reminders/${b.closest("[data-rem]").dataset.rem}`, {})).reminders;
      }
    } catch (ex) {
      toast(ex.message, "error");
    }
    renderRemindersCard();
  };
}

FEATURE_CARDS.settings.push({
  id: "reminders-card",
  when: () => !!ME(),
  render: () => {
    renderRemindersCard();
    loadReminders().then(renderRemindersCard).catch((ex) => toast(ex.message, "error"));
  },
});

FEATURE_EVENTS.reminder = (ev, { epoch }) => {
  if (ev.action === "add" && ev.reminder) {
    const r = ev.reminder;
    chatNote(t("rem.event_add", { icon: kindIcon(r.kind), when: fmtDate(r.due), text: r.text }), epoch);
    // Para que el aviso llegue también como notificación del sistema.
    if ("Notification" in window && Notification.permission === "default" && !NOTIFY.asked) {
      NOTIFY.asked = true;
      Notification.requestPermission().catch(() => {});
    }
  } else if (ev.action === "remove") {
    chatNote(t("rem.event_remove"), epoch);
  }
  NOTIFY.rem = null;
};
// ── Listas y notas (ver app/skills/lists.py) ───────────────────────────
// Vista "Listas": las propias y las de la casa. También se manejan
// hablándole a cualquier asistente ("agrega leche a la lista de compras").
const FEATURE_VIEWS = {};
const LISTS = { data: null };

FEATURE_VIEWS.lists = {
  title: () => t("nav.lists"),
  render: renderListsView,
};

FEATURE_INITS.push(() => {
  const b = $("#btn-lists");
  if (b) b.onclick = () => select({ kind: "lists" });
});

NOTIFY_HANDLERS.lists = () => {
  if (S.view?.kind === "lists" && !$("#main [data-li-edit]:focus")) loadLists();
};

async function loadLists() {
  try {
    LISTS.data = await api("GET", "/api/lists");
  } catch (ex) {
    toast(ex.message, "error");
  }
  if (S.view?.kind === "lists") drawLists();
}

function renderListsView() {
  const main = $("#main");
  main.oninput = main.onchange = main.onkeydown = null;
  main.innerHTML = `<div class="editor lists-view">
    <header class="editor-head">
      <div class="avatar avatar-lg">📝</div>
      <div class="head-text"><h1>${esc(t("lists.title"))}</h1><p>${esc(t("lists.sub"))}</p></div>
    </header>
    <div id="lists-body" class="editor-body"><p class="note">${esc(t("loading"))}</p></div>
  </div>`;
  main.onclick = onListsClick;
  main.onkeydown = onListsKey;
  main.onchange = onListsChange;
  if (LISTS.data) drawLists();
  loadLists();
}

function listCard(scope, lst) {
  const notes = lst.kind === "notes";
  const items = lst.items.map((i) => `<li class="li-item ${i.done ? "done" : ""}" data-item="${esc(i.id)}">
      ${notes ? "" : `<input type="checkbox" data-li-act="toggle" ${i.done ? "checked" : ""} aria-label="${esc(t("lists.check"))}">`}
      <span class="li-text" data-li-edit contenteditable="plaintext-only" spellcheck="true">${esc(i.text)}</span>
      <button class="icon-btn small" type="button" data-li-act="remove" aria-label="${esc(t("lists.remove"))}">${ICON.close}</button>
    </li>`).join("");
  const done = lst.items.filter((i) => i.done).length;
  return `<section class="card li-card" data-scope="${scope}" data-list="${esc(lst.id)}">
    <div class="li-head">
      <h2 class="li-name" data-li-rename contenteditable="plaintext-only">${esc(lst.name)}</h2>
      <span class="badge">${notes ? esc(t("lists.kind_notes")) : `${lst.items.length - done}/${lst.items.length}`}</span>
    </div>
    <ul class="li-items">${items || `<li class="note">${esc(t(notes ? "lists.no_notes" : "lists.no_items"))}</li>`}</ul>
    <div class="li-add"><input class="text-input" data-li-new placeholder="${esc(t(notes ? "lists.add_note" : "lists.add_item"))}" maxlength="1000"></div>
    <div class="li-foot">
      ${done ? `<button class="btn btn-sm" type="button" data-li-act="clear_done">${esc(t("lists.clear_done"))}</button>` : ""}
      ${scope === "home" && isGuest() ? "" : `<button class="btn btn-sm btn-ghost-danger" type="button" data-li-act="delete">${esc(t("lists.delete"))}</button>`}
    </div>
  </section>`;
}

function drawLists() {
  const box = $("#lists-body");
  if (!box || !LISTS.data) return;
  const section = (scope, lists) => `<section class="card li-section" data-scope="${scope}">
      <div class="li-section-head"><h2>${esc(t(`lists.${scope}`))}</h2><p>${esc(t(`lists.${scope}_sub`))}</p></div>
      <div class="li-grid">${lists.map((l) => listCard(scope, l)).join("") || `<p class="note">${esc(t("lists.none"))}</p>`}</div>
      <div class="li-create">
        <input class="text-input" data-li-create placeholder="${esc(t("lists.new_ph"))}" maxlength="60">
        <select class="text-input" data-li-kind aria-label="${esc(t("lists.kind"))}">
          <option value="list">${esc(t("lists.kind_list"))}</option><option value="notes">${esc(t("lists.kind_notes"))}</option></select>
        <button class="btn btn-sm btn-primary" type="button" data-li-act="create">${esc(t("lists.create"))}</button>
      </div>
    </section>`;
  box.innerHTML = (LISTS.data.personal ? section("personal", LISTS.data.personal) : "") + section("home", LISTS.data.home);
}

async function listOp(scope, op) {
  try {
    LISTS.data = await api("POST", `/api/lists/${scope}`, op);
  } catch (ex) {
    toast(ex.message, "error");
  }
  drawLists();
}

async function onListsClick(e) {
  const b = e.target.closest("[data-li-act]");
  if (!b) return;
  const act = b.dataset.liAct;
  const sec = b.closest("[data-scope]");
  const scope = sec.dataset.scope;
  const card = b.closest("[data-list]");
  if (act === "create") {
    const input = $("[data-li-create]", sec);
    const text = input.value.trim();
    if (!text) return void input.focus();
    return listOp(scope, { op: "create", text, kind: $("[data-li-kind]", sec).value });
  }
  if (act === "delete") {
    const name = $(".li-name", card).textContent.trim();
    if (!(await confirmDialog(t("lists.delete_title", { name }), t("lists.delete_text"), t("lists.delete")))) return;
    return listOp(scope, { op: "delete", list: card.dataset.list });
  }
  if (act === "clear_done") return listOp(scope, { op: "clear_done", list: card.dataset.list });
  const item = b.closest("[data-item]");
  if (item && (act === "toggle" || act === "remove")) return listOp(scope, { op: act, list: card.dataset.list, item: item.dataset.item });
}

function onListsKey(e) {
  if (e.key !== "Enter") return;
  if (e.target.matches("[data-li-new]")) {
    e.preventDefault();
    const text = e.target.value.trim();
    if (!text) return;
    const card = e.target.closest("[data-list]");
    listOp(card.closest("[data-scope]").dataset.scope, { op: "add", list: card.dataset.list, text })
      .then(() => $(`[data-list="${card.dataset.list}"] [data-li-new]`)?.focus());
  } else if (e.target.matches("[data-li-create]")) {
    e.preventDefault();
    $("[data-li-act=create]", e.target.closest("[data-scope]")).click();
  } else if (e.target.matches("[data-li-edit], [data-li-rename]") && !e.shiftKey) {
    e.preventDefault();
    e.target.blur();
  }
}

// Editar el texto de un elemento o el nombre de la lista: al salir del campo.
function onListsChange() { /* los contenteditable avisan con focusout (abajo) */ }
document.addEventListener("focusout", (e) => {
  if (S?.view?.kind !== "lists" || !e.target.matches?.("[data-li-edit], [data-li-rename]")) return;
  const card = e.target.closest("[data-list]");
  const scope = card.closest("[data-scope]").dataset.scope;
  const lst = LISTS.data?.[scope]?.find((l) => l.id === card.dataset.list);
  const text = e.target.textContent.trim();
  if (e.target.matches("[data-li-rename]")) {
    if (lst && text && text !== lst.name) listOp(scope, { op: "rename", list: lst.id, text });
    else if (lst) e.target.textContent = lst.name;
    return;
  }
  const id = e.target.closest("[data-item]").dataset.item;
  const item = lst?.items.find((i) => i.id === id);
  if (item && text !== item.text) listOp(scope, { op: "edit", list: lst.id, item: id, text });
});

FEATURE_EVENTS.lists = (ev, { epoch }) => {
  if (ev.added?.length) chatNote(t("lists.event_add", { n: ev.added.length, list: ev.list }), epoch);
  else if (ev.changed) chatNote(t("lists.event_change"), epoch);
};
// ── Documentos del asistente (ver app/skills/knowledge.py) ─────────────
// Panel del asistente → "Documentos": su carpeta de conocimiento. Los PDF
// se leen aquí con pdf.js (el mismo de los adjuntos); el resto lo lee el
// servidor (app/core/attachments.py).
const KNOW = { name: null, st: null, busy: 0, timer: null };

FEATURE_CARDS.assistant.push({
  id: "sec-docs",
  jump: "sec.docs",
  when: () => S.view?.kind === "assistant",
  render: () => {
    KNOW.name = S.view.name;
    KNOW.st = null;
    renderDocsCard();
    loadDocs();
  },
});

async function loadDocs() {
  const name = KNOW.name;
  try {
    const st = await api("GET", `/api/knowledge/${name}`);
    if (KNOW.name !== name) return;
    KNOW.st = st;
  } catch (ex) {
    KNOW.st = { files: [], error: ex.message };
  }
  renderDocsCard();
  clearTimeout(KNOW.timer);
  if (KNOW.st?.indexing) KNOW.timer = setTimeout(loadDocs, 3000);
}

function renderDocsCard() {
  const box = $("#sec-docs");
  if (!box) return;
  const st = KNOW.st;
  const editable = st?.editable;
  const rows = (st?.files || []).map((f) => `<div class="doc-row" data-doc="${esc(f.id)}">
      <span class="doc-icon">${ICON.file}</span>
      <div class="doc-main"><strong>${esc(f.name)}</strong>
        <small>${esc([f.format, t("docs.chars", { n: Number(f.chars || 0).toLocaleString(S.lang) }), t("docs.parts", { n: f.chunks }),
          st.embeddings ? (f.embedded >= f.chunks ? t("docs.indexed") : t("docs.indexing_n", { done: f.embedded, n: f.chunks })) : ""].filter(Boolean).join(" · "))}</small></div>
      ${editable ? `<button class="icon-btn small" type="button" data-doc-act="delete" aria-label="${esc(t("docs.delete"))}" title="${esc(t("docs.delete"))}">${ICON.close}</button>` : ""}
    </div>`).join("");
  const pending = (st?.files || []).some((f) => f.embedded < f.chunks);
  box.innerHTML = `
    <div class="card-head"><div><h2>📚 ${esc(t("docs.title"))}</h2><p>${esc(t("docs.sub"))}</p></div></div>
    ${st == null ? `<p class="note">${esc(t("loading"))}</p>` : st.error ? `<p class="note">${esc(st.error)}</p>`
      : rows ? `<div class="doc-list">${rows}</div>` : `<p class="note">${esc(t("docs.none"))}</p>`}
    ${editable ? `<div class="doc-actions">
      <label class="btn btn-sm btn-primary ${KNOW.busy ? "disabled" : ""}">${ICON.clip} ${esc(t(KNOW.busy ? "docs.uploading" : "docs.add"))}
        <input type="file" multiple hidden data-doc-file accept="${esc(docsAccept())}" ${KNOW.busy ? "disabled" : ""}></label>
      ${st?.embeddings && pending && !st.indexing ? `<button class="btn btn-sm" type="button" data-doc-act="index">${esc(t("docs.index"))}</button>` : ""}
    </div>` : ""}
    <p class="note">${esc(t(st?.embeddings ? "docs.mode_emb" : "docs.mode_words"))}
      ${st && !st.embeddings && isAdmin() ? ` <button class="btn btn-sm" type="button" data-doc-act="pull">${esc(t("docs.pull"))}</button>` : ""}</p>`;
  box.onclick = onDocsClick;
  box.onchange = (e) => {
    if (e.target.matches("[data-doc-file]")) uploadDocs([...e.target.files]);
  };
}

const docsAccept = () => [".pdf", ...DOC_EXT.filter((x) => x !== "pdf").map((x) => `.${x}`)].join(",");

async function uploadDocs(files) {
  const name = KNOW.name;
  KNOW.busy = files.length;
  renderDocsCard();
  for (const file of files) {
    try {
      if (extOf(file.name) === "pdf") {
        const text = await pdfFullText(file);
        await api("POST", `/api/knowledge/${name}`, { name: file.name, text, format: "PDF" });
      } else {
        const res = await fetch(`/api/knowledge/${name}?name=${encodeURIComponent(file.name)}`, {
          method: "POST", headers: { "Content-Type": "application/octet-stream", "X-UI-Lang": S.lang }, body: file,
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) throw new Error(data?.error || `HTTP ${res.status}`);
      }
      toast(t("docs.added", { name: file.name }));
    } catch (ex) {
      toast(`${file.name}: ${ex.message}`, "error", 7000);
    }
    KNOW.busy -= 1;
  }
  KNOW.busy = 0;
  if (KNOW.name === name) loadDocs();
}

// Todo el texto de un PDF (los adjuntos del chat se recortan; esto no).
async function pdfFullText(file) {
  const lib = await loadPdfJs();
  const pdf = await lib.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  const pages = [];
  for (let n = 1; n <= pdf.numPages; n++) {
    const content = await (await pdf.getPage(n)).getTextContent();
    let text = "";
    for (const item of content.items) text += item.str + (item.hasEOL ? "\n" : item.str ? " " : "");
    pages.push(`--- ${t("att.page", { n })} ---\n${text.replace(/[ \t]+\n/g, "\n").trim()}`);
  }
  const text = pages.join("\n\n");
  if (text.replace(/---[^\n]*---/g, "").trim().length < 40 * pdf.numPages) throw new Error(t("docs.scanned"));
  return text;
}

async function onDocsClick(e) {
  const b = e.target.closest("[data-doc-act]");
  if (!b) return;
  const act = b.dataset.docAct;
  try {
    if (act === "delete") {
      const row = b.closest("[data-doc]");
      const fname = $("strong", row).textContent;
      if (!(await confirmDialog(t("docs.delete_title", { name: fname }), t("docs.delete_text"), t("docs.delete")))) return;
      KNOW.st = await api("DELETE", `/api/knowledge/${KNOW.name}/${row.dataset.doc}`, {});
    } else if (act === "index") {
      KNOW.st = await api("POST", `/api/knowledge/${KNOW.name}/index`, {});
      KNOW.timer = setTimeout(loadDocs, 3000);
    } else if (act === "pull") {
      await startPull("nomic-embed-text");
      toast(t("docs.pulling"), "ok", 6000);
    }
  } catch (ex) {
    toast(ex.message, "error");
  }
  renderDocsCard();
}

FEATURE_EVENTS.sources = (ev, { epoch }) => {
  if (ev.sources?.length) chatNote(t("docs.event", { names: ev.sources.join(", ") }), epoch);
};
// ── Rutinas (ver app/skills/routines.py) ───────────────────────────────
// Ajustes → Rutinas: "Buenos días" = clima + recordatorios + listas +
// titulares… Cada una con cuándo usarla, qué junta y, si se quiere, una
// hora a la que el asistente la dice sola.
const ROUT = { st: null, dirty: false };
const ROUT_DAYS = [0, 1, 2, 3, 4, 5, 6];

FEATURE_CARDS.settings.push({
  id: "routines-card",
  when: () => !!ME(),
  render: () => {
    renderRoutinesCard();
    api("GET", "/api/routines").then((st) => { ROUT.st = st; ROUT.dirty = false; renderRoutinesCard(); })
      .catch((ex) => toast(ex.message, "error"));
  },
});

function dayName(d) {
  // 0 = lunes (como Python: datetime.weekday()).
  const ref = new Date(2024, 0, 1 + d); // 1 de enero de 2024 fue lunes
  return ref.toLocaleDateString(S.lang, { weekday: "short" });
}

function routineRow(r, i, editable, blocks) {
  const dis = editable ? "" : "disabled";
  const own = (S.data.assistants || []);
  return `<div class="rt-item card-sub" data-rt="${i}">
    <div class="grid-2">
      <div class="field"><label>${esc(t("rt.name"))}</label><input class="text-input" data-rt-f="name" value="${esc(r.name)}" maxlength="60" ${dis}></div>
      <div class="field"><label>${esc(t("rt.when"))}</label><input class="text-input" data-rt-f="when" value="${esc(r.when)}" maxlength="300" placeholder="${esc(t("rt.when_ph"))}" ${dis}></div>
    </div>
    <div class="rt-blocks">${blocks.map((b) => `<label class="rt-chip"><input type="checkbox" data-rt-block="${b}" ${r.blocks.includes(b) ? "checked" : ""} ${dis}> ${esc(t(`rt.b_${b}`))}</label>`).join("")}</div>
    <div class="grid-2">
      <div class="field"><label>${esc(t("rt.news_topic"))}</label><input class="text-input" data-rt-f="news_topic" value="${esc(r.news_topic)}" maxlength="120" placeholder="${esc(t("rt.news_ph"))}" ${dis}></div>
      <div class="field"><label>${esc(t("rt.extra"))}</label><input class="text-input" data-rt-f="extra" value="${esc(r.extra)}" maxlength="600" placeholder="${esc(t("rt.extra_ph"))}" ${dis}></div>
    </div>
    ${editable ? `<div class="rt-schedule">
      <label class="rt-time">${esc(t("rt.time"))} <input type="time" class="text-input" data-rt-f="time" value="${esc(r.time)}"></label>
      <span class="rt-days">${ROUT_DAYS.map((d) => `<label class="rt-chip small"><input type="checkbox" data-rt-day="${d}" ${(!r.days.length || r.days.includes(d)) ? "checked" : ""}> ${esc(dayName(d))}</label>`).join("")}</span>
      <label>${esc(t("rt.assistant"))} <select class="text-input" data-rt-f="assistant">
        <option value="">${esc(t("rt.assistant_any"))}</option>
        ${own.map((a) => `<option value="${esc(a.name)}" ${a.name === r.assistant ? "selected" : ""}>${esc(displayName(a))}</option>`).join("")}</select></label>
      <button class="btn btn-sm btn-ghost-danger" type="button" data-rt-act="delete">${esc(t("rt.delete"))}</button>
    </div>` : ""}
  </div>`;
}

function renderRoutinesCard() {
  const box = $("#routines-card");
  if (!box) return;
  const st = ROUT.st;
  box.innerHTML = `
    <div class="card-head"><div><h2>☀️ ${esc(t("rt.title"))}</h2><p>${esc(t("rt.sub"))}</p></div></div>
    ${st == null ? `<p class="note">${esc(t("loading"))}</p>` : `<div class="rt-list">${st.routines.map((r, i) => routineRow(r, i, st.editable, st.blocks)).join("")}</div>
    ${st.editable ? `<div class="rt-actions">
      <button class="btn btn-sm" type="button" data-rt-act="add">${esc(t("rt.add"))}</button>
      <button class="btn btn-sm btn-primary" type="button" data-rt-act="save" ${ROUT.dirty ? "" : "disabled"}>${esc(t("rt.save"))}</button>
    </div>` : `<p class="note">${esc(t("rt.guest"))}</p>`}`}`;
  box.oninput = box.onchange = (e) => {
    if (!ROUT.st?.editable) return;
    const row = e.target.closest("[data-rt]");
    if (!row) return;
    const r = ROUT.st.routines[Number(row.dataset.rt)];
    if (e.target.dataset.rtF) r[e.target.dataset.rtF] = e.target.value;
    if (e.target.dataset.rtBlock) r.blocks = $$("[data-rt-block]", row).filter((x) => x.checked).map((x) => x.dataset.rtBlock);
    if (e.target.dataset.rtDay != null) r.days = $$("[data-rt-day]", row).filter((x) => x.checked).map((x) => Number(x.dataset.rtDay));
    ROUT.dirty = true;
    const save = $("[data-rt-act=save]", box);
    if (save) save.disabled = false;
  };
  box.onclick = async (e) => {
    const b = e.target.closest("[data-rt-act]");
    if (!b) return;
    const act = b.dataset.rtAct;
    if (act === "add") {
      ROUT.st.routines.push({ name: t("rt.new_name", { n: ROUT.st.routines.length + 1 }), when: "", blocks: ["weather"], news_topic: "", extra: "", time: "", days: [], assistant: "" });
      ROUT.dirty = true;
    } else if (act === "delete") {
      ROUT.st.routines.splice(Number(b.closest("[data-rt]").dataset.rt), 1);
      ROUT.dirty = true;
    } else if (act === "save") {
      try {
        ROUT.st = await api("PUT", "/api/routines", { routines: ROUT.st.routines });
        ROUT.dirty = false;
        toast(t("rt.saved"));
      } catch (ex) {
        return toast(ex.message, "error");
      }
    }
    renderRoutinesCard();
  };
}

FEATURE_EVENTS.routine = (ev, { epoch }) => chatNote(t("rt.event", { name: ev.name }), epoch);
// ── Exportar / importar asistentes (.auravox, ver assistant_io.py) ─────
FEATURE_CARDS.assistant.push({
  id: "sec-export",
  jump: "sec.export",
  when: () => S.view?.kind === "assistant",
  render: () => {
    const box = $("#sec-export");
    if (!box) return;
    box.innerHTML = `
      <div class="card-head"><div><h2>📦 ${esc(t("io.title"))}</h2><p>${esc(t("io.sub"))}</p></div></div>
      <label class="rt-chip"><input type="checkbox" id="io-docs"> ${esc(t("io.with_docs"))}</label>
      <div class="doc-actions" style="margin-top:10px"><button class="btn btn-sm btn-primary" type="button" id="io-export">${esc(t("io.export"))}</button></div>
      <p class="note">${esc(t("io.note"))}</p>`;
    $("#io-export").onclick = () => {
      const docs = $("#io-docs").checked ? "?docs=1" : "";
      const a = Object.assign(document.createElement("a"), { href: `/api/assistants/${S.view.name}/export${docs}`, download: "" });
      document.body.append(a);
      a.click();
      a.remove();
    };
  },
});

FEATURE_CARDS.gallery.push({
  id: "g-import",
  when: () => !isGuest(),
  html: () => `<label class="g-card g-new g-import" id="g-import">
      <span class="g-plus">📦</span>
      <h2>${esc(t("io.import"))}</h2>
      <p>${esc(t("io.import_sub"))}</p>
      <input type="file" accept=".auravox,application/json" hidden id="io-file">
    </label>`,
  render: () => {
    const input = $("#io-file");
    if (input) input.onchange = () => importAssistant(input.files[0]);
  },
});

async function importAssistant(file) {
  if (!file) return;
  let payload;
  try {
    payload = JSON.parse(await file.text());
  } catch {
    return toast(t("io.bad_file"), "error");
  }
  try {
    const r = await api("POST", "/api/assistants/import", { file: payload });
    setData(r.state);
    toast([t("io.imported", { name: displayName(S.data.assistants.find((a) => a.name === r.name) || { name: r.name }) }), ...r.notes].join(" "), "ok", 8000);
    if (r.model && S.models.online && !modelInstalled(r.model)) toast(t("io.model_missing", { m: r.model }), "warn", 9000);
    select({ kind: "assistant", name: r.name }, { force: true });
  } catch (ex) {
    toast(ex.message, "error", 7000);
  }
}
// ── Plugins (ver app/core/plugins.py y plugins/README.md) ─────────────
// Ajustes → Plugins (administrador): activar, rol mínimo y recargar.
const PLUG = { st: null };

FEATURE_CARDS.settings.push({
  id: "plugins-card",
  when: () => isAdmin(),
  render: () => {
    renderPluginsCard();
    api("GET", "/api/plugins").then((st) => { PLUG.st = st; renderPluginsCard(); }).catch((ex) => toast(ex.message, "error"));
  },
});

function renderPluginsCard() {
  const box = $("#plugins-card");
  if (!box) return;
  const st = PLUG.st;
  const roleSel = (p) => `<select class="text-input" data-pl-role aria-label="${esc(t("pl.min_role"))}">${["guest", "user", "admin"].map((r) =>
    `<option value="${r}" ${r === p.min_role ? "selected" : ""}>${esc(t(`pl.role_${r}`))}</option>`).join("")}</select>`;
  const rows = (st?.plugins || []).map((p) => `<div class="pl-row ${p.enabled ? "" : "off"}" data-pl="${esc(p.id)}">
      <label class="pl-switch"><input type="checkbox" data-pl-on ${p.enabled ? "checked" : ""} aria-label="${esc(t("pl.enabled"))}"><span></span></label>
      <div class="pl-main"><span class="pl-name"><strong>${esc(p.name)}</strong> ${p.builtin ? `<span class="badge">${esc(t("pl.builtin"))}</span>` : ""}</span>
        <small>${esc(p.description)}</small>
        <small class="pl-tools">${p.tools.map((x) => `<code>${esc(x)}</code>`).join(" ")}${p.author ? ` · ${esc(p.author)}` : ""}${p.version ? ` · v${esc(p.version)}` : ""}</small>
        ${p.error ? `<small class="err">${esc(p.error)}</small>` : ""}
        ${p.settings_schema?.length ? pluginSettingsForm(p) : ""}</div>
      ${roleSel(p)}
      ${p.id === "comfyui" && p.enabled && !p.error ? `<details class="pl-settings cu-wrap" ${CU.panelOpen ? "open" : ""}><summary>${esc(t("cu.panel"))}</summary><div class="cu-panel" data-cu-panel></div></details>` : ""}
    </div>`).join("");
  box.innerHTML = `
    <div class="card-head"><div><h2>🧩 ${esc(t("pl.title"))}</h2><p>${esc(t("pl.sub"))}</p></div>
      <button class="btn btn-sm" type="button" data-pl-act="reload">${esc(t("pl.reload"))}</button></div>
    ${st == null ? `<p class="note">${esc(t("loading"))}</p>` : `<div class="pl-list">${rows}</div>
    <p class="note">${esc(t("pl.how", { folder: st.folder }))}</p>`}`;
  const cuWrap = $(".cu-wrap", box);
  if (cuWrap) {
    cuWrap.ontoggle = () => { CU.panelOpen = cuWrap.open; if (cuWrap.open) cuMount(); };
    if (cuWrap.open) cuMount();
  }
  box.onchange = async (e) => {
    const row = e.target.closest("[data-pl]");
    if (!row || e.target.closest(".pl-settings")) return;
    const body = e.target.matches("[data-pl-on]") ? { enabled: e.target.checked } : { min_role: e.target.value };
    if (body.enabled && !PLUG.st.plugins.find((p) => p.id === row.dataset.pl).builtin
      && !(await confirmDialog(t("pl.trust_title"), t("pl.trust_text"), t("pl.trust_ok"), false))) {
      e.target.checked = false;
      return;
    }
    try {
      PLUG.st = await api("PUT", `/api/plugins/${row.dataset.pl}`, body);
    } catch (ex) {
      toast(ex.message, "error");
    }
    renderPluginsCard();
  };
  box.onclick = async (e) => {
    const sb = e.target.closest("[data-pl-set]");
    if (sb) return pluginSettingsAction(sb);
    if (!e.target.closest("[data-pl-act=reload]")) return;
    try {
      PLUG.st = await api("POST", "/api/plugins/reload", {});
      toast(t("pl.reloaded"));
    } catch (ex) {
      toast(ex.message, "error");
    }
    renderPluginsCard();
  };
}
// ── Servidores MCP (ver app/core/mcp_client.py) ───────────────────────
// Ajustes → Servidores MCP (administrador): conectar servidores MCP como
// herramientas de los asistentes.
const MCP = { st: null, adding: false };

FEATURE_CARDS.settings.push({
  id: "mcp-card",
  when: () => isAdmin(),
  render: () => {
    renderMcpCard();
    loadMcp();
  },
});

async function loadMcp() {
  try {
    MCP.st = await api("GET", "/api/mcp");
  } catch (ex) {
    toast(ex.message, "error");
  }
  renderMcpCard();
  clearTimeout(MCP.timer);
  if (MCP.st?.servers.some((s) => s.status === "starting") && $("#mcp-card")) MCP.timer = setTimeout(loadMcp, 2500);
}

function renderMcpCard() {
  const box = $("#mcp-card");
  if (!box) return;
  const st = MCP.st;
  const roleSel = (s) => `<select class="text-input" data-mcp-role aria-label="${esc(t("pl.min_role"))}">${["guest", "user", "admin"].map((r) =>
    `<option value="${r}" ${r === s.min_role ? "selected" : ""}>${esc(t(`pl.role_${r}`))}</option>`).join("")}</select>`;
  const badge = (s) => ({ ready: `<span class="badge ok">${esc(t("mcp.ready", { n: s.tools.length }))}</span>`,
    starting: `<span class="badge">${esc(t("mcp.starting"))}</span>`, stopped: `<span class="badge">${esc(t("mcp.stopped"))}</span>` }[s.status]
    || `<span class="badge warn">${esc(t("mcp.error"))}</span>`);
  const rows = (st?.servers || []).map((s) => `<div class="pl-row ${s.enabled ? "" : "off"}" data-mcp="${esc(s.id)}">
      <label class="pl-switch"><input type="checkbox" data-mcp-on ${s.enabled ? "checked" : ""} aria-label="${esc(t("pl.enabled"))}"><span></span></label>
      <div class="pl-main"><span class="pl-name"><strong>${esc(s.name)}</strong> ${badge(s)}</span>
        <small><code>${esc(s.transport === "http" ? s.url : [s.command, ...(s.args || [])].join(" "))}</code>${s.server ? ` · ${esc(s.server)}` : ""}${s.env_keys.length ? ` · env: ${esc(s.env_keys.join(", "))}` : ""}</small>
        ${s.tools.length ? `<small class="pl-tools">${s.tools.slice(0, 30).map((x) => `<code>${esc(x)}</code>`).join(" ")}${s.tools.length > 30 ? " …" : ""}</small>` : ""}
        ${s.error ? `<small class="err">${esc(s.error)}</small>` : ""}
        <span class="mcp-acts"><button class="btn btn-sm" type="button" data-mcp-act="restart">${esc(t("mcp.restart"))}</button>
          <button class="btn btn-sm btn-ghost-danger" type="button" data-mcp-act="delete">${esc(t("mcp.delete"))}</button></span></div>
      ${roleSel(s)}
    </div>`).join("");
  box.innerHTML = `
    <div class="card-head"><div><h2>🔌 ${esc(t("mcp.title"))}</h2><p>${esc(t("mcp.sub"))}</p></div></div>
    ${st == null ? `<p class="note">${esc(t("loading"))}</p>` : rows ? `<div class="pl-list">${rows}</div>` : `<p class="note">${esc(t("mcp.none"))}</p>`}
    <details class="mcp-add" ${MCP.adding ? "open" : ""}><summary>${esc(t("mcp.add"))}</summary>
      <div class="grid-2">
        <div class="field"><label>${esc(t("mcp.name"))}</label><input class="text-input" id="mcp-name" maxlength="40" placeholder="${esc(t("mcp.name_ph"))}"></div>
        <div class="field"><label>${esc(t("mcp.transport"))}</label><select class="text-input" id="mcp-transport">
          <option value="stdio">${esc(t("mcp.stdio"))}</option><option value="http">${esc(t("mcp.http"))}</option></select></div>
      </div>
      <div class="field" id="mcp-cmd-wrap"><label>${esc(t("mcp.command"))}</label><input class="text-input" id="mcp-command" placeholder="${esc(t("mcp.command_ph"))}"></div>
      <div class="field" id="mcp-url-wrap" hidden><label>URL</label><input class="text-input" id="mcp-url" placeholder="https://example.com/mcp"></div>
      <div class="field"><label>${esc(t("mcp.env"))}</label><textarea class="text-input" id="mcp-env" rows="2" placeholder="GITHUB_TOKEN=..."></textarea><small>${esc(t("mcp.env_help"))}</small></div>
      <div class="rt-actions"><button class="btn btn-sm btn-primary" type="button" data-mcp-act="add">${esc(t("mcp.connect"))}</button></div>
    </details>
    <p class="note">${esc(t("mcp.note"))}</p>`;
  $("#mcp-transport").onchange = (e) => {
    $("#mcp-cmd-wrap").hidden = e.target.value !== "stdio";
    $("#mcp-url-wrap").hidden = e.target.value === "stdio";
    $("label", $("#mcp-env").closest(".field")).textContent = t(e.target.value === "stdio" ? "mcp.env" : "mcp.headers");
  };
  $(".mcp-add", box).ontoggle = (e) => { MCP.adding = e.target.open; };
  box.onchange = async (e) => {
    const row = e.target.closest("[data-mcp]");
    if (!row) return;
    const body = e.target.matches("[data-mcp-on]") ? { enabled: e.target.checked } : e.target.matches("[data-mcp-role]") ? { min_role: e.target.value } : null;
    if (!body) return;
    try {
      MCP.st = await api("PUT", `/api/mcp/${row.dataset.mcp}`, body);
    } catch (ex) {
      toast(ex.message, "error");
    }
    loadMcp();
  };
  box.onclick = async (e) => {
    const b = e.target.closest("[data-mcp-act]");
    if (!b) return;
    const act = b.dataset.mcpAct;
    const id = b.closest("[data-mcp]")?.dataset.mcp;
    try {
      if (act === "add") {
        const transport = $("#mcp-transport").value;
        const pairs = Object.fromEntries($("#mcp-env").value.split(/\n/).map((l) => l.trim()).filter((l) => l.includes("=") || l.includes(":"))
          .map((l) => { const i = transport === "stdio" ? l.indexOf("=") : l.search(/[:=]/); return [l.slice(0, i).trim(), l.slice(i + 1).trim()]; }));
        const body = { name: $("#mcp-name").value, transport, min_role: "admin" };
        if (transport === "stdio") Object.assign(body, { command: $("#mcp-command").value, env: pairs });
        else Object.assign(body, { url: $("#mcp-url").value, headers: pairs });
        if (!(await confirmDialog(t("mcp.trust_title"), t("mcp.trust_text"), t("mcp.connect"), false))) return;
        MCP.st = await api("POST", "/api/mcp", body);
        MCP.adding = false;
        toast(t("mcp.added"));
      } else if (act === "restart") {
        MCP.st = await api("POST", `/api/mcp/${id}/restart`, {});
      } else if (act === "delete") {
        if (!(await confirmDialog(t("mcp.delete_title"), t("mcp.delete_text"), t("mcp.delete")))) return;
        MCP.st = await api("DELETE", `/api/mcp/${id}`, {});
      }
    } catch (ex) {
      return toast(ex.message, "error", 7000);
    }
    loadMcp();
  };
}
// ── Escucha por nombre desde este dispositivo (celular, otra PC…) ──────
// La escucha manos libres de siempre usa el micrófono de la PC donde corre
// AuraVox. Aquí la usa el del navegador: VAD por energía (como la
// conversación por voz), cada frase va a /api/wake/listen (Whisper en el
// servidor) y si empieza con el nombre de un asistente se abre su
// conversación por voz, igual que una llamada desde la PC (hfHandle).
const BW = { on: false, stream: null, ctx: null, analyser: null, buf: null, lock: null, state: "off", loop: false };

FEATURE_INITS.push(() => {
  if (LOCAL_PAGE && S.data.voice_listener) return; // en la PC escucha el servidor
  const b = $("#btn-mic");
  if (!b) return;
  b.hidden = false;
  const menu = $("[data-top=mic]");
  if (menu) menu.hidden = false;
  b.onclick = () => (BW.on ? bwStop(true) : bwStart());
  bwRender();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && BW.on) bwWakeLock();
  });
  let wanted = false;
  try { wanted = localStorage.getItem("bw-on") === "1"; } catch { /* sin almacenamiento local */ }
  // El navegador pide un toque antes de abrir el micrófono: se retoma con el primero.
  if (wanted) document.addEventListener("pointerdown", () => { if (!BW.on) bwStart(); }, { once: true });
  if (wanted) toast(t("bw.tap_resume"), "ok", 6000);
});

function bwRender() {
  const b = $("#btn-mic");
  if (!b || (LOCAL_PAGE && S.data.voice_listener)) return;
  const state = !BW.on ? "browser" : BW.state === "hearing" || BW.state === "sending" ? "hearing" : BW.state === "paused" ? "paused" : "on";
  b.dataset.state = state;
  const title = t(BW.on ? "bw.title_on" : "bw.title_off", { names: wakeNames() || "—" });
  b.title = title;
  b.setAttribute("aria-label", title);
  b.setAttribute("aria-pressed", String(BW.on));
  $(".mic-icon", b).innerHTML = BW.on ? ICON.micSmall : ICON.micOff;
  $(".top-label", b).textContent = t(BW.on ? `bw.${state}` : "bw.off");
}

async function bwStart() {
  if (!wakeNames()) return toast(t("bw.no_names"), "warn", 7000);
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return toast(t("conv.unsupported"), "error");
  try {
    BW.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (e) {
    return toast(t("conv.mic_denied", { error: e.message }), "error", 7000);
  }
  BW.ctx = new AudioContext();
  if (BW.ctx.state === "suspended") await BW.ctx.resume().catch(() => {});
  BW.analyser = BW.ctx.createAnalyser();
  BW.analyser.fftSize = 1024;
  BW.buf = new Float32Array(BW.analyser.fftSize);
  BW.ctx.createMediaStreamSource(BW.stream).connect(BW.analyser);
  BW.on = true;
  try { localStorage.setItem("bw-on", "1"); } catch { /* sin almacenamiento local */ }
  ensureOutputAnalyser();
  bwWakeLock();
  toast(t("bw.started", { names: wakeNames() }), "ok", 6000);
  bwRender();
  if (!BW.loop) bwLoop();
}

function bwStop(byUser = false) {
  BW.on = false;
  BW.cancel?.();
  BW.stream?.getTracks().forEach((tr) => tr.stop());
  BW.ctx?.close().catch(() => {});
  BW.stream = BW.ctx = BW.analyser = null;
  BW.lock?.release?.().catch(() => {});
  BW.lock = null;
  if (byUser) {
    try { localStorage.setItem("bw-on", "0"); } catch { /* sin almacenamiento local */ }
    toast(t("bw.stopped"));
  }
  bwRender();
}

// Que la pantalla no se apague mientras escucha (si se apaga, el navegador
// del celular corta el micrófono).
async function bwWakeLock() {
  try {
    if ("wakeLock" in navigator && !BW.lock) {
      BW.lock = await navigator.wakeLock.request("screen");
      BW.lock.addEventListener("release", () => { BW.lock = null; });
    }
  } catch { /* sin permiso o sin soporte: sigue igual */ }
}

const bwSleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

async function bwLoop() {
  BW.loop = true;
  try {
    while (BW.on) {
      // Mientras hay una conversación por voz (con su propio micrófono), piensa,
      // habla o la pestaña está oculta, no se escucha el nombre.
      if (CHAT.conv || CHAT.busy || CHAT.speaking || document.hidden) {
        if (BW.state !== "paused") { BW.state = "paused"; bwRender(); }
        await bwSleep(300);
        continue;
      }
      BW.state = "listening";
      bwRender();
      const blob = await bwCapture();
      if (!blob || !BW.on) continue;
      BW.state = "sending";
      bwRender();
      let d;
      try {
        const res = await fetch("/api/wake/listen", { method: "POST", headers: { "Content-Type": blob.type || "audio/webm", "X-UI-Lang": S.lang }, body: blob });
        d = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(d.error || `HTTP ${res.status}`);
      } catch (e) {
        toast(e.message, "error");
        await bwSleep(2000);
        continue;
      }
      if (d.wake && BW.on) {
        chime(1);
        await hfHandle({ type: "wake", assistant: d.wake, text: d.text, lang: d.lang, remainder: d.remainder });
      }
    }
  } finally {
    BW.loop = false;
    BW.state = "off";
    bwRender();
  }
}

// Una frase: espera voz (umbral sobre el ruido de fondo), graba hasta 0,9 s
// de silencio (o 10 s). La grabación empieza antes para no cortar el nombre.
function bwCapture() {
  return new Promise((resolve) => {
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m));
    let rec;
    try {
      rec = new MediaRecorder(BW.stream, mime ? { mimeType: mime } : undefined);
    } catch {
      return resolve(null);
    }
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    rec.start();
    const startedAt = performance.now();
    let noise = 0, samples = 0, loud = 0, speaking = false, speechAt = 0, silentMs = 0, done = false;
    const finish = (keep) => {
      if (done) return;
      done = true;
      clearInterval(timer);
      BW.cancel = null;
      rec.onstop = () => resolve(keep && chunks.length ? new Blob(chunks, { type: rec.mimeType || "audio/webm" }) : null);
      if (rec.state !== "inactive") rec.stop();
      else rec.onstop();
    };
    BW.cancel = () => finish(false);
    const timer = setInterval(() => {
      if (!BW.on || !BW.analyser || CHAT.conv || CHAT.speaking) return finish(false);
      BW.analyser.getFloatTimeDomainData(BW.buf);
      let sum = 0;
      for (const v of BW.buf) sum += v * v;
      const level = Math.sqrt(sum / BW.buf.length);
      const now = performance.now();
      if (now - startedAt < 350) {
        noise += level;
        samples++;
        return;
      }
      const threshold = Math.min(0.05, Math.max(0.012, (noise / Math.max(samples, 1)) * 2.5));
      if (!speaking) {
        loud = level > threshold ? loud + 1 : 0;
        if (loud >= 3) {
          speaking = true;
          speechAt = now;
          BW.state = "hearing";
          bwRender();
        } else if (now - startedAt > 15000) {
          finish(false); // sin voz: se reinicia para no acumular silencio
        }
      } else {
        silentMs = level > threshold * 0.8 ? 0 : silentMs + 50;
        if (silentMs >= 900 || now - speechAt > 10000) finish(now - speechAt > 300);
      }
    }, 50);
  });
}
// ── Diagnóstico (ver app/webui/diagnostics.py) ─────────────────────────
// Vista "Diagnóstico" (administrador): qué anda y qué no, con "Arreglar"
// donde se puede. Más las pruebas de ESTE dispositivo (micrófono,
// altavoz, notificaciones), que solo puede hacer el navegador.
const DIAG = { st: null, busy: null, mic: null };

FEATURE_VIEWS.diag = {
  title: () => t("dg.title"),
  render: renderDiagView,
};

FEATURE_CARDS.settings.push({
  id: "diag-card",
  when: () => isAdmin(),
  render: () => {
    const box = $("#diag-card");
    box.innerHTML = `<div class="card-head"><div><h2>🩺 ${esc(t("dg.title"))}</h2><p>${esc(t("dg.card_sub"))}</p></div>
      <button class="btn btn-sm btn-primary" type="button" id="diag-open">${esc(t("dg.open"))}</button></div>`;
    $("#diag-open").onclick = () => select({ kind: "diag" });
  },
});

const DG_GROUPS = ["ollama", "system", "voice", "network", "extras", "device"];
const DG_ICON = { ok: "✅", warn: "⚠️", error: "❌", info: "ℹ️" };

function renderDiagView() {
  const main = $("#main");
  main.oninput = main.onchange = main.onkeydown = null;
  if (!isAdmin()) return void select({ kind: "gallery" }, { force: true });
  main.innerHTML = `<div class="editor diag-view">
    <header class="editor-head">
      <div class="avatar avatar-lg">🩺</div>
      <div class="head-text"><h1>${esc(t("dg.title"))}</h1><p>${esc(t("dg.sub"))}</p></div>
      <button class="btn" type="button" data-dg-act="refresh">${ICON.retry} ${esc(t("dg.refresh"))}</button>
    </header>
    <div id="diag-body" class="editor-body"><p class="note">${esc(t("dg.checking"))}</p></div>
  </div>`;
  main.onclick = onDiagClick;
  if (DIAG.st) drawDiag();
  loadDiag();
}

async function loadDiag() {
  try {
    DIAG.st = await api("GET", "/api/diagnostics");
  } catch (ex) {
    toast(ex.message, "error");
  }
  if (S.view?.kind === "diag") drawDiag();
}

function deviceChecks() {
  const out = [];
  const perm = "Notification" in window ? Notification.permission : "unsupported";
  out.push({ id: "dev_secure", status: window.isSecureContext ? "ok" : "warn", title: t(window.isSecureContext ? "dg.secure_ok" : "dg.secure_no"),
    detail: window.isSecureContext ? "" : t("dg.secure_no_d") });
  out.push({ id: "dev_notif", status: perm === "granted" ? "ok" : perm === "denied" ? "warn" : "info",
    title: t(`dg.notif_${perm}`), detail: "", fix: perm === "default" ? "dev_notif" : null });
  out.push({ id: "dev_sw", status: NOTIFY.sw ? "ok" : "info", title: t(NOTIFY.sw ? "dg.sw_ok" : "dg.sw_no"), detail: NOTIFY.sw ? "" : t("dg.sw_no_d") });
  const mic = DIAG.mic;
  out.push({ id: "dev_mic", status: mic ? (mic.error ? "error" : mic.peak > 0.02 ? "ok" : "warn") : "info",
    title: t("dg.dev_mic"), detail: mic ? (mic.error || t("dg.dev_mic_level", { name: mic.name || "?", pct: Math.round(Math.min(1, mic.peak * 8) * 100) })) : t("dg.dev_mic_d"),
    fix: "dev_mic" });
  out.push({ id: "dev_speaker", status: "info", title: t("dg.dev_speaker"), detail: t("dg.dev_speaker_d"), fix: "dev_speaker" });
  return out;
}

function drawDiag() {
  const box = $("#diag-body");
  if (!box || !DIAG.st) return;
  const all = [...DIAG.st.checks, ...deviceChecks().map((c) => ({ ...c, group: "device" }))];
  const counts = { error: 0, warn: 0 };
  all.forEach((c) => { if (counts[c.status] != null) counts[c.status]++; });
  const summary = counts.error ? t("dg.sum_errors", { n: counts.error }) : counts.warn ? t("dg.sum_warns", { n: counts.warn }) : t("dg.sum_ok");
  const row = (c) => `<div class="dg-row ${c.status}" data-dg="${esc(c.id)}">
      <span class="dg-icon" aria-hidden="true">${DG_ICON[c.status] || "•"}</span>
      <div class="dg-main"><strong>${esc(c.title)}</strong>${c.detail ? `<small>${esc(c.detail)}</small>` : ""}</div>
      <div class="dg-acts">
        ${c.link ? `<a class="btn btn-sm" href="${esc(c.link)}" target="_blank" rel="noopener">${esc(t("dg.open_link"))}</a>` : ""}
        ${c.fix ? `<button class="btn btn-sm ${c.status === "error" || c.status === "warn" ? "btn-primary" : ""}" type="button" data-dg-fix="${esc(c.fix)}" ${DIAG.busy ? "disabled" : ""}>${esc(DIAG.busy === c.fix ? t("dg.fixing") : t(`dg.fix_${c.fix}`))}</button>` : ""}
      </div>
    </div>`;
  box.innerHTML = `<div class="callout ${counts.error ? "warn" : "info"} dg-summary"><div>${esc(summary)} <small>${esc(t("dg.when", { when: fmtDate(DIAG.st.at) }))}</small></div></div>
    ${DG_GROUPS.map((g) => {
    const items = all.filter((c) => c.group === g);
    return items.length ? `<section class="card"><div class="card-head"><div><h2>${esc(t(`dg.g_${g}`))}</h2></div></div><div class="dg-list">${items.map(row).join("")}</div></section>` : "";
  }).join("")}
    ${DIAG.st.local ? "" : `<p class="note">${esc(t("dg.remote_note"))}</p>`}`;
}

async function onDiagClick(e) {
  if (e.target.closest("[data-dg-act=refresh]")) {
    DIAG.st = null;
    $("#diag-body").innerHTML = `<p class="note">${esc(t("dg.checking"))}</p>`;
    return loadDiag();
  }
  const b = e.target.closest("[data-dg-fix]");
  if (!b) return;
  const fix = b.dataset.dgFix;
  if (fix === "dev_notif") {
    await Notification.requestPermission().catch(() => {});
    return drawDiag();
  }
  if (fix === "dev_mic") return testMic();
  if (fix === "dev_speaker") return testSpeaker();
  if (["firewall_allow", "net_private"].includes(fix) && !(await confirmDialog(t("dg.uac_title"), t("dg.uac_text"), t("dg.fix_" + fix), false))) return;
  DIAG.busy = fix;
  drawDiag();
  try {
    const r = await api("POST", "/api/diagnostics/fix", { id: fix });
    DIAG.st = r;
    toast(r.ok ? t("dg.fixed") + (r.note ? ` (${r.note})` : "") : t("dg.not_fixed"), r.ok ? "ok" : "warn", 6000);
    if (fix.startsWith("pull_")) pollPull();
  } catch (ex) {
    toast(ex.message, "error", 7000);
  }
  DIAG.busy = null;
  drawDiag();
}

async function testMic() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    DIAG.mic = { error: t("conv.mic_denied", { error: e.message }), peak: 0 };
    return drawDiag();
  }
  toast(t("dg.dev_mic_speak"), "ok", 3500);
  const ctx = new AudioContext();
  const an = ctx.createAnalyser();
  an.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(an);
  const buf = new Float32Array(an.fftSize);
  let peak = 0;
  const t0 = performance.now();
  while (performance.now() - t0 < 3000) {
    an.getFloatTimeDomainData(buf);
    let s = 0;
    for (const v of buf) s += v * v;
    peak = Math.max(peak, Math.sqrt(s / buf.length));
    await new Promise((ok) => setTimeout(ok, 50));
  }
  DIAG.mic = { peak, name: stream.getAudioTracks()[0]?.label || "" };
  stream.getTracks().forEach((tr) => tr.stop());
  ctx.close().catch(() => {});
  drawDiag();
}

async function testSpeaker() {
  const a = S.data.assistants[0];
  try {
    const res = await fetch("/api/tts", {
      method: "POST", headers: { "Content-Type": "application/json", "X-UI-Lang": S.lang },
      body: JSON.stringify({ text: t("dg.dev_speaker_text"), voice: a?.voice || "F1", speed: a?.speed || 1, lang: S.lang }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `HTTP ${res.status}`);
    const url = URL.createObjectURL(await res.blob());
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    await audio.play();
  } catch (ex) {
    toast(ex.message, "error");
  }
}
// ── Respaldo y restauración (ver app/webui/backup.py) ──────────────────
const BAK = { st: null, busy: false };

FEATURE_CARDS.settings.push({
  id: "backup-card",
  when: () => isAdmin(),
  render: () => {
    renderBackupCard();
    api("GET", "/api/backups").then((st) => { BAK.st = st; renderBackupCard(); }).catch((ex) => toast(ex.message, "error"));
  },
});

function renderBackupCard() {
  const box = $("#backup-card");
  if (!box) return;
  const st = BAK.st;
  const rows = (st?.backups || []).map((b) => `<div class="doc-row" data-bak="${esc(b.name)}">
      <span class="doc-icon">📦</span>
      <div class="doc-main"><strong>${esc(fmtDate(b.created))} · ${esc(t(`bak.kind_${b.kind}`) || b.kind)}</strong>
        <small>${esc([bakSize(b.size), t("bak.files", { n: b.files }), b.attachments ? t("bak.with_att") : "", b.secrets ? t("bak.with_keys") : ""].filter(Boolean).join(" · "))}</small></div>
      <span class="bak-acts">
        <a class="btn btn-sm" href="/api/backups/${encodeURIComponent(b.name)}" download>${esc(t("bak.download"))}</a>
        <button class="btn btn-sm" type="button" data-bak-act="restore" ${BAK.busy ? "disabled" : ""}>${esc(t("bak.restore"))}</button>
        <button class="icon-btn small" type="button" data-bak-act="delete" aria-label="${esc(t("bak.delete"))}" title="${esc(t("bak.delete"))}">${ICON.close}</button>
      </span>
    </div>`).join("");
  box.innerHTML = `
    <div class="card-head"><div><h2>🗄️ ${esc(t("bak.title"))}</h2><p>${esc(t("bak.sub"))}</p></div></div>
    <div class="bak-create">
      <label class="rt-chip"><input type="checkbox" id="bak-att"> ${esc(t("bak.opt_att"))}</label>
      <label class="rt-chip"><input type="checkbox" id="bak-keys"> ${esc(t("bak.opt_keys"))}</label>
      <button class="btn btn-sm btn-primary" type="button" data-bak-act="create" ${BAK.busy ? "disabled" : ""}>${esc(t(BAK.busy ? "bak.working" : "bak.create"))}</button>
      <label class="btn btn-sm ${BAK.busy ? "disabled" : ""}">${esc(t("bak.upload"))}<input type="file" accept=".zip,application/zip" hidden id="bak-file"></label>
    </div>
    ${st == null ? `<p class="note">${esc(t("loading"))}</p>` : rows ? `<div class="doc-list">${rows}</div>` : `<p class="note">${esc(t("bak.none"))}</p>`}
    <p class="note">${esc(t("bak.note", { folder: st?.folder || "backups" }))}</p>`;
  $("#bak-file").onchange = (e) => restoreBackup(null, e.target.files[0]);
  box.onclick = async (e) => {
    const b = e.target.closest("[data-bak-act]");
    if (!b) return;
    const name = b.closest("[data-bak]")?.dataset.bak;
    if (b.dataset.bakAct === "create") {
      BAK.busy = true;
      renderBackupCard();
      try {
        BAK.st = await api("POST", "/api/backups", { attachments: $("#bak-att").checked, secrets: $("#bak-keys").checked });
        toast(t("bak.created"));
      } catch (ex) {
        toast(ex.message, "error");
      }
      BAK.busy = false;
      renderBackupCard();
    } else if (b.dataset.bakAct === "delete") {
      if (!(await confirmDialog(t("bak.delete_title"), t("bak.delete_text"), t("bak.delete")))) return;
      try {
        BAK.st = await api("DELETE", `/api/backups/${encodeURIComponent(name)}`, {});
      } catch (ex) {
        toast(ex.message, "error");
      }
      renderBackupCard();
    } else if (b.dataset.bakAct === "restore") {
      restoreBackup(name, null);
    }
  };
}

async function restoreBackup(name, file) {
  if (!(await confirmDialog(t("bak.restore_title"), t("bak.restore_text"), t("bak.restore")))) return;
  BAK.busy = true;
  renderBackupCard();
  try {
    let r;
    if (file) {
      const res = await fetch("/api/backups/restore", { method: "POST", headers: { "Content-Type": "application/octet-stream", "X-UI-Lang": S.lang }, body: file });
      r = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(r.error || `HTTP ${res.status}`);
    } else {
      r = await api("POST", `/api/backups/${encodeURIComponent(name)}/restore`, {});
    }
    toast(t("bak.restored", { n: r.restored.files }), "ok", 6000);
    setTimeout(() => location.reload(), 1500); // todo vuelve a cargarse con lo restaurado
  } catch (ex) {
    toast(ex.message, "error", 7000);
    BAK.busy = false;
    renderBackupCard();
  }
}
// Ajustes de un plugin (p. ej. la dirección y el token de Home Assistant).
const plLabel = (v) => (v && typeof v === "object" ? v[S.lang] || v.es || v.en || "" : String(v || ""));

function pluginSettingsForm(p) {
  const fields = p.settings_schema.map((f) => {
    const secretSet = f.type === "secret" && p.secrets_set.includes(f.key);
    const help = f.help ? `<small>${esc(plLabel(f.help))}</small>` : "";
    if (f.type === "select") {
      const cur = p.settings[f.key] || f.options?.[0]?.value || "";
      return `<div class="field"><label>${esc(plLabel(f.label))}</label>
        <select class="text-input" data-pl-field="${esc(f.key)}">${(f.options || []).map((o) =>
          `<option value="${esc(o.value)}" ${o.value === cur ? "selected" : ""}>${esc(plLabel(o.label))}</option>`).join("")}</select>${help}</div>`;
    }
    if (f.type === "bool") {
      return `<div class="field"><label class="check-row"><input type="checkbox" data-pl-field="${esc(f.key)}" data-bool
        ${p.settings[f.key] === "true" ? "checked" : ""}> ${esc(plLabel(f.label))}</label>${help}</div>`;
    }
    return `<div class="field"><label>${esc(plLabel(f.label))}</label>
      <input class="text-input" data-pl-field="${esc(f.key)}" type="${f.type === "secret" ? "password" : f.type === "number" ? "number" : "text"}"
        value="${esc(f.type === "secret" ? "" : p.settings[f.key] || "")}" autocomplete="off"
        placeholder="${esc(secretSet ? t("pl.secret_set") : f.placeholder || "")}">
      ${f.help ? `<small>${esc(plLabel(f.help))}</small>` : ""}</div>`;
  }).join("");
  const missing = p.settings_schema.some((f) => (f.type === "secret" ? !p.secrets_set.includes(f.key) : false));
  return `<details class="pl-settings" ${missing && p.enabled ? "open" : ""}><summary>${esc(t("pl.configure"))}${missing ? ` <span class="badge warn">${esc(t("pl.needs_setup"))}</span>` : ""}</summary>
    ${fields}
    <div class="mcp-acts"><button class="btn btn-sm btn-primary" type="button" data-pl-set="save">${esc(t("pl.save"))}</button>
      ${p.can_check ? `<button class="btn btn-sm" type="button" data-pl-set="check">${esc(t("pl.check"))}</button>` : ""}
      <small class="pl-check-msg"></small></div>
  </details>`;
}

async function pluginSettingsAction(b) {
  const row = b.closest("[data-pl]");
  const id = row.dataset.pl;
  const values = Object.fromEntries($$("[data-pl-field]", row).map((i) => [i.dataset.plField, i.dataset.bool != null ? String(i.checked) : i.value]));
  const msg = $(".pl-check-msg", row);
  try {
    if (b.dataset.plSet === "save" || b.dataset.plSet === "check") {
      PLUG.st = await api("PUT", `/api/plugins/${id}`, { settings: values });
    }
    if (b.dataset.plSet === "check") {
      const r = await api("POST", `/api/plugins/${id}/check`, {});
      toast(r.message, r.ok ? "ok" : "warn", 7000);
    } else {
      toast(t("pl.saved"));
    }
    if (id === "comfyui") CU.st = null; // la dirección pudo cambiar: se vuelve a leer
  } catch (ex) {
    if (msg) msg.textContent = ex.message;
    return toast(ex.message, "error");
  }
  renderPluginsCard();
}
const bakSize = (n) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

// ── Modo voz: adjuntar, foto y videollamada (visión) ──────────────────
// En la conversación por voz también se adjuntan archivos y fotos (van con
// lo próximo que digas). La videollamada abre la cámara (la de atrás en el
// celular, con botón para cambiarla) y, con cada cosa que dices, manda al
// modelo lo que ve la cámara en ese momento: así reconoce los objetos que le
// muestras ("¿qué es esto?", "¿cuántas manzanas hay?", "lee esta etiqueta").
// El modelo tiene que tener visión (gemma4 la tiene).
const VC_ICON = {
  video: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><rect x="3" y="6" width="12" height="12" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15 10.5l5-3v9l-5-3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
  videoOff: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><rect x="3" y="6" width="12" height="12" rx="2.5" fill="currentColor"/><path d="M15 10.5l5-3v9l-5-3z" fill="currentColor"/></svg>',
  flip: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M4 12a8 8 0 0 1 13.7-5.6M20 12a8 8 0 0 1-13.7 5.6M18 3v4h-4M6 21v-4h4" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  eye: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg>',
};
const VC = { on: false, stream: null, facing: "environment", busy: false, frameSide: 1024 };

function voiceSides(center) {
  const vision = canSeeImages();
  const btn = (act, icon, label, extra = "") => `<button class="side-btn ${extra}" type="button" ${act} aria-label="${esc(label)}" title="${esc(label)}">${icon}</button>`;
  // Adjuntar, biblioteca y cámara van juntos en un solo botón "+" que despliega las opciones.
  const left = `<div class="voice-side"><details class="menu voice-attach">
      <summary class="side-btn" aria-label="${esc(t("att.add"))}" title="${esc(t("att.add"))}">${ICON.plus}</summary>
      <div class="menu-pop up">
        <button class="menu-item" type="button" data-chat-act="attach">${ICON.clip}<span>${esc(t("att.files"))}</span></button>
        ${!isGuest() ? `<button class="menu-item" type="button" data-chat-act="library">${ICON.library}<span>${esc(t("att.from_library"))}</span></button>` : ""}
        ${vision ? `<button class="menu-item" type="button" data-chat-act="camera">${ICON.camera}<span>${esc(t("cam.open"))}</span></button>` : ""}
      </div></details></div>`;
  const right = `<div class="voice-side">${vision ? btn('data-vc="toggle"', VC.on ? VC_ICON.videoOff : VC_ICON.video, t(VC.on ? "vc.stop" : "vc.start"), VC.on ? "on" : "") : ""}</div>`;
  return `<div class="voice-row">${left}${center}${right}</div>`;
}

// Lo que va con lo que dijiste: los adjuntos pendientes y el cuadro actual de la cámara.
function voiceFiles() {
  if (CHAT.mode !== "voice") return null;
  const att = CHAT.attachments.length ? takeAttachments() : null;
  const frame = VC.on ? grabFrame() : null;
  if (!att && !frame) return null;
  const out = { display: [...(att?.display || [])], history: { attachments: [...(att?.history.attachments || [])], images: [...(att?.history.images || [])] } };
  if (frame) {
    out.display.push({ kind: "image", name: frame.name, thumb: frame.thumb });
    out.history.attachments.push({ kind: "image", name: frame.name, info: t("vc.frame_info") });
    out.history.images.push(frame.image);
  }
  return out;
}

function grabFrame() {
  const video = $("#vc-video");
  if (!video || !video.videoWidth) return null;
  const scale = Math.min(1, VC.frameSide / Math.max(video.videoWidth, video.videoHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  const data = canvas.toDataURL("image/jpeg", 0.82);
  const small = document.createElement("canvas");
  const s2 = 240 / Math.max(canvas.width, canvas.height);
  small.width = Math.round(canvas.width * s2);
  small.height = Math.round(canvas.height * s2);
  small.getContext("2d").drawImage(canvas, 0, 0, small.width, small.height);
  // Un destello en la vista: se "tomó" lo que ve.
  $("#video-pip")?.classList.remove("flash");
  void $("#video-pip")?.offsetWidth;
  $("#video-pip")?.classList.add("flash");
  return { name: `${t("vc.frame_name")}-${new Date().toTimeString().slice(0, 8).replace(/:/g, "")}.jpg`, image: data.split(",")[1], thumb: small.toDataURL("image/jpeg", 0.7) };
}

async function startVideoCall() {
  if (!canSeeImages()) return toast(t("att.no_vision", { model: S.draft.base_model }), "error", 7000);
  if (!navigator.mediaDevices?.getUserMedia) return toast(t(window.isSecureContext ? "vc.unsupported" : "cam.insecure", { error: "" }), "error", 7000);
  try {
    VC.stream?.getTracks().forEach((tr) => tr.stop());
    VC.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: VC.facing, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
  } catch (e) {
    VC.stream = null;
    return toast(t(window.isSecureContext ? "cam.denied" : "cam.insecure", { error: e.message }), "error", 7000);
  }
  VC.on = true;
  syncVideoCall();
  renderChatFoot();
  // La conversación por voz se abre con la videollamada (si no estaba abierta).
  if (!CHAT.conv) startConversation();
  toast(t("vc.started"), "ok", 5000);
}

function stopVideoCall() {
  if (!VC.on && !VC.stream) return;
  VC.on = false;
  VC.stream?.getTracks().forEach((tr) => tr.stop());
  VC.stream = null;
  const pip = $("#video-pip");
  if (pip) { pip.hidden = true; pip.innerHTML = ""; }
  $(".voice-stage")?.classList.remove("vc-on");
  if (CHAT.mode === "voice") renderChatFoot();
}

// Dibuja (o quita) la vista de la cámara según el estado.
function syncVideoCall() {
  if (CHAT.mode !== "voice") return stopVideoCall();
  const pip = $("#video-pip");
  if (!pip) return;
  $(".voice-stage")?.classList.toggle("vc-on", !!(VC.on && VC.stream));
  if (!VC.on || !VC.stream) {
    pip.hidden = true;
    pip.innerHTML = "";
    return;
  }
  if (!$("#vc-video", pip)) {
    pip.innerHTML = `<video id="vc-video" autoplay playsinline muted></video>
      <div class="vc-bar">
        <button class="vc-btn" type="button" data-vc="look" title="${esc(t("vc.look"))}" aria-label="${esc(t("vc.look"))}">${VC_ICON.eye}<span>${esc(t("vc.look_short"))}</span></button>
        <button class="vc-btn" type="button" data-vc="flip" title="${esc(t("cam.flip"))}" aria-label="${esc(t("cam.flip"))}">${VC_ICON.flip}</button>
        <button class="vc-btn" type="button" data-vc="toggle" title="${esc(t("vc.stop"))}" aria-label="${esc(t("vc.stop"))}">${ICON.close}</button>
      </div>`;
  }
  const video = $("#vc-video", pip);
  if (video.srcObject !== VC.stream) video.srcObject = VC.stream;
  video.classList.toggle("mirror", VC.facing === "user");
  pip.hidden = false;
  navigator.mediaDevices.enumerateDevices().then((ds) => {
    const flip = $("[data-vc=flip]", pip);
    if (flip) flip.hidden = ds.filter((d) => d.kind === "videoinput").length < 2;
  }).catch(() => {});
}

// "¿Qué ves?": pregunta con lo que ve la cámara ahora, sin tener que hablar.
async function lookNow() {
  if (CHAT.busy) return toast(t("att.wait"));
  ensureOutputAnalyser();
  stopSpeaking();
  await sendChat(t("vc.look_prompt"), spokenLang(CHAT.lang), null, voiceFiles());
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-vc]");
  if (!b) return;
  const act = b.dataset.vc;
  if (act === "toggle") (VC.on ? stopVideoCall() : startVideoCall());
  else if (act === "flip") {
    VC.facing = VC.facing === "user" ? "environment" : "user";
    startVideoCall();
  } else if (act === "look") lookNow();
});

// El modelo sabe que es una videollamada (ver config_ui._chat_request).
FEATURE_BODY.push(() => (VC.on && CHAT.mode === "voice" ? { video_call: true } : {}));
// ── ComfyUI: imágenes y videos (ver plugins/comfyui) ──────────────────
// El modelo llama generate_image / edit_image / generate_video y el
// servidor manda un evento "job": aquí queda una tarjeta con un lienzo del
// tamaño de lo que se está creando (animado), la barra de progreso
// (sondeo de /api/plugin/comfyui/jobs) y cancelar. Al terminar, la imagen
// o el video se ve en la tarjeta y queda como archivo de la respuesta (el
// modelo lo puede volver a usar: "ahora ponle un sombrero"). "Regenerar"
// hace otra versión (otra semilla): la tarjeta guarda todas y se ven de a
// una, con ‹ 2/3 › para pasar de una a otra. El trabajo arranca recién
// cuando termina la respuesta y su voz ("go"): así el aviso se dice antes
// de que se descargue el modelo. Mientras dibuja con la GPU del asistente,
// lo que escribas espera su turno (featureHoldSend).
const FEATURE_ROLES = {};
const CJOB = { timer: null, held: [], going: new Set(), notified: new Set() };
const CJOB_ACTIVE = ["waiting", "queued", "starting", "running"];
const CJOB_FIELDS = ["id", "status", "progress", "eta_left", "position", "error", "result", "label", "wf_name", "size", "workflow", "note"];
const cjobIcon = (k, size = 18) => svgIcon({ image: "image", edit: "wand", video: "film" }[k] || "image", size);

// Las tarjetas de antes (una sola versión) pasan a tener la lista de versiones.
function cjobIters(d) {
  if (!d.iters) {
    d.iters = [Object.fromEntries(CJOB_FIELDS.map((k) => [k, d[k]]))];
    d.cur = 0;
  }
  if (!(d.cur >= 0 && d.cur < d.iters.length)) d.cur = d.iters.length - 1;
  return d.iters;
}

FEATURE_EVENTS.job = (ev, { key, epoch }) => {
  if (epoch !== CHAT.epoch || !ev.job?.id) return;
  const turn = [...CHAT.history].reverse().find((h) => h.role === "user")?.id || null;
  const plugin = ev.plugin || "comfyui";
  CHAT.messages.push({ role: "job", data: {
    plugin, kind: ev.job.kind, hold: !!ev.hold, src: ev.src || null, turn, speaker: key,
    iters: [Object.fromEntries(CJOB_FIELDS.map((k) => [k, ev.job[k]]))], cur: 0,
  } });
  renderChatLog();
  cjobGoAfterTurn(ev.job.id, plugin);
  cjobPoll();
};

// "go" cuando el turno terminó y el asistente se calló.
async function cjobGoAfterTurn(id, plugin) {
  if (CJOB.going.has(id)) return;
  CJOB.going.add(id);
  const t0 = Date.now();
  while ((CHAT.busy || CHAT.speaking) && Date.now() - t0 < 40000) await new Promise((ok) => setTimeout(ok, 300));
  try {
    await api("POST", `/api/plugin/${plugin}/go`, { ids: [id] });
  } catch { /* arranca solo a los 45 s */ }
}

const cjobMsgs = () => (typeof CHAT === "undefined" ? [] : CHAT.messages.filter((m) => m.role === "job" && m.data));

// La tarjeta y la versión de un trabajo.
function cjobFind(id) {
  for (const m of cjobMsgs()) {
    const it = cjobIters(m.data).find((x) => x.id === id);
    if (it) return { m, it };
  }
  return {};
}

function cjobPoll() {
  if (CJOB.timer) return;
  CJOB.timer = setTimeout(cjobTick, 1200);
}

const cjobLive = () => cjobMsgs().flatMap((m) => cjobIters(m.data).filter((it) => CJOB_ACTIVE.includes(it.status)).map((it) => ({ m, it })));

async function cjobTick() {
  CJOB.timer = null;
  const live = cjobLive();
  if (!live.length) return cjobRelease();
  const byPlugin = {};
  live.forEach(({ m, it }) => (byPlugin[m.data.plugin || "comfyui"] ||= []).push(it.id));
  for (const [plugin, ids] of Object.entries(byPlugin)) {
    try {
      const r = await api("POST", `/api/plugin/${plugin}/jobs`, { ids });
      r.jobs.forEach((j) => cjobUpdate(j, r.hold));
      // Los que el servidor ya no conoce (se borraron): error.
      ids.filter((id) => !r.jobs.some((j) => j.id === id)).forEach((id) => cjobUpdate({ id, status: "error", error: t("cj.lost") }));
    } catch { /* se reintenta */ }
  }
  cjobRelease();
  if (cjobLive().length) CJOB.timer = setTimeout(cjobTick, 1500);
}

function cjobUpdate(j, hold) {
  const { m, it } = cjobFind(j.id);
  if (!m) return;
  const was = it.status;
  Object.assign(it, Object.fromEntries(CJOB_FIELDS.filter((k) => k in j).map((k) => [k, j[k]])));
  if (hold != null) m.data.hold = hold;
  if (was !== it.status) {
    if (it.status === "done" && it.result) {
      cjobAttach(m, it);
      it.reveal = true; // aparece desenfocándose, como al revelarse
    }
    CHAT_SAVE.sig = ""; // el resultado también se guarda con la conversación
    renderChatLog();
    if (it.status === "done") cjobDoneNotice(m.data, it);
    return;
  }
  // Solo la barra y el tiempo, sin redibujar el chat.
  const card = document.querySelector(`[data-cjob-it="${CSS.escape(j.id)}"]`);
  if (!card) return;
  const bar = card.querySelector(".progress > div");
  if (bar) bar.style.width = `${Math.round((it.progress || 0) * 100)}%`;
  const st = card.querySelector(".cj-state");
  if (st) st.textContent = cjobState(m.data, it);
}

// El archivo queda en la respuesta de ese turno (así el modelo lo ve en el historial).
function cjobAttach(m, it) {
  const file = { name: it.result.name, url: it.result.url };
  const ui = CHAT.history.findIndex((h) => h.id && h.id === m.data.turn);
  let target = null;
  if (ui >= 0) target = CHAT.history.slice(ui + 1).find((h) => h.role === "assistant");
  target ||= [...CHAT.history].reverse().find((h) => h.role === "assistant");
  if (target && !(target.files || []).some((f) => f.url === file.url)) target.files = [...(target.files || []), file];
}

function cjobDoneNotice(d, it) {
  if (CJOB.notified.has(it.id)) return;
  CJOB.notified.add(it.id);
  if (document.hidden || d.kind === "video") {
    systemNotify(t(`cj.ready_${d.kind}`), it.label || "", `cj-${it.id}`);
    if (d.kind === "video") chime(1);
  }
}

const cjobState = (d, it) => {
  if (it.status === "waiting") return t("cj.waiting");
  if (it.status === "queued") return t("cj.queued");
  if (it.status === "starting") return t("cj.starting");
  if (it.status === "running") {
    if (it.position > 1) return t("cj.position", { n: it.position });
    const left = it.eta_left > 90 ? t("cj.left_min", { n: Math.round(it.eta_left / 60) }) : t("cj.left_s", { n: Math.max(1, it.eta_left || 0) });
    return `${t(`cj.doing_${d.kind}`)} · ${it.progress >= 0.95 ? t("cj.almost") : left}`;
  }
  if (it.status === "cancelled") return t("cj.cancelled");
  if (it.status === "error") return t("cj.error", { error: it.error || "?" });
  return "";
};

// Lienzo del tamaño de lo que se crea, mientras se crea.
function cjobCanvas(d, it) {
  const [w, h] = Array.isArray(it.size) && it.size[0] > 0 && it.size[1] > 0 ? it.size : d.kind === "video" ? [832, 480] : [1024, 1024];
  return `<div class="cj-canvas ${d.kind}" style="aspect-ratio:${w} / ${h};width:min(100%, calc(56vh * ${w} / ${h}))">
    <span class="cj-blob a"></span><span class="cj-blob b"></span><span class="cj-blob c"></span><span class="cj-sweep"></span>
    <span class="cj-canvas-ico">${cjobIcon(d.kind, 28)}</span><span class="cj-size">${w} × ${h}</span></div>`;
}

const cjBtn = (attrs, icon, label, cls = "") =>
  `<button class="btn btn-sm cj-btn ${cls}" type="button" ${attrs} title="${esc(label)}">${svgIcon(icon, 15)}<span>${esc(label)}</span></button>`;

FEATURE_ROLES.job = (m) => {
  const d = m.data || {};
  const iters = cjobIters(d);
  const it = iters[d.cur];
  const active = CJOB_ACTIVE.includes(it.status);
  if (cjobLive().length) cjobPoll();
  const key = esc(iters[0].id);
  const r = it.result;
  let body;
  if (it.status === "done" && r) {
    const reveal = it.reveal ? "reveal" : "";
    it.reveal = false;
    const media = r.kind === "video"
      ? `<video class="cj-media ${reveal}" src="${esc(r.url)}" controls playsinline loop preload="metadata"></video>`
      : `<button class="cj-view" type="button" data-cj-view="${esc(it.id)}" title="${esc(t("iv.view"))}"><img class="cj-media ${reveal}" src="${esc(r.url)}" alt="${esc(it.label || r.name)}" loading="lazy"></button>`;
    body = `${media}<div class="cj-acts">
      ${r.kind !== "video" ? cjBtn(`data-cj-edit="${esc(it.id)}"`, "pencil", t("cj.edit")) : ""}
      ${cjBtn(`data-cj-regen="${esc(it.id)}"`, "regenerate", t("cj.regen"))}
      ${cjBtn(`data-cj-view="${esc(it.id)}"`, "maximize", t("iv.view"))}
      <a class="btn btn-sm btn-primary cj-btn" href="${esc(r.url)}" download="${esc(r.name)}" title="${esc(t("file.download"))}">${svgIcon("download", 15)}<span>${esc(t("file.download"))}</span></a></div>`;
  } else if (active) {
    body = `${cjobCanvas(d, it)}<div class="progress"><div style="width:${Math.round((it.progress || 0) * 100)}%"></div></div>
      <div class="cj-row"><small class="cj-state">${esc(cjobState(d, it))}</small>
      ${cjBtn(`data-cj-cancel="${esc(it.id)}"`, "x", t("chat.cancel"), "btn-quiet")}</div>`;
  } else {
    body = `<div class="cj-row"><small class="cj-state ${it.status === "error" ? "err" : ""}">${esc(cjobState(d, it))}</small>
      ${cjBtn(`data-cj-regen="${esc(it.id)}"`, "regenerate", t("cj.regen"))}</div>`;
  }
  const nav = iters.length > 1 ? `<div class="cj-nav">
      <button class="icon-btn small" type="button" data-cj-nav="-1" data-cj-key="${key}" ${d.cur === 0 ? "disabled" : ""} aria-label="${esc(t("cj.prev"))}" title="${esc(t("cj.prev"))}">${svgIcon("chevronLeft", 16)}</button>
      <span>${d.cur + 1} / ${iters.length}</span>
      <button class="icon-btn small" type="button" data-cj-nav="1" data-cj-key="${key}" ${d.cur === iters.length - 1 ? "disabled" : ""} aria-label="${esc(t("cj.next"))}" title="${esc(t("cj.next"))}">${svgIcon("chevronRight", 16)}</button></div>` : "";
  const title = t(it.status === "done" ? `cj.done_${d.kind}` : `cj.title_${d.kind}`);
  // El prompt queda oculto bajo la imagen; se despliega con su botón.
  const prompt = it.label ? `<details class="cj-prompt"><summary>${svgIcon("note", 14)}<span>${esc(t("cj.prompt_show"))}</span>${svgIcon("chevronRight", 14)}</summary>
      <p>${esc(it.label)}</p></details>` : "";
  return `<div class="msg job" data-cjob="${key}"><div class="cj-card ${esc(it.status)}" data-cjob-it="${esc(it.id)}">
    <div class="cj-head"><span class="cj-ico ${active ? "busy" : ""}">${cjobIcon(d.kind)}</span>
      <div class="cj-title"><strong>${esc(title)}</strong>
      ${it.wf_name ? `<small class="cj-wf">${esc(t("cj.with_wf", { name: it.wf_name }))}</small>` : ""}
      ${it.note ? `<small class="cj-note">${svgIcon("warn", 13)} ${esc(t(`cj.${it.note}`))}</small>` : ""}</div>${nav}</div>
    ${body}${prompt}</div></div>`;
};

async function cjobRegen(id) {
  const { m, it } = cjobFind(id);
  if (!m) return;
  try {
    const r = await api("POST", `/api/plugin/${m.data.plugin || "comfyui"}/regen`, { id: it.id });
    const iters = cjobIters(m.data);
    iters.push(Object.fromEntries(CJOB_FIELDS.map((k) => [k, r.job[k]])));
    m.data.cur = iters.length - 1;
    if (r.hold != null) m.data.hold = r.hold;
    CHAT_SAVE.sig = "";
    renderChatLog();
    cjobPoll();
  } catch (ex) {
    toast(ex.message, "error");
  }
}

document.addEventListener("click", async (e) => {
  const c = e.target.closest("[data-cj-cancel]");
  if (c) {
    const { m } = cjobFind(c.dataset.cjCancel);
    c.disabled = true;
    try {
      await api("POST", `/api/plugin/${m?.data.plugin || "comfyui"}/cancel`, { id: c.dataset.cjCancel });
      cjobUpdate({ id: c.dataset.cjCancel, status: "cancelled" });
    } catch (ex) {
      toast(ex.message, "error");
    }
    return;
  }
  const nv = e.target.closest("[data-cj-nav]");
  if (nv) {
    const { m } = cjobFind(nv.dataset.cjKey);
    if (!m) return;
    const iters = cjobIters(m.data);
    m.data.cur = Math.max(0, Math.min(iters.length - 1, m.data.cur + Number(nv.dataset.cjNav)));
    CHAT_SAVE.sig = "";
    renderChatLog();
    return;
  }
  const rg = e.target.closest("[data-cj-regen]");
  if (rg) {
    rg.disabled = true;
    return cjobRegen(rg.dataset.cjRegen);
  }
  const vw = e.target.closest("[data-cj-view]");
  if (vw) {
    const { it } = cjobFind(vw.dataset.cjView);
    const r = it?.result;
    if (r) openImageViewer(r.url, r.name, { video: r.kind === "video", onEdit: r.kind === "video" ? null : () => cjobEdit(r) });
    return;
  }
  const ed = e.target.closest("[data-cj-edit]");
  if (ed) cjobEdit(cjobFind(ed.dataset.cjEdit).it?.result);
});

// "Editar": deja escrito "Edita «imagen_….png»: " para pedir el cambio.
function cjobEdit(r) {
  const input = $("#chat-input");
  if (!r || !input) return;
  input.value = t("cj.edit_prefix", { name: r.name });
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

// ¿Hay que esperar? Solo imágenes y ediciones en modo "intercambio" (el
// video corre de fondo: se puede seguir charlando).
const cjobHolding = () => cjobLive().some(({ m }) => m.data.hold && m.data.kind !== "video");

function featureHoldSend(send, text) {
  if (!cjobHolding()) return false;
  CJOB.held.push(send);
  CHAT.messages.push({ role: "event", icon: "hourglass", text: t("cj.held", { text: String(text || "").slice(0, 60) }) });
  renderChatLog();
  return true;
}

async function cjobRelease() {
  if (!CJOB.held.length || cjobHolding() || CHAT.busy) return;
  const queue = CJOB.held.splice(0);
  for (const send of queue) {
    await send();
    while (CHAT.busy) await new Promise((ok) => setTimeout(ok, 300));
  }
}

// Aviso del servidor al terminar (también si estás en otro chat o la
// página está en segundo plano: el video avisa siempre).
NOTIFY_HANDLERS.comfyui = (ev) => {
  const j = ev.job;
  if (!j) return;
  if (cjobFind(j.id).m) return cjobUpdate(j);
  if (j.status === "done" && !CJOB.notified.has(j.id)) {
    CJOB.notified.add(j.id);
    toast(t(`cj.ready_${j.kind}`), "ok", 8000);
    systemNotify(t(`cj.ready_${j.kind}`), j.label || "", `cj-${j.id}`);
    if (j.kind === "video") chime(1);
  }
};

// ── Ajustes → Plugins → ComfyUI: modelos, flujos y mapeo ──────────────
const CU = { st: null, loading: false, open: {}, path: null, timer: null };
const CU_ROLES = ["prompt", "negative", "seed", "width", "height", "length", "fps", "image", "image2", "image3", "model", "model2", "steps", "cfg", "denoise"];
const CU_TASKS = ["image", "edit", "video"];

async function cuLoad(refresh = false) {
  if (CU.loading) return;
  CU.loading = true;
  cuRender();
  try {
    CU.st = await api("GET", `/api/plugin/comfyui/admin${refresh ? "?refresh=1" : ""}`);
  } catch (ex) {
    CU.st = { connected: false, error: ex.message };
  }
  CU.loading = false;
  cuRender();
}

async function cuPost(action, body, okMsg = t("pl.saved")) {
  try {
    CU.st = await api("POST", `/api/plugin/comfyui/${action}`, body);
    cuRender();
    toast(okMsg);
  } catch (ex) {
    toast(ex.message, "error");
  }
}

function cuRender() {
  const box = $("[data-cu-panel]");
  if (!box) return;
  const st = CU.st;
  if (!st) {
    box.innerHTML = `<p class="note">${esc(t("loading"))}</p>`;
    if (!CU.loading) cuLoad();
    return;
  }
  const dev = st.stats?.devices?.[0];
  const gb = (n) => (n / 1024 ** 3).toFixed(1);
  const gpu = dev ? String(dev.name || "").replace(/^cuda:\d+\s*/, "").replace(/\s*:.*$/, "") : "";
  const head = st.connected
    ? `<span class="badge good">${esc(t("cu.connected"))}</span> <span>ComfyUI ${esc(st.stats?.version || "")}${dev ? ` · ${esc(gpu)} · ${esc(t("cu.vram_free", { free: gb(dev.vram_free), total: gb(dev.vram_total) }))}` : ""}</span>`
    : `<span class="badge bad">${esc(t("cu.disconnected"))}</span> <span>${esc(t("cu.not_running", { url: st.url || "" }))}</span>`;
  const refresh = `<button class="btn btn-sm" type="button" data-cu="refresh" ${CU.loading ? "disabled" : ""}>${esc(t(CU.loading ? "loading" : "cu.refresh"))}</button>`;
  const vr = st.vram?.swapped ? `<small class="note">${esc(t("cu.swapped", { models: (st.vram.remember || []).join(", ") || "—" }))}</small>` : "";
  cuWatchStart(st);
  if (!st.connected || !st.workflows) {
    box.innerHTML = `<div class="cu-head">${head}${refresh}</div>${vr}${st.error ? `<small class="err">${esc(st.error)}</small>` : ""}
      ${cuInstall(st)}${cuHf(st)}${cuDisk(st)}`;
    cuHfBind();
    return;
  }
  const wfs = st.workflows;
  const wfName = (id) => wfs.find((w) => w.id === id)?.name || id;
  const taskRows = CU_TASKS.map((task) => {
    const tc = st.tasks?.[task] || {};
    const usable = st.usable?.[task] || [];
    const choices = wfs.filter((w) => !w.error && (w.task === task || w.suggested === task || w.id === tc.workflow));
    const chosen = wfs.find((w) => w.id === (tc.workflow || usable[0]));
    const opts = `<option value="">${esc(t("cu.auto", { name: usable[0] ? wfName(usable[0]) : t("cu.none") }))}</option>`
      + choices.map((w) => `<option value="${esc(w.id)}" ${w.id === tc.workflow ? "selected" : ""}>${esc(w.name)}</option>`).join("");
    const models = chosen?.models || [];
    const modelSel = models.length
      ? `<select class="text-input" data-cu-task="${task}" data-k="model" aria-label="${esc(t("cu.model"))}">
        <option value="">${esc(t("cu.model_wf"))}</option>${models.map((n) => `<option ${n === tc.model ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`
      : `<small class="note">${esc(t("cu.model_none"))}</small>`;
    const num = (k) => `<input class="text-input" type="number" min="0" data-cu-task="${task}" data-k="${k}" value="${esc(tc[k] || "")}"
      placeholder="${esc(t(`cu.${k}`))}" aria-label="${esc(t(`cu.${k}`))}" title="${esc(t(`cu.${k}`))}">`;
    const extra = task === "edit" ? "" : `<div class="cu-nums">${num("width")}${num("height")}${task === "video" ? num("duration") : ""}${num("steps")}</div>`;
    return `<div class="cu-task"><strong>${cjobIcon(task)} ${esc(t(`cu.task_${task}`))}</strong>
      <select class="text-input" data-cu-task="${task}" data-k="workflow" aria-label="${esc(t("cu.workflow"))}">${opts}</select>${modelSel}${extra}
      <small class="note">${esc(chosen ? t("cu.eta", { s: Math.round(chosen.eta) }) : t("cu.no_wf"))}</small></div>`;
  }).join("");
  const wfRows = wfs.map((w) => {
    const warn = [w.error, w.missing_nodes?.length ? t("cu.miss_nodes", { list: w.missing_nodes.join(", ") }) : "",
      w.missing_models?.length ? t("cu.miss_models", { list: w.missing_models.join(", ") }) : ""].filter(Boolean);
    const taskSel = `<select class="text-input" data-cu-wf="${esc(w.id)}" ${w.error ? "disabled" : ""} aria-label="${esc(t("cu.task"))}">
      <option value="" ${!w.task_saved ? "selected" : ""}>${esc(t("cu.task_auto", { s: w.suggested ? t(`cu.task_${w.suggested}`) : t("cu.none") }))}</option>
      ${CU_TASKS.map((x) => `<option value="${x}" ${w.task_saved === x ? "selected" : ""}>${esc(t(`cu.task_${x}`))}</option>`).join("")}
      <option value="none" ${w.task_saved === "none" ? "selected" : ""}>${esc(t("cu.task_none"))}</option></select>`;
    return `<div class="cu-wf ${w.task ? "on" : ""}">
      <div class="cu-wf-head"><div class="cu-wf-name"><strong>${esc(w.name)}</strong>
        <span class="badge">${esc(t(`cu.src_${w.source}`))}</span>${w.task ? `<span class="badge use">${esc(t(`cu.task_${w.task}`))}</span>` : ""}</div>
        ${taskSel}</div>
      ${warn.map((x) => `<small class="err">${esc(x)}</small>`).join("")}
      <div class="cu-wf-acts">${w.error ? "" : `<button class="link" type="button" data-cu-map="${esc(w.id)}">${esc(t(CU.open[w.id] ? "cu.map_hide" : "cu.map_show", { n: w.mapping.length }))}</button>`}
      ${w.source === "folder" ? `<button class="link" type="button" data-cu-del="${esc(w.id)}">${esc(t("cu.delete"))}</button>` : ""}</div>
      ${CU.open[w.id] ? cuMapping(w) : ""}</div>`;
  }).join("");
  box.innerHTML = `<div class="cu-head">${head}${refresh}</div>${vr}
    ${cuInstall(st)}${cuHf(st)}
    <h4>${esc(t("cu.tasks"))}</h4><p class="note">${esc(t("cu.tasks_sub"))}</p>
    <div class="cu-tasks">${taskRows}</div>
    <div class="mcp-acts"><button class="btn btn-sm btn-primary" type="button" data-cu="save-tasks">${esc(t("pl.save"))}</button></div>
    <h4>${esc(t("cu.workflows"))}</h4><p class="note">${esc(t("cu.workflows_sub"))}</p>
    <div class="cu-wfs">${wfRows}</div>
    <div class="mcp-acts"><label class="btn btn-sm">${esc(t("cu.import"))}<input type="file" accept=".json,application/json" data-cu-import hidden></label>
      <small class="note">${esc(t("cu.import_sub", { folder: st.folder }))}</small></div>`;
  cuHfBind();
}

// Modelos de ComfyUI desde Hugging Face: un archivo de un repo a la
// subcarpeta de models\ que corresponda (se sugiere por el nombre).
const CUHF = { repo: "", info: null, loading: false, error: "", job: null, timer: null, filter: "" };

function cuHf(st) {
  const inst = st.install || {};
  if (!inst.path || inst.missing) return "";
  const i = CUHF.info;
  const job = CUHF.job;
  const running = job?.state === "running";
  const pct = job?.total ? Math.floor((job.completed / job.total) * 100) : 0;
  const jobHtml = !job || job.state === "idle" ? "" : running
    ? `<div class="progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
       <div class="pull-state">${esc(t("cuhf.running", { name: job.label, pct, done: fmtSize(job.completed), total: fmtSize(job.total) }))}
       <button class="icon-btn small danger" type="button" data-cuhf="cancel" title="${esc(t("cuhf.cancel"))}" aria-label="${esc(t("cuhf.cancel"))}">${svgIcon("x", 14)}</button></div>`
    : `<div class="pull-state ${job.state === "done" ? "" : "error"}">${esc(t(`cuhf.${job.state}`, { name: job.label || "", error: job.error || "" }))}</div>`;
  const f = CUHF.filter.toLowerCase();
  const files = i ? i.files.filter((x) => !f || x.path.toLowerCase().includes(f)) : [];
  return `<details class="cu-hf" ${CUHF.open ? "open" : ""} data-cuhf-wrap><summary>${svgIcon("download", 15)} ${esc(t("cuhf.title"))}</summary>
    <p class="note">${esc(t("cuhf.sub"))}</p>
    <form class="ic-row" data-cuhf-form>
      <input class="text-input" data-cuhf-repo value="${esc(CUHF.repo)}" placeholder="${esc(t("cuhf.ph"))}" spellcheck="false" autocomplete="off" autocapitalize="off" aria-label="${esc(t("cuhf.ph"))}">
      <button class="btn" type="submit" title="${esc(t("hf.search"))}" aria-label="${esc(t("hf.search"))}" ${CUHF.loading ? "disabled" : ""}>${svgIcon("search", 16)}</button>
    </form>
    ${CUHF.error ? `<small class="err">${esc(CUHF.error)}</small>` : ""}
    ${CUHF.loading ? `<p class="note">${esc(t("hf.loading"))}</p>` : ""}
    ${i ? `<div class="hf-quants-head"><strong>${esc(i.id)}</strong>${i.private || i.gated ? `<span class="badge bad">${esc(t(i.private ? "hf.private" : "hf.gated"))}</span>` : ""}
        <a class="icon-btn small" href="https://huggingface.co/${esc(i.id)}" target="_blank" rel="noopener" title="${esc(t("hf.open"))}" aria-label="${esc(t("hf.open"))}">${svgIcon("globe", 14)}</a></div>
      ${i.files.length > 8 ? `<input class="text-input" data-cuhf-filter value="${esc(CUHF.filter)}" placeholder="${esc(t("cuhf.filter"))}" aria-label="${esc(t("cuhf.filter"))}">` : ""}
      <div class="cuhf-files">${files.map((x) => `<div class="hf-quant cuhf-file">
          <span class="cuhf-name" title="${esc(x.path)}">${esc(x.path)}</span><span class="mm-meta">${esc(fmtSize(x.size))}</span>
          <select class="text-input" data-cuhf-folder="${esc(x.path)}" aria-label="${esc(t("cuhf.folder"))}" title="${esc(t("cuhf.folder"))}">
            ${i.folders.map((d) => `<option ${d === x.folder ? "selected" : ""}>${esc(d)}</option>`).join("")}</select>
          <button class="icon-btn" type="button" data-cuhf="dl" data-path="${esc(x.path)}" ${running ? "disabled" : ""} title="${esc(t("cuhf.download"))}" aria-label="${esc(t("cuhf.download"))}">${svgIcon("download", 16)}</button>
        </div>`).join("") || `<p class="empty">${esc(t("cuhf.none"))}</p>`}</div>` : ""}
    ${jobHtml}
  </details>`;
}

function cuHfPaint() {
  const old = $("[data-cuhf-wrap]");
  if (!old || !CU.st) return;
  const tmp = document.createElement("div");
  tmp.innerHTML = cuHf(CU.st);
  const fresh = tmp.firstElementChild;
  if (fresh) old.replaceWith(fresh);
  cuHfBind();
}

async function cuHfPoll() {
  clearTimeout(CUHF.timer);
  const was = CUHF.job?.state;
  try {
    CUHF.job = await api("GET", "/api/plugin/comfyui/hf_status");
  } catch {
    return;
  }
  cuHfPaint();
  if (CUHF.job.state === "running") CUHF.timer = setTimeout(cuHfPoll, 1000);
  else if (CUHF.job.state === "done" && was === "running") {
    toast(t("cuhf.done", { name: CUHF.job.label }));
    cuLoad(true);
  }
}

function cuHfBind() {
  const wrap = $("[data-cuhf-wrap]");
  if (!wrap) return;
  wrap.ontoggle = () => {
    CUHF.open = wrap.open;
    if (wrap.open && !CUHF.job) cuHfPoll();
  };
  const repoInput = $("[data-cuhf-repo]", wrap);
  if (repoInput) repoInput.oninput = () => { CUHF.repo = repoInput.value; };
  wrap.onsubmit = async (e) => {
    e.preventDefault();
    CUHF.repo = $("[data-cuhf-repo]", wrap).value.trim();
    if (!CUHF.repo) return;
    CUHF.loading = true;
    CUHF.error = "";
    CUHF.info = null;
    cuHfPaint();
    try {
      CUHF.info = await api("POST", "/api/plugin/comfyui/hf_files", { repo: CUHF.repo });
    } catch (ex) {
      CUHF.error = ex.message;
    }
    CUHF.loading = false;
    cuHfPaint();
  };
  const filter = $("[data-cuhf-filter]", wrap);
  if (filter) filter.oninput = () => {
    CUHF.filter = filter.value;
    const pos = filter.selectionStart;
    cuHfPaint();
    const again = $("[data-cuhf-filter]");
    again?.focus();
    again?.setSelectionRange(pos, pos);
  };
  wrap.onclick = async (e) => {
    e.stopPropagation();
    const b = e.target.closest("[data-cuhf]");
    if (!b) return;
    if (b.dataset.cuhf === "cancel") {
      await api("POST", "/api/plugin/comfyui/hf_cancel", {}).catch(() => {});
      return cuHfPoll();
    }
    if (b.dataset.cuhf === "dl") {
      const sel = wrap.querySelector(`[data-cuhf-folder="${CSS.escape(b.dataset.path)}"]`);
      try {
        CUHF.job = await api("POST", "/api/plugin/comfyui/hf_download", { repo: CUHF.info.id, path: b.dataset.path, folder: sel.value });
        cuHfPoll();
      } catch (ex) {
        toast(ex.message, "error", 7000);
      }
    }
  };
}


// Dónde está ComfyUI (ver plugins/comfyui/cu_locate.py): lo detectado
// (portable o Desktop), o la carpeta elegida a mano con el explorador de
// carpetas de la app; y el botón para arrancarlo si está cerrado.
function cuInstall(st) {
  const inst = st.install || {};
  const found = inst.path && !inst.missing;
  const kind = found ? t(`cu.kind_${inst.kind || "portable"}`) : "";
  const status = st.detecting
    ? `<small class="note">${esc(t("cu.detecting"))}</small>`
    : inst.missing
      ? `<small class="err">${esc(t("cu.path_missing", { path: inst.path }))}</small>`
      : found
        ? `<div class="cu-inst-found"><span class="badge good">${esc(kind)}</span>${inst.version ? `<span class="badge">v${esc(inst.version)}</span>` : ""}
            <span class="badge">${esc(t(inst.manual ? "cu.path_manual" : "cu.path_auto"))}</span>
            <code class="cu-path" title="${esc(inst.path)}">${esc(inst.path)}</code>
            <small class="note">${esc(t("cu.inst_url", { url: inst.url || "" }))}${st.url_auto ? ` · ${esc(t("cu.url_from_inst"))}` : ""}</small></div>`
        : `<small class="note">${esc(t("cu.not_found"))}</small>`;
  const others = (st.installs || []).filter((x) => x.path !== inst.path);
  const start = !st.connected && found && inst.can_start
    ? `<button class="btn btn-sm btn-primary" type="button" data-cu="start" ${st.starting ? "disabled" : ""}>${svgIcon("play", 15)} ${esc(t(st.starting ? "cu.starting" : "cu.start"))}</button>`
    : "";
  const value = CU.path ?? (inst.manual ? inst.path : "");
  return `<div class="cu-inst"><h4>${svgIcon("folder", 15)} ${esc(t("cu.install"))}</h4>
    <p class="note">${esc(t("cu.install_sub"))}</p>${status}
    ${others.length ? `<div class="cu-inst-others">${others.map((x) => `<div class="cu-inst-other"><span class="badge">${esc(t(`cu.kind_${x.kind}`))}</span>
      <code class="cu-path" title="${esc(x.path)}">${esc(x.path)}</code>
      <button class="link" type="button" data-cu-use="${esc(x.path)}">${esc(t("cu.use_this"))}</button></div>`).join("")}</div>` : ""}
    <div class="cu-inst-row">
      <input class="text-input" type="text" data-cu-path value="${esc(value)}" placeholder="${esc(t("cu.path_ph"))}"
        aria-label="${esc(t("cu.path"))}" autocomplete="off" spellcheck="false">
      <button class="btn btn-sm" type="button" data-cu="browse">${svgIcon("folder", 15)} ${esc(t("cu.browse"))}</button>
      <button class="btn btn-sm" type="button" data-cu="path-save">${svgIcon("check", 15)} ${esc(t("cu.path_save"))}</button>
    </div>
    <div class="mcp-acts">${start}
      <button class="btn btn-sm" type="button" data-cu="locate" ${st.detecting ? "disabled" : ""}>${svgIcon("search", 15)} ${esc(t("cu.detect"))}</button>
      ${inst.manual ? `<button class="btn btn-sm" type="button" data-cu="path-auto">${esc(t("cu.path_auto_btn"))}</button>` : ""}</div></div>`;
}

// Con ComfyUI cerrado: los flujos y modelos que hay en su carpeta.
function cuDisk(st) {
  const d = st.disk;
  if (!d) return "";
  const models = Object.entries(d.models || {});
  const nModels = models.reduce((n, [, v]) => n + v.length, 0);
  return `<details class="cu-disk"><summary>${esc(t("cu.disk", { w: d.workflows.length, m: nModels }))}</summary>
    <p class="note">${esc(t("cu.disk_sub"))}</p>
    ${d.workflows.length ? `<h4>${esc(t("cu.workflows"))}</h4><ul class="cu-disk-list">${d.workflows.map((w) => `<li>${esc(w.replace(/\.json$/i, ""))}</li>`).join("")}</ul>` : ""}
    ${models.map(([k, v]) => `<h4>${esc(k)} (${v.length})</h4><ul class="cu-disk-list">${v.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`).join("")}
  </details>`;
}

// Tras «Arrancar», se pregunta cada pocos segundos hasta que responda.
function cuWatchStart(st) {
  clearTimeout(CU.timer);
  if (st.starting && !st.connected) CU.timer = setTimeout(() => { if ($("[data-cu-panel]")) cuLoad(); }, 4000);
  else if (st.detecting) CU.timer = setTimeout(() => { if ($("[data-cu-panel]")) cuLoad(); }, 2000);
}

// Explorador de carpetas (del servidor: el navegador no da rutas completas).
async function cuBrowse(start) {
  let dlg = $("#cu-browse");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "cu-browse";
    dlg.className = "cu-browse-dlg";
    document.body.append(dlg);
  }
  const show = async (path) => {
    let r;
    try {
      r = await api("POST", "/api/plugin/comfyui/browse", { path });
    } catch (ex) {
      if (path) return show(""); // la ruta escrita no existe: desde las unidades
      toast(ex.message, "error");
      return dlg.close();
    }
    dlg.innerHTML = `<header class="fp-head"><div class="fp-title"><span class="fp-ico">${svgIcon("folder", 18)}</span>
        <div><strong>${esc(t("cu.browse_title"))}</strong><small>${esc(r.path || t("cu.browse_drives"))}</small></div></div>
        <button type="button" class="icon-btn" data-cb="close" aria-label="${esc(t("chat.close"))}">${svgIcon("x", 18)}</button></header>
      <div class="cu-browse-list">
        ${r.parent != null && r.path ? `<button type="button" class="cu-browse-item" data-cb-go="${esc(r.parent)}">${svgIcon("arrowLeft", 15)} ${esc(t("cu.browse_up"))}</button>` : ""}
        ${r.dirs.map((d) => `<button type="button" class="cu-browse-item ${d.comfy ? "comfy" : ""}" data-cb-go="${esc(d.path)}">${svgIcon("folder", 15)}
          <span>${esc(d.name)}</span>${d.comfy ? `<span class="badge good">ComfyUI</span>` : ""}</button>`).join("")
        || `<p class="note">${esc(t("cu.browse_empty"))}</p>`}
      </div>
      <div class="cu-browse-foot">${r.here ? `<span class="badge good">${esc(t("cu.browse_ok"))}</span>` : `<small class="note">${esc(t("cu.browse_hint"))}</small>`}
        <button type="button" class="btn btn-sm btn-primary" data-cb="pick" ${r.path ? "" : "disabled"}>${esc(t("cu.browse_pick"))}</button></div>`;
    dlg.onclick = (e) => {
      if (e.target === dlg || e.target.closest("[data-cb=close]")) return dlg.close();
      const go = e.target.closest("[data-cb-go]");
      if (go) return show(go.dataset.cbGo);
      if (e.target.closest("[data-cb=pick]") && r.path) {
        dlg.close();
        CU.path = r.path;
        cuPost("install", { path: r.path }).then(() => { CU.path = null; cuRender(); });
      }
    };
  };
  if (!dlg.open) dlg.showModal();
  dlg.innerHTML = `<p class="note">${esc(t("loading"))}</p>`;
  show(start || "");
}

// Qué entrada del flujo es el prompt, la semilla, el tamaño…
function cuMapping(w) {
  const key = (f) => `${f.node}|${f.input}`;
  const label = (f) => `#${f.node} ${f.title && f.title !== f.class ? `${f.title} (${f.class})` : f.class} · ${f.input} = ${String(f.value).slice(0, 40)}`;
  const rows = CU_ROLES.map((role) => {
    const cur = w.mapping.filter((m) => m.role === role).map((m) => `${m.node}|${m.input}`);
    const opts = w.fields.map((f) => `<option value="${esc(key(f))}" ${cur.includes(key(f)) ? "selected" : ""}>${esc(label(f))}</option>`).join("");
    // Lo que no es un valor fijo (p. ej. un ancho que llega enlazado) también se puede elegir si ya estaba.
    const extra = cur.filter((c) => !w.fields.some((f) => key(f) === c)).map((c) => `<option value="${esc(c)}" selected>#${esc(c.replace("|", " · "))}</option>`).join("");
    return `<label class="cu-map-row"><span>${esc(t(`cu.role_${role}`))}</span>
      <select class="text-input" data-cu-role="${role}"><option value="">—</option>${extra}${opts}</select></label>`;
  }).join("");
  return `<div class="cu-map" data-cu-mapwf="${esc(w.id)}"><p class="note">${esc(t("cu.map_sub"))}</p>${rows}
    <div class="mcp-acts"><button class="btn btn-sm btn-primary" type="button" data-cu-mapsave="${esc(w.id)}">${esc(t("cu.map_save"))}</button>
    ${w.custom_mapping ? `<button class="btn btn-sm" type="button" data-cu-mapreset="${esc(w.id)}">${esc(t("cu.map_reset"))}</button>` : ""}</div></div>`;
}

function cuMount() {
  const box = $("[data-cu-panel]");
  if (!box) return;
  cuRender();
  box.onclick = (e) => {
    e.stopPropagation();
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.cu === "refresh") return cuLoad(true);
    if (b.dataset.cu === "locate") return cuPost("locate", {}, t("cu.detected"));
    if (b.dataset.cu === "start") return cuPost("start", {}, t("cu.start_sent"));
    if (b.dataset.cu === "browse") return cuBrowse($("[data-cu-path]", box)?.value.trim() || CU.st?.install?.path || "");
    if (b.dataset.cu === "path-save") {
      const path = $("[data-cu-path]", box)?.value.trim() || "";
      if (!path) return toast(t("cu.path_empty"), "warn");
      CU.path = path;
      return cuPost("install", { path }).then(() => { CU.path = null; cuRender(); });
    }
    if (b.dataset.cu === "path-auto") return cuPost("install", { path: "" });
    if (b.dataset.cuUse) return cuPost("install", { path: b.dataset.cuUse });
    if (b.dataset.cu === "save-tasks") {
      const tasks = {};
      $$("[data-cu-task]", box).forEach((el) => { (tasks[el.dataset.cuTask] ||= {})[el.dataset.k] = el.value; });
      return cuPost("tasks", { tasks });
    }
    if (b.dataset.cuMap) {
      CU.open[b.dataset.cuMap] = !CU.open[b.dataset.cuMap];
      return cuRender();
    }
    if (b.dataset.cuMapreset) return cuPost("workflow", { id: b.dataset.cuMapreset, mapping: null });
    if (b.dataset.cuMapsave) {
      const wrap = box.querySelector(`[data-cu-mapwf="${CSS.escape(b.dataset.cuMapsave)}"]`);
      const mapping = [];
      $$("[data-cu-role]", wrap).forEach((sel) => {
        if (!sel.value) return;
        const [node, input] = sel.value.split("|");
        mapping.push({ role: sel.dataset.cuRole, node, input });
      });
      // La semilla puede estar en varios nodos (p. ej. dos samplers): se conservan los demás detectados.
      const w = CU.st.workflows.find((x) => x.id === b.dataset.cuMapsave);
      const seedSel = mapping.find((m) => m.role === "seed");
      (w?.mapping || []).filter((m) => m.role === "seed" && seedSel && !(m.node === seedSel.node && m.input === seedSel.input))
        .forEach((m) => mapping.push(m));
      return cuPost("workflow", { id: b.dataset.cuMapsave, mapping });
    }
    if (b.dataset.cuDel) return cuPost("delete", { id: b.dataset.cuDel });
  };
  box.onchange = async (e) => {
    e.stopPropagation();
    const el = e.target;
    if (el.dataset.cuWf) return cuPost("workflow", { id: el.dataset.cuWf, task: el.value || null });
    if (el.dataset.cuTask) {
      // Se guarda al elegir (antes había que tocar "Guardar" y era fácil olvidarlo).
      const tasks = {};
      $$("[data-cu-task]", box).forEach((x) => { (tasks[x.dataset.cuTask] ||= {})[x.dataset.k] = x.value; });
      return cuPost("tasks", { tasks });
    }
    if (el.matches("[data-cu-import]") && el.files[0]) {
      try {
        const wf = JSON.parse(await el.files[0].text());
        await cuPost("import", { name: el.files[0].name, workflow: wf });
      } catch {
        toast(t("cu.import_bad"), "error");
      }
    }
  };
}

// ── Visor de imágenes con zoom (dentro de la app) ──────────────────────
// Para las imágenes de ComfyUI, los archivos y los adjuntos: pantalla
// completa, rueda o pellizco para acercar (hacia donde apuntas), arrastrar
// para moverla, doble clic/toque para acercar o volver, y + / − / ajustar.
const IV = { s: 1, x: 0, y: 0, pts: new Map(), pinch: null, drag: null, onEdit: null };

function openImageViewer(url, name = "", { video = false, onEdit = null } = {}) {
  let dlg = $("#img-viewer");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "img-viewer";
    dlg.className = "img-viewer";
    document.body.append(dlg);
  }
  Object.assign(IV, { s: 1, x: 0, y: 0, pts: new Map(), pinch: null, drag: null, onEdit });
  const media = video
    ? `<video src="${esc(url)}" controls autoplay playsinline loop></video>`
    : `<img src="${esc(url)}" alt="${esc(name)}" draggable="false">`;
  const zoom = video ? "" : `<button class="icon-btn" type="button" data-iv="out" aria-label="${esc(t("iv.out"))}" title="${esc(t("iv.out"))}">−</button>
      <button class="btn btn-sm btn-quiet iv-pct" type="button" data-iv="fit" title="${esc(t("iv.fit"))}">100%</button>
      <button class="icon-btn" type="button" data-iv="in" aria-label="${esc(t("iv.in"))}" title="${esc(t("iv.in"))}">+</button>`;
  dlg.innerHTML = `<div class="iv-bar"><strong title="${esc(name)}">${esc(name)}</strong><span class="spacer"></span>${zoom}
      ${onEdit ? `<button class="btn btn-sm" type="button" data-iv="edit">✏️ ${esc(t("cj.edit"))}</button>` : ""}
      <a class="btn btn-sm btn-primary" href="${esc(url)}" download="${esc(name)}">${esc(t("file.download"))}</a>
      <button class="icon-btn" type="button" data-iv="close" aria-label="${esc(t("cam.cancel"))}">${ICON.close}</button></div>
    <div class="iv-stage ${video ? "video" : ""}">${media}</div>`;
  dlg.showModal();
  if (!video) ivWire(dlg);
  dlg.onclick = (e) => {
    const b = e.target.closest("[data-iv]");
    if (!b) return;
    const act = b.dataset.iv;
    if (act === "close") return dlg.close();
    if (act === "edit") {
      dlg.close();
      return IV.onEdit?.();
    }
    const st = $(".iv-stage", dlg).getBoundingClientRect();
    if (act === "in") ivZoom(IV.s * 1.5, st.width / 2, st.height / 2);
    if (act === "out") ivZoom(IV.s / 1.5, st.width / 2, st.height / 2);
    if (act === "fit") ivZoom(1, 0, 0, true);
  };
  dlg.onclose = () => { dlg.innerHTML = ""; }; // corta el video si sonaba
}

function ivApply() {
  const img = $("#img-viewer .iv-stage img");
  if (!img) return;
  img.style.transform = `translate(${IV.x}px, ${IV.y}px) scale(${IV.s})`;
  img.style.cursor = IV.s > 1 ? (IV.drag ? "grabbing" : "grab") : "zoom-in";
  const pct = $("#img-viewer .iv-pct");
  if (pct) pct.textContent = `${Math.round(IV.s * 100)}%`;
}

// Acerca a `s` dejando quieto el punto (cx, cy) del escenario bajo el cursor.
function ivZoom(s, cx, cy, reset = false) {
  const stage = $("#img-viewer .iv-stage");
  if (!stage) return;
  s = Math.min(12, Math.max(1, s));
  if (reset || s === 1) {
    Object.assign(IV, { s: 1, x: 0, y: 0 });
    return ivApply();
  }
  const r = stage.getBoundingClientRect();
  const px = cx - r.width / 2;
  const py = cy - r.height / 2;
  IV.x = px - ((px - IV.x) * s) / IV.s;
  IV.y = py - ((py - IV.y) * s) / IV.s;
  IV.s = s;
  ivApply();
}

function ivWire(dlg) {
  const stage = $(".iv-stage", dlg);
  const rel = (e) => {
    const r = stage.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  stage.onwheel = (e) => {
    e.preventDefault();
    ivZoom(IV.s * Math.exp(-e.deltaY * 0.0015), ...rel(e));
  };
  stage.ondblclick = (e) => (IV.s > 1 ? ivZoom(1, 0, 0, true) : ivZoom(2.5, ...rel(e)));
  stage.onpointerdown = (e) => {
    stage.setPointerCapture(e.pointerId);
    IV.pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (IV.pts.size === 2) {
      const [a, b] = [...IV.pts.values()];
      IV.pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, s: IV.s };
      IV.drag = null;
    } else IV.drag = { x: e.clientX - IV.x, y: e.clientY - IV.y };
    ivApply();
  };
  stage.onpointermove = (e) => {
    if (!IV.pts.has(e.pointerId)) return;
    IV.pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (IV.pinch && IV.pts.size === 2) {
      const [a, b] = [...IV.pts.values()];
      const r = stage.getBoundingClientRect();
      ivZoom(IV.pinch.s * (Math.hypot(a[0] - b[0], a[1] - b[1]) / IV.pinch.d), (a[0] + b[0]) / 2 - r.left, (a[1] + b[1]) / 2 - r.top);
    } else if (IV.drag && IV.s > 1) {
      IV.x = e.clientX - IV.drag.x;
      IV.y = e.clientY - IV.drag.y;
      ivApply();
    }
  };
  stage.onpointerup = stage.onpointercancel = (e) => {
    IV.pts.delete(e.pointerId);
    if (IV.pts.size < 2) IV.pinch = null;
    if (!IV.pts.size) IV.drag = null;
    else {
      const [p] = [...IV.pts.values()];
      IV.drag = { x: p[0] - IV.x, y: p[1] - IV.y };
    }
    ivApply();
  };
  ivApply();
}

// Imágenes de los archivos convertidos y otras tarjetas: abrir en el visor.
document.addEventListener("click", (e) => {
  const v = e.target.closest("[data-iv-open]");
  if (!v) return;
  e.preventDefault();
  openImageViewer(v.dataset.ivOpen, v.dataset.ivName || "", { video: v.dataset.ivVideo === "1" });
});


// ── Dashboard de inicio y Bibliotecas de Medios y Archivos ─────────────
const DASH = {
  data: null,
  loading: false,
  mediaFilter: { q: "", kind: "all", preset: "all", from: "", to: "", sort: "date_desc" },
  filesFilter: { q: "", kind: "all", preset: "all", from: "", to: "", sort: "date_desc" },
  sel: { media: new Set(), files: new Set() }, // elegidos para borrar varios a la vez
};

FEATURE_CARDS.gallery.push({
  id: "home-dashboard-mount",
  when: () => true,
  html: () => "",
  render: () => {
    renderHomeDashboard();
    loadDashboardData().then(() => {
      if (S.view?.kind === "gallery") renderHomeDashboard();
    });
  },
});

FEATURE_VIEWS.media = {
  title: () => t("lib.media_title"),
  render: () => {
    renderMediaView();
    loadDashboardData().then(() => {
      if (S.view?.kind === "media") renderMediaView();
    });
  },
};

FEATURE_VIEWS.files = {
  title: () => t("lib.files_title"),
  render: () => {
    renderFilesView();
    loadDashboardData().then(() => {
      if (S.view?.kind === "files") renderFilesView();
    });
  },
};

async function loadDashboardData() {
  if (DASH.loading) return DASH.data;
  DASH.loading = true;
  try {
    const res = await api("GET", "/api/dashboard");
    if (isGuest() && res?.skills_stats) {
      const gMem = guestGet("memory", []);
      const gLists = guestGet("lists", []);
      res.skills_stats.memory_count = Array.isArray(gMem) ? gMem.length : 0;
      res.skills_stats.lists_count = Array.isArray(gLists) ? gLists.length : 0;
    }
    DASH.data = res;
    return res;
  } catch (e) {
    console.error(e);
    return DASH.data;
  } finally {
    DASH.loading = false;
  }
}

function fmtGpuTime(secs) {
  const s = Number(secs) || 0;
  if (s <= 0) return "0 s";
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  if (m < 60) return rem ? `${m} min ${rem} s` : `${m} min`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h} h ${rm} min`;
}

function fmtShortDate(ts) {
  if (!ts) return "—";
  try {
    return new Date(ts * 1000).toLocaleString(S.lang === "es" ? "es" : "en", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function renderHomeDashboard() {
  const box = $("#home-dashboard");
  if (!box) return;
  const d = DASH.data;
  const userName = S.data?.user_context?.nombre || ME()?.name || "AuraVox";
  const cs = d?.chat_stats || { total_messages: 0, user_messages: 0, assistant_messages: 0, total_words: 0, active_chats: 0, total_assistants: (S.data?.assistants || []).length, tool_events: 0 };
  const ms = d?.media_stats || { total: 0, images: 0, edits: 0, videos: 0, total_jobs: 0, total_gpu_seconds: 0, total_bytes: 0 };
  const fs = d?.file_stats || { total: 0, generated_count: 0, attachment_count: 0, total_bytes: 0 };
  const ss = d?.skills_stats || { memory_count: 0, reminders_pending: 0, lists_count: 0, routines_count: 0, docs_count: 0, cloned_voices_count: 0 };
  const byAsst = d?.by_assistant || (S.data?.assistants || []).map((a) => ({
    name: a.name, label: displayName(a), model: a.base_model, voice: a.voice, color: a.color,
    messages: 0, words: 0, media_count: 0, files_count: 0, docs_count: 0,
  }));
  const maxScore = Math.max(1, ...byAsst.map((a) => (a.messages || 0) + (a.media_count || 0) * 2 + (a.files_count || 0)));
  const recentMedia = (d?.media || []).slice(0, 4);
  const recentFiles = (d?.files || []).slice(0, 4);

  box.innerHTML = `
  <div class="dash-wrap">
    <div class="dash-hero">
      <div class="dash-hero-text">
        <span class="dash-eyebrow">${svgIcon("chart", 15)} Dashboard</span>
        <h1>${esc(t("dash.welcome", { name: userName }))}</h1>
        <p>${esc(t("dash.sub"))}</p>
      </div>
      <div class="dash-hero-actions">
        <button type="button" class="btn btn-primary dash-lib-btn" data-act="open-media">
          ${svgIcon("image", 18)}
          <span>${esc(t("dash.btn_media"))}</span>
          <span class="dash-badge">${ms.total}</span>
        </button>
        <button type="button" class="btn dash-lib-btn" data-act="open-files">
          ${svgIcon("folder", 18)}
          <span>${esc(t("dash.btn_files"))}</span>
          <span class="dash-badge">${fs.total}</span>
        </button>
      </div>
    </div>

    <div class="dash-kpis">
      <article class="dash-kpi">
        <div class="dash-kpi-top">
          <span class="dash-kpi-ico accent">${svgIcon("chat", 20)}</span>
          <span class="dash-kpi-label">${esc(t("dash.kpi_chats"))}</span>
        </div>
        <strong class="dash-kpi-val">${(cs.total_messages || 0).toLocaleString()}</strong>
        <p class="dash-kpi-sub">${esc(t("dash.kpi_chats_sub", {
          user: (cs.user_messages || 0).toLocaleString(),
          asst: (cs.assistant_messages || 0).toLocaleString(),
          words: (cs.total_words || 0).toLocaleString(),
        }))}</p>
        <small class="dash-kpi-meta">${esc(t("dash.kpi_chats_meta", { active: cs.active_chats || 0, total: cs.total_assistants || 0 }))}</small>
      </article>

      <article class="dash-kpi clickable" data-act="open-media" role="button" tabindex="0">
        <div class="dash-kpi-top">
          <span class="dash-kpi-ico purple">${svgIcon("image", 20)}</span>
          <span class="dash-kpi-label">${esc(t("dash.kpi_media"))}</span>
        </div>
        <strong class="dash-kpi-val">${(ms.total || 0).toLocaleString()}</strong>
        <p class="dash-kpi-sub">${esc(t("dash.kpi_media_sub", { img: ms.images || 0, edit: ms.edits || 0, vid: ms.videos || 0 }))}</p>
        <small class="dash-kpi-meta">${esc(t("dash.kpi_media_meta", { jobs: ms.total_jobs || 0, gpu: fmtGpuTime(ms.total_gpu_seconds) }))}</small>
      </article>

      <article class="dash-kpi clickable" data-act="open-files" role="button" tabindex="0">
        <div class="dash-kpi-top">
          <span class="dash-kpi-ico amber">${svgIcon("folder", 20)}</span>
          <span class="dash-kpi-label">${esc(t("dash.kpi_files"))}</span>
        </div>
        <strong class="dash-kpi-val">${(fs.total || 0).toLocaleString()}</strong>
        <p class="dash-kpi-sub">${esc(t("dash.kpi_files_sub", { gen: fs.generated_count || 0, att: fs.attachment_count || 0 }))}</p>
        <small class="dash-kpi-meta">${esc(t("dash.kpi_files_meta", { size: fmtSize(fs.total_bytes || 0), tools: cs.tool_events || 0 }))}</small>
      </article>

      <article class="dash-kpi">
        <div class="dash-kpi-top">
          <span class="dash-kpi-ico blue">${svgIcon("brain", 20)}</span>
          <span class="dash-kpi-label">${esc(t("dash.kpi_skills"))}</span>
        </div>
        <strong class="dash-kpi-val">${(ss.memory_count || 0) + (ss.reminders_pending || 0) + (ss.docs_count || 0)}</strong>
        <p class="dash-kpi-sub">${esc(t("dash.kpi_skills_sub", { mem: ss.memory_count || 0, rem: ss.reminders_pending || 0 }))}</p>
        <small class="dash-kpi-meta">${esc(t("dash.kpi_skills_meta", {
          lists: ss.lists_count || 0,
          routines: ss.routines_count || 0,
          docs: ss.docs_count || 0,
          voices: ss.cloned_voices_count || 0,
        }))}</small>
      </article>
    </div>

    <div class="dash-panels">
      <div class="card dash-panel">
        <div class="card-head">
          <div>
            <h2>${esc(t("dash.by_asst"))}</h2>
            <p>${esc(t("dash.by_asst_sub"))}</p>
          </div>
        </div>
        <div class="dash-asst-list">
          ${byAsst.map((a) => {
            const score = (a.messages || 0) + (a.media_count || 0) * 2 + (a.files_count || 0);
            const pct = score > 0 ? Math.max(6, Math.round((score / maxScore) * 100)) : 0;
            const style = colorStyle(a);
            return `<div class="dash-asst-row" data-open="${esc(a.name)}" role="button" tabindex="0" style="${style}">
              ${orbAvatar(a, "dash-orb")}
              <div class="dash-asst-main">
                <div class="dash-asst-head">
                  <strong>${esc(a.label || displayName(a))}</strong>
                  <code>${esc(a.model || "")}</code>
                </div>
                <div class="dash-asst-bar"><span style="width:${pct}%"></span></div>
                <div class="dash-asst-stats">
                  <span>${esc(t("dash.asst_msgs", { n: a.messages || 0 }))}</span>
                  <span>· ${esc(t("dash.asst_words", { n: (a.words || 0).toLocaleString() }))}</span>
                  ${a.media_count ? `<span>· ${esc(t("dash.asst_media", { n: a.media_count }))}</span>` : ""}
                  ${a.files_count ? `<span>· ${esc(t("dash.asst_files", { n: a.files_count }))}</span>` : ""}
                  ${a.docs_count ? `<span>· ${esc(t("dash.asst_docs", { n: a.docs_count }))}</span>` : ""}
                </div>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>

      <div class="card dash-panel">
        <div class="dash-split-block">
          <div class="dash-mini-head">
            <h3>${svgIcon("image", 16)} ${esc(t("dash.recent_media"))}</h3>
            <button type="button" class="link" data-act="open-media">${esc(t("dash.view_all"))} (${ms.total}) →</button>
          </div>
          ${recentMedia.length ? `<div class="dash-media-strip">
            ${recentMedia.map((m, idx) => `<button type="button" class="dash-media-thumb" data-dash-media="${idx}" title="${esc(m.name)}">
              ${m.media_type === "video"
                ? `<video src="${esc(m.url)}" preload="metadata" muted playsinline></video><span class="dash-play-badge">${svgIcon("play", 12)}</span>`
                : `<img src="${esc(m.url)}" alt="${esc(m.name)}" loading="lazy">`}
              <span class="dash-thumb-cap">${esc(m.name)}</span>
            </button>`).join("")}
          </div>` : `<p class="note">${esc(t("dash.no_media_yet"))}</p>`}
        </div>

        <div class="dash-split-block">
          <div class="dash-mini-head">
            <h3>${svgIcon("folder", 16)} ${esc(t("dash.recent_files"))}</h3>
            <button type="button" class="link" data-act="open-files">${esc(t("dash.view_all"))} (${fs.total}) →</button>
          </div>
          ${recentFiles.length ? `<div class="dash-recent-files">
            ${recentFiles.map((f, idx) => `<button type="button" class="dash-file-row" data-dash-file="${idx}">
              <span class="dash-file-ico">${fileKindIcon(f.kind)}</span>
              <span class="dash-file-info">
                <strong>${esc(f.name)}</strong>
                <small>${esc(f.assistant_label || "")} · ${esc(fmtSize(f.size || 0))} · ${esc(fmtShortDate(f.at))}</small>
              </span>
              <span class="badge">${esc(f.ext ? f.ext.toUpperCase() : t(`lib.kind_${f.kind || "other"}`))}</span>
            </button>`).join("")}
          </div>` : `<p class="note">${esc(t("dash.no_files_yet"))}</p>`}
        </div>
      </div>
    </div>
  </div>`;
}

function fileKindIcon(kind) {
  const map = {
    image: "image",
    edit: "wand",
    video: "film",
    audio: "music",
    pdf: "book",
    doc: "note",
    sheet: "table",
    slide: "monitor",
    code: "code",
    text: "note",
  };
  return svgIcon(map[kind] || "file", 18);
}

window.openDashMediaPreview = (idx) => {
  const list = DASH.data?.media || [];
  if (list[idx]) openMediaLightbox(list, idx);
};

window.openDashFilePreview = (idx) => {
  const list = DASH.data?.files || [];
  if (list[idx]) openFilePreviewModal(list, idx);
};

// ── Filtrado y ordenamiento común por nombre y fecha ───────────────────
function matchDateFilter(ts, filter) {
  if (!ts) return true;
  const itemMs = ts * 1000;
  const now = new Date();
  if (filter.preset === "today") {
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    if (itemMs < startOfToday) return false;
  } else if (filter.preset === "7d") {
    if (itemMs < Date.now() - 7 * 86400 * 1000) return false;
  } else if (filter.preset === "30d") {
    if (itemMs < Date.now() - 30 * 86400 * 1000) return false;
  }
  if (filter.from) {
    const fromTime = new Date(`${filter.from}T00:00:00`).getTime();
    if (!Number.isNaN(fromTime) && itemMs < fromTime) return false;
  }
  if (filter.to) {
    const toTime = new Date(`${filter.to}T23:59:59.999`).getTime();
    if (!Number.isNaN(toTime) && itemMs > toTime) return false;
  }
  return true;
}

function sortLibraryItems(items, sortKey) {
  const arr = [...items];
  arr.sort((a, b) => {
    if (sortKey === "date_asc") return (a.at || 0) - (b.at || 0);
    if (sortKey === "name_asc") return String(a.name || "").localeCompare(String(b.name || ""), undefined, { numeric: true, sensitivity: "base" });
    if (sortKey === "name_desc") return String(b.name || "").localeCompare(String(a.name || ""), undefined, { numeric: true, sensitivity: "base" });
    if (sortKey === "size_desc") return (b.size || 0) - (a.size || 0);
    if (sortKey === "size_asc") return (a.size || 0) - (b.size || 0);
    return (b.at || 0) - (a.at || 0); // date_desc
  });
  return arr;
}

function filterMediaItems() {
  const all = DASH.data?.media || [];
  const f = DASH.mediaFilter;
  const q = f.q.trim().toLowerCase();
  const filtered = all.filter((m) => {
    if (f.kind !== "all") {
      if (f.kind === "video" && m.media_type !== "video" && m.kind !== "video") return false;
      if (f.kind === "image" && m.kind !== "image") return false;
      if (f.kind === "edit" && m.kind !== "edit") return false;
    }
    if (!matchDateFilter(m.at, f)) return false;
    if (q) {
      const hay = `${m.name || ""} ${m.prompt || ""} ${m.workflow || ""} ${m.assistant_label || ""} ${m.assistant || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  return sortLibraryItems(filtered, f.sort);
}

function filterFileItems() {
  const all = DASH.data?.files || [];
  const f = DASH.filesFilter;
  const q = f.q.trim().toLowerCase();
  const filtered = all.filter((it) => {
    if (f.kind !== "all") {
      if (f.kind === "generated" && it.origin !== "converted" && it.origin !== "generated") return false;
      if (f.kind === "attachment" && it.origin !== "attachment") return false;
      if (f.kind === "doc" && !["pdf", "doc", "sheet", "slide", "code", "text"].includes(it.kind)) return false;
      if (f.kind === "audio" && it.kind !== "audio") return false;
      if (f.kind === "media" && !["image", "video"].includes(it.kind)) return false;
    }
    if (!matchDateFilter(it.at, f)) return false;
    if (q) {
      const hay = `${it.name || ""} ${it.from_name || ""} ${it.assistant_label || ""} ${it.assistant || ""} ${it.info || ""} ${it.preview_text || ""} ${it.ext || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  return sortLibraryItems(filtered, f.sort);
}

// ── Vista: Biblioteca de Imágenes y Videos Generados (#/media) ─────────
// Barra de filtros de las bibliotecas: búsqueda, tipo (iconos), fechas y
// orden. Los botones solo con icono llevan title y aria-label.
function libToolbarHtml(p, f, pills) {
  const sortOpt = (k, label) => `<option value="${k}" ${f.sort === k ? "selected" : ""}>${esc(label)}</option>`;
  const dateOpt = (k, label) => `<option value="${k}" ${f.preset === k ? "selected" : ""}>${esc(label)}</option>`;
  const attr = p === "media" ? "data-media-kind" : "data-file-kind";
  const pill = ([k, icon, label]) => `<button type="button" class="lib-pill ${f.kind === k ? "active" : ""}" ${attr}="${k}"
    title="${esc(label)}" aria-label="${esc(label)}" aria-pressed="${f.kind === k}">${svgIcon(icon, 16)}</button>`;
  const filtered = f.q || f.kind !== "all" || f.preset !== "all" || f.from || f.to || f.sort !== "date_desc";
  return `<section class="lib-toolbar">
      <div class="lib-search-wrap">
        ${svgIcon("search", 16)}
        <input type="search" id="${p}-q" class="text-input" value="${esc(f.q)}" placeholder="${esc(t(p === "media" ? "lib.search_media" : "lib.search_files"))}" autocomplete="off" aria-label="${esc(t(p === "media" ? "lib.search_media" : "lib.search_files"))}">
      </div>
      <div class="lib-pills" role="group">${pills.map(pill).join("")}</div>
      <div class="lib-filters">
        <label class="lib-inline-field" title="${esc(t("lib.date_all"))}">${svgIcon("calendar", 15)}
          <select id="${p}-preset" class="text-input" aria-label="${esc(t("lib.date_all"))}">
            ${dateOpt("all", t("lib.date_all"))}${dateOpt("today", t("lib.date_today"))}${dateOpt("7d", t("lib.date_7d"))}${dateOpt("30d", t("lib.date_30d"))}${dateOpt("range", t("lib.date_range"))}
          </select></label>
        <span class="lib-range" ${f.preset === "range" || f.from || f.to ? "" : "hidden"}>
          <input type="date" id="${p}-from" class="text-input lib-date" value="${esc(f.from)}" title="${esc(t("lib.date_from"))}" aria-label="${esc(t("lib.date_from"))}">
          <span class="lib-dash" aria-hidden="true">–</span>
          <input type="date" id="${p}-to" class="text-input lib-date" value="${esc(f.to)}" title="${esc(t("lib.date_to"))}" aria-label="${esc(t("lib.date_to"))}">
        </span>
        <label class="lib-inline-field" title="${esc(t("lib.sort_label"))}">${svgIcon("sort", 15)}
          <select id="${p}-sort" class="text-input" aria-label="${esc(t("lib.sort_label"))}">
            ${sortOpt("date_desc", t("lib.sort_date_desc"))}${sortOpt("date_asc", t("lib.sort_date_asc"))}
            ${sortOpt("name_asc", t("lib.sort_name_asc"))}${sortOpt("name_desc", t("lib.sort_name_desc"))}
            ${sortOpt("size_desc", t("lib.sort_size_desc"))}${sortOpt("size_asc", t("lib.sort_size_asc"))}
          </select></label>
        ${filtered ? `<button type="button" class="icon-btn small" data-lib-act="clear-${p === "media" ? "media" : "files"}" title="${esc(t("lib.clear_filters"))}" aria-label="${esc(t("lib.clear_filters"))}">${svgIcon("eraser", 16)}</button>` : ""}
      </div>
      <div class="lib-count-bar" id="${p}-count-bar"></div>
    </section>`;
}

function libHeadHtml(icon, title, sub, otherAct, otherIcon, otherLabel) {
  return `<header class="lib-head">
      <button type="button" class="icon-btn" data-lib-act="home" title="${esc(t("lib.back_home"))}" aria-label="${esc(t("lib.back_home"))}">${svgIcon("arrowLeft", 18)}</button>
      <div class="lib-head-text">
        <h1>${svgIcon(icon, 22)} ${esc(title)}</h1>
        <p>${esc(sub)}</p>
      </div>
      <button type="button" class="icon-btn" data-lib-act="${otherAct}" title="${esc(otherLabel)}" aria-label="${esc(otherLabel)}">${svgIcon(otherIcon, 18)}</button>
    </header>`;
}

function renderMediaView() {
  const main = $("#main");
  const ms = DASH.data?.media_stats || { total: 0, total_bytes: 0 };
  const f = DASH.mediaFilter;
  main.innerHTML = `
  <div class="lib-view">
    ${libHeadHtml("image", t("lib.media_title"), t("lib.media_sub", { n: ms.total || 0, size: fmtSize(ms.total_bytes || 0) }), "go-files", "folder", t("dash.btn_files"))}
    ${libToolbarHtml("media", f, [["all", "grid", t("lib.filter_all")], ["image", "image", t("lib.filter_image")],
      ["edit", "pencil", t("lib.filter_edit")], ["video", "film", t("lib.filter_video")]])}
    <div id="media-lib-grid" class="media-lib-grid"></div>
  </div>`;

  paintMediaGrid();

  $("#media-q").oninput = (e) => { DASH.mediaFilter.q = e.target.value; paintMediaGrid(); };
  $("#media-preset").onchange = (e) => {
    DASH.mediaFilter.preset = e.target.value;
    if (e.target.value !== "range") Object.assign(DASH.mediaFilter, { from: "", to: "" });
    libRerender("media");
  };
  $("#media-from").onchange = (e) => { DASH.mediaFilter.from = e.target.value; libRerender("media"); };
  $("#media-to").onchange = (e) => { DASH.mediaFilter.to = e.target.value; libRerender("media"); };
  $("#media-sort").onchange = (e) => { DASH.mediaFilter.sort = e.target.value; libRerender("media"); };

  main.onclick = (e) => {
    const act = e.target.closest("[data-lib-act]")?.dataset.libAct;
    if (act === "home") return select({ kind: "gallery" });
    if (act === "go-files") return select({ kind: "files" });
    if (act === "clear-media") {
      DASH.mediaFilter = { q: "", kind: "all", preset: "all", from: "", to: "", sort: "date_desc" };
      return renderMediaView();
    }
    const kindBtn = e.target.closest("[data-media-kind]");
    if (kindBtn) {
      DASH.mediaFilter.kind = kindBtn.dataset.mediaKind;
      return renderMediaView();
    }
    const prevBtn = e.target.closest("[data-media-idx]");
    if (prevBtn) {
      const items = filterMediaItems();
      const idx = Number(prevBtn.dataset.mediaIdx);
      if (items[idx]) openMediaLightbox(items, idx);
      return;
    }
    if (libSelClick(e, "media")) return;
    const useBtn = e.target.closest("[data-media-chat-idx]");
    if (useBtn) {
      const items = filterMediaItems();
      const idx = Number(useBtn.dataset.mediaChatIdx);
      if (items[idx]) useLibraryItemInChat(items[idx]);
    }
  };
}

// Tras cambiar un filtro de fecha/orden: se vuelve a dibujar la vista (para
// mostrar u ocultar "limpiar filtros") sin perder el foco de la búsqueda.
function libRerender(p) {
  if (p === "media") renderMediaView();
  else renderFilesView();
}

function paintMediaGrid() {
  const grid = $("#media-lib-grid");
  const countBar = $("#media-count-bar");
  if (!grid) return;
  const total = (DASH.data?.media || []).length;
  const items = filterMediaItems();
  if (countBar) paintLibSelBar("media", items, total);

  if (!items.length) {
    grid.innerHTML = `<div class="card lib-empty"><p>${esc(t(total ? "lib.empty_match" : "dash.no_media_yet"))}</p></div>`;
    return;
  }

  grid.innerHTML = items.map((m, idx) => {
    const isVid = m.media_type === "video" || m.kind === "video";
    const kindLabel = t(`lib.kind_${isVid ? "video" : m.kind === "edit" ? "edit" : "image"}`);
    const dims = Array.isArray(m.dimensions) && m.dimensions.length === 2 ? `${m.dimensions[0]}×${m.dimensions[1]}` : "";
    return `<article class="media-card ${DASH.sel.media.has(m.id) ? "selected" : ""}">
      ${libCheck("media", m)}
      <button type="button" class="media-thumb-btn" data-media-idx="${idx}" aria-label="${esc(t("lib.preview"))} ${esc(m.name)}">
        ${isVid
          ? `<video src="${esc(m.url)}" preload="metadata" muted loop playsinline onmouseenter="this.play().catch(()=>{})" onmouseleave="this.pause()"></video>
             <span class="media-vid-badge" title="${esc(kindLabel)}">${svgIcon("film", 14)}</span>`
          : `<img src="${esc(m.url)}" alt="${esc(m.name)}" loading="lazy">
             ${m.kind === "edit" ? `<span class="media-kind-badge edit" title="${esc(kindLabel)}">${svgIcon("pencil", 13)}</span>` : ""}`}
        ${dims ? `<span class="media-dim-badge">${esc(dims)}</span>` : ""}
      </button>
      <div class="media-card-body">
        <div class="media-card-title" title="${esc(m.name)}"><strong>${esc(m.name)}</strong></div>
        <div class="media-card-meta">
          <span>${esc(fmtShortDate(m.at))}</span>
          <span>· ${esc(fmtSize(m.size || 0))}</span>
          ${m.took ? `<span>· ${m.took} s</span>` : ""}
        </div>
        ${m.prompt ? `<p class="media-card-prompt" title="${esc(m.prompt)}">${esc(m.prompt)}</p>` : ""}
        <div class="media-card-acts">
          ${m.assistant_label ? `<span class="badge" title="${esc(m.workflow || "")}">${esc(m.assistant_label)}</span>` : ""}
          <span class="spacer"></span>
          <button type="button" class="icon-btn small" data-media-chat-idx="${idx}" title="${esc(t("lib.use_in_chat"))}" aria-label="${esc(t("lib.use_in_chat"))}">${ICON.chat}</button>
          <a class="icon-btn small" href="${esc(m.url)}" download="${esc(m.name)}" title="${esc(t("lib.download"))}" aria-label="${esc(t("lib.download"))}">${svgIcon("download", 16)}</a>
          ${libDelBtn("media", idx)}
        </div>
      </div>
    </article>`;
  }).join("");
}

// ── Vista: Biblioteca de Archivos Generados (#/files) ──────────────────
function renderFilesView() {
  const main = $("#main");
  const fs = DASH.data?.file_stats || { total: 0, total_bytes: 0 };
  const f = DASH.filesFilter;
  main.innerHTML = `
  <div class="lib-view">
    ${libHeadHtml("folder", t("lib.files_title"), t("lib.files_sub", { n: fs.total || 0, size: fmtSize(fs.total_bytes || 0) }), "go-media", "image", t("dash.btn_media"))}
    ${libToolbarHtml("files", f, [["all", "grid", t("lib.filter_all")], ["generated", "wand", t("lib.filter_generated")],
      ["attachment", "clip", t("lib.filter_attachment")], ["doc", "file", t("lib.filter_doc")],
      ["audio", "music", t("lib.filter_audio")], ["media", "image", t("lib.filter_media")]])}
    <div id="files-lib-list" class="files-lib-list"></div>
  </div>`;

  paintFilesList();

  $("#files-q").oninput = (e) => { DASH.filesFilter.q = e.target.value; paintFilesList(); };
  $("#files-preset").onchange = (e) => {
    DASH.filesFilter.preset = e.target.value;
    if (e.target.value !== "range") Object.assign(DASH.filesFilter, { from: "", to: "" });
    libRerender("files");
  };
  $("#files-from").onchange = (e) => { DASH.filesFilter.from = e.target.value; libRerender("files"); };
  $("#files-to").onchange = (e) => { DASH.filesFilter.to = e.target.value; libRerender("files"); };
  $("#files-sort").onchange = (e) => { DASH.filesFilter.sort = e.target.value; libRerender("files"); };

  main.onclick = (e) => {
    const act = e.target.closest("[data-lib-act]")?.dataset.libAct;
    if (act === "home") return select({ kind: "gallery" });
    if (act === "go-media") return select({ kind: "media" });
    if (act === "clear-files") {
      DASH.filesFilter = { q: "", kind: "all", preset: "all", from: "", to: "", sort: "date_desc" };
      return renderFilesView();
    }
    const kindBtn = e.target.closest("[data-file-kind]");
    if (kindBtn) {
      DASH.filesFilter.kind = kindBtn.dataset.fileKind;
      return renderFilesView();
    }
    const prevBtn = e.target.closest("[data-file-idx]");
    if (prevBtn) {
      const items = filterFileItems();
      const idx = Number(prevBtn.dataset.fileIdx);
      if (items[idx]) openFilePreviewModal(items, idx);
      return;
    }
    if (libSelClick(e, "files")) return;
    const useBtn = e.target.closest("[data-file-chat-idx]");
    if (useBtn) {
      const items = filterFileItems();
      const idx = Number(useBtn.dataset.fileChatIdx);
      if (items[idx]) useLibraryItemInChat(items[idx]);
    }
  };
}

function paintFilesList() {
  const listEl = $("#files-lib-list");
  const countBar = $("#files-count-bar");
  if (!listEl) return;
  const total = (DASH.data?.files || []).length;
  const items = filterFileItems();
  if (countBar) paintLibSelBar("files", items, total);

  if (!items.length) {
    listEl.innerHTML = `<div class="card lib-empty"><p>${esc(t(total ? "lib.empty_match" : "dash.no_files_yet"))}</p></div>`;
    return;
  }

  listEl.innerHTML = items.map((it, idx) => {
    const originKey = it.origin === "converted" ? "lib.origin_converted" : it.origin === "generated" ? "lib.origin_generated" : "lib.origin_attachment";
    const kindLabel = t(`lib.kind_${it.kind || "other"}`);
    const isImg = it.kind === "image";
    const isVid = it.kind === "video";
    return `<article class="card file-lib-card ${DASH.sel.files.has(it.id) ? "selected" : ""}">
      ${libCheck("files", it)}
      <button type="button" class="file-lib-preview-thumb" data-file-idx="${idx}" title="${esc(t("lib.preview"))}">
        ${isImg
          ? `<img src="${esc(it.url)}" alt="${esc(it.name)}" loading="lazy">`
          : isVid
            ? `<video src="${esc(it.url)}" preload="metadata" muted playsinline></video>`
            : `<span class="file-lib-icon ${esc(it.kind || "other")}">${fileKindIcon(it.kind)}</span>`}
      </button>
      <div class="file-lib-main">
        <div class="file-lib-top">
          <strong class="file-lib-name" title="${esc(it.name)}">${esc(it.name)}</strong>
          <span class="badge">${esc(it.ext ? `.${it.ext.toUpperCase()}` : kindLabel)}</span>
          <span class="lib-origin" title="${esc(t(originKey))}" aria-label="${esc(t(originKey))}">${svgIcon(it.origin === "attachment" ? "clip" : it.origin === "converted" ? "fileConvert" : "wand", 14)}</span>
        </div>
        <div class="file-lib-meta">
          <span>${esc(fmtShortDate(it.at))}</span>
          <span>· ${esc(fmtSize(it.size || 0))}</span>
          ${it.assistant_label ? `<span>· ${esc(it.assistant_label)}</span>` : ""}
          ${it.from_name ? `<span>· ${esc(t("file.from", { name: it.from_name }))}</span>` : ""}
          ${it.info ? `<span>· ${esc(it.info)}</span>` : ""}
        </div>
        ${it.preview_text ? `<p class="file-lib-snippet">${esc(it.preview_text.slice(0, 220))}${it.preview_text.length > 220 ? "…" : ""}</p>` : ""}
      </div>
      <div class="file-lib-acts">
        <button type="button" class="icon-btn small" data-file-idx="${idx}" title="${esc(t("lib.preview"))}" aria-label="${esc(t("lib.preview"))}">${svgIcon("eye", 16)}</button>
        <button type="button" class="icon-btn small" data-file-chat-idx="${idx}" title="${esc(t("lib.use_in_chat"))}" aria-label="${esc(t("lib.use_in_chat"))}">${ICON.chat}</button>
        <a class="icon-btn small" href="${esc(it.url)}" download="${esc(it.name)}" title="${esc(t("lib.download"))}" aria-label="${esc(t("lib.download"))}">${svgIcon("download", 16)}</a>
        ${libDelBtn("files", idx)}
      </div>
    </article>`;
  }).join("");
}

// ── Borrar de la biblioteca (uno o varios; ver dashboard.delete_files) ──
// Cada tarjeta tiene su casilla y su botón de papelera; con algo elegido, la
// barra de arriba ofrece elegir todo lo que se ve y borrar lo elegido. La
// confirmación es el diálogo de la app (confirmDialog), no el del navegador.
function libCheck(kind, it) {
  if (isGuest()) return "";
  return `<label class="lib-check" title="${esc(t("lib.select"))}"><input type="checkbox" data-lib-sel="${esc(it.id)}"
    ${DASH.sel[kind].has(it.id) ? "checked" : ""} aria-label="${esc(t("lib.select_item", { name: it.name }))}"></label>`;
}

function libDelBtn(kind, idx) {
  if (isGuest()) return "";
  return `<button type="button" class="icon-btn small lib-del" data-lib-del="${idx}" title="${esc(t("lib.delete"))}" aria-label="${esc(t("lib.delete"))}">${svgIcon("trash", 16)}</button>`;
}

function paintLibSelBar(kind, items, total) {
  const bar = $(kind === "media" ? "#media-count-bar" : "#files-count-bar");
  if (!bar) return;
  // Lo elegido que ya no está (se borró, o es de otro perfil) se olvida.
  const ids = new Set((DASH.data?.[kind] || []).map((x) => x.id));
  [...DASH.sel[kind]].forEach((id) => { if (!ids.has(id)) DASH.sel[kind].delete(id); });
  const n = DASH.sel[kind].size;
  const showing = `<span>${esc(t("lib.showing", { shown: items.length, total }))}</span>`;
  if (isGuest() || (!items.length && !n)) {
    bar.innerHTML = showing;
    return;
  }
  const allShown = items.length && items.every((x) => DASH.sel[kind].has(x.id));
  bar.innerHTML = `${showing}<div class="lib-selbar">
    ${n ? `<strong>${esc(t("lib.selected", { n }))}</strong>` : ""}
    ${items.length ? `<button type="button" class="icon-btn small ${allShown ? "on" : ""}" data-lib-act="sel-all" title="${esc(t(allShown ? "lib.unselect_all" : "lib.select_all"))}" aria-label="${esc(t(allShown ? "lib.unselect_all" : "lib.select_all"))}">${svgIcon("check", 16)}</button>` : ""}
    ${n ? `<button type="button" class="icon-btn small" data-lib-act="sel-clear" title="${esc(t("lib.select_clear"))}" aria-label="${esc(t("lib.select_clear"))}">${svgIcon("x", 16)}</button>
      <button type="button" class="btn btn-sm btn-danger" data-lib-act="sel-delete" title="${esc(t("lib.delete_n", { n }))}">${svgIcon("trash", 15)} ${n}</button>` : ""}
  </div>`;
}

// Clics de selección y borrado en #/media y #/files; true si era uno de ellos.
function libSelClick(e, kind) {
  const items = kind === "media" ? filterMediaItems() : filterFileItems();
  const sel = DASH.sel[kind];
  const repaint = () => (kind === "media" ? paintMediaGrid() : paintFilesList());
  const box = e.target.closest("[data-lib-sel]");
  if (box) {
    if (box.checked) sel.add(box.dataset.libSel);
    else sel.delete(box.dataset.libSel);
    box.closest(".media-card, .file-lib-card")?.classList.toggle("selected", box.checked);
    paintLibSelBar(kind, items, (DASH.data?.[kind] || []).length);
    return true;
  }
  if (e.target.closest(".lib-check")) return true; // el clic en el borde de la casilla
  const act = e.target.closest("[data-lib-act]")?.dataset.libAct;
  if (act === "sel-all") {
    const allShown = items.every((x) => sel.has(x.id));
    items.forEach((x) => (allShown ? sel.delete(x.id) : sel.add(x.id)));
    repaint();
    return true;
  }
  if (act === "sel-clear") {
    sel.clear();
    repaint();
    return true;
  }
  if (act === "sel-delete") {
    deleteLibraryItems((DASH.data?.[kind] || []).filter((x) => sel.has(x.id)));
    return true;
  }
  const del = e.target.closest("[data-lib-del]");
  if (del) {
    const it = items[Number(del.dataset.libDel)];
    if (it) deleteLibraryItems([it]);
    return true;
  }
  return false;
}

async function deleteLibraryItems(list) {
  if (!list?.length || isGuest()) return false;
  const one = list.length === 1;
  const ok = await confirmDialog(
    one ? t("lib.del_title_one") : t("lib.del_title_many", { n: list.length }),
    one ? t("lib.del_text_one", { name: list[0].name }) : t("lib.del_text_many", { n: list.length }),
    one ? t("lib.delete") : t("lib.delete_n", { n: list.length }),
  );
  if (!ok) return false;
  let r;
  try {
    r = await api("POST", "/api/files/delete", { ids: list.map((x) => x.id) });
  } catch (ex) {
    toast(ex.message, "error");
    return false;
  }
  // Sus referencias se quitaron de las conversaciones guardadas: también de la abierta.
  window.purgeChatFiles?.([...r.deleted, ...r.kept]);
  list.forEach((x) => { DASH.sel.media.delete(x.id); DASH.sel.files.delete(x.id); });
  const done = r.deleted.length + r.kept.length;
  if (!done) toast(t("lib.del_none"), "warn");
  else toast(t("lib.del_done", { n: done }) + (r.kept.length ? ` ${t("lib.del_kept", { n: r.kept.length })}` : ""), "ok", r.kept.length ? 8000 : 4000);
  await loadDashboardData();
  if (S.view?.kind === "media") renderMediaView();
  else if (S.view?.kind === "files") renderFilesView();
  else if (S.view?.kind === "gallery") renderHomeDashboard();
  return true;
}

// ── Visor Multimedia Interactivo con navegación (Imágenes y Videos) ────
function openMediaLightbox(items, startIndex = 0) {
  let idx = Math.max(0, Math.min(items.length - 1, startIndex));
  const m = items[idx];
  if (!m) return;
  openImageViewer(m.url, m.name, { video: m.media_type === "video" || m.kind === "video" });
  const dlg = $("#img-viewer");
  if (!dlg) return;

  const paintMetaAndNav = () => {
    const cur = items[idx];
    dlg.querySelector(".iv-meta-bar")?.remove();
    const meta = document.createElement("div");
    meta.className = "iv-meta-bar";
    const dims = Array.isArray(cur.dimensions) && cur.dimensions.length === 2 ? `${cur.dimensions[0]}×${cur.dimensions[1]}` : "";
    meta.innerHTML = `
      <div class="iv-meta-info">
        ${cur.assistant_label ? `<span class="badge">${esc(cur.assistant_label)}</span>` : ""}
        ${cur.workflow ? `<span class="badge">${esc(cur.workflow)}</span>` : ""}
        ${dims ? `<span>${esc(dims)}</span>` : ""}
        <span>${esc(fmtSize(cur.size || 0))}</span>
        ${cur.took ? `<span>· ${cur.took} s GPU</span>` : ""}
        <span>· ${esc(fmtShortDate(cur.at))}</span>
        ${cur.prompt ? `<p class="iv-meta-prompt">${esc(cur.prompt)}</p>` : ""}
      </div>
      <div class="iv-nav-btns">
        ${items.length > 1 ? `
          <button type="button" class="icon-btn" data-iv-step="-1" ${idx === 0 ? "disabled" : ""} title="${esc(t("lib.prev_item"))}" aria-label="${esc(t("lib.prev_item"))}">${svgIcon("chevronLeft", 18)}</button>
          <span class="iv-nav-pos">${idx + 1} / ${items.length}</span>
          <button type="button" class="icon-btn" data-iv-step="1" ${idx === items.length - 1 ? "disabled" : ""} title="${esc(t("lib.next_item"))}" aria-label="${esc(t("lib.next_item"))}">${svgIcon("chevronRight", 18)}</button>
        ` : ""}
        <button type="button" class="icon-btn" data-iv-use-chat="1" title="${esc(t("lib.use_in_chat"))}" aria-label="${esc(t("lib.use_in_chat"))}">${ICON.chat}</button>
        ${isGuest() ? "" : `<button type="button" class="icon-btn lib-del" data-iv-del="1" title="${esc(t("lib.delete"))}" aria-label="${esc(t("lib.delete"))}">${svgIcon("trash", 17)}</button>`}
      </div>`;
    dlg.append(meta);
    meta.onclick = async (ev) => {
      if (ev.target.closest("[data-iv-del]")) {
        // La confirmación es otro <dialog>: se cierra el visor antes para que no lo tape.
        const curItem = items[idx];
        dlg.close();
        if (curItem) await deleteLibraryItems([curItem]);
        return;
      }
      if (ev.target.closest("[data-iv-use-chat]")) {
        const curItem = items[idx];
        dlg.close();
        if (curItem) useLibraryItemInChat(curItem);
        return;
      }
      const stepBtn = ev.target.closest("[data-iv-step]");
      if (!stepBtn) return;
      const nextIdx = idx + Number(stepBtn.dataset.ivStep);
      if (nextIdx >= 0 && nextIdx < items.length) {
        idx = nextIdx;
        const nextItem = items[idx];
        openImageViewer(nextItem.url, nextItem.name, { video: nextItem.media_type === "video" || nextItem.kind === "video" });
        paintMetaAndNav();
      }
    };
  };
  paintMetaAndNav();
}

// ── Modal de Previsualización de Archivos (Audio, PDF, Office, Código, Imagen, Video) ──
function openFilePreviewModal(items, startIndex = 0) {
  let idx = Math.max(0, Math.min(items.length - 1, startIndex));
  let dlg = $("#file-preview-dialog");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "file-preview-dialog";
    dlg.className = "file-preview-dlg";
    dlg.addEventListener("close", () => { dlg.innerHTML = ""; });
    document.body.append(dlg);
  }

  const renderCurrent = async () => {
    const it = items[idx];
    if (!it) return;
    const kind = it.kind || "other";
    dlg.innerHTML = `
      <header class="fp-head">
        <div class="fp-title">
          <span class="fp-ico">${fileKindIcon(kind)}</span>
          <div>
            <strong>${esc(it.name)}</strong>
            <small>${esc(fmtShortDate(it.at))} · ${esc(fmtSize(it.size || 0))}${it.assistant_label ? ` · ${esc(it.assistant_label)}` : ""}${it.from_name ? ` · ${esc(t("file.from", { name: it.from_name }))}` : ""}</small>
          </div>
        </div>
        <div class="fp-acts">
          ${items.length > 1 ? `
            <button type="button" class="icon-btn small" data-fp-step="-1" ${idx === 0 ? "disabled" : ""} title="${esc(t("lib.prev_item"))}" aria-label="${esc(t("lib.prev_item"))}">${svgIcon("chevronLeft", 16)}</button>
            <span class="fp-pos">${idx + 1} / ${items.length}</span>
            <button type="button" class="icon-btn small" data-fp-step="1" ${idx === items.length - 1 ? "disabled" : ""} title="${esc(t("lib.next_item"))}" aria-label="${esc(t("lib.next_item"))}">${svgIcon("chevronRight", 16)}</button>
          ` : ""}
          <button type="button" class="icon-btn small" data-fp-use-chat="1" title="${esc(t("lib.use_in_chat"))}" aria-label="${esc(t("lib.use_in_chat"))}">${ICON.chat}</button>
          ${(kind === "image" || kind === "video") ? `<button type="button" class="icon-btn small" data-fp-zoom="1" title="${esc(t("iv.view"))}" aria-label="${esc(t("iv.view"))}">${svgIcon("maximize", 16)}</button>` : ""}
          <a class="icon-btn small" href="${esc(it.url)}" download="${esc(it.name)}" title="${esc(t("lib.download"))}" aria-label="${esc(t("lib.download"))}">${svgIcon("download", 16)}</a>
          ${isGuest() ? "" : `<button type="button" class="icon-btn small lib-del" data-fp-del="1" title="${esc(t("lib.delete"))}" aria-label="${esc(t("lib.delete"))}">${svgIcon("trash", 16)}</button>`}
          <button type="button" class="icon-btn" data-fp-close="1" aria-label="${esc(t("chat.close"))}">${svgIcon("x", 18)}</button>
        </div>
      </header>
      <div class="fp-body" id="fp-body">
        <p class="note">${esc(t("lib.loading_preview"))}</p>
      </div>`;

    dlg.onclick = async (e) => {
      if (e.target === dlg || e.target.closest("[data-fp-close]")) return dlg.close();
      if (e.target.closest("[data-fp-del]")) {
        // La confirmación es otro <dialog>: se cierra este antes para que no lo tape.
        dlg.close();
        await deleteLibraryItems([it]);
        return;
      }
      if (e.target.closest("[data-fp-use-chat]")) {
        dlg.close();
        useLibraryItemInChat(it);
        return;
      }
      const step = e.target.closest("[data-fp-step]");
      if (step) {
        const next = idx + Number(step.dataset.fpStep);
        if (next >= 0 && next < items.length) {
          idx = next;
          renderCurrent();
        }
        return;
      }
      if (e.target.closest("[data-fp-zoom]")) {
        dlg.close();
        openImageViewer(it.url, it.name, { video: kind === "video" });
      }
    };

    const body = $("#fp-body", dlg);
    if (!body) return;

    if (kind === "image") {
      body.innerHTML = `<div class="fp-media-wrap">
        <img src="${esc(it.url)}" alt="${esc(it.name)}" class="fp-img">
        ${it.info ? `<p class="note">${esc(it.info)}</p>` : ""}
      </div>`;
      return;
    }
    if (kind === "video") {
      body.innerHTML = `<div class="fp-media-wrap">
        <video src="${esc(it.url)}" controls autoplay loop class="fp-video"></video>
        ${it.info ? `<p class="note">${esc(it.info)}</p>` : ""}
      </div>`;
      return;
    }
    if (kind === "audio") {
      body.innerHTML = `<div class="fp-audio-wrap">
        <div class="fp-audio-card">
          ${svgIcon("music", 28)}
          <audio src="${esc(it.url)}" controls autoplay class="fp-audio"></audio>
          ${it.info ? `<small class="note">${esc(it.info)}</small>` : ""}
        </div>
        ${it.preview_text ? `<div class="fp-transcript">
          <h4>${esc(t("lib.transcription"))}</h4>
          <pre class="fp-text">${esc(it.preview_text)}</pre>
        </div>` : ""}
      </div>`;
      return;
    }
    if (kind === "pdf") {
      body.innerHTML = `<iframe src="${esc(it.url)}" class="fp-pdf" title="${esc(it.name)}"></iframe>`;
      return;
    }

    // Documentos Office (DOCX, XLSX, PPTX), código o texto plano: pedir vista previa al servidor
    if (it.preview_text) {
      body.innerHTML = `<div class="fp-doc-wrap"><pre class="fp-text">${esc(it.preview_text)}</pre></div>`;
      return;
    }
    try {
      const prev = await api("GET", `/api/files/${encodeURIComponent(it.id)}/preview`);
      if (!$("#fp-body", dlg)) return;
      if (prev?.text) {
        body.innerHTML = `<div class="fp-doc-wrap">
          ${prev.truncated ? `<p class="note">${esc(t("lib.truncated_note"))}</p>` : ""}
          <pre class="fp-text">${esc(prev.text)}</pre>
        </div>`;
      } else {
        body.innerHTML = `<div class="fp-empty"><p>${esc(t("lib.no_preview"))}</p></div>`;
      }
    } catch {
      if ($("#fp-body", dlg)) {
        body.innerHTML = `<div class="fp-empty"><p>${esc(t("lib.no_preview"))}</p></div>`;
      }
    }
  };

  if (!dlg.open) dlg.showModal();
  renderCurrent();
}

// ── Referenciar cualquier archivo o medio de la biblioteca en otro chat del mismo perfil ──
async function useLibraryItemInChat(item) {
  if (!item) return;
  if (S.view?.kind === "assistant") {
    await window.attachLibraryItemToChat?.(item);
    return;
  }
  const assistants = S.data?.assistants || [];
  if (!assistants.length) return;
  if (assistants.length === 1) {
    await select({ kind: "assistant", name: assistants[0].name });
    await window.attachLibraryItemToChat?.(item);
    return;
  }
  let dlg = $("#pick-asst-dialog");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "pick-asst-dialog";
    dlg.className = "file-preview-dlg pick-asst-dlg";
    dlg.addEventListener("close", () => { dlg.innerHTML = ""; });
    document.body.append(dlg);
  }
  dlg.innerHTML = `
    <header class="fp-head">
      <div class="fp-title">
        <span class="fp-ico">${ICON.chat}</span>
        <div>
          <strong>${esc(t("lib.pick_asst_title", { name: item.name }))}</strong>
          <small>${esc(t("lib.pick_asst_sub"))}</small>
        </div>
      </div>
      <button type="button" class="icon-btn" data-pa-close="1" aria-label="${esc(t("chat.close"))}">${svgIcon("x", 18)}</button>
    </header>
    <div class="fp-body pick-asst-grid">
      ${assistants.map((a) => `
        <button type="button" class="dash-asst-row" data-pa-pick="${esc(a.name)}">
          ${orbAvatar(a, "dash-orb")}
          <div class="dash-asst-main">
            <div class="dash-asst-head">
              <strong>${esc(displayName(a))}</strong>
              <code>${esc(a.base_model)}</code>
            </div>
          </div>
        </button>`).join("")}
    </div>`;
  dlg.onclick = async (e) => {
    if (e.target === dlg || e.target.closest("[data-pa-close]")) return dlg.close();
    const pick = e.target.closest("[data-pa-pick]");
    if (pick) {
      const name = pick.dataset.paPick;
      dlg.close();
      await select({ kind: "assistant", name });
      await window.attachLibraryItemToChat?.(item);
    }
  };
  if (!dlg.open) dlg.showModal();
}

async function openLibraryPickerModal() {
  let dlg = $("#lib-picker-dialog");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "lib-picker-dialog";
    dlg.className = "file-preview-dlg lib-picker-dlg";
    dlg.addEventListener("close", () => { dlg.innerHTML = ""; });
    document.body.append(dlg);
  }
  if (!DASH.data) {
    try {
      DASH.data = await api("GET", "/api/dashboard");
    } catch { /* sin datos */ }
  }
  let q = "";
  let kindFilter = "all";
  const allItems = () => {
    const files = DASH.data?.files || [];
    const media = DASH.data?.media || [];
    const byId = new Map();
    for (const m of media) byId.set(m.id, { ...m, _isMedia: true });
    for (const f of files) {
      if (!byId.has(f.id)) byId.set(f.id, f);
      else byId.set(f.id, { ...f, ...byId.get(f.id) });
    }
    return [...byId.values()].sort((a, b) => (b.at || 0) - (a.at || 0));
  };

  const renderPickerList = () => {
    const listBox = $("#lp-list", dlg);
    if (!listBox) return;
    const term = q.trim().toLowerCase();
    const filtered = allItems().filter((it) => {
      const k = it.media_type === "video" || it.kind === "video" ? "video" : it.kind === "edit" ? "image" : it.kind;
      if (kindFilter === "media" && k !== "image" && k !== "video") return false;
      if (kindFilter === "doc" && !["pdf", "doc", "sheet", "slide", "code", "text"].includes(k)) return false;
      if (kindFilter === "audio" && k !== "audio") return false;
      if (term) {
        const hay = `${it.name || ""} ${it.prompt || ""} ${it.assistant_label || ""} ${it.assistant || ""} ${it.info || ""} ${it.preview_text || ""}`.toLowerCase();
        if (!hay.includes(term)) return false;
      }
      return true;
    });
    if (!filtered.length) {
      listBox.innerHTML = `<div class="lib-empty"><p>${esc(t(allItems().length ? "lib.empty_match" : "dash.no_files_yet"))}</p></div>`;
      return;
    }
    listBox.innerHTML = filtered.map((it, i) => {
      const isImg = it.kind === "image" || it.kind === "edit";
      const isVid = it.media_type === "video" || it.kind === "video";
      return `<div class="card file-lib-card lp-item-row">
        <div class="file-lib-preview-thumb">
          ${isImg
            ? `<img src="${esc(it.url)}" alt="${esc(it.name)}" loading="lazy">`
            : isVid
              ? `<video src="${esc(it.url)}" preload="metadata" muted playsinline></video>`
              : `<span class="file-lib-icon ${esc(it.kind || "other")}">${fileKindIcon(it.kind)}</span>`}
        </div>
        <div class="file-lib-main">
          <div class="file-lib-top">
            <strong class="file-lib-name">${esc(it.name)}</strong>
            ${it.assistant_label ? `<span class="badge">${esc(it.assistant_label)}</span>` : ""}
          </div>
          <div class="file-lib-meta">
            <span>${esc(fmtShortDate(it.at))}</span>
            <span>· ${esc(fmtSize(it.size || 0))}</span>
            ${it.prompt || it.info ? `<span>· ${esc((it.prompt || it.info).slice(0, 80))}</span>` : ""}
          </div>
        </div>
        <div class="file-lib-acts">
          <button type="button" class="btn btn-sm btn-primary" data-lp-pick="${i}">${ICON.clip} ${esc(t("lib.picker_attach"))}</button>
        </div>
      </div>`;
    }).join("");
    listBox._items = filtered;
  };

  dlg.innerHTML = `
    <header class="fp-head">
      <div class="fp-title">
        <span class="fp-ico">${ICON.library}</span>
        <div>
          <strong>${esc(t("lib.picker_title"))}</strong>
          <small>${esc(t("lib.picker_sub"))}</small>
        </div>
      </div>
      <button type="button" class="icon-btn" data-lp-close="1" aria-label="${esc(t("chat.close"))}">${svgIcon("x", 18)}</button>
    </header>
    <div class="fp-body lp-body">
      <div class="lib-toolbar-row">
        <div class="lib-search-wrap">
          ${svgIcon("search", 16)}
          <input type="search" id="lp-q" class="text-input" placeholder="${esc(t("lib.search_files"))}" autocomplete="off">
        </div>
        <div class="lib-pills" role="group">
          <button type="button" class="lib-pill active" data-lp-kind="all">${esc(t("lib.filter_all"))}</button>
          <button type="button" class="lib-pill" data-lp-kind="media">${esc(t("lib.filter_media"))}</button>
          <button type="button" class="lib-pill" data-lp-kind="doc">${esc(t("lib.filter_doc"))}</button>
          <button type="button" class="lib-pill" data-lp-kind="audio">${esc(t("lib.filter_audio"))}</button>
        </div>
      </div>
      <div id="lp-list" class="files-lib-list lp-list"></div>
    </div>`;

  renderPickerList();

  $("#lp-q", dlg).oninput = (e) => {
    q = e.target.value;
    renderPickerList();
  };
  dlg.onclick = async (e) => {
    if (e.target === dlg || e.target.closest("[data-lp-close]")) return dlg.close();
    const kBtn = e.target.closest("[data-lp-kind]");
    if (kBtn) {
      kindFilter = kBtn.dataset.lpKind;
      $$("[data-lp-kind]", dlg).forEach((b) => b.classList.toggle("active", b.dataset.lpKind === kindFilter));
      renderPickerList();
      return;
    }
    const pBtn = e.target.closest("[data-lp-pick]");
    if (pBtn) {
      const listBox = $("#lp-list", dlg);
      const item = listBox?._items?.[Number(pBtn.dataset.lpPick)];
      dlg.close();
      if (item) await window.attachLibraryItemToChat?.(item);
    }
  };

  if (!dlg.open) dlg.showModal();
  // Actualizar catálogo en segundo plano por si se creó algo nuevo recién
  api("GET", "/api/dashboard").then((fresh) => {
    DASH.data = fresh;
    if (dlg.open) renderPickerList();
  }).catch(() => {});
}
window.openLibraryPickerModal = openLibraryPickerModal;


// ── Modelos de Hugging Face (Ajustes → Modelos de IA) ──────────────────
// Buscar repos GGUF, ver sus cuantizaciones y descargar una: Ollama la
// baja sola con hf.co/<repo>:<quant> (los privados/restringidos los baja
// el servidor con el token y los importa). El progreso es el mismo de
// "ollama pull" (S.pull / renderPullStatus en app.js).
const HFS = { open: false, q: "", results: null, searching: false, repo: null, info: null, loading: false, token: null, error: "" };

function hfBoxHtml() {
  const tok = HFS.token;
  const results = HFS.results == null ? "" : HFS.results.length
    ? `<div class="hf-results">${HFS.results.map((m) => `
        <button type="button" class="hf-repo ${HFS.repo === m.id ? "active" : ""}" data-hf="repo" data-repo="${esc(m.id)}">
          <span class="hf-repo-name">${esc(m.id)}</span>
          <span class="hf-repo-meta">${svgIcon("download", 12)} ${esc(fmtCount(m.downloads))}${m.gated || m.private ? ` · ${svgIcon("shield", 12)}` : ""}</span>
        </button>`).join("")}</div>`
    : `<p class="empty">${esc(t("hf.none"))}</p>`;
  let quants = "";
  if (HFS.loading) quants = `<p class="note">${esc(t("hf.loading"))}</p>`;
  else if (HFS.info) {
    const i = HFS.info;
    const locked = (i.private || i.gated) && !tok?.has_token;
    quants = `<div class="hf-quants">
      <div class="hf-quants-head"><strong>${esc(i.id)}</strong>
        <a class="icon-btn" href="https://huggingface.co/${esc(i.id)}" target="_blank" rel="noopener" title="${esc(t("hf.open"))}" aria-label="${esc(t("hf.open"))}">${svgIcon("globe", 15)}</a>
        ${i.vision ? `<span class="badge">${esc(t("model.vision"))}</span>` : ""}
        ${i.private || i.gated ? `<span class="badge bad">${esc(t(i.private ? "hf.private" : "hf.gated"))}</span>` : ""}</div>
      ${locked ? `<div class="callout warn"><div>${esc(t("hf.need_token"))}</div></div>` : ""}
      ${i.quants.length ? `<div class="hf-list">${i.quants.map((q) => `<div class="hf-quant">
          <span class="hf-q">${esc(q.quant)}</span><span class="mm-meta">${esc(fmtSize(q.size))}${q.sharded ? ` · ${esc(t("hf.sharded", { n: q.files.length }))}` : ""}</span>
          <button class="btn btn-sm" type="button" data-hf="pull" data-quant="${esc(q.quant)}" ${S.pull?.state === "running" || locked ? "disabled" : ""}
            title="${esc(t("hf.download_t", { name: `hf.co/${i.id}:${q.quant}` }))}" aria-label="${esc(t("hf.download_t", { name: `hf.co/${i.id}:${q.quant}` }))}">${svgIcon("download", 14)} <span class="btn-label">${esc(t("hf.download"))}</span></button>
        </div>`).join("")}</div>` : `<p class="empty">${esc(t("hf.no_gguf"))}</p>`}
    </div>`;
  }
  return `
    <form class="ic-row" data-hf-form="search">
      <input class="text-input" id="hf-q" value="${esc(HFS.q)}" placeholder="${esc(t("hf.ph"))}" spellcheck="false" autocomplete="off" autocapitalize="off" aria-label="${esc(t("hf.ph"))}">
      <button class="btn" type="submit" ${HFS.searching ? "disabled" : ""} title="${esc(t("hf.search"))}" aria-label="${esc(t("hf.search"))}">${svgIcon("search", 16)}</button>
    </form>
    <small class="note">${t("hf.help")}</small>
    ${HFS.error ? `<div class="callout warn"><div>${esc(HFS.error)}</div></div>` : ""}
    ${results}${quants}
    <details class="subtle hf-token" ${tok && !tok.has_token && HFS.info?.gated ? "open" : ""}>
      <summary>${svgIcon("shield", 14)} ${esc(t(tok?.has_token ? "hf.token_saved" : "hf.token"))}</summary>
      <form class="ic-row" data-hf-form="token">
        <input class="text-input" type="password" id="hf-token" placeholder="${esc(tok?.has_token ? "••••••••" : "hf_…")}" autocomplete="off" aria-label="${esc(t("hf.token"))}">
        <button class="btn btn-sm" type="submit">${esc(t("hf.token_save"))}</button>
        ${tok?.has_token ? `<button class="btn btn-sm btn-ghost-danger" type="button" data-hf="token-clear" title="${esc(t("hf.token_clear"))}" aria-label="${esc(t("hf.token_clear"))}">${svgIcon("trash", 14)}</button>` : ""}
      </form>
      <small class="note">${esc(t("hf.token_help"))}</small>
    </details>`;
}

const fmtCount = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${Math.round(n / 1e3)} k` : String(n || 0));

function renderHfBox() {
  const box = $("#hf-box");
  if (!box) return;
  box.innerHTML = hfBoxHtml();
  if (HFS.token == null) {
    HFS.token = {};
    api("GET", "/api/hf/token").then((r) => { HFS.token = r; renderHfBox(); }).catch(() => {});
  }
}

async function hfSearch(q) {
  HFS.q = q;
  HFS.searching = true;
  HFS.error = "";
  renderHfBox();
  try {
    // Un repo pegado tal cual (usuario/repo o su enlace): directo a sus cuantizaciones.
    const repo = q.replace(/^https?:\/\/(huggingface\.co|hf\.co)\//, "").replace(/^hf\.co\//, "").split(/[?#:]/)[0];
    if (/^[\w.-]+\/[\w.-]+$/.test(repo)) {
      HFS.results = null;
      await hfOpenRepo(repo);
    } else {
      HFS.results = (await api("GET", `/api/hf/search?q=${encodeURIComponent(q)}`)).models;
      HFS.info = null;
      HFS.repo = null;
    }
  } catch (e) {
    HFS.error = e.message;
  }
  HFS.searching = false;
  renderHfBox();
}

async function hfOpenRepo(repo) {
  HFS.repo = repo;
  HFS.loading = true;
  HFS.info = null;
  HFS.error = "";
  renderHfBox();
  try {
    HFS.info = await api("GET", `/api/hf/repo?repo=${encodeURIComponent(repo)}`);
  } catch (e) {
    HFS.error = e.message;
  }
  HFS.loading = false;
  renderHfBox();
}

function mountHfBox(card) {
  const det = card.querySelector("#hf-details");
  if (!det) return;
  det.addEventListener("input", (e) => { if (e.target.id === "hf-q") HFS.q = e.target.value; });
  det.ontoggle = () => { HFS.open = det.open; };
  renderHfBox();
  det.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target.closest("[data-hf-form]");
    if (form?.dataset.hfForm === "search") {
      const q = $("#hf-q").value.trim();
      if (q) hfSearch(q);
    } else if (form?.dataset.hfForm === "token") {
      const v = $("#hf-token").value.trim();
      if (!v) return;
      try {
        HFS.token = await api("PUT", "/api/hf/token", { token: v });
        toast(t("hf.token_ok"));
        if (HFS.repo) hfOpenRepo(HFS.repo);
      } catch (err) {
        toast(err.message, "error", 6000);
      }
      renderHfBox();
    }
  });
  det.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-hf]");
    if (!b) return;
    if (b.dataset.hf === "repo") hfOpenRepo(b.dataset.repo);
    else if (b.dataset.hf === "token-clear") {
      HFS.token = await api("PUT", "/api/hf/token", { token: "" }).catch(() => HFS.token);
      renderHfBox();
    } else if (b.dataset.hf === "pull") {
      b.disabled = true;
      try {
        S.pull = await api("POST", "/api/hf/pull", { repo: HFS.info.id, quant: b.dataset.quant });
        S.pullWatching = true;
        $("#pull-box") && ($("#pull-box").open = true);
        renderPullStatus();
        pollPull();
      } catch (err) {
        toast(err.message, "error", 7000);
        b.disabled = false;
      }
    }
  });
}


// ── Proveedores de IA por API (Ajustes → Modelos de IA) ────────────────
// Opcionales: compatibles con OpenAI (/v1: OpenAI, OpenRouter, LM Studio,
// llama-server…), Anthropic y Gemini. La clave se guarda cifrada en la PC
// (config/secrets.json) y nunca vuelve a la página. Un asistente usa uno
// eligiendo "@proveedor/modelo" como modelo (ver app/core/llm_remote.py).
const PROV = { list: null, kinds: [], defaults: {}, edit: null, models: null, test: null, busy: false };
const PROV_PRESETS = [
  { id: "openai", name: "OpenAI", kind: "openai", base_url: "https://api.openai.com/v1" },
  { id: "openrouter", name: "OpenRouter", kind: "openai", base_url: "https://openrouter.ai/api/v1" },
  { id: "lmstudio", name: "LM Studio", kind: "openai", base_url: "http://127.0.0.1:1234/v1" },
  { id: "llamacpp", name: "llama-server", kind: "openai", base_url: "http://127.0.0.1:8080/v1" },
  { id: "anthropic", name: "Anthropic", kind: "anthropic", base_url: "https://api.anthropic.com/v1" },
  { id: "gemini", name: "Google Gemini", kind: "gemini", base_url: "https://generativelanguage.googleapis.com/v1beta" },
];

async function loadProviders() {
  try {
    const r = await api("GET", "/api/llm/providers");
    Object.assign(PROV, { list: r.providers, kinds: r.kinds, defaults: r.defaults });
  } catch {
    PROV.list = PROV.list || [];
  }
  renderProvidersCard();
}

function provRowHtml(p) {
  const models = p.models || [];
  return `<div class="mm-row">
    <div class="mm-main">
      <div class="mm-name">${svgIcon("server", 15)}<strong>${esc(p.name || p.id)}</strong>
        <span class="badge">${esc(t(`prov.kind_${p.kind}`))}</span>
        ${p.has_key ? `<span class="badge good" title="${esc(t("prov.key_saved"))}">${svgIcon("shield", 11)}</span>` : ""}
        ${p.enabled ? "" : `<span class="badge bad">${esc(t("prov.disabled"))}</span>`}</div>
      <div class="mm-meta">${esc(p.base_url)}</div>
      <div class="badges">${models.map((m) => `<span class="badge use" title="@${esc(p.id)}/${esc(m.name)}">${esc(m.name)}</span>`).join("") || `<span class="mm-unused">${esc(t("prov.no_models"))}</span>`}</div>
    </div>
    <div class="mm-acts">
      <button class="icon-btn" type="button" data-prov="edit" data-id="${esc(p.id)}" title="${esc(t("prov.edit"))}" aria-label="${esc(t("prov.edit"))}">${svgIcon("pencil", 16)}</button>
      <button class="icon-btn danger" type="button" data-prov="delete" data-id="${esc(p.id)}" title="${esc(t("prov.delete"))}" aria-label="${esc(t("prov.delete"))}">${svgIcon("trash", 16)}</button>
    </div>
  </div>`;
}

function provFormHtml() {
  const e = PROV.edit;
  const kinds = ["openai", "anthropic", "gemini"];
  const found = PROV.models;
  const chosen = new Set(e.models.map((m) => m.name));
  const avail = (found || []).filter((m) => !chosen.has(m.name));
  return `<form class="prov-form" data-prov-form>
    ${e.isNew ? `<div class="prov-presets">${PROV_PRESETS.map((p) => `<button type="button" class="chip-btn ${e.preset === p.id ? "active" : ""}" data-prov="preset" data-preset="${p.id}">${esc(p.name)}</button>`).join("")}</div>` : ""}
    <div class="grid-2">
      <div class="field"><label for="prov-name">${esc(t("prov.name"))}</label>
        <input id="prov-name" value="${esc(e.name)}" maxlength="60" autocomplete="off"></div>
      <div class="field"><label for="prov-kind">${esc(t("prov.kind"))}</label>
        <select id="prov-kind">${kinds.map((k) => `<option value="${k}" ${e.kind === k ? "selected" : ""}>${esc(t(`prov.kind_${k}`))}</option>`).join("")}</select></div>
    </div>
    <div class="field"><label for="prov-url">${esc(t("prov.url"))}</label>
      <input id="prov-url" value="${esc(e.base_url)}" spellcheck="false" autocomplete="off" autocapitalize="off" inputmode="url"></div>
    <div class="field"><label for="prov-key">${esc(t("prov.key"))}</label>
      <div class="ic-row"><input id="prov-key" class="text-input" type="password" value="${esc(e.api_key || "")}" placeholder="${esc(e.has_key ? t("prov.key_keep") : e.kind === "openai" ? t("prov.key_optional") : "")}" autocomplete="off" spellcheck="false">
        ${e.has_key ? `<button class="icon-btn danger" type="button" data-prov="clear-key" title="${esc(t("prov.key_clear"))}" aria-label="${esc(t("prov.key_clear"))}">${svgIcon("trash", 15)}</button>` : ""}</div>
      <small>${esc(t("prov.key_help"))}</small></div>
    <div class="field"><span class="field-label">${esc(t("prov.models"))}</span>
      <div class="prov-models">${e.models.map((m, i) => `<div class="prov-model">
          <code>${esc(m.name)}</code>
          <label class="mini-check" title="${esc(t("model.tools_t"))}"><input type="checkbox" data-cap="tools" data-i="${i}" ${m.caps.includes("tools") ? "checked" : ""}> tools</label>
          <label class="mini-check" title="${esc(t("prov.vision_t"))}"><input type="checkbox" data-cap="vision" data-i="${i}" ${m.caps.includes("vision") ? "checked" : ""}> ${esc(t("model.vision"))}</label>
          <button class="icon-btn" type="button" data-prov="test" data-i="${i}" title="${esc(t("prov.test"))}" aria-label="${esc(t("prov.test"))}" ${PROV.busy ? "disabled" : ""}>${svgIcon("play", 14)}</button>
          <button class="icon-btn danger" type="button" data-prov="rm-model" data-i="${i}" title="${esc(t("prov.rm_model"))}" aria-label="${esc(t("prov.rm_model"))}">${svgIcon("x", 14)}</button>
        </div>`).join("") || `<p class="note">${esc(t("prov.no_models"))}</p>`}</div>
      <div class="ic-row">
        <input class="text-input" id="prov-add-model" list="prov-found" placeholder="${esc(t("prov.model_ph"))}" spellcheck="false" autocomplete="off" autocapitalize="off" aria-label="${esc(t("prov.model_ph"))}">
        <datalist id="prov-found">${avail.slice(0, 400).map((m) => `<option value="${esc(m.name)}">${esc(m.label || "")}</option>`).join("")}</datalist>
        <button class="icon-btn" type="button" data-prov="add-model" title="${esc(t("prov.add_model"))}" aria-label="${esc(t("prov.add_model"))}">${svgIcon("check", 16)}</button>
        <button class="icon-btn" type="button" data-prov="fetch" title="${esc(t("prov.fetch"))}" aria-label="${esc(t("prov.fetch"))}" ${PROV.busy ? "disabled" : ""}>${svgIcon("regenerate", 16)}</button>
      </div>
      ${found ? `<small>${esc(t("prov.found", { n: found.length }))}</small>` : ""}
    </div>
    ${PROV.test ? `<div class="callout ${PROV.test.ok ? (PROV.test.tools === false ? "warn" : "ok") : "warn"}"><div>${esc(PROV.test.text)}</div></div>` : ""}
    <label class="switch"><input type="checkbox" id="prov-enabled" ${e.enabled !== false ? "checked" : ""}><span class="track"></span>${esc(t("prov.enabled"))}</label>
    <div class="prov-actions">
      <button class="btn" type="button" data-prov="cancel">${esc(t("prov.cancel"))}</button>
      <button class="btn btn-primary" type="submit" ${PROV.busy ? "disabled" : ""}>${esc(t("prov.save"))}</button>
    </div>
  </form>`;
}

function renderProvidersCard() {
  const box = $("#providers-card");
  if (!box) return;
  if (!isAdmin()) {
    box.hidden = true;
    return;
  }
  if (PROV.list == null) {
    box.innerHTML = `<div class="card-head"><div><h2>${esc(t("prov.title"))}</h2></div></div><p class="note">…</p>`;
    loadProviders();
    return;
  }
  box.innerHTML = `
    <div class="card-head"><div><h2>${esc(t("prov.title"))}</h2><p>${esc(t("prov.sub"))}</p></div>
      ${PROV.edit ? "" : `<button class="btn btn-sm" type="button" data-prov="new">${svgIcon("plug", 14)} ${esc(t("prov.add"))}</button>`}</div>
    ${PROV.edit ? provFormHtml() : `<div class="mm-list">${PROV.list.map(provRowHtml).join("") || `<p class="empty">${esc(t("prov.none"))}</p>`}</div>`}
    <small class="note">${esc(t("prov.privacy"))}</small>`;
  box.onclick = onProvClick;
  box.onsubmit = (e) => { e.preventDefault(); provSave(); };
  box.onchange = (e) => {
    const c = e.target.closest("[data-cap]");
    if (c && PROV.edit) {
      provSync();
      const m = PROV.edit.models[+c.dataset.i];
      const caps = new Set(m.caps);
      c.checked ? caps.add(c.dataset.cap) : caps.delete(c.dataset.cap);
      m.caps = [...caps];
    } else if (e.target.id === "prov-kind" && PROV.edit) {
      provSync();
      const prevDefault = Object.values(PROV.defaults).includes(PROV.edit.base_url) || !PROV.edit.base_url;
      if (prevDefault) PROV.edit.base_url = PROV.defaults[PROV.edit.kind] || "";
      PROV.models = null;
      renderProvidersCard();
    }
  };
}

// Lo escrito en el formulario → PROV.edit (antes de volver a dibujarlo).
function provSync() {
  const e = PROV.edit;
  if (!e || !$("#prov-name")) return;
  e.name = $("#prov-name").value.trim();
  e.kind = $("#prov-kind").value;
  e.base_url = $("#prov-url").value.trim();
  e.api_key = $("#prov-key").value.trim();
  e.enabled = $("#prov-enabled").checked;
}

function provBody(e) {
  return { id: e.id, kind: e.kind, base_url: e.base_url, api_key: e.api_key || "" };
}

function provId(name, taken) {
  let base = (name || "api").toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 24) || "api";
  let id = base;
  for (let i = 2; taken.has(id); i++) id = `${base}-${i}`;
  return id;
}

async function provPut(list) {
  const r = await api("PUT", "/api/llm/providers", { providers: list });
  PROV.list = r.providers;
  if (r.models) S.models = r.models;
  if (typeof renderModelList === "function") renderModelList();
}

async function onProvClick(ev) {
  const b = ev.target.closest("[data-prov]");
  if (!b) return;
  const act = b.dataset.prov;
  if (act !== "new" && act !== "edit" && act !== "delete") provSync();
  const e = PROV.edit;
  if (act === "new") {
    PROV.edit = { isNew: true, id: "", name: "", kind: "openai", base_url: PROV.defaults.openai || "", api_key: "", models: [], enabled: true };
    PROV.models = null;
    PROV.test = null;
  } else if (act === "preset") {
    const p = PROV_PRESETS.find((x) => x.id === b.dataset.preset);
    Object.assign(e, { preset: p.id, name: p.name, kind: p.kind, base_url: p.base_url });
    PROV.models = null;
  } else if (act === "edit") {
    const p = PROV.list.find((x) => x.id === b.dataset.id);
    PROV.edit = { ...p, models: (p.models || []).map((m) => ({ ...m, caps: [...m.caps] })), api_key: "" };
    PROV.models = null;
    PROV.test = null;
  } else if (act === "cancel") {
    PROV.edit = null;
  } else if (act === "delete") {
    const p = PROV.list.find((x) => x.id === b.dataset.id);
    const used = (S.data.assistants || []).filter((a) => String(a.base_model || "").startsWith(`@${p.id}/`)).map(displayName);
    const text = used.length ? t("prov.delete_used", { name: p.name, list: used.join(", ") }) : t("prov.delete_text", { name: p.name });
    if (!(await confirmDialog(t("prov.delete"), text, t("prov.delete")))) return;
    try {
      await provPut(PROV.list.filter((x) => x.id !== p.id).map((x) => ({ ...x, api_key: "" })));
    } catch (err) {
      toast(err.message, "error", 6000);
    }
  } else if (act === "clear-key") {
    e.clear_key = true;
    e.has_key = false;
    e.api_key = "";
  } else if (act === "rm-model") {
    e.models.splice(+b.dataset.i, 1);
  } else if (act === "add-model") {
    const name = $("#prov-add-model").value.trim();
    if (!name || /\s/.test(name)) return;
    if (!e.models.some((m) => m.name === name)) {
      const info = (PROV.models || []).find((m) => m.name === name) || {};
      const caps = [info.tools === false ? null : "tools", info.vision === false ? null : (info.vision || e.kind !== "openai" ? "vision" : null)].filter(Boolean);
      e.models.push({ name, caps });
    }
  } else if (act === "fetch") {
    PROV.busy = true;
    renderProvidersCard();
    try {
      PROV.models = (await api("POST", "/api/llm/models", provBody(e))).models;
    } catch (err) {
      PROV.models = null;
      toast(err.message, "error", 7000);
    }
    PROV.busy = false;
  } else if (act === "test") {
    const m = e.models[+b.dataset.i];
    PROV.busy = true;
    PROV.test = { ok: true, text: t("prov.testing", { model: m.name }) };
    renderProvidersCard();
    try {
      const r = await api("POST", "/api/llm/test", { ...provBody(e), model: m.name });
      PROV.test = { ok: true, tools: r.tools, text: t(r.tools === false ? "prov.test_ok_notools" : "prov.test_ok", { model: m.name, ms: r.ms, reply: r.reply }) };
      if (r.tools === false && m.caps.includes("tools")) m.caps = m.caps.filter((c) => c !== "tools");
    } catch (err) {
      PROV.test = { ok: false, text: t("prov.test_fail", { model: m.name, error: err.message }) };
    }
    PROV.busy = false;
  }
  renderProvidersCard();
}

async function provSave() {
  provSync();
  const e = PROV.edit;
  if (!e) return;
  if (!e.base_url) return toast(t("prov.need_url"), "warn");
  if ((e.kind === "anthropic" || e.kind === "gemini") && !e.api_key && !e.has_key) return toast(t("prov.need_key"), "warn");
  const others = PROV.list.filter((x) => x.id !== e.id);
  const item = { ...e, id: e.isNew ? provId(e.name || e.kind, new Set(others.map((x) => x.id))) : e.id };
  delete item.isNew;
  delete item.preset;
  delete item.has_key;
  PROV.busy = true;
  try {
    await provPut([...others.map((x) => ({ ...x, api_key: "" })), item]);
    PROV.edit = null;
    PROV.test = null;
    toast(t("prov.saved"));
  } catch (err) {
    toast(err.message, "error", 7000);
  }
  PROV.busy = false;
  renderProvidersCard();
}
