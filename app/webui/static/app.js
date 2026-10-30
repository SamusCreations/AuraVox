"use strict";
/* global STRINGS, LANG_NAMES, BEHAVIOR_INFO, KEY_LABELS */

// ── Utilidades ─────────────────────────────────────────────────────────
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ICON = {
  play: '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>',
  stop: '<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg>',
  check: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" stroke="currentColor" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  gear: '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="7" r="2.2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="17" r="2.2" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
  chat: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
  mic: '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
  micSmall: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
  // El mismo micrófono que `mic`, tachado (botón de silenciar de la conversación por voz).
  micMuted: '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M4 4l16 16" stroke="var(--mic-slash-gap, #12111c)" stroke-width="4.5" stroke-linecap="round"/><path d="M4 4l16 16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  micOff: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M15 10.5V6a3 3 0 0 0-5.6-1.5M9 9v2a3 3 0 0 0 4.6 2.5M5.5 11a6.5 6.5 0 0 0 10.4 5.2M18.5 11c0 .7-.1 1.4-.3 2M12 17.5V21M4 4l16 16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
  speaker: '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16.5 8.5a5 5 0 0 1 0 7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
  close: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  pin: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 21s-6.5-6.1-6.5-11a6.5 6.5 0 0 1 13 0c0 4.9-6.5 11-6.5 11z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="12" cy="10" r="2.3" fill="currentColor"/></svg>',
  back: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M15 5l-7 7 7 7" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  sliders: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="7" r="2.2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="17" r="2.2" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
  wave: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/></svg>',
  file: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M7 3h7l5 5v13H7z" stroke="currentColor" stroke-width="1.9" fill="none" stroke-linejoin="round"/><path d="M14 3v5h5M10 13h6M10 17h6" stroke="currentColor" stroke-width="1.9" fill="none" stroke-linecap="round"/></svg>',
  retry: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.6-5.9M20 4v5h-5" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  camera: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 8h3l2-3h6l2 3h3v11H4z" stroke="currentColor" stroke-width="2" fill="none" stroke-linejoin="round"/><circle cx="12" cy="13" r="3.6" stroke="currentColor" stroke-width="2" fill="none"/></svg>',
  clip: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M20 11.5l-7.8 7.8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.4 3.4 0 0 1 4.8 4.8l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  send: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" stroke="currentColor" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  plus: '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  more: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="5" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="19" cy="12" r="2" fill="currentColor"/></svg>',
  edit: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16zM14 6l4 4" stroke="currentColor" stroke-width="2" fill="none" stroke-linejoin="round"/></svg>',
  lock: '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
  people: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="9" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3 19c.6-3.2 3-5 6-5s5.4 1.8 6 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="17" cy="9" r="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M17.5 14c2 .3 3.2 1.8 3.5 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  library: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
};
// Los del chat, delineados y de un solo color (icons.js).
Object.assign(ICON, ICON_CHAT);

// Tiene que coincidir con API_VERSION de config_ui.py: si no, esta página
// está hablando con un servidor viejo que quedó abierto.
const API_VERSION = 10;

// Nombre/variante válida como palabra de activación: minúsculas sin tildes.
const normWord = (v) =>
  String(v || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");

function initialLang() {
  try {
    const saved = localStorage.getItem("ui-lang");
    if (saved === "es" || saved === "en") return saved;
  } catch { /* sin almacenamiento local */ }
  return (navigator.language || "es").toLowerCase().startsWith("es") ? "es" : "en";
}

// En pantallas angostas el panel tapa el chat: arranca cerrado.
const NARROW = "(max-width: 1000px)";
function initialPanelOpen() {
  try {
    const saved = localStorage.getItem("panel-open");
    if (saved === "1" || saved === "0") return saved === "1";
  } catch { /* sin almacenamiento local */ }
  return !window.matchMedia(NARROW).matches;
}

const S = {
  lang: initialLang(),
  data: null, // /api/state
  models: { online: null, models: [], hidden: [] },
  view: null, // {kind:"gallery"} | {kind:"assistant", name} | {kind:"new"} | {kind:"shared"}
  panelOpen: initialPanelOpen(), // panel lateral de configuración (junto al chat)
  draft: null,
  baseline: "",
  pull: null,
  pullTimer: null,
  pullWatching: false,
  wakeTimer: null,
  wakeSeq: 0,
  previewTimer: null,
  capturing: false,
  stopCapture: null,
};

function t(key, params = {}) {
  let s = STRINGS[S.lang]?.[key] ?? STRINGS.es[key] ?? key;
  for (const [k, v] of Object.entries(params)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

function applyStaticI18n() {
  document.documentElement.lang = S.lang;
  document.title = t("app.title");
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  $$("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
  $$("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  $$("[data-ui-lang]").forEach((b) => b.classList.toggle("active", b.dataset.uiLang === S.lang));
}

async function api(method, url, body) {
  const opt = { method, headers: { "X-UI-Lang": S.lang } };
  if (body !== undefined) {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, opt);
  } catch {
    throw Object.assign(new Error(t("net.down")), { status: 0, fields: {} });
  }
  let data = null;
  try {
    data = await res.json();
  } catch { /* respuesta sin JSON */ }
  if (!res.ok) {
    // La sesión del perfil se venció o se cerró desde otro lado (p. ej. un
    // administrador borró el perfil): de vuelta a elegir perfil.
    if (res.status === 401 && data?.login && !S.relogin) {
      S.relogin = true;
      location.reload();
    }
    throw Object.assign(new Error(data?.error || `Error ${res.status}`), { status: res.status, fields: data?.fields || {} });
  }
  return data;
}

function toast(message, kind = "ok", ms = 3800) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), ms);
}

function confirmDialog(title, text, okLabel, danger = true) {
  const dlg = $("#dialog");
  $("#dialog-title").textContent = title;
  $("#dialog-text").textContent = text;
  const ok = $("#dialog-ok");
  ok.textContent = okLabel || t("dialog.ok");
  ok.className = `btn ${danger ? "btn-danger" : "btn-primary"}`;
  // Se resuelve desde el clic en el botón / Escape en vez de esperar el
  // evento "close" del <dialog>, que no siempre llega (visto en pruebas).
  return new Promise((resolve) => {
    const finish = (value) => {
      dlg.removeEventListener("click", onClick);
      dlg.removeEventListener("cancel", onCancel);
      if (dlg.open) dlg.close();
      resolve(value);
    };
    const onClick = (e) => {
      const button = e.target.closest("button");
      if (!button) return;
      e.preventDefault();
      finish(button.value === "ok");
    };
    const onCancel = (e) => {
      e.preventDefault();
      finish(false);
    };
    dlg.addEventListener("click", onClick);
    dlg.addEventListener("cancel", onCancel);
    dlg.showModal();
    $("button[value=cancel]", dlg).focus();
  });
}

const voiceGender = (code) => (String(code || "").startsWith("F") ? "female" : "male");
// Voces clonadas (Qwen3-TTS): "custom:<id>", ver Ajustes compartidos → Voces.
const isCustomVoice = (code) => String(code || "").startsWith("custom:");
const customVoices = () => S.data?.voice_settings?.custom_voices || [];
const customVoice = (code) => customVoices().find((v) => v.code === code);
const voiceName = (code) => (isCustomVoice(code)
  ? (customVoice(code)?.name || code)
  : t(voiceGender(code) === "female" ? "voice.female" : "voice.male", { n: String(code).slice(1) }));
// Muestra de una voz en el idioma de la interfaz (las clonadas, con su marca:
// si se cambia el audio o el texto de referencia, es otra muestra).
const previewUrl = (code) => (isCustomVoice(code)
  ? `/previews/${S.lang}/custom-${code.slice(7)}.wav?v=${customVoice(code)?.stamp || ""}`
  : `/previews/${S.lang}/${code}.wav`);
const displayName = (a) => a.label || (a.name ? a.name.toUpperCase() : t("new.title"));
const langName = (code) => LANG_NAMES[S.lang][code] || code;
const allLangCodes = () => S.data.languages.map((l) => (typeof l === "string" ? l : l.code));
// Todos los idiomas del pipeline: assistants.yaml los guarda uno por uno
// (una lista vacía, escrita a mano, también significa todos).
const hasAllLangs = (a) => !a.languages.length || allLangCodes().every((c) => a.languages.includes(c));

function keyLabel(key) {
  if (!key) return "";
  const labels = KEY_LABELS[S.lang];
  const num = /^NUMPAD(\d)$/.exec(key);
  if (num) return labels.NUMPAD.replace("{n}", num[1]);
  return labels[key] || key;
}

// Teclas que no escriben ni disparan nada en otras ventanas: seguras para
// push to talk. Cualquier otra muestra un aviso.
const SAFE_PTT_KEYS = new Set(["PAUSE", "SCROLLLOCK", "MBUTTON", "XBUTTON1", "XBUTTON2",
  ...Array.from({ length: 12 }, (_, i) => `F${i + 13}`)]);

function modelInstalled(name) {
  if (!name) return false;
  return S.models.models.some((m) => m.name === name || (!name.includes(":") && m.name === `${name}:latest`));
}

function fmtSize(bytes) {
  if (!bytes) return "";
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(bytes / 1024 ** 2)} MB`;
}

function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
}
function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((o, k) => o[k], obj)[last] = value;
}

const isDirty = () => !!S.draft && !S.readOnly && JSON.stringify(S.draft) !== S.baseline;

// ── Carga ──────────────────────────────────────────────────────────────
async function loadState() {
  setData(await api("GET", "/api/state"));
}

async function loadModels() {
  try {
    S.models = await api("GET", "/api/models");
  } catch (e) {
    S.models = { online: false, error: e.message, models: [], hidden: [] };
  }
  renderOllamaStatus();
  loadMemory(); // aparte: la primera vez lee los metadatos de cada modelo
  loadUpdates(); // versiones nuevas (lo ya comprobado; el servidor revisa cada 6 h)
}

// VRAM de cada modelo (medida o estimada) y lo que suma la voz.
async function loadMemory() {
  try {
    S.memory = await api("GET", "/api/models/memory");
  } catch {
    S.memory = { online: false, models: {} };
  }
  renderModelList();
}

function modelMemory(name) {
  const all = S.memory?.models || {};
  return all[name] || (!String(name).includes(":") ? all[`${name}:latest`] : null) || null;
}

const gb = (bytes) => `${(bytes / 1024 ** 3).toFixed(1)} GB`;

// Desglose de memoria del modelo elegido: el modelo, lo que suma la voz y
// el total contra la VRAM de la GPU.
function renderMemoryBox() {
  const box = $("#model-mem");
  if (!box) return;
  const name = S.draft.base_model;
  if (!S.memory) {
    box.innerHTML = `<p class="note">${esc(t("mem.loading"))}</p>`;
    return;
  }
  const m = modelMemory(name);
  if (!S.memory.online || !m) {
    box.innerHTML = "";
    return;
  }
  const v = S.memory.voice;
  const llm = m.measured ?? m.estimate;
  const ctx = (m.measured ? m.measured_ctx : S.memory.ctx) || S.memory.ctx;
  const detail = m.measured
    ? t("mem.measured_detail", { ctx: ctx.toLocaleString(), p: gb(S.memory.process) })
    : t("mem.estimate_detail", { w: gb(m.weights), kv: gb(m.kv || 0), p: gb(S.memory.process) });
  const rows = [
    [t("mem.model", { ctx: ctx.toLocaleString() }), llm, `<span class="mem-tag ${m.measured ? "good" : ""}">${esc(t(m.measured ? "mem.measured" : "mem.estimated"))}</span>`, detail],
    [t("mem.whisper", { model: v.whisper_model || "small" }), v.whisper, "", ""],
    [t("mem.supertonic"), v.supertonic, "", ""],
  ];
  if (String(S.draft.voice || "").startsWith("custom:")) rows.push([t("mem.qwen", { model: v.qwen_model || "0.6B" }), v.qwen, "", ""]);
  const total = rows.reduce((sum, r) => sum + r[1], 0);
  const gpu = S.memory.gpu || {};
  const pct = gpu.total ? Math.min(100, (total / gpu.total) * 100) : 0;
  const llmPct = gpu.total ? Math.min(100, (llm / gpu.total) * 100) : 0;
  let warn = "";
  if (gpu.total && total > gpu.total) warn = `<div class="callout warn"><div>${esc(t("mem.too_big"))}</div></div>`;
  else if (gpu.total && total > gpu.total * 0.85) warn = `<div class="callout warn"><div>${esc(t("mem.tight"))}</div></div>`;
  box.innerHTML = `
    <div class="mem-head"><strong>${esc(t("mem.title"))}</strong>
      <button class="btn btn-sm" type="button" data-act="measure-model" ${S.measuring ? "disabled" : ""}>${esc(t(S.measuring ? "mem.measuring" : m.measured ? "mem.remeasure" : "mem.measure"))}</button></div>
    <table class="mem-table">${rows.map(([label, bytes, tag, sub]) => `<tr>
      <td>${esc(label)} ${tag}${sub ? `<small>${esc(sub)}</small>` : ""}</td><td class="num">${gb(bytes)}</td></tr>`).join("")}
      <tr class="mem-total"><td>${esc(t("mem.total_voice"))}</td><td class="num">${gb(total)}</td></tr>
    </table>
    ${gpu.total ? `<div class="mem-bar" title="${esc(t("mem.of_gpu", { total: gb(gpu.total), gpu: gpu.name }))}">
      <div class="mem-llm" style="width:${llmPct}%"></div><div class="mem-voice" style="width:${Math.max(0, pct - llmPct)}%"></div></div>
      <small class="note">${esc(t("mem.of_gpu", { total: gb(gpu.total), gpu: gpu.name }))}. ${esc(t("mem.now", { used: gb(gpu.used || 0) }))}</small>` : ""}
    ${warn}
    <small class="note">${esc(t("mem.shared"))}</small>`;
}

async function measureModel() {
  const name = S.draft.base_model;
  if (!name || S.measuring) return;
  S.measuring = true;
  renderMemoryBox();
  try {
    S.memory = await api("POST", "/api/models/measure", { model: name });
  } catch (e) {
    toast(e.message, "error", 6000);
  }
  S.measuring = false;
  renderModelList();
}

function renderOllamaStatus() {
  const el = $("#ollama-status");
  el.classList.toggle("online", S.models.online === true);
  el.classList.toggle("offline", S.models.online === false);
  $(".status-text", el).textContent = S.models.online === null
    ? t("status.connecting")
    : S.models.online ? t("status.online", { n: S.models.models.length }) : t("status.offline");
}

// ── Navegación ─────────────────────────────────────────────────────────
async function guardDirty() {
  if (!isDirty()) return true;
  return confirmDialog(t("dirty.title"), t("dirty.text"), t("dirty.discard"));
}

// Vistas: la galería de asistentes (inicio), un asistente (chat al centro y
// su configuración en el panel lateral), uno nuevo y los ajustes
// compartidos. Cada una tiene su dirección (#/a/jarvis…) para que atrás y
// adelante del navegador funcionen y recargar no saque de donde estabas.
// `keepChat`: la conversación sigue (guardar o descartar cambios del mismo
// asistente no la borra). `mode`/`autostart`: entrar directo a la voz.
async function select(view, { force = false, draft = null, keepChat = false, mode = null, autostart = false, push = true } = {}) {
  if (!force && !(await guardDirty())) return false;
  stopPreview();
  cancelKeyCapture();
  clearTimeout(S.wakeTimer);
  if (!keepChat) {
    persistChat(true); // lo último, antes de salir
    resetChat();
  }
  if (mode) CHAT.mode = mode;
  if (view.kind === "new" && isGuest()) view = { kind: "gallery" };
  S.readOnly = false;

  if (view.kind === "assistant") {
    const a = S.data.assistants.find((x) => x.name === view.name);
    if (!a) return select({ kind: "gallery" }, { force: true, push: false });
    S.draft = { ...structuredClone(a), add_exclusions: [] };
    S.readOnly = !a.editable; // de otro perfil: se usa y se prueba, pero no se guarda
    // En pantallas angostas el panel tapa el chat: se entra viendo el chat
    // (sin cambiar la preferencia guardada para pantallas anchas).
    if (window.matchMedia(NARROW).matches) S.panelOpen = false;
  } else if (view.kind === "new") {
    S.draft = draft || newDraft();
    setPanelOpen(true);
  } else if (view.kind === "gallery" || FEATURE_VIEWS[view.kind]) {
    S.draft = null; // las vistas de features.js (Listas…) no tienen borrador
  } else {
    const uc = S.data.user_context;
    S.draft = {
      user_context: {
        nombre: uc.nombre, pais: uc.pais, ubicacion: uc.ubicacion,
        latitud: uc.latitud == null ? "" : String(uc.latitud),
        longitud: uc.longitud == null ? "" : String(uc.longitud),
      },
    };
    // Lo de todos (reglas, exclusiones) lo cambia un administrador; el
    // perfil propio (nombre y PIN), cualquiera menos el invitado.
    if (isAdmin()) Object.assign(S.draft, { shared_context: S.data.shared_context, exclusions: [...S.data.exclusions] });
    if (!isGuest()) S.draft.me = { name: ME().name, pin: "", pin_confirm: "" };
  }
  S.view = view;
  S.baseline = S.draft ? JSON.stringify(S.draft) : "";
  // De quién es la conversación (se guarda en el servidor, ver persistChat).
  const owner = view.kind === "assistant" ? view.name : null;
  if (keepChat && owner && CHAT.owner !== owner) CHAT_SAVE.sig = "";
  CHAT.owner = owner;
  CHAT.restoring = false;
  syncUrl(view, push);
  renderView();
  if (owner && !keepChat) restoreChat(owner);
  window.scrollTo(0, 0);
  if (autostart && CHAT.mode === "voice") startConversation();
  return true;
}

function renderView() {
  $("#main").dataset.view = S.view.kind;
  renderNav();
  if (S.view.kind === "gallery") renderGallery();
  else if (S.view.kind === "shared") renderShared();
  else if (FEATURE_VIEWS[S.view.kind]) FEATURE_VIEWS[S.view.kind].render();
  else renderAssistant();
}

const viewHash = (v) =>
  v.kind === "assistant" ? `#/a/${v.name}` : v.kind === "new" ? "#/new" : v.kind === "shared" ? "#/shared"
    : FEATURE_VIEWS[v.kind] ? `#/${v.kind}` : "#/";

function viewFromHash() {
  const h = location.hash;
  const m = /^#\/a\/([a-z0-9_]+)$/.exec(h);
  if (m) return { kind: "assistant", name: m[1] };
  if (h === "#/new") return { kind: "new" };
  if (h === "#/shared") return { kind: "shared" };
  const fv = /^#\/([a-z]+)$/.exec(h);
  if (fv && FEATURE_VIEWS[fv[1]]) return { kind: fv[1] };
  return { kind: "gallery" };
}

function syncUrl(view, push) {
  const h = viewHash(view);
  if (location.hash !== h) history[push ? "pushState" : "replaceState"](null, "", h);
}

async function onPopState() {
  if (location.hash && !location.hash.startsWith("#/")) return; // anclas dentro de la página
  const v = viewFromHash();
  if (S.view && viewHash(v) === viewHash(S.view)) return;
  const ok = await select(v, { push: false });
  if (!ok) history.pushState(null, "", viewHash(S.view)); // se canceló por cambios sin guardar
}

// Color de cada asistente: el que se eligió en su configuración (campo
// `color`, "#rrggbb") o, si no hay, uno automático que sale de su nombre.
// Pinta el aro del modo voz, su orbe en la galería y en el chat.
function autoHue(name) {
  let h = 0;
  for (const ch of String(name || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return name ? (h * 47) % 360 : 262;
}

function hexToHsl(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h *= 60;
  }
  return { h: Math.round(h), s: Math.round(s * 100), l: Math.round(l * 100) };
}

const COLOR_RE = /^#[0-9a-f]{6}$/;

function assistantColor(a) {
  if (COLOR_RE.test(a?.color || "")) {
    const { h, s } = hexToHsl(a.color);
    return { h, s: Math.min(95, s) };
  }
  return { h: autoHue(a?.name), s: 88 };
}

const colorStyle = (a) => {
  const { h, s } = assistantColor(a);
  return `--hue:${h};--sat:${s}%`;
};

function orbAvatar(a, cls = "") {
  const title = displayName(a);
  return `<span class="avatar orb-avatar ${cls}" style="${colorStyle(a)}" aria-hidden="true">${esc(a.name ? title[0] : "+")}</span>`;
}

// Colores sugeridos para el aro (además de uno libre y el automático).
const COLOR_PRESETS = ["#8b5cf6", "#6366f1", "#3b82f6", "#0ea5e9", "#06b6d4", "#14b8a6",
  "#10b981", "#84cc16", "#f59e0b", "#f97316", "#f43f5e", "#ec4899", "#d946ef"];

// Panel lateral de configuración
function setPanelOpen(open) {
  S.panelOpen = open;
  try { localStorage.setItem("panel-open", open ? "1" : "0"); } catch { /* sin almacenamiento local */ }
  $("#workspace")?.classList.toggle("panel-closed", !open);
  $$("[data-act=toggle-panel]").forEach((b) => b.setAttribute("aria-pressed", String(open)));
}

const personalityTemplate = (name, lang = S.lang) =>
  (STRINGS[lang]["pers.template"]).replace("{name}", name || (lang === "es" ? "NOMBRE" : "NAME"));

function newDraft() {
  const L = S.data.limits;
  const withTools = S.models.models.find((m) => (m.capabilities || []).includes("tools"));
  return {
    name: "",
    label: "",
    base_model: S.data.assistants[0]?.base_model || withTools?.name || "",
    voice: "F2",
    speed: L.speed.default,
    language: allLangCodes().includes(S.lang) ? S.lang : "es",
    languages: allLangCodes(),
    temperature: L.temperature.default,
    top_k: L.top_k.default,
    top_p: L.top_p.default,
    max_history: L.max_history.default,
    max_tool_rounds: L.max_tool_rounds.default,
    think_pause: L.think_pause.default,
    search_announcement: t("new.search"),
    fallback_message: t("new.fallback"),
    personality: personalityTemplate(""),
    wake_word: true,
    push_to_talk_key: "",
    color: "",
    shared: isAdmin(),
    aliases: [],
    add_exclusions: [],
  };
}

async function setUiLang(lang) {
  if (lang === S.lang) return;
  const old = S.lang;
  S.lang = lang;
  try { localStorage.setItem("ui-lang", lang); } catch { /* sin almacenamiento local */ }
  stopPreview();
  cancelKeyCapture();
  // Un asistente nuevo que todavía conserva los textos de ejemplo los
  // cambia al idioma nuevo.
  const d = S.draft;
  if (S.view?.kind === "new" && d) {
    if (d.personality === personalityTemplate(d.name.toUpperCase(), old)) d.personality = personalityTemplate(d.name.toUpperCase(), lang);
    if (d.search_announcement === STRINGS[old]["new.search"]) d.search_announcement = STRINGS[lang]["new.search"];
    if (d.fallback_message === STRINGS[old]["new.fallback"]) d.fallback_message = STRINGS[lang]["new.fallback"];
  }
  applyStaticI18n();
  renderOllamaStatus();
  if (S.data) renderProfileButton();
  if (S.login) return renderLogin(S.login);
  if (!S.data || !S.view) return;
  renderView();
}

// Barra superior: dónde estás (galería / asistente / ajustes compartidos).
function renderNav() {
  const v = S.view;
  $("#btn-shared").classList.toggle("active", v?.kind === "shared");
  Object.keys(FEATURE_VIEWS).forEach((k) => $(`#btn-${k}`)?.classList.toggle("active", v?.kind === k));
  const here = !v || v.kind === "gallery" ? "" : v.kind === "shared" ? t(settingsKey())
    : FEATURE_VIEWS[v.kind] ? FEATURE_VIEWS[v.kind].title() : displayName(S.draft);
  $("#crumb").innerHTML = here ? `<span class="sep" aria-hidden="true">/</span><span class="here">${esc(here)}</span>` : "";
}

// ── Galería (página de inicio) ─────────────────────────────────────────
function langsSummary(a) {
  return hasAllLangs(a)
    ? t("head.all_langs")
    : a.languages.length === 1 ? langName(a.languages[0]) : t("head.n_langs", { n: a.languages.length });
}

function galleryCard(a) {
  const name = displayName(a);
  const missing = S.models.online && !modelInstalled(a.base_model);
  const activation = [a.wake_word ? t("gallery.wake") : "", a.push_to_talk_key ? t("gallery.ptt", { key: keyLabel(a.push_to_talk_key) }) : ""]
    .filter(Boolean).join(" · ");
  return `<article class="g-card" data-open="${esc(a.name)}" tabindex="0" role="button" aria-label="${esc(t("gallery.open", { name }))}" style="${colorStyle(a)}">
    <div class="g-top">
      ${orbAvatar(a, "g-orb")}
      ${missing ? `<span class="g-flag" title="${esc(t("flag.missing", { m: a.base_model }))}">!</span>` : ""}
    </div>
    <h2>${esc(name)}</h2>
    <p class="g-model"><code>${esc(a.base_model)}</code></p>
    <div class="g-tags">
      <span class="g-tag">${ICON.speaker} ${esc(voiceName(a.voice))}</span>
      <span class="g-tag">${esc(langsSummary(a))}</span>
      ${activation ? `<span class="g-tag">${esc(activation)}</span>` : ""}
      ${!a.shared ? `<span class="g-tag g-private">${ICON.lock} ${esc(t("share.private"))}</span>` : ""}
      ${a.shared && !a.mine && a.owner_name ? `<span class="g-tag">${esc(t("share.by", { name: a.owner_name }))}</span>` : ""}
    </div>
    <div class="g-actions">
      <button class="btn btn-sm" type="button" data-open-mode="text">${ICON.chat} ${esc(t("gallery.chat"))}</button>
      <button class="btn btn-sm btn-primary" type="button" data-open-mode="voice">${ICON.wave} ${esc(t("gallery.voice"))}</button>
    </div>
  </article>`;
}

function renderGallery() {
  const main = $("#main");
  main.innerHTML = `
  <div class="gallery">
    ${guestBanner()}
    <section id="home-dashboard" class="home-dashboard"></section>
    <section class="gallery-section" id="assistants-gallery-sec">
      <header class="gallery-head">
        <div>
          <h1>${esc(t("dash.assistants_title"))}</h1>
          <p>${esc(t("dash.assistants_sub"))}</p>
          <p class="hf-hint" id="hf-hint" hidden></p>
        </div>
      </header>
      <div class="gallery-grid">
        ${S.data.assistants.map(galleryCard).join("")}
        ${isGuest() ? "" : `<button class="g-card g-new" type="button" data-act="new">
          <span class="g-plus">${ICON.plus}</span>
          <h2>${esc(t("nav.new"))}</h2>
          <p>${esc(t("gallery.new_sub"))}</p>
        </button>`}
        ${featureTiles("gallery")}
      </div>
      <p class="hint gallery-hint">${t("hint.apply")}</p>
    </section>
  </div>`;
  renderHfHint();
  main.oninput = main.onchange = null;
  mountFeatureCards("gallery");
  main.onclick = (e) => {
    if (e.target.closest("[data-act=new]")) return select({ kind: "new" });
    if (e.target.closest("[data-act=open-media]")) return select({ kind: "media" });
    if (e.target.closest("[data-act=open-files]")) return select({ kind: "files" });
    const previewMedia = e.target.closest("[data-dash-media]");
    if (previewMedia && typeof window.openDashMediaPreview === "function") {
      return window.openDashMediaPreview(Number(previewMedia.dataset.dashMedia));
    }
    const previewFile = e.target.closest("[data-dash-file]");
    if (previewFile && typeof window.openDashFilePreview === "function") {
      return window.openDashFilePreview(Number(previewFile.dataset.dashFile));
    }
    const card = e.target.closest("[data-open]");
    if (!card) return;
    const mode = e.target.closest("[data-open-mode]")?.dataset.openMode || null;
    // El clic es el gesto que el navegador exige para poder sonar.
    ensureOutputAnalyser();
    select({ kind: "assistant", name: card.dataset.open }, { mode, autostart: mode === "voice" });
  };
  main.onkeydown = (e) => {
    const card = e.target.closest?.("[data-open]");
    if (card && e.target === card && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      select({ kind: "assistant", name: card.dataset.open });
    }
  };
}

// ── Plantillas de campos ───────────────────────────────────────────────
function textField({ field, label, value, help = "", placeholder = "", attrs = "" }) {
  return `<div class="field" data-wrap="${field}">
    <label for="f-${field}">${label}</label>
    <input type="text" id="f-${field}" data-field="${field}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${attrs}>
    ${help ? `<small>${help}</small>` : ""}
    <div class="err" data-err="${field}"></div>
  </div>`;
}

function sliderField({ field, label, value, min, max, step, sliderMax, int = false, help = "" }) {
  const num = int ? "int" : "float";
  return `<div class="field slider-field" data-wrap="${field}">
    <div class="slider-head"><label for="f-${field}">${label}</label><code>${field}</code></div>
    <div class="slider-row">
      <input type="range" data-field="${field}" data-num="${num}" min="${min}" max="${sliderMax ?? max}" step="${step}" value="${value}" aria-label="${esc(label)}">
      <input type="number" id="f-${field}" data-field="${field}" data-num="${num}" min="${min}" max="${max}" step="${step}" value="${value}">
    </div>
    ${help ? `<small>${help}</small>` : ""}
    <div class="err" data-err="${field}"></div>
  </div>`;
}

function zoneLabel(field, value) {
  const zones = BEHAVIOR_INFO[field]?.[S.lang]?.zones || [];
  return (zones.find(([limit]) => value <= limit) || [0, ""])[1];
}

// Parámetro de comportamiento: slider + etiqueta en vivo del valor actual +
// explicación desplegable (qué hace, cómo se nota al subir/bajar, rango).
function behaviorField({ field, min, max, step, sliderMax, int = false }) {
  const info = BEHAVIOR_INFO[field][S.lang];
  const value = S.draft[field];
  const num = int ? "int" : "float";
  return `<div class="field slider-field behavior" data-wrap="${field}">
    <div class="slider-head"><label for="f-${field}">${info.label}</label><span class="zone" data-zone="${field}">${esc(zoneLabel(field, value))}</span></div>
    <small class="short">${esc(info.short)}</small>
    <div class="slider-row">
      <input type="range" data-field="${field}" data-num="${num}" min="${min}" max="${sliderMax ?? max}" step="${step}" value="${value}" aria-label="${esc(info.label)}">
      <input type="number" id="f-${field}" data-field="${field}" data-num="${num}" min="${min}" max="${max}" step="${step}" value="${value}">
    </div>
    <details class="info">
      <summary>${esc(t("beh.what"))}</summary>
      <p>${esc(info.what)}</p>
      <dl>
        <dt>↑ ${esc(t("beh.up"))}</dt><dd>${esc(info.up)}</dd>
        <dt>↓ ${esc(t("beh.down"))}</dt><dd>${esc(info.down)}</dd>
        <dt>✓ ${esc(t("beh.rec"))}</dt><dd>${esc(info.rec)}</dd>
      </dl>
    </details>
    <div class="err" data-err="${field}"></div>
  </div>`;
}

function saveBar(label) {
  return `<div class="savebar" id="savebar" hidden>
    <span id="savebar-text"></span>
    <button class="btn" type="button" data-act="discard">${esc(t("save.discard"))}</button>
    <button class="btn btn-primary" type="button" data-act="save">${esc(label)}</button>
  </div>`;
}

function refreshSaveBar() {
  const bar = $("#savebar");
  if (!bar) return;
  const isNew = S.view.kind === "new";
  bar.hidden = !(isDirty() || isNew);
  $("#savebar-text").textContent = isNew ? t("save.new_unsaved") : t("save.unsaved");
}

// ── Editor de asistente ────────────────────────────────────────────────
// Asistente abierto: el chat (o la conversación por voz) ocupa el centro y
// la configuración va en el panel lateral, que se puede ocultar.
function selectAssistantCat(id) {
  S.asstCat = id || "sec-identity";
  $$("#settings-panel [data-jump]").forEach((b) => {
    const on = b.dataset.jump === S.asstCat;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  $$("#panel-body > .card").forEach((c) => {
    c.hidden = S.asstCat !== "all" && c.id !== S.asstCat;
  });
  const body = $("#panel-body");
  if (body) body.scrollTop = 0;
  if (S.asstCat === "sec-personality" && $("#yaml-box")?.open) refreshPreview();
}

function renderAssistant() {
  const isNew = S.view.kind === "new";
  const ro = S.readOnly;
  if (!S.asstCat) S.asstCat = "sec-identity";
  const jump = (id, key) => `<button type="button" class="asst-cat-btn ${S.asstCat === id ? "active" : ""}" data-jump="${id}">${esc(t(key))}</button>`;
  $("#main").innerHTML = `
  <div class="workspace ${S.panelOpen ? "" : "panel-closed"}" id="workspace">
    <section class="stage" id="stage" aria-labelledby="head-title"></section>
    <div class="panel-backdrop" data-act="close-panel" aria-hidden="true"></div>
    <aside class="settings-panel" id="settings-panel" aria-label="${esc(t("panel.title"))}">
      <div class="panel-inner">
        <header class="panel-head">
          <div class="panel-title"><h2>${esc(t("panel.title"))}</h2><p>${esc(t("panel.sub"))}</p></div>
          <div class="panel-actions">
            ${isNew || isGuest() ? "" : `<button class="btn btn-sm" type="button" data-act="duplicate">${esc(t("head.duplicate"))}</button>`}
            ${isNew || ro ? "" : `<button class="btn btn-sm btn-ghost-danger" type="button" data-act="delete">${esc(t("head.delete"))}</button>`}
            <button class="icon-btn small" type="button" data-act="close-panel" aria-label="${esc(t("panel.close"))}" title="${esc(t("panel.close"))}">${ICON.close}</button>
          </div>
        </header>
        <nav class="section-nav asst-cat-nav" role="tablist" aria-label="${esc(t("cfg.menu_label"))}">
          ${jump("sec-identity", "sec.identity")}${jump("sec-model", "sec.model")}${jump("sec-voice", "sec.voice")}
          ${jump("sec-langs", "sec.langs")}${jump("sec-behavior", "sec.behavior")}${jump("sec-personality", "sec.personality")}
          ${featureJumps("assistant", jump)}
          ${jump("all", "cfg.sec_all")}
        </nav>
        <div class="panel-body editor" id="panel-body">
          ${ro ? `<div class="callout info ro-note"><div>${esc(readOnlyNote())}</div></div>` : ""}
          ${identitySection()}
          ${modelSection()}
          ${voiceSection()}
          ${languageSection()}
          ${behaviorSection()}
          ${personalitySection()}
          ${featureCards("assistant")}
        </div>
        ${ro ? "" : saveBar(isNew ? t("save.create") : t("save.save"))}
      </div>
    </aside>
  </div>`;

  renderChat();
  bindMain();
  $("#alias-input").addEventListener("keydown", onChipKey(addAlias, () => {
    S.draft.aliases.pop();
    afterAliasChange();
  }, () => S.draft.aliases.length));
  $("#alias-input").addEventListener("blur", (e) => { addAlias(e.target.value); e.target.value = ""; });
  $("#lang-filter").addEventListener("input", renderLangs);
  $("#yaml-box").addEventListener("toggle", (e) => { if (e.target.open) refreshPreview(); });

  updateHead();
  renderAliasChips();
  renderColorPicker();
  renderActivation();
  renderModelList();
  renderLangs();
  renderPullStatus();
  updateCount();
  refreshSaveBar();
  scheduleWakeCheck(0);
  mountFeatureCards("assistant"); // documentos, exportar… (ver features.js)
  if (!$("#settings-panel [data-jump].active")) S.asstCat = "sec-identity";
  selectAssistantCat(S.asstCat);
}

function identitySection() {
  const d = S.draft;
  const example = d.name ? d.name[0].toUpperCase() + d.name.slice(1) : "Nova";
  return `<section class="card" id="sec-identity">
    <div class="card-head"><div><h2>${esc(t("id.title"))}</h2><p>${esc(t("id.sub"))}</p></div></div>
    <div class="grid-2">
      ${textField({
        field: "name", label: esc(t("id.name")), value: d.name, placeholder: S.lang === "es" ? "p. ej. nova" : "e.g. nova",
        help: esc(t("id.name_help", { example })), attrs: 'autocomplete="off" spellcheck="false" maxlength="30"',
      })}
      ${textField({
        field: "label", label: esc(t("id.label")), value: d.label, placeholder: d.name ? d.name.toUpperCase() : "NOVA",
        help: esc(t("id.label_help")), attrs: 'maxlength="40"',
      })}
    </div>
    <div class="field" data-wrap="color">
      <div class="field-label">${esc(t("color.title"))}</div>
      <div class="color-row">
        <span class="color-preview js-assistant-color" aria-hidden="true"></span>
        <div class="swatches" id="color-picker" role="radiogroup" aria-label="${esc(t("color.title"))}"></div>
      </div>
      <small>${esc(t("color.help"))}</small>
      <div class="err" data-err="color"></div>
    </div>
    ${S.readOnly || isGuest() ? "" : `<div class="act-option share-option" data-wrap="shared">
      <label class="switch"><input type="checkbox" id="f-shared" ${d.shared ? "checked" : ""}><span class="track" aria-hidden="true"></span> ${esc(t("share.title"))}</label>
      <small class="note">${esc(t("share.help"))}</small>
    </div>`}
    <div class="activation" id="activation"></div>
    <div class="field" data-wrap="aliases">
      <label for="alias-input">${esc(t("id.aliases"))}</label>
      <div class="chips-input"><span id="alias-chips" class="chips"></span>
        <input id="alias-input" placeholder="${esc(t("id.aliases_ph"))}" autocomplete="off" spellcheck="false"></div>
      <small>${esc(t("id.aliases_help"))}</small>
      <div class="err" data-err="aliases"></div>
    </div>
    <div id="wake-report" class="stack"></div>
  </section>`;
}

// Color del asistente: automático, uno de los sugeridos o uno libre.
function renderColorPicker() {
  const box = $("#color-picker");
  if (!box) return;
  const current = S.draft.color || "";
  const custom = current && !COLOR_PRESETS.includes(current);
  const auto = assistantColor({ name: S.draft.name });
  const swatch = (value, cls, style, label, inner = "") => {
    const on = value === current;
    return `<button type="button" class="swatch ${cls} ${on ? "selected" : ""}" data-color="${value}" style="${style}"
      role="radio" aria-checked="${on}" aria-label="${esc(label)}" title="${esc(label)}">${inner}</button>`;
  };
  box.innerHTML =
    swatch("", "auto", `--hue:${auto.h};--sat:${auto.s}%`, t("color.auto"), "A") +
    COLOR_PRESETS.map((c) => swatch(c, "", `--c:${c}`, c)).join("") +
    `<label class="swatch custom ${custom ? "selected" : ""}" title="${esc(t("color.custom"))}" ${custom ? `style="--c:${current}"` : ""}>
      <input type="color" id="color-custom" value="${custom ? current : "#8b5cf6"}" aria-label="${esc(t("color.custom"))}">
    </label>`;
}

function setColor(value) {
  S.draft.color = COLOR_RE.test(value || "") ? value.toLowerCase() : "";
  // El selector libre se redibuja al soltarlo, no mientras se arrastra.
  if (document.activeElement?.id !== "color-custom") renderColorPicker();
  else $(".swatch.custom")?.style.setProperty("--c", S.draft.color);
  afterChange("color");
}

// Activación: por nombre y/o push to talk
function renderActivation() {
  const box = $("#activation");
  if (!box) return;
  const d = S.draft;
  const key = d.push_to_talk_key;
  const pttOn = !!key || S.capturing;
  let keyRow = "";
  if (S.capturing) {
    keyRow = `<div class="ptt-row"><span class="key-capture">${esc(t("act.capturing"))}</span>
      <button class="btn btn-sm" type="button" data-act="cancel-capture">${esc(t("dialog.cancel"))}</button></div>`;
  } else if (key) {
    keyRow = `<div class="ptt-row"><kbd class="key">${esc(keyLabel(key))}</kbd>
      <button class="btn btn-sm" type="button" data-act="capture-key">${esc(t("act.change"))}</button></div>`;
    if (!SAFE_PTT_KEYS.has(key)) keyRow += `<div class="callout warn"><div>${esc(t("act.typing_warn"))}</div></div>`;
  }
  box.innerHTML = `
    <div class="field-label">${esc(t("act.title"))}</div>
    <div class="act-option">
      <label class="switch"><input type="checkbox" id="act-wake" ${d.wake_word ? "checked" : ""}><span class="track" aria-hidden="true"></span> ${esc(t("act.wake"))}</label>
      <small class="note">${esc(t("act.wake_help"))}</small>
    </div>
    <div class="act-option" data-wrap="push_to_talk_key">
      <label class="switch"><input type="checkbox" id="act-ptt" ${pttOn ? "checked" : ""}><span class="track" aria-hidden="true"></span> ${esc(t("act.ptt"))}</label>
      <small class="note">${esc(t("act.ptt_help"))}</small>
      ${keyRow}
      ${key && !d.wake_word ? `<small class="note">${esc(t("act.ptt_only"))}</small>` : ""}
      <div class="err" data-err="push_to_talk_key"></div>
    </div>
    <div class="err" data-err="wake_word"></div>`;
}

const CODE_TO_KEY = {
  Space: "SPACE", Tab: "TAB", CapsLock: "CAPSLOCK", Pause: "PAUSE", ScrollLock: "SCROLLLOCK",
  Insert: "INSERT", Delete: "DELETE", Home: "HOME", End: "END", PageUp: "PAGEUP", PageDown: "PAGEDOWN",
  ShiftLeft: "LSHIFT", ShiftRight: "RSHIFT", ControlLeft: "LCTRL", ControlRight: "RCTRL",
  AltLeft: "LALT", AltRight: "RALT", Backquote: "BACKQUOTE",
};

function codeToKey(code) {
  let m;
  let key = CODE_TO_KEY[code] || null;
  if ((m = /^F(\d{1,2})$/.exec(code))) key = `F${m[1]}`;
  else if ((m = /^Key([A-Z])$/.exec(code))) key = m[1];
  else if ((m = /^Digit(\d)$/.exec(code))) key = m[1];
  else if ((m = /^Numpad(\d)$/.exec(code))) key = `NUMPAD${m[1]}`;
  return key && S.data.ptt_keys.includes(key) ? key : null;
}

function startKeyCapture() {
  cancelKeyCapture();
  S.capturing = true;
  renderActivation();
  const mouseMap = { 1: "MBUTTON", 3: "XBUTTON1", 4: "XBUTTON2" };
  const onKey = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.code === "Escape") return finish(null);
    const key = codeToKey(e.code);
    if (!key) {
      toast(t("act.unsupported"), "warn");
      return;
    }
    finish(key);
  };
  const onMouse = (e) => {
    if (!mouseMap[e.button]) return;
    e.preventDefault();
    finish(mouseMap[e.button]);
  };
  // Que los botones laterales (atrás/adelante) no naveguen al soltarlos.
  const block = (e) => { if (e.button >= 1) e.preventDefault(); };
  window.addEventListener("keydown", onKey, true);
  window.addEventListener("mousedown", onMouse, true);
  window.addEventListener("mouseup", block, true);
  window.addEventListener("auxclick", block, true);

  function finish(key) {
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("mousedown", onMouse, true);
    setTimeout(() => {
      window.removeEventListener("mouseup", block, true);
      window.removeEventListener("auxclick", block, true);
    }, 400);
    S.capturing = false;
    S.stopCapture = null;
    if (key) {
      S.draft.push_to_talk_key = key;
      afterChange("push_to_talk_key");
    }
    renderActivation();
  }
  S.stopCapture = () => finish(null);
}

function cancelKeyCapture() {
  if (S.stopCapture) S.stopCapture();
}


function modelSection() {
  return `<section class="card" id="sec-model">
    <div class="card-head"><div><h2>${esc(t("model.title"))}</h2><p>${esc(t("model.sub"))}</p></div>
      <button class="btn btn-sm" type="button" data-act="refresh-models">${esc(t("model.refresh"))}</button></div>
    <div id="model-list" class="model-list"></div>
    <p class="note" id="model-hidden"></p>
    <div class="err" data-err="base_model"></div>
    <div class="mem-box" id="model-mem"></div>
    <div class="mem-box upd-box" id="model-upd"></div>
    <details class="subtle" id="pull-box">
      <summary>${esc(t("pull.summary"))}</summary>
      <div class="pull-row">
        <input class="text-input" id="pull-input" placeholder="${esc(t("pull.ph"))}" spellcheck="false" autocomplete="off">
        <button class="btn" type="button" data-act="pull">${esc(t("pull.button"))}</button>
      </div>
      <small class="note">${t("pull.help")}</small>
      <div id="pull-status"></div>
    </details>
  </section>`;
}

function voiceSection() {
  const d = S.draft;
  const L = S.data.limits.speed;
  const group = (gender, title) => `<div class="voice-group"><h3>${esc(title)}</h3><div class="voice-grid">
    ${S.data.voices.filter((v) => v.gender === gender).map(voiceCard).join("")}</div></div>`;
  return `<section class="card" id="sec-voice">
    <div class="card-head"><div><h2>${esc(t("voice.title"))}</h2><p>${esc(t("voice.sub"))}</p></div></div>
    <div class="voice-groups" role="radiogroup" aria-label="${esc(t("voice.title"))}">${group("female", t("voice.female_group"))}${group("male", t("voice.male_group"))}
      <div class="voice-group"><h3>${esc(t("voice.custom_group"))}</h3>
        ${customVoices().length ? `<div class="voice-grid">${customVoices().map((v) => voiceCard({ code: v.code })).join("")}</div>`
          : `<p class="note">${esc(t("voice.custom_none"))} <button class="btn btn-sm" type="button" data-act="go-shared">${esc(t("voice.custom_create"))}</button></p>`}
      </div></div>
    ${sliderField({ field: "speed", label: esc(t("voice.speed")), value: d.speed, min: L.min, max: L.max, step: 0.01, help: esc(t("voice.speed_help")) })}
  </section>`;
}

function voiceCard(v) {
  const sel = S.draft.voice === v.code;
  const name = voiceName(v.code);
  const custom = isCustomVoice(v.code) ? customVoice(v.code) : null;
  const sub = custom ? t("voice.custom_sub", { lang: langName(custom.language) }) : name;
  return `<div class="voice-card ${sel ? "selected" : ""} ${custom ? "custom" : ""}" role="radio" aria-checked="${sel}" tabindex="0" data-voice="${esc(v.code)}">
    <button type="button" class="play" data-play="${esc(v.code)}" aria-label="${esc(t("voice.listen", { name }))}">${ICON.play}</button>
    <span class="vc-text"><strong>${esc(custom ? custom.name : v.code)}</strong><span>${esc(sub)}</span></span>
    <span class="check">${ICON.check}</span>
  </div>`;
}

function languageSection() {
  const all = hasAllLangs(S.draft);
  return `<section class="card" id="sec-langs">
    <div class="card-head"><div><h2>${esc(t("langs.title"))}</h2><p>${esc(t("langs.sub", { n: allLangCodes().length }))}</p></div></div>
    <label class="switch"><input type="checkbox" id="lang-all" ${all ? "checked" : ""}><span class="track" aria-hidden="true"></span> ${esc(t("langs.all"))}</label>
    <div class="lang-toolbar" id="lang-toolbar">
      <span class="note" id="lang-count"></span><span class="spacer"></span>
      <input class="text-input" id="lang-filter" placeholder="${esc(t("langs.filter"))}" autocomplete="off">
      <button class="btn btn-sm" type="button" data-act="lang-es-en">${esc(t("langs.es_en"))}</button>
    </div>
    <div id="lang-grid" class="lang-grid"></div>
    <div class="err" data-err="languages"></div>
    <div class="field narrow" data-wrap="language">
      <label for="f-language">${esc(t("langs.default"))}</label>
      <select id="f-language" data-field="language"></select>
      <small>${esc(t("langs.default_help"))}</small>
      <div class="err" data-err="language"></div>
    </div>
  </section>`;
}

function behaviorSection() {
  const d = S.draft;
  const L = S.data.limits;
  const T = S.data.text_defaults;
  return `<section class="card" id="sec-behavior">
    <div class="card-head"><div><h2>${esc(t("beh.title"))}</h2><p>${esc(t("beh.sub"))}</p></div>
      <button class="btn btn-sm" type="button" data-act="reset-behavior">${esc(t("beh.reset"))}</button></div>
    <div class="callout info"><div>${esc(t("beh.sampling_note"))}</div></div>
    <div class="behavior-list">
      ${behaviorField({ field: "temperature", min: L.temperature.min, max: L.temperature.max, step: 0.05 })}
      ${behaviorField({ field: "top_p", min: L.top_p.min, max: L.top_p.max, step: 0.01 })}
      ${behaviorField({ field: "top_k", min: L.top_k.min, max: L.top_k.max, sliderMax: 200, step: 1, int: true })}
      ${behaviorField({ field: "max_history", min: L.max_history.min, max: L.max_history.max, sliderMax: 100, step: 1, int: true })}
      ${behaviorField({ field: "max_tool_rounds", min: L.max_tool_rounds.min, max: L.max_tool_rounds.max, step: 1, int: true })}
      ${behaviorField({ field: "think_pause", min: L.think_pause.min, max: L.think_pause.max, step: 0.25 })}
    </div>
    <div class="grid-2">
      ${textField({ field: "search_announcement", label: esc(t("beh.search")), value: d.search_announcement, placeholder: T.search_announcement, attrs: 'maxlength="300"' })}
      ${textField({ field: "fallback_message", label: esc(t("beh.fallback")), value: d.fallback_message, placeholder: T.fallback_message, attrs: 'maxlength="300"' })}
    </div>
  </section>`;
}

function personalitySection() {
  return `<section class="card" id="sec-personality">
    <div class="card-head"><div><h2>${esc(t("pers.title"))}</h2><p>${esc(t("pers.sub"))}</p></div></div>
    <div class="field" data-wrap="personality">
      <textarea id="f-personality" data-field="personality" class="tall" aria-label="${esc(t("pers.title"))}">${esc(S.draft.personality)}</textarea>
      <span class="counter" id="personality-count"></span>
      <div class="err" data-err="personality"></div>
    </div>
    <div class="callout info"><div>${t("pers.info")}</div></div>
    <details class="subtle" id="yaml-box"><summary>${esc(t("pers.yaml"))}</summary><pre class="yaml" id="yaml-preview">${esc(t("pers.yaml_loading"))}</pre></details>
  </section>`;
}

function updateHead() {
  const d = S.draft;
  if (!d || !$("#head-title")) return;
  const title = displayName(d);
  $("#head-title").textContent = title;
  $("#head-sub").textContent = t("head.sub", { model: d.base_model || t("head.no_model"), voice: d.voice, langs: langsSummary(d) });
  const { h, s } = assistantColor(d);
  $$(".js-assistant-avatar").forEach((av) => { av.textContent = d.name ? title[0] : "+"; });
  // El escenario (y el aro del modo voz) y la vista previa toman el color.
  $$(".js-assistant-avatar, .js-assistant-color, #stage").forEach((el) => {
    el.style.setProperty("--hue", h);
    el.style.setProperty("--sat", `${s}%`);
  });
  const empty = $("#chat-empty-title");
  if (empty) empty.textContent = t("chat.title", { name: title });
  $$(".js-host-name").forEach((el) => { el.textContent = title; });
  renderNav();
}

function updateCount() {
  const el = $("#personality-count");
  if (el) el.textContent = t("pers.count", { n: S.draft.personality.length });
}

// Modelo
function renderModelList() {
  renderModelsCard(); // la de Ajustes compartidos, si está a la vista
  const box = $("#model-list");
  if (!box) return;
  const d = S.draft;
  const hiddenNote = $("#model-hidden");
  hiddenNote.textContent = S.models.hidden?.length
    ? t("model.hidden", { n: S.models.hidden.length, list: S.models.hidden.map((m) => m.name).join(", ") })
    : "";
  if (S.models.online === false) {
    box.innerHTML = `<div class="callout warn wide">
      <div>${esc(t("model.offline"))} <button class="link" type="button" data-act="refresh-models">${esc(t("model.retry"))}</button>.</div>
      <input class="text-input" data-field="base_model" value="${esc(d.base_model)}" placeholder="gemma4:E4B" spellcheck="false" aria-label="${esc(t("model.title"))}">
    </div>`;
    return;
  }
  const usedBy = (name) =>
    S.data.assistants.filter((a) => a.base_model === name && a.name !== S.view.name).map(displayName);
  let html = "";
  const hidden = S.models.hidden?.find((m) => m.name === d.base_model);
  if (hidden) {
    html += `<div class="model-card missing"><strong>${esc(d.base_model)}</strong>
      <span class="meta">${esc(t("model.custom", { parent: hidden.parent || "?" }))}</span></div>`;
  } else if (d.base_model && !modelInstalled(d.base_model)) {
    html += `<div class="model-card missing">
      <strong>${esc(d.base_model)}</strong><span class="meta">${esc(t("model.missing"))}</span>
      <div><button class="btn btn-sm" type="button" data-act="pull-current">${esc(t("model.download_it"))}</button></div>
    </div>`;
  }
  html += S.models.models.map((m) => {
    const sel = m.name === d.base_model || (!d.base_model.includes(":") && m.name === `${d.base_model}:latest`);
    const caps = m.capabilities;
    const badges = [];
    if (caps == null) badges.push(`<span class="badge" title="${esc(t("model.caps_unknown_t"))}">${esc(t("model.caps_unknown"))}</span>`);
    else if (caps.includes("tools")) badges.push(`<span class="badge good" title="${esc(t("model.tools_t"))}">tools</span>`);
    else badges.push(`<span class="badge bad" title="${esc(t("model.no_tools_t"))}">${esc(t("model.no_tools"))}</span>`);
    if (caps && !caps.includes("completion")) badges.push(`<span class="badge bad">${esc(t("model.not_chat"))}</span>`);
    if (caps?.includes("thinking")) badges.push('<span class="badge">thinking</span>');
    if (caps?.includes("vision")) badges.push(`<span class="badge">${esc(t("model.vision"))}</span>`);
    usedBy(m.name).forEach((n) => badges.push(`<span class="badge use" title="${esc(t("model.also_used", { n }))}">${esc(n)}</span>`));
    if (modelUpdate(m.name)?.state === "available") badges.push(`<span class="badge bad" title="${esc(t("upd.badge_t"))}">${esc(t("upd.badge"))}</span>`);
    const meta = [m.parameter_size, m.quantization, fmtSize(m.size)].filter(Boolean).join(" · ");
    const mem = modelMemory(m.name);
    const vram = mem ? `<span class="meta vram" title="${esc(t(mem.measured ? "mem.measured" : "mem.estimated"))}">${esc(t("mem.card", { size: gb(mem.measured ?? mem.estimate) }))}${mem.measured ? "" : " *"}</span>` : "";
    return `<label class="model-card ${sel ? "selected" : ""}">
      <input type="radio" name="model" value="${esc(m.name)}" ${sel ? "checked" : ""}>
      <strong>${esc(m.name)}</strong><span class="meta">${esc(meta)}</span>${vram}
      <div class="badges">${badges.join("")}</div>
    </label>`;
  }).join("");
  if (!S.models.models.length) html += `<p class="empty">${esc(t("model.none"))}</p>`;
  box.innerHTML = html;
  renderMemoryBox();
  renderUpdateBox();
}

// ── Versiones nuevas de los modelos (ver model_updates.py) ─────────────
// Cada modelo se compara con su registro (ollama.com o Hugging Face). Si
// hay una versión nueva, se actualiza con el mismo pull de siempre: Ollama
// baja lo que cambió y borra la versión anterior. Con "actualizar
// automáticamente" lo hace solo el servidor cada 6 horas.
async function loadUpdates(force = false, only = null) {
  try {
    const q = new URLSearchParams();
    if (force) q.set("check", "1");
    if (only) q.set("model", only);
    S.updates = await api("GET", `/api/models/updates${q.toString() ? `?${q}` : ""}`);
  } catch {
    S.updates = S.updates || null;
  }
  renderModelList();
}

const modelUpdate = (name) => S.updates?.models?.[name] || null;
const autoUpdate = (name) => S.updates?.auto?.[name] ?? true;

function fmtClock(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const sameDay = d.toDateString() === new Date().toDateString();
  return d.toLocaleString(S.lang, sameDay ? { hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function renderUpdateBox() {
  const box = $("#model-upd");
  if (!box) return;
  const name = S.draft.base_model;
  if (!S.updates || !modelInstalled(name)) {
    box.innerHTML = "";
    return;
  }
  const u = modelUpdate(name);
  const pulling = S.pull?.state === "running" && S.pull.model === name;
  let line;
  let action = "";
  if (pulling || S.updates.updating === name) {
    line = `<span class="upd-state busy">${esc(t("upd.updating"))}</span>`;
  } else if (!u) {
    line = `<span class="upd-state">${esc(t(S.updates.checking ? "upd.checking" : "upd.unchecked"))}</span>`;
    action = `<button class="btn btn-sm" type="button" data-act="check-model-update">${esc(t("upd.check"))}</button>`;
  } else if (u.state === "available") {
    line = `<span class="upd-state new">${esc(t("upd.available", { size: u.size ? fmtSize(u.size) : "?" }))}</span>`;
    action = `<button class="btn btn-sm btn-primary" type="button" data-act="update-model">${esc(t("upd.update"))}</button>`;
  } else if (u.state === "current") {
    line = `<span class="upd-state ok">${esc(t("upd.current", { when: fmtClock(u.checked_at) }))}</span>`;
    action = `<button class="btn btn-sm btn-quiet" type="button" data-act="check-model-update">${esc(t("upd.check"))}</button>`;
  } else {
    line = `<span class="upd-state">${esc(t("upd.unknown", { error: u.error || "?" }))}</span>`;
    action = `<button class="btn btn-sm btn-quiet" type="button" data-act="check-model-update">${esc(t("upd.check"))}</button>`;
  }
  box.innerHTML = `
    <div class="mem-head"><strong>${esc(t("upd.title"))}</strong>${action}</div>
    <div>${line}</div>
    <label class="switch small"><input type="checkbox" id="upd-auto" ${autoUpdate(name) ? "checked" : ""}>
      <span class="track" aria-hidden="true"></span> ${esc(t("upd.auto"))}</label>
    <small class="note">${esc(t("upd.note"))}</small>`;
  $("#upd-auto").onchange = async (e) => {
    try {
      S.updates = await api("PUT", "/api/models/updates/auto", { model: name, auto: e.target.checked });
      toast(t(e.target.checked ? "upd.auto_on" : "upd.auto_off", { model: name }));
    } catch (err) {
      toast(err.message, "error");
      e.target.checked = !e.target.checked;
    }
  };
}

async function updateModel() {
  const name = S.draft.base_model;
  try {
    S.pull = await api("POST", "/api/models/update", { model: name });
    S.pullWatching = true;
    $("#pull-box") && ($("#pull-box").open = true);
    renderPullStatus();
    renderUpdateBox();
    pollPull();
  } catch (e) {
    toast(e.message, "error", 6000);
  }
}


async function startPull(name) {
  name = String(name || "").trim();
  if (!name) {
    toast(t("pull.need_name"), "warn");
    return;
  }
  try {
    S.pull = await api("POST", "/api/models/pull", { model: name });
    S.pullWatching = true;
    renderPullStatus();
    pollPull();
  } catch (e) {
    toast(e.message, "error", 6000);
  }
}

async function pollPull() {
  clearTimeout(S.pullTimer);
  try {
    S.pull = await api("GET", "/api/models/pull");
  } catch {
    return;
  }
  renderPullStatus();
  if (S.pull.state === "running") {
    S.pullWatching = true;
    S.pullTimer = setTimeout(pollPull, 800);
  } else if (S.pullWatching) {
    S.pullWatching = false;
    if (S.pull.state === "done") {
      toast(t("pull.done_toast", { model: S.pull.model }));
      // Si fue una actualización, el servidor la verifica al terminar.
      setTimeout(() => loadUpdates(), 2500);
      await loadModels();
      renderModelList();
      if (S.view?.kind === "gallery") renderGallery();
    } else if (S.pull.state === "error") {
      toast(t("pull.error_toast", { model: S.pull.model, error: S.pull.error }), "error", 8000);
    }
  }
}

function renderPullStatus() {
  const box = $("#pull-status");
  if (!box) return;
  const p = S.pull;
  const btn = $('[data-act="pull"]');
  if (btn) btn.disabled = p?.state === "running";
  if (!p || p.state === "idle") {
    box.innerHTML = "";
    return;
  }
  if (p.state === "running") {
    $("#pull-box").open = true;
    const pct = p.total ? Math.floor((p.completed / p.total) * 100) : 0;
    const detail = p.total ? t("pull.detail", { pct, done: fmtSize(p.completed), total: fmtSize(p.total) }) : "";
    box.innerHTML = `<div class="progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
      <div class="pull-state">${t("pull.running", { model: esc(p.model), status: esc(p.status || "…"), detail })}</div>`;
  } else if (p.state === "done") {
    box.innerHTML = `<div class="pull-state">${t("pull.done", { model: esc(p.model) })}</div>`;
  } else {
    box.innerHTML = `<div class="pull-state error">${t("pull.error", { model: esc(p.model), error: esc(p.error) })}</div>`;
  }
}

// Muestras de voz (en el idioma de la interfaz)
const previewAudio = new Audio();
previewAudio.preservesPitch = true;
let previewCode = null;
previewAudio.addEventListener("ended", () => { previewCode = null; updatePlayButtons(); });

const clampRate = (v) => Math.min(4, Math.max(0.25, Number(v) || 1));

function playPreview(code) {
  if (previewCode === code) {
    stopPreview();
    return;
  }
  stopPreview();
  previewAudio.src = previewUrl(code);
  // Las voces clonadas no cambian de velocidad (Qwen3-TTS no lo permite).
  previewAudio.defaultPlaybackRate = previewAudio.playbackRate = isCustomVoice(code) ? 1 : clampRate(S.draft.speed);
  if (isCustomVoice(code)) toast(t("voice.custom_generating"), "ok", 4000); // la primera vez tarda unos segundos
  previewCode = code;
  previewAudio.play().catch(() => {
    previewCode = null;
    updatePlayButtons();
    toast(t("voice.play_failed"), "error");
  });
  updatePlayButtons();
}

function stopPreview() {
  previewAudio.pause();
  previewCode = null;
  updatePlayButtons();
}

function updatePlayButtons() {
  $$("[data-play]").forEach((b) => {
    const on = b.dataset.play === previewCode;
    b.classList.toggle("playing", on);
    b.innerHTML = on ? ICON.stop : ICON.play;
  });
}

function selectVoice(code) {
  S.draft.voice = code;
  $$("[data-voice]").forEach((el) => {
    const on = el.dataset.voice === code;
    el.classList.toggle("selected", on);
    el.setAttribute("aria-checked", String(on));
  });
  afterChange("voice");
}

// Idiomas
function renderLangs() {
  const d = S.draft;
  const all = hasAllLangs(d);
  const filter = ($("#lang-filter")?.value || "").trim().toLowerCase();
  const grid = $("#lang-grid");
  grid.classList.toggle("disabled", all);
  grid.innerHTML = allLangCodes()
    .filter((c) => !filter || langName(c).toLowerCase().includes(filter) || c.includes(filter))
    .map((c) => `<label class="lang-item"><input type="checkbox" data-lang="${c}" ${all || d.languages.includes(c) ? "checked" : ""} ${all ? 'tabindex="-1"' : ""}>
      ${esc(langName(c))}<code>${c}</code></label>`)
    .join("") || `<p class="empty">${esc(t("langs.none_match"))}</p>`;
  $("#lang-all").checked = all;
  $("#lang-toolbar").classList.toggle("dim", all);
  $("#lang-count").textContent = all
    ? t("langs.count_all", { n: allLangCodes().length })
    : t("langs.count", { k: d.languages.length, n: allLangCodes().length });
  const options = all ? allLangCodes() : allLangCodes().filter((c) => d.languages.includes(c));
  $("#f-language").innerHTML = options
    .map((c) => `<option value="${c}" ${c === d.language ? "selected" : ""}>${esc(langName(c))} (${c})</option>`)
    .join("");
}

function setLanguages(list) {
  const d = S.draft;
  d.languages = [...new Set(list)].sort();
  if (d.languages.length && !d.languages.includes(d.language)) {
    d.language = d.languages.includes("es") ? "es" : d.languages[0];
    toast(t("langs.default_changed", { lang: langName(d.language) }), "warn");
  }
  renderLangs();
  afterChange("languages");
}

function toggleLang(code, checked) {
  const d = S.draft;
  if (!checked && d.languages.length === 1 && d.languages[0] === code) {
    toast(t("langs.keep_one"), "warn");
    renderLangs();
    return;
  }
  setLanguages(checked ? [...d.languages, code] : d.languages.filter((c) => c !== code));
}

// Variantes (alias) y exclusiones
function onChipKey(add, removeLast, count) {
  return (e) => {
    if (e.key === "Enter" || e.key === "," || e.key === " ") {
      e.preventDefault();
      add(e.target.value);
      e.target.value = "";
    } else if (e.key === "Backspace" && !e.target.value && count()) {
      removeLast();
    }
  };
}

function addAlias(raw) {
  const word = normWord(raw);
  if (!word) return;
  if (word === S.draft.name || S.draft.aliases.includes(word)) return;
  S.draft.aliases.push(word);
  afterAliasChange();
}

function afterAliasChange() {
  renderAliasChips();
  afterChange("aliases");
  scheduleWakeCheck();
}

function renderAliasChips() {
  $("#alias-chips").innerHTML = S.draft.aliases
    .map((a, i) => `<span class="chip">${esc(a)}<button type="button" data-rm-alias="${i}" aria-label="× ${esc(a)}">×</button></span>`)
    .join("");
}

function scheduleWakeCheck(delay = 350) {
  clearTimeout(S.wakeTimer);
  S.wakeTimer = setTimeout(runWakeCheck, delay);
}

async function runWakeCheck() {
  const box = $("#wake-report");
  if (!box || !S.draft) return;
  const d = S.draft;
  if (!d.name) {
    box.innerHTML = "";
    return;
  }
  if (!d.wake_word) {
    box.innerHTML = `<div class="callout info"><div>${esc(t("wake.off"))}</div></div>`;
    return;
  }
  const seq = ++S.wakeSeq;
  let r;
  try {
    r = await api("POST", "/api/wake-check", {
      name: d.name,
      aliases: d.aliases,
      original: S.view.kind === "assistant" ? S.view.name : null,
      exclusions: d.add_exclusions,
    });
  } catch {
    return;
  }
  if (seq !== S.wakeSeq || !$("#wake-report")) return;

  let html = "";
  if (r.collisions.length) {
    html += `<div class="callout warn">
      <div>${t("wake.collisions", { name: esc(d.name) })}</div>
      <div class="row">${r.collisions.map((c) => `<span class="tag">${esc(c.word)} <em>${Math.round(c.ratio * 100)}%</em>
        <button type="button" data-exclude="${esc(c.word)}">${esc(t("wake.exclude"))}</button></span>`).join("")}</div>
      <div class="row"><button class="btn btn-sm" type="button" data-act="exclude-all">${esc(t("wake.exclude_all"))}</button></div>
    </div>`;
  }
  if (r.confusions.length) {
    const list = r.confusions.map((c) => t("wake.confusion_item", { word: esc(c.word), assistant: esc(c.assistant.toUpperCase()), pct: Math.round(c.ratio * 100) })).join(", ");
    html += `<div class="callout warn"><div>${t("wake.confusions", { list })}</div></div>`;
  }
  if (!html) html = `<div class="callout ok"><div>${esc(t("wake.ok"))}</div></div>`;
  if (d.add_exclusions.length) {
    html += `<div class="callout info"><div>${esc(t("wake.pending"))}</div>
      <div class="row">${d.add_exclusions.map((w) => `<span class="chip pending">${esc(w)}<button type="button" data-unexclude="${esc(w)}" aria-label="× ${esc(w)}">×</button></span>`).join("")}</div></div>`;
  }
  box.innerHTML = html;
}

function excludeWords(words) {
  const d = S.draft;
  words.forEach((w) => { if (!d.add_exclusions.includes(w)) d.add_exclusions.push(w); });
  afterChange("add_exclusions");
  scheduleWakeCheck(0);
}

// Vista previa YAML
async function refreshPreview() {
  const pre = $("#yaml-preview");
  if (!pre || !$("#yaml-box").open) return;
  try {
    const r = await api("POST", "/api/preview", { assistant: S.draft });
    pre.textContent = r.yaml;
  } catch (e) {
    pre.textContent = t("pers.yaml_failed", { error: e.message });
  }
}

// ── Cambios, errores y guardado ────────────────────────────────────────
function afterChange(field) {
  clearError(field);
  if (S.view.kind !== "shared") {
    if (["name", "label", "voice", "base_model", "languages", "language", "color"].includes(field)) updateHead();
    if (field === "name" && !S.draft.color) renderColorPicker(); // el automático depende del nombre
    if (field === "name") {
      $("#f-label").placeholder = S.draft.name ? S.draft.name.toUpperCase() : "NOVA";
      scheduleWakeCheck();
    }
    if (field === "wake_word" || field === "push_to_talk_key") {
      clearError("wake_word");
      clearError("push_to_talk_key");
    }
    if (field === "personality") updateCount();
    if (field === "speed" && previewCode) previewAudio.playbackRate = clampRate(S.draft.speed);
    if (BEHAVIOR_INFO[field]) {
      const zone = $(`[data-zone="${field}"]`);
      if (zone) zone.textContent = zoneLabel(field, S.draft[field]);
    }
    clearTimeout(S.previewTimer);
    S.previewTimer = setTimeout(refreshPreview, 400);
    if (field === "languages" || field === "language") renderChatLangSelect();
    if (field === "voice") renderMemoryBox();
    if (field === "base_model") {
      pruneGuests();
      renderChat();
    }
  }
  if (field === "user_context.latitud" || field === "user_context.longitud") updatePlaceLabel();
  refreshSaveBar();
}

function onFieldInput(el) {
  const field = el.dataset.field;
  let value = el.value;
  if (el.dataset.num) {
    if (value === "") return; // escribiendo; se valida al guardar
    value = el.dataset.num === "int" ? parseInt(value, 10) : parseFloat(value);
    if (Number.isNaN(value)) return;
    $$(`[data-field="${field}"]`).forEach((other) => { if (other !== el) other.value = value; });
  }
  if (field === "name") {
    const clean = normWord(value);
    if (clean !== value) el.value = clean;
    value = clean;
    const d = S.draft;
    if (d.personality === personalityTemplate(d.name.toUpperCase())) {
      d.personality = personalityTemplate(clean.toUpperCase());
      $("#f-personality").value = d.personality;
    }
  }
  setPath(S.draft, field, value);
  afterChange(field);
}

function clearError(field) {
  const err = $(`[data-err="${CSS.escape(field)}"]`);
  if (err) err.textContent = "";
  $(`[data-wrap="${CSS.escape(field)}"]`)?.classList.remove("invalid");
}

function clearErrors() {
  $$("[data-err]").forEach((e) => { e.textContent = ""; });
  $$(".invalid").forEach((e) => e.classList.remove("invalid"));
}

function showErrors(fields) {
  clearErrors();
  let first = null;
  for (const [field, msg] of Object.entries(fields)) {
    const err = $(`[data-err="${CSS.escape(field)}"]`);
    if (!err) continue;
    err.textContent = msg;
    $(`[data-wrap="${CSS.escape(field)}"]`)?.classList.add("invalid");
    first = first || err;
  }
  if (first) {
    const cfgSec = first.closest("[data-cfg-section]");
    if (cfgSec && cfgSec.hidden) selectSettingsCat(cfgSec.dataset.cfgSection);
    const asstCard = first.closest("#panel-body > .card");
    if (asstCard && asstCard.hidden && asstCard.id) selectAssistantCat(asstCard.id);
    first.closest(".card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function validateAssistant() {
  const d = S.draft;
  const e = {};
  if (!/^[a-z][a-z0-9]{1,29}$/.test(d.name)) {
    e.name = t("err.name");
  } else if (S.data.assistants.some((a) => a.name === d.name && !(S.view.kind === "assistant" && S.view.name === a.name))) {
    e.name = t("err.name_taken", { name: d.name });
  }
  if (!d.base_model.trim()) e.base_model = t("err.model");
  for (const [key, lim] of Object.entries(S.data.limits)) {
    const v = d[key];
    if (typeof v !== "number" || Number.isNaN(v) || v < lim.min || v > lim.max || (lim.int && !Number.isInteger(v))) {
      e[key] = t("err.range", { min: lim.min, max: lim.max });
    }
  }
  if (!d.personality.trim()) e.personality = t("err.personality");
  if (!d.wake_word && !d.push_to_talk_key) e.wake_word = t("err.activation");
  const other = d.push_to_talk_key && S.data.assistants.find((a) =>
    a.push_to_talk_key === d.push_to_talk_key && !(S.view.kind === "assistant" && S.view.name === a.name));
  if (other) e.push_to_talk_key = t("err.ptt_taken", { other: displayName(other) });
  return e;
}

async function saveAssistant() {
  const errors = validateAssistant();
  if (Object.keys(errors).length) {
    setPanelOpen(true);
    showErrors(errors);
    toast(t("save.check"), "error");
    return;
  }
  const isNew = S.view.kind === "new";
  const btn = $('[data-act="save"]');
  btn.disabled = true;
  try {
    const payload = { version: S.data.version, assistant: S.draft };
    const res = isNew
      ? await api("POST", "/api/assistants", payload)
      : await api("PUT", `/api/assistants/${encodeURIComponent(S.view.name)}`, payload);
    setData(res.state);
    toast(t(isNew ? "save.created" : "save.saved", { name: displayName(S.draft) }));
    await select({ kind: "assistant", name: res.name }, { force: true, keepChat: true, push: false });
  } catch (e) {
    handleSaveError(e);
  } finally {
    if (btn.isConnected) btn.disabled = false;
  }
}

function handleSaveError(e) {
  if (e.status === 409) {
    confirmDialog(t("save.conflict_title"), e.message, t("save.reload"), false).then(async (ok) => {
      if (!ok) return;
      await loadState();
      await select(S.view.kind === "new" ? { kind: "new" } : S.view, { force: true, keepChat: true, push: false });
    });
    return;
  }
  if (Object.keys(e.fields || {}).length) setPanelOpen(true);
  showErrors(e.fields || {});
  toast(e.message, "error", 6000);
}

async function deleteAssistant() {
  const a = S.data.assistants.find((x) => x.name === S.view.name);
  if (!a) return;
  if (S.data.assistants.length === 1) {
    toast(t("del.keep_one"), "warn");
    return;
  }
  const ok = await confirmDialog(t("del.title", { name: displayName(a) }), t("del.text"), t("del.ok"));
  if (!ok) return;
  try {
    const res = await api("DELETE", `/api/assistants/${encodeURIComponent(a.name)}`, { version: S.data.version });
    setData(res.state);
    toast(t("del.done", { name: displayName(a) }));
    await select({ kind: "gallery" }, { force: true });
  } catch (e) {
    handleSaveError(e);
  }
}

async function duplicateAssistant() {
  if (!(await guardDirty())) return;
  const source = S.data.assistants.find((x) => x.name === S.view.name);
  const copy = { ...structuredClone(source), name: "", label: "", aliases: [], add_exclusions: [], push_to_talk_key: "", wake_word: true,
    shared: isAdmin(), editable: true, mine: true, owner: "", owner_name: "" };
  await select({ kind: "new" }, { force: true, draft: copy });
  toast(t("dup.toast", { name: displayName(source) }));
  $("#f-name").focus();
}

function resetBehavior() {
  const L = S.data.limits;
  for (const key of ["temperature", "top_p", "top_k", "max_history", "max_tool_rounds", "think_pause"]) {
    S.draft[key] = L[key].default;
    $$(`[data-field="${key}"]`).forEach((el) => { el.value = L[key].default; });
    afterChange(key);
  }
}

async function discard() {
  if (S.view.kind === "new") {
    await select({ kind: "gallery" });
  } else {
    await select(S.view, { force: true, keepChat: true, push: false });
  }
}

// ── Ajustes compartidos (divididos por categoría con menú general) ────
function settingsCategories(admin) {
  const cats = [
    { id: "profile", icon: svgIcon("user", 18), title: t("cfg.cat_profile"), sub: t("cfg.cat_profile_sub") },
  ];
  if (!isGuest()) {
    cats.push(
      { id: "security", icon: svgIcon("shield", 18), title: t("cfg.cat_security"), sub: t("cfg.cat_security_sub") },
    );
  }
  cats.push(
    { id: "memory", icon: svgIcon("brain", 18), title: t("cfg.cat_memory"), sub: t("cfg.cat_memory_sub") },
    { id: "models", icon: svgIcon("cpu", 18), title: t("cfg.cat_models"), sub: t("cfg.cat_models_sub") },
  );
  if (admin) {
    cats.push(
      { id: "voice", icon: svgIcon("mic", 18), title: t("cfg.cat_voice"), sub: t("cfg.cat_voice_sub") },
      { id: "rules", icon: svgIcon("users", 18), title: t("cfg.cat_rules"), sub: t("cfg.cat_rules_sub") },
      { id: "plugins", icon: svgIcon("plug", 18), title: t("cfg.cat_plugins"), sub: t("cfg.cat_plugins_sub") },
      { id: "system", icon: svgIcon("server", 18), title: t("cfg.cat_system"), sub: t("cfg.cat_system_sub") },
    );
  }
  return cats;
}

function selectSettingsCat(catId) {
  const cats = settingsCategories(isAdmin());
  if (!cats.some((c) => c.id === catId)) catId = cats[0].id;
  S.settingsCat = catId;
  $$("[data-cfg-cat]").forEach((b) => {
    const on = b.dataset.cfgCat === catId;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  $$("[data-cfg-section]").forEach((sec) => {
    sec.hidden = sec.dataset.cfgSection !== catId;
  });
  if (catId === "profile") updatePlaceLabel();
}

function renderShared() {
  const d = S.draft;
  const uc = d.user_context;
  const admin = isAdmin();
  const cats = settingsCategories(admin);
  if (!S.settingsCat || !cats.some((c) => c.id === S.settingsCat)) S.settingsCat = cats[0].id;

  const knownFeatureIds = new Set(["memory-card", "reminders-card", "routines-card", "plugins-card", "mcp-card", "diag-card", "backup-card"]);
  const extraFeatureCards = (FEATURE_CARDS.settings || [])
    .filter((c) => c.when() && !knownFeatureIds.has(c.id))
    .map((c) => `<section class="card" id="${c.id}"></section>`)
    .join("\n");

  const secHead = (cat) => `<div class="cfg-sec-banner">
    <div class="cfg-sec-ico">${cat.icon}</div>
    <div><h2>${esc(cat.title)}</h2><p>${esc(cat.sub)}</p></div>
  </div>`;

  const catMap = Object.fromEntries(cats.map((c) => [c.id, c]));

  $("#main").innerHTML = `
  <div class="settings-shell">
    <header class="editor-head cfg-top-head">
      <div class="avatar avatar-lg">${ICON.gear}</div>
      <div class="head-text"><h1>${esc(t(settingsKey()))}</h1><p>${esc(t(admin ? "shared.sub" : "settings.sub_user"))}</p></div>
    </header>
    ${guestBanner()}
    <div class="cfg-layout">
      <aside class="cfg-sidebar">
        <nav class="cfg-menu" role="tablist" aria-label="${esc(t("cfg.menu_label"))}">
          ${cats.map((c) => `<button type="button" role="tab" class="cfg-menu-btn ${S.settingsCat === c.id ? "active" : ""}"
            aria-selected="${S.settingsCat === c.id}" data-cfg-cat="${c.id}">
            <span class="cfg-menu-ico">${c.icon}</span>
            <span class="cfg-menu-text">
              <strong>${esc(c.title)}</strong>
              <small>${esc(c.sub)}</small>
            </span>
          </button>`).join("")}
        </nav>
      </aside>
      <div class="cfg-content editor">
        <div class="cfg-section" data-cfg-section="profile" ${S.settingsCat === "profile" ? "" : "hidden"}>
          ${secHead(catMap.profile)}
          ${d.me ? myProfileCard() : ""}
          <section class="card" id="you-card">
            <div class="card-head"><div><h2>${esc(t("shared.you"))}</h2><p>${esc(t("shared.you_sub"))}</p></div></div>
            <div class="grid-3">
              ${textField({ field: "user_context.nombre", label: esc(t("shared.name")), value: uc.nombre, attrs: 'maxlength="80"' })}
              ${textField({ field: "user_context.pais", label: esc(t("shared.country")), value: uc.pais, attrs: 'maxlength="80"' })}
              ${textField({ field: "user_context.ubicacion", label: esc(t("shared.city")), value: uc.ubicacion, attrs: 'maxlength="200"' })}
            </div>
            <div class="grid-2">
              ${textField({ field: "user_context.latitud", label: esc(t("shared.lat")), value: uc.latitud, placeholder: "10.2833", attrs: 'inputmode="decimal" autocomplete="off"' })}
              ${textField({ field: "user_context.longitud", label: esc(t("shared.lon")), value: uc.longitud, placeholder: "-84.2333", attrs: 'inputmode="decimal" autocomplete="off"' })}
            </div>
            <div class="place-row">
              <button class="btn" type="button" data-act="open-map">${ICON.pin} ${esc(t("map.open"))}</button>
              <span class="place-label" id="place-label"></span>
            </div>
            <p class="note">${esc(t("shared.coords_help"))}</p>
          </section>
        </div>

        ${d.me ? `
        <div class="cfg-section" data-cfg-section="security" ${S.settingsCat === "security" ? "" : "hidden"}>
          ${secHead(catMap.security)}
          ${mySecurityCard()}
        </div>` : ""}

        <div class="cfg-section" data-cfg-section="memory" ${S.settingsCat === "memory" ? "" : "hidden"}>
          ${secHead(catMap.memory)}
          <section class="card" id="memory-card"></section>
          <section class="card" id="reminders-card"></section>
          <section class="card" id="routines-card"></section>
        </div>

        <div class="cfg-section" data-cfg-section="models" ${S.settingsCat === "models" ? "" : "hidden"}>
          ${secHead(catMap.models)}
          <section class="card" id="ollama-card"></section>
          <section class="card" id="models-card"></section>
        </div>

        ${admin ? `
        <div class="cfg-section" data-cfg-section="voice" ${S.settingsCat === "voice" ? "" : "hidden"}>
          ${secHead(catMap.voice)}
          <section class="card" id="voices-card"></section>
          <section class="card" id="excl-card">
            <div class="card-head"><div><h2>${esc(t("shared.excl"))}</h2><p>${t("shared.excl_sub")}</p></div></div>
            <div class="field" data-wrap="exclusions">
              <div class="chips-input"><span id="excl-chips" class="chips"></span>
                <input id="excl-input" placeholder="${esc(t("shared.excl_ph"))}" autocomplete="off" spellcheck="false" aria-label="${esc(t("shared.excl_ph"))}"></div>
              <small>${esc(t("shared.excl_help"))}</small>
              <div class="err" data-err="exclusions"></div>
            </div>
          </section>
        </div>

        <div class="cfg-section" data-cfg-section="rules" ${S.settingsCat === "rules" ? "" : "hidden"}>
          ${secHead(catMap.rules)}
          <section class="card" id="rules-card">
            <div class="card-head"><div><h2>${esc(t("shared.rules"))}</h2><p>${t("shared.rules_sub")}</p></div></div>
            <div class="field" data-wrap="shared_context">
              <textarea data-field="shared_context" class="tall" aria-label="${esc(t("shared.rules"))}">${esc(d.shared_context)}</textarea>
              <div class="err" data-err="shared_context"></div>
            </div>
          </section>
          <section class="card" id="profiles-card"></section>
        </div>

        <div class="cfg-section" data-cfg-section="plugins" ${S.settingsCat === "plugins" ? "" : "hidden"}>
          ${secHead(catMap.plugins)}
          <section class="card" id="plugins-card"></section>
          <section class="card" id="mcp-card"></section>
          ${extraFeatureCards}
        </div>

        <div class="cfg-section" data-cfg-section="system" ${S.settingsCat === "system" ? "" : "hidden"}>
          ${secHead(catMap.system)}
          <section class="card" id="net-card"></section>
          <section class="card" id="diag-card"></section>
          <section class="card" id="backup-card"></section>
        </div>` : ""}
      </div>
    </div>
  </div>
  ${saveBar(t(admin ? "save.shared" : "save.save"))}`;

  bindMain();
  const input = $("#excl-input");
  if (input) {
    input.addEventListener("keydown", onChipKey(addExclusion, () => {
      S.draft.exclusions.pop();
      renderExclusionChips();
      refreshSaveBar();
    }, () => S.draft.exclusions.length));
    input.addEventListener("blur", (e) => { addExclusion(e.target.value); e.target.value = ""; });
    renderExclusionChips();
  }
  refreshSaveBar();
  updatePlaceLabel();
  renderOllamaCard();
  loadOllamaUpdate().then((st) => { if (OLLAMA_BUSY.includes(st?.state)) pollOllamaUpdate(); });
  renderModelsCard();
  loadUpdates();
  mountFeatureCards("settings");
  if (admin) {
    renderVoicesCard();
    renderProfilesCard();
    renderNetCard();
    loadNetCard();
  }
}

// ── Modelos de IA instalados (Ajustes compartidos) ────────────────────
// Ver, agregar (ollama pull), actualizar y eliminar los modelos base. Si
// un asistente usa el que se va a borrar, se avisa antes.
const usersOf = (name) => S.data.assistants.filter((a) => a.base_model === name || (!a.base_model.includes(":") && `${a.base_model}:latest` === name));

function renderModelsCard() {
  const box = $("#models-card");
  if (!box) return;
  const pulling = S.pull?.state === "running" ? S.pull.model : null;
  const rows = (S.models.models || []).map((m) => {
    const users = usersOf(m.name);
    const upd = modelUpdate(m.name);
    const mem = modelMemory(m.name);
    const caps = (m.capabilities || []).filter((c) => ["tools", "vision", "thinking", "audio"].includes(c));
    const meta = [m.parameter_size, m.quantization, fmtSize(m.size), mem ? t("mem.card", { size: gb(mem.measured ?? mem.estimate) }) : ""].filter(Boolean).join(" · ");
    const busy = pulling === m.name;
    const state = busy ? `<span class="mm-state busy">${esc(t("upd.updating_short"))}</span>`
      : upd?.state === "available" ? `<span class="badge bad">${esc(t("upd.badge"))}</span>`
      : upd?.state === "current" ? `<span class="badge good">${esc(t("mm.latest"))}</span>` : "";
    return `<div class="mm-row ${busy ? "busy" : ""}">
      <div class="mm-main">
        <div class="mm-name"><strong>${esc(m.name)}</strong>${state}</div>
        <div class="mm-meta">${esc(meta)}</div>
        <div class="badges">${caps.map((c) => `<span class="badge">${esc(c === "vision" ? t("model.vision") : c)}</span>`).join("")}
          ${users.length ? users.map((a) => `<span class="badge use">${esc(displayName(a))}</span>`).join("") : `<span class="mm-unused">${esc(t("mm.unused"))}</span>`}</div>
      </div>
      <div class="mm-acts">
        ${upd?.state === "available" ? `<button class="btn btn-sm btn-primary admin-act" type="button" data-mm="update" data-model="${esc(m.name)}" ${pulling ? "disabled" : ""}>${esc(t("upd.update"))}</button>` : ""}
        <button class="btn btn-sm btn-ghost-danger admin-act" type="button" data-mm="delete" data-model="${esc(m.name)}" ${busy ? "disabled" : ""}>${esc(t("mm.delete"))}</button>
      </div>
    </div>`;
  }).join("");
  box.innerHTML = `
    <div class="card-head"><div><h2>${esc(t("mm.title"))}</h2><p>${esc(t("mm.sub"))}</p></div>
      <button class="btn btn-sm" type="button" data-mm="check" ${S.updates?.checking ? "disabled" : ""}>${esc(t(S.updates?.checking ? "upd.checking" : "mm.check"))}</button></div>
    ${S.models.online === false ? `<div class="callout warn"><div>${esc(t("model.offline"))}</div></div>` : ""}
    <div class="mm-list">${rows || `<p class="empty">${esc(t("model.none"))}</p>`}</div>
    ${isAdmin() ? "" : `<p class="note">${esc(t("admin.only"))}</p>`}
    <details class="subtle admin-act" id="pull-box" ${S.pull?.state === "running" ? "open" : ""}>
      <summary>${esc(t("mm.add"))}</summary>
      <div class="pull-row">
        <input class="text-input" id="pull-input" placeholder="${esc(t("pull.ph"))}" spellcheck="false" autocomplete="off" autocapitalize="off">
        <button class="btn" type="button" data-act="pull">${esc(t("pull.button"))}</button>
      </div>
      <small class="note">${t("pull.help")}</small>
      <div id="pull-status"></div>
    </details>`;
  renderPullStatus();
  box.onclick = onModelsCardClick;
}

async function onModelsCardClick(e) {
  const b = e.target.closest("[data-mm]");
  if (!b) return;
  const name = b.dataset.model;
  if (b.dataset.mm === "check") {
    S.updates = { ...(S.updates || {}), checking: true };
    renderModelsCard();
    return loadUpdates(true);
  }
  if (b.dataset.mm === "update") {
    try {
      S.pull = await api("POST", "/api/models/update", { model: name });
      S.pullWatching = true;
      renderModelsCard();
      pollPull();
    } catch (err) {
      toast(err.message, "error", 6000);
    }
    return;
  }
  if (b.dataset.mm === "delete") {
    const users = usersOf(name).map(displayName);
    const text = users.length
      ? t("mm.delete_used", { model: name, list: users.join(", ") })
      : t("mm.delete_text", { model: name });
    if (!(await confirmDialog(t("mm.delete_title"), text, t("mm.delete")))) return;
    b.disabled = true;
    try {
      S.models = await api("DELETE", "/api/models", { model: name });
      toast(t("mm.deleted", { model: name }));
      loadMemory();
      loadUpdates();
    } catch (err) {
      toast(err.message, "error", 7000);
    }
    renderModelsCard();
  }
}


// ── Acceso desde otros dispositivos (ver network.py) ──────────────────
const NET = { st: null };
const QRLIB = {
  js: ["https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js", "sha512-ZDSPMa/JM1D+7kdg2x3BsruQ6T/JpJo3jWDWkCZsP+5yVyp1KfESqLI+7RqB5k24F7p2cV7i2YHh/890y6P6Sw=="],
  loading: null,
};

function loadQrLib() {
  if (window.qrcode) return Promise.resolve();
  if (QRLIB.loading) return QRLIB.loading;
  QRLIB.loading = new Promise((resolve, reject) => {
    const s = Object.assign(document.createElement("script"), { src: QRLIB.js[0], integrity: QRLIB.js[1], crossOrigin: "anonymous", referrerPolicy: "no-referrer" });
    s.onload = resolve;
    s.onerror = () => { QRLIB.loading = null; reject(new Error("QR")); };
    document.head.append(s);
  });
  return QRLIB.loading;
}

async function loadNetCard() {
  try {
    NET.st = await api("GET", "/api/network");
  } catch (e) {
    NET.st = { error: e.message };
  }
  renderNetCard();
}

function renderNetCard() {
  const box = $("#net-card");
  if (!box) return;
  const st = NET.st;
  const head = `<div class="card-head"><div><h2>${esc(t("net.title"))}</h2><p>${esc(t("net.sub"))}</p></div></div>`;
  if (!st) {
    box.innerHTML = `${head}<p class="note">${esc(t("ollama.loading"))}</p>`;
    return;
  }
  if (!st.local) {
    box.innerHTML = `${head}<p>${esc(t("net.remote", { host: location.host }))}</p>`;
    return;
  }
  const toggle = `<label class="switch"><input type="checkbox" id="net-enabled" ${st.enabled ? "checked" : ""}>
    <span class="track" aria-hidden="true"></span> ${esc(t("net.enable"))}</label>`;
  let body = "";
  if (st.enabled && st.running && st.urls?.length) {
    const links = st.urls.map((u) => `<div class="net-url"><code>${esc(u)}</code>
      <button class="btn btn-sm" type="button" data-net-copy="${esc(u)}">${esc(t("net.copy"))}</button></div>`).join("");
    body = `<div class="net-grid">
      <div class="net-qr" id="net-qr" aria-label="${esc(t("net.qr"))}"></div>
      <div class="net-info">
        <p><strong>${esc(t("net.open_on"))}</strong></p>${links}
        <ol class="net-steps"><li>${esc(t("net.step1"))}</li><li>${esc(t("net.step2"))}</li><li>${esc(t("net.step3"))}</li><li>${esc(t("net.step4"))}</li></ol>
        <button class="btn btn-sm btn-quiet" type="button" data-net-act="token">${esc(t("net.new_key"))}</button>
      </div></div>`;
  } else if (st.enabled && !st.running) {
    body = `<div class="callout warn"><div>${esc(t("net.not_running", { error: st.error || "?" }))}</div></div>`;
  } else if (st.enabled) {
    body = `<p class="note">${esc(t("net.no_ip"))}</p>`;
  }
  box.innerHTML = `${head}${toggle}${body}<small class="note">${esc(t("net.note"))}</small>`;
  box.onchange = async (e) => {
    if (e.target.id !== "net-enabled") return;
    try {
      NET.st = await api("PUT", "/api/network", { enabled: e.target.checked });
    } catch (err) {
      toast(err.message, "error");
    }
    renderNetCard();
  };
  box.onclick = async (e) => {
    const copy = e.target.closest("[data-net-copy]")?.dataset.netCopy;
    if (copy) {
      try { await navigator.clipboard.writeText(copy); toast(t("net.copied")); } catch { toast(copy); }
      return;
    }
    if (e.target.closest("[data-net-act=token]")) {
      if (!(await confirmDialog(t("net.new_key_title"), t("net.new_key_text"), t("net.new_key"), false))) return;
      NET.st = await api("POST", "/api/network/token", {});
      renderNetCard();
    }
  };
  if (st.urls?.length && $("#net-qr")) {
    loadQrLib().then(() => {
      const qr = window.qrcode(0, "M");
      qr.addData(st.urls[0]);
      qr.make();
      const el = $("#net-qr");
      if (el) el.innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
    }).catch(() => { const el = $("#net-qr"); if (el) el.textContent = t("net.qr_failed"); });
  }
}


// ── Ollama: versión y actualización (Ajustes compartidos) ─────────────
// Ver app/webui/ollama_update.py. Mientras se actualiza, se consulta el
// estado cada segundo y medio.
const OLLAMA_UPD = { st: null, timer: null };
const OLLAMA_BUSY = ["checking", "downloading", "verifying", "installing", "restarting"];

async function loadOllamaUpdate(force = false) {
  try {
    OLLAMA_UPD.st = await api("GET", `/api/ollama/update${force ? "?check=1" : ""}`);
  } catch (e) {
    OLLAMA_UPD.st = { error: e.message };
  }
  renderOllamaCard();
  return OLLAMA_UPD.st;
}

function renderOllamaCard() {
  const box = $("#ollama-card");
  if (!box) return;
  const st = OLLAMA_UPD.st;
  const busy = st && OLLAMA_BUSY.includes(st.state);
  let line = t("ollama.loading");
  let action = "";
  if (st) {
    const installed = st.current ? t("ollama.installed", { v: st.current }) : t("ollama.offline");
    const latest = st.available ? `<span class="badge bad">${esc(t("ollama.latest", { v: st.latest }))}</span>`
      : st.current && st.latest ? `<span class="badge good">${esc(t("ollama.uptodate"))}</span>` : "";
    line = `<strong>${esc(installed)}</strong> ${latest}`;
    if (!st.supported) action = `<p class="note">${esc(t("ollama.unsupported"))}</p>`;
    else if (st.available) action = `<button class="btn btn-primary admin-act" type="button" data-ollama-act="update" ${busy ? "disabled" : ""}>${esc(t("ollama.update", { v: st.latest }))}</button>`;
    else action = `<button class="btn" type="button" data-ollama-act="check" ${busy ? "disabled" : ""}>${esc(t("ollama.check"))}</button>`;
  }
  let progress = "";
  if (busy) {
    const pct = st.total ? Math.round((st.downloaded / st.total) * 100) : 0;
    const text = st.step === "downloading" && st.total
      ? t("ollama.step_downloading", { done: fmtSize(st.downloaded) || "0 MB", total: fmtSize(st.total), pct })
      : t(`ollama.step_${st.step || "checking"}`);
    progress = `<div class="ollama-progress"><p>${esc(text)}</p>
      <div class="progress"><div style="width:${st.step === "downloading" ? pct : 100}%" class="${st.step === "downloading" ? "" : "indeterminate"}"></div></div></div>`;
  } else if (st?.state === "error") {
    progress = `<div class="callout warn"><div>${esc(t("ollama.failed", { error: st.error }))}</div></div>`;
  } else if (st?.check_error) {
    progress = `<p class="note">${esc(t("ollama.check_failed", { error: st.check_error }))}</p>`;
  }
  box.innerHTML = `
    <div class="card-head"><div><h2>${esc(t("ollama.title"))}</h2><p>${esc(t("ollama.sub"))}</p></div></div>
    <div class="ollama-row"><div class="ollama-ver">${line}</div>${action}</div>
    ${progress}
    <small class="note">${esc(t("ollama.note"))}</small>`;
  box.onclick = onOllamaCardClick;
}

async function onOllamaCardClick(e) {
  const act = e.target.closest("[data-ollama-act]")?.dataset.ollamaAct;
  if (act === "check") {
    e.target.disabled = true;
    const st = await loadOllamaUpdate(true);
    if (st && !st.available && st.current && !st.check_error) toast(t("ollama.up_to_date"));
  } else if (act === "update") {
    const v = OLLAMA_UPD.st.latest;
    if (!(await confirmDialog(t("ollama.confirm_title"), t("ollama.confirm_text", { v }), t("ollama.confirm_ok"), false))) return;
    try {
      OLLAMA_UPD.st = await api("POST", "/api/ollama/update", {});
    } catch (err) {
      toast(err.message, "error", 7000);
      return;
    }
    renderOllamaCard();
    pollOllamaUpdate();
  }
}

function pollOllamaUpdate() {
  clearTimeout(OLLAMA_UPD.timer);
  OLLAMA_UPD.timer = setTimeout(async () => {
    const before = OLLAMA_UPD.st?.state;
    const st = await loadOllamaUpdate();
    if (OLLAMA_BUSY.includes(st?.state)) return pollOllamaUpdate();
    if (OLLAMA_BUSY.includes(before) && st?.state === "done") {
      toast(st.step === "up_to_date" ? t("ollama.up_to_date") : t("ollama.updated", { v: st.current }), "ok", 6000);
      await loadModels(); // capacidades y modelos con la versión nueva
      renderOllamaStatus();
    }
  }, 1500);
}


// ── Voces y oído (Ajustes compartidos) ────────────────────────────────
// Se guardan al momento (config/voice_settings.yaml), aparte del botón
// "Guardar" de esta página.
const VOICE_REC = { rec: null, stream: null, timer: null, started: 0 };

function langOptions(selected, codes = allLangCodes()) {
  return codes.map((c) => `<option value="${c}" ${c === selected ? "selected" : ""}>${esc(langName(c))}</option>`).join("");
}

function fallbackOptions(selected) {
  return S.data.voices.map((v) => `<option value="${v.code}" ${v.code === selected ? "selected" : ""}>${v.code} · ${esc(voiceName(v.code))}</option>`).join("");
}

function renderVoicesCard() {
  const box = $("#voices-card");
  if (!box) return;
  const vs = S.data.voice_settings;
  const q = vs.qwen;
  const qwenLangs = vs.qwen_languages.filter((c) => allLangCodes().includes(c));
  const sttRadio = Object.keys(vs.stt_models).map((code) => `
    <label class="radio-card ${vs.stt_model === code ? "selected" : ""}">
      <input type="radio" name="stt-model" value="${code}" ${vs.stt_model === code ? "checked" : ""}>
      <strong>${esc(t(`voices.stt_name_${code}`))}</strong><small>${esc(t(`voices.stt_${code}`))}</small>
    </label>`).join("");
  const rows = vs.custom_voices.map((v) => `
    <div class="cv-row" data-cv="${esc(v.id)}">
      <div class="cv-main">
        <input class="text-input cv-name" value="${esc(v.name)}" maxlength="40" aria-label="${esc(t("voices.name"))}">
        <select class="cv-lang" aria-label="${esc(t("voices.lang"))}">${langOptions(v.language, qwenLangs.includes(v.language) ? qwenLangs : [...qwenLangs, v.language])}</select>
        <select class="cv-fallback" aria-label="${esc(t("voices.fallback"))}" title="${esc(t("voices.fallback_help"))}">${fallbackOptions(v.fallback_voice)}</select>
        <button class="btn btn-sm" type="button" data-cv-act="orig">${ICON.play} ${esc(t("voices.original"))}</button>
        <button class="btn btn-sm" type="button" data-cv-act="clone">${ICON.play} ${esc(t("voices.cloned"))}</button>
        <button class="btn btn-sm btn-ghost-danger" type="button" data-cv-act="delete">${esc(t("voices.delete"))}</button>
      </div>
      ${v.missing_audio ? `<p class="err">${esc(t("voices.missing_audio"))}</p>` : ""}
      <label class="cv-ref"><span>${esc(t("voices.ref_text"))}</span>
        <textarea class="cv-text" rows="2" maxlength="1000">${esc(v.ref_text)}</textarea></label>
      <div class="cv-foot"><small>${esc(t("voices.ref_help"))}</small>
        <button class="btn btn-sm btn-primary" type="button" data-cv-act="save" hidden>${esc(t("voices.save"))}</button></div>
    </div>`).join("");
  box.innerHTML = `
    <div class="card-head"><div><h2>${esc(t("voices.title"))}</h2><p>${esc(t("voices.sub"))}</p></div></div>
    <h3 class="sub-h">${esc(t("voices.stt"))}</h3>
    <div class="radio-cards" id="stt-models">${sttRadio}</div>
    <h3 class="sub-h">${esc(t("voices.custom"))}</h3>
    <p class="note">${esc(t("voices.custom_sub", { langs: qwenLangs.map(langName).join(", ") }))}</p>
    <div class="callout ${q.available ? "ok" : "warn"}"><div>${!q.available
      ? esc(t("voices.qwen_problem", { problem: q.problem }))
      : q.warming ? esc(t("voices.qwen_warming", { model: q.model }))
        : esc(t("voices.qwen_ok", { model: q.model, device: q.ready ? q.device : t("voices.qwen_idle") }))}</div></div>
    <div class="grid-2">
      <div class="field"><label for="qwen-model">${esc(t("voices.qwen_model"))}</label>
        <select id="qwen-model">${vs.qwen_models.map((m) => `<option value="${m}" ${m === vs.qwen_model ? "selected" : ""}>${m} · ${esc(t(`voices.qwen_${m.replace(".", "_")}`))}</option>`).join("")}</select></div>
      <div class="field"><label for="qwen-python">${esc(t("voices.qwen_python"))}</label>
        <input id="qwen-python" class="text-input" value="${esc(vs.qwen_python)}" placeholder="${esc(vs.qwen_python_default || t("voices.qwen_python_none"))}" spellcheck="false">
        <small>${esc(t("voices.qwen_python_help"))}</small></div>
    </div>
    <label class="switch"><input type="checkbox" id="qwen-compile" ${vs.qwen_compile ? "checked" : ""}><span class="track" aria-hidden="true"></span>
      ${esc(t("voices.qwen_compile"))}</label>
    <p class="note">${esc(t("voices.qwen_compile_help"))}</p>
    <div class="cv-list">${rows || `<p class="empty">${esc(t("voices.none"))}</p>`}</div>
    <div class="cv-add">
      <h4>${esc(t("voices.add"))}</h4>
      <div class="cv-main">
        <input class="text-input" id="cv-new-name" placeholder="${esc(t("voices.name_ph"))}" maxlength="40">
        <select id="cv-new-lang" aria-label="${esc(t("voices.lang"))}">${langOptions(qwenLangs.includes(S.lang) ? S.lang : "es", qwenLangs)}</select>
        <select id="cv-new-fallback" aria-label="${esc(t("voices.fallback"))}" title="${esc(t("voices.fallback_help"))}">${fallbackOptions("M5")}</select>
      </div>
      <div class="cv-main">
        <label class="btn btn-sm">${esc(t("voices.upload"))}<input type="file" id="cv-file" accept="audio/*,video/webm" hidden></label>
        <button class="btn btn-sm" type="button" id="cv-record">${ICON.micSmall} ${esc(t("voices.record"))}</button>
        <span class="note" id="cv-status"></span>
      </div>
      <small>${esc(t("voices.add_help"))}</small>
    </div>`;
  box.onchange = onVoicesChange;
  box.oninput = (e) => {
    const row = e.target.closest("[data-cv]");
    if (row) $("[data-cv-act=save]", row).hidden = false;
  };
  box.onclick = onVoicesClick;
}

async function putVoiceSettings(changes) {
  try {
    const r = await api("PUT", "/api/voice-settings", changes);
    S.data.voice_settings = r.state.voice_settings;
    renderVoicesCard();
    toast(t("voices.saved"));
  } catch (e) {
    toast(e.message, "error");
  }
}

function onVoicesChange(e) {
  const tgt = e.target;
  if (tgt.name === "stt-model") return putVoiceSettings({ stt_model: tgt.value });
  if (tgt.id === "qwen-model") return putVoiceSettings({ qwen_model: tgt.value });
  if (tgt.id === "qwen-python") return putVoiceSettings({ qwen_python: tgt.value.trim() });
  if (tgt.id === "qwen-compile") return putVoiceSettings({ qwen_compile: tgt.checked });
  if (tgt.id === "cv-file" && tgt.files[0]) return uploadVoice(tgt.files[0]);
  const row = tgt.closest("[data-cv]");
  if (row) $("[data-cv-act=save]", row).hidden = false;
}

async function onVoicesClick(e) {
  if (e.target.closest("#cv-record")) return toggleVoiceRecording();
  const btn = e.target.closest("[data-cv-act]");
  if (!btn) return;
  const row = btn.closest("[data-cv]");
  const id = row.dataset.cv;
  const act = btn.dataset.cvAct;
  if (act === "orig") {
    stopPreview();
    previewAudio.src = `/voices/${id}.wav?v=${Date.now()}`;
    previewAudio.playbackRate = 1;
    previewAudio.play().catch(() => toast(t("voice.play_failed"), "error"));
  } else if (act === "clone") {
    playPreview(`custom:${id}`);
  } else if (act === "save") {
    try {
      const r = await api("PUT", `/api/voices/${id}`, {
        name: $(".cv-name", row).value, language: $(".cv-lang", row).value,
        fallback_voice: $(".cv-fallback", row).value, ref_text: $(".cv-text", row).value,
      });
      S.data = { ...S.data, voice_settings: r.state.voice_settings, assistants: r.state.assistants };
      renderVoicesCard();
      toast(t("voices.saved"));
    } catch (err) {
      toast(err.message, "error");
    }
  } else if (act === "delete") {
    if (!(await confirmDialog(t("voices.delete_title"), t("voices.delete_text", { name: $(".cv-name", row).value }), t("voices.delete")))) return;
    try {
      const r = await api("DELETE", `/api/voices/${id}`, {});
      S.data = { ...S.data, voice_settings: r.state.voice_settings };
      renderVoicesCard();
    } catch (err) {
      toast(err.message, "error", 6000);
    }
  }
}

async function uploadVoice(blob) {
  const name = $("#cv-new-name").value.trim() || t("voices.default_name");
  const status = $("#cv-status");
  status.textContent = t("voices.uploading");
  const q = new URLSearchParams({ name, lang: $("#cv-new-lang").value, fallback: $("#cv-new-fallback").value });
  try {
    const res = await fetch(`/api/voices?${q}`, {
      method: "POST",
      headers: { "Content-Type": blob.type && blob.type.startsWith("audio/") ? blob.type : "audio/wav", "X-UI-Lang": S.lang },
      body: blob,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    S.data = { ...S.data, voice_settings: data.state.voice_settings };
    renderVoicesCard();
    toast(t("voices.created", { name }));
  } catch (e) {
    status.textContent = "";
    toast(e.message, "error", 7000);
  }
}

// Grabar la voz de referencia con el micrófono del navegador (hasta 20 s).
async function toggleVoiceRecording() {
  const btn = $("#cv-record");
  if (VOICE_REC.rec) {
    VOICE_REC.rec.stop();
    return;
  }
  try {
    VOICE_REC.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    toast(t("conv.mic_denied", { error: e.message }), "error");
    return;
  }
  const chunks = [];
  const rec = new MediaRecorder(VOICE_REC.stream);
  VOICE_REC.rec = rec;
  VOICE_REC.started = Date.now();
  rec.ondataavailable = (ev) => { if (ev.data.size) chunks.push(ev.data); };
  rec.onstop = () => {
    clearInterval(VOICE_REC.timer);
    VOICE_REC.stream.getTracks().forEach((tr) => tr.stop());
    VOICE_REC.rec = null;
    btn.classList.remove("recording");
    uploadVoice(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
  };
  rec.start();
  btn.classList.add("recording");
  VOICE_REC.timer = setInterval(() => {
    const secs = Math.floor((Date.now() - VOICE_REC.started) / 1000);
    btn.innerHTML = `${ICON.stop} ${esc(t("voices.recording", { s: secs }))}`;
    if (secs >= 20) rec.stop();
  }, 250);
}

// Nombre del lugar de las coordenadas actuales (debajo de latitud/longitud).
let placeLabelTimer = null;
function updatePlaceLabel() {
  clearTimeout(placeLabelTimer);
  placeLabelTimer = setTimeout(async () => {
    const el = $("#place-label");
    if (!el) return;
    const lat = parseFloat(String(S.draft.user_context.latitud).replace(",", "."));
    const lon = parseFloat(String(S.draft.user_context.longitud).replace(",", "."));
    if (Number.isNaN(lat) || Number.isNaN(lon)) {
      el.textContent = t("map.no_coords");
      return;
    }
    try {
      const r = await api("GET", `/api/geo/reverse?lat=${lat}&lon=${lon}`);
      if ($("#place-label") === el) el.textContent = r.label || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    } catch {
      el.textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    }
  }, 500);
}

function addExclusion(raw) {
  const word = normWord(raw);
  if (!word || S.draft.exclusions.includes(word)) return;
  S.draft.exclusions.push(word);
  renderExclusionChips();
  afterChange("exclusions");
}

function renderExclusionChips() {
  $("#excl-chips").innerHTML = S.draft.exclusions
    .map((w, i) => `<span class="chip">${esc(w)}<button type="button" data-rm-excl="${i}" aria-label="× ${esc(w)}">×</button></span>`)
    .join("");
}

async function saveShared() {
  const btn = $('[data-act="save"]');
  const d = S.draft;
  const base = JSON.parse(S.baseline);
  const changed = (key) => JSON.stringify(d[key]) !== JSON.stringify(base[key]);
  if (!isGuest() && d.me && (d.me.pin || d.me.pin_confirm)) {
    if (!/^\S{4,64}$/.test(d.me.pin)) {
      showErrors({ "me.pin": t("prof.pin_format") });
      toast(t("prof.pin_format"), "error");
      return;
    }
    if (d.me.pin !== d.me.pin_confirm) {
      showErrors({ "me.pin_confirm": t("sec_card.mismatch") });
      toast(t("sec_card.mismatch"), "error");
      return;
    }
  }
  btn.disabled = true;
  try {
    if (isGuest()) {
      // El invitado: en este navegador (sessionStorage), nada en el servidor.
      guestSet("user_context", d.user_context);
      setData(S.data);
      toast(t("prof.guest_saved"));
    } else {
      // Datos y perfil propios (cada uno los suyos) y, si es admin, lo de todos.
      if (changed("user_context") || changed("me")) {
        const me = { user_context: d.user_context };
        if (d.me.name !== base.me.name) me.name = d.me.name;
        if (d.me.pin || d.me.pin_confirm) Object.assign(me, { pin: d.me.pin, pin_confirm: d.me.pin_confirm });
        setData((await api("PUT", "/api/profile/me", me)).state);
      }
      if (isAdmin() && (changed("shared_context") || changed("exclusions"))) {
        setData((await api("PUT", "/api/shared", { version: S.data.version, shared_context: d.shared_context, exclusions: d.exclusions })).state);
      }
      toast(t(isAdmin() ? "shared.saved" : "prof.mine_saved"));
    }
    await select({ kind: "shared" }, { force: true, push: false });
  } catch (e) {
    handleSaveError(e);
  } finally {
    if (btn.isConnected) btn.disabled = false;
  }
}

async function savePinDirect() {
  const d = S.draft?.me;
  if (!d) return;
  clearErrors();
  if (!/^\S{4,64}$/.test(d.pin || "")) {
    showErrors({ "me.pin": t("prof.pin_format") });
    toast(t("prof.pin_format"), "error");
    return;
  }
  if (d.pin !== d.pin_confirm) {
    showErrors({ "me.pin_confirm": t("sec_card.mismatch") });
    toast(t("sec_card.mismatch"), "error");
    return;
  }
  try {
    const res = await api("PUT", "/api/profile/me", { pin: d.pin, pin_confirm: d.pin_confirm });
    setData(res.state);
    d.pin = "";
    d.pin_confirm = "";
    const base = JSON.parse(S.baseline);
    if (base.me) {
      base.me.pin = "";
      base.me.pin_confirm = "";
      S.baseline = JSON.stringify(base);
    }
    toast(t("sec_card.saved"));
    renderShared();
  } catch (e) {
    handleSaveError(e);
  }
}

async function clearPinDirect() {
  if (!(await confirmDialog(t("sec_card.clear_btn"), t("sec_card.clear_confirm"), t("sec_card.clear_btn")))) return;
  try {
    const res = await api("PUT", "/api/profile/me", { clear_pin: true });
    setData(res.state);
    if (S.draft?.me) {
      S.draft.me.pin = "";
      S.draft.me.pin_confirm = "";
    }
    toast(t("sec_card.cleared"));
    renderShared();
  } catch (e) {
    handleSaveError(e);
  }
}

// ── Mapa para elegir la ubicación (Leaflet + OpenStreetMap, gratis) ────
// Leaflet se carga del CDN recién al abrir el mapa (con verificación de
// integridad). La búsqueda de lugares y el nombre del punto elegido pasan
// por el servidor hacia Nominatim (ver /api/geo/* en config_ui.py).
const LEAFLET = {
  css: ["https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="],
  js: ["https://unpkg.com/leaflet@1.9.4/dist/leaflet.js", "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="],
};
const MAP = { map: null, pick: null, accuracy: null, saved: null, selection: null, place: null, reverseTimer: null, seq: 0, loading: null };

function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (MAP.loading) return MAP.loading;
  MAP.loading = new Promise((resolve, reject) => {
    const link = Object.assign(document.createElement("link"), { rel: "stylesheet", href: LEAFLET.css[0], integrity: LEAFLET.css[1], crossOrigin: "" });
    const script = Object.assign(document.createElement("script"), { src: LEAFLET.js[0], integrity: LEAFLET.js[1], crossOrigin: "" });
    script.onload = () => resolve();
    script.onerror = () => { MAP.loading = null; reject(new Error(t("map.load_failed"))); };
    document.head.append(link, script);
  });
  return MAP.loading;
}

function savedCoords() {
  const lat = parseFloat(String(S.draft.user_context.latitud).replace(",", "."));
  const lon = parseFloat(String(S.draft.user_context.longitud).replace(",", "."));
  return Number.isNaN(lat) || Number.isNaN(lon) ? null : [lat, lon];
}

async function openMap() {
  try {
    await loadLeaflet();
  } catch (e) {
    toast(e.message, "error", 7000);
    return;
  }
  const dlg = $("#map-dialog");
  const saved = savedCoords();
  const uc = S.draft.user_context;
  $("#map-fill").checked = !uc.ubicacion && !uc.pais;
  $("#map-saved-btn").hidden = !saved;
  $("#map-results").hidden = true;
  $("#map-q").value = "";
  dlg.showModal();

  if (!MAP.map) {
    MAP.map = L.map("map-canvas", { zoomControl: true, attributionControl: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    }).addTo(MAP.map);
    MAP.map.on("click", (e) => setMapSelection([e.latlng.lat, e.latlng.lng], null));
  }
  // El <dialog> recién se muestra: Leaflet necesita recalcular su tamaño.
  setTimeout(() => MAP.map.invalidateSize(), 50);

  if (MAP.saved) MAP.saved.remove();
  MAP.saved = saved
    ? L.circleMarker(saved, { radius: 7, color: "#7a776f", fillColor: "#a4a198", fillOpacity: 0.9, weight: 2 })
      .bindTooltip(t("map.saved_tip")).addTo(MAP.map)
    : null;

  // Mientras el navegador responde se muestra lo guardado (o el mundo).
  if (saved) setMapSelection(saved, null, 15);
  else {
    clearMapSelection();
    MAP.map.setView([15, -40], 2);
  }
  // Por defecto: la ubicación actual del navegador.
  locateBrowser(false);
}

function clearMapSelection() {
  MAP.selection = null;
  if (MAP.pick) MAP.pick.remove();
  if (MAP.accuracy) MAP.accuracy.remove();
  MAP.pick = MAP.accuracy = null;
  $("#map-place").textContent = t("map.click_hint");
  $("#map-coords").textContent = "";
  $("#map-use").disabled = true;
}

function setMapSelection(latlng, accuracy, zoom = null) {
  MAP.selection = latlng;
  if (MAP.pick) MAP.pick.remove();
  if (MAP.accuracy) MAP.accuracy.remove();
  MAP.accuracy = accuracy ? L.circle(latlng, { radius: accuracy, color: "#0e7a6d", weight: 1, fillOpacity: 0.08 }).addTo(MAP.map) : null;
  MAP.pick = L.circleMarker(latlng, { radius: 9, color: "#fff", fillColor: "#0e7a6d", fillOpacity: 1, weight: 3 }).addTo(MAP.map);
  if (zoom) MAP.map.setView(latlng, zoom);
  $("#map-coords").textContent = `${latlng[0].toFixed(6)}, ${latlng[1].toFixed(6)}` +
    (accuracy ? ` · ${t("map.accuracy", { m: Math.round(accuracy) })}` : "");
  $("#map-place").textContent = t("map.looking_up");
  $("#map-use").disabled = false;
  MAP.place = null;
  clearTimeout(MAP.reverseTimer);
  const seq = ++MAP.seq;
  MAP.reverseTimer = setTimeout(async () => {
    try {
      const r = await api("GET", `/api/geo/reverse?lat=${latlng[0]}&lon=${latlng[1]}`);
      if (seq !== MAP.seq) return;
      MAP.place = r;
      $("#map-place").textContent = r.label || t("map.no_name");
    } catch (e) {
      if (seq === MAP.seq) $("#map-place").textContent = t("map.no_name");
    }
  }, 400);
}

function locateBrowser(explicit) {
  if (!navigator.geolocation) {
    if (explicit) toast(t("geo.unsupported"), "warn");
    return;
  }
  $("#map-place").textContent = t("map.locating");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      if (!$("#map-dialog").open) return;
      const { latitude, longitude, accuracy } = pos.coords;
      setMapSelection([latitude, longitude], accuracy, accuracy > 2000 ? 12 : 16);
    },
    (err) => {
      if (!$("#map-dialog").open) return;
      if (MAP.selection) $("#map-place").textContent = MAP.place?.label || t("map.no_name");
      else $("#map-place").textContent = t("map.click_hint");
      toast(t("geo.failed", { error: err.message }), "warn", 6000);
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
  );
}

async function searchMap(e) {
  e.preventDefault();
  const q = $("#map-q").value.trim();
  const box = $("#map-results");
  if (!q) return;
  box.hidden = false;
  box.innerHTML = `<p class="note">${esc(t("map.searching"))}</p>`;
  try {
    const r = await api("GET", `/api/geo/search?q=${encodeURIComponent(q)}`);
    box.innerHTML = r.results.length
      ? r.results.map((p, i) => `<button type="button" class="map-result" data-result="${i}">${esc(p.label)}</button>`).join("")
      : `<p class="note">${esc(t("map.no_results"))}</p>`;
    box.onclick = (ev) => {
      const b = ev.target.closest("[data-result]");
      if (!b) return;
      const p = r.results[Number(b.dataset.result)];
      setMapSelection([p.lat, p.lon], null, 16);
      box.hidden = true;
    };
  } catch (err) {
    box.innerHTML = `<p class="note error">${esc(err.message)}</p>`;
  }
}

function closeMap() {
  $("#map-dialog").close();
}

function useMapSelection() {
  if (!MAP.selection) return;
  const values = { latitud: MAP.selection[0].toFixed(6), longitud: MAP.selection[1].toFixed(6) };
  if ($("#map-fill").checked && MAP.place) {
    values.ubicacion = MAP.place.ciudad || MAP.place.barrio || "";
    values.pais = MAP.place.pais || "";
  }
  for (const [key, value] of Object.entries(values)) {
    const field = `user_context.${key}`;
    setPath(S.draft, field, value);
    const input = $(`[data-field="${field}"]`);
    if (input) input.value = value;
    clearError(field);
  }
  refreshSaveBar();
  updatePlaceLabel();
  closeMap();
  toast(t("map.applied"));
}

function initMapDialog() {
  const dlg = $("#map-dialog");
  $("#map-search").onsubmit = searchMap;
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); closeMap(); });
  dlg.onclick = (e) => {
    const act = e.target.closest("[data-map-act]")?.dataset.mapAct;
    if (act === "cancel") closeMap();
    else if (act === "use") useMapSelection();
    else if (act === "here") locateBrowser(true);
    else if (act === "saved") {
      const saved = savedCoords();
      if (saved) setMapSelection(saved, null, 16);
    }
  };
}

// ── Chat de prueba ─────────────────────────────────────────────────────
// Usa el borrador (S.draft) tal cual está, aunque no esté guardado. Modo
// "text": tú escribes y responde hablando; modo "voice": conversación por
// micrófono en bucle (escucha → transcribe → responde → vuelve a escuchar).
const CHAT = {
  mode: "text",
  // "auto" o un código. Escrito: "auto" = responde en el idioma en que
  // escribas. Voz: "auto" = entiende y habla cualquiera de los idiomas del
  // asistente; un código = solo ese.
  lang: "auto",
  lastLang: null, // idioma del último turno (pista para Whisper y para "ok", "sí"...)
  voiceOn: false, // chat escrito: leer las respuestas en voz alta (en el menú ⋯)
  history: [],
  // Resumen de lo viejo de la conversación: al pasar el historial del
  // asistente, el servidor resume lo más viejo en vez de cortarlo (ver
  // features.js y chat_runtime.summarize).
  summary: "",
  messages: [],
  busy: false,
  epoch: 0, // cambia al reiniciar: las respuestas que lleguen tarde se descartan
  speaking: false,
  speakGen: 0,
  audio: null,
  audioDone: null,
  announce: null,
  conv: null,
  convState: "idle",
  convNote: "",
  noticeShown: false,
  sttNoticeShown: false,
  // Conversación con varios asistentes: otros asistentes del MISMO modelo
  // (así no se cargan dos modelos a la vez). Escuchan todo, pero solo
  // responden si se los nombra; sin nombrar a nadie responde el de la página.
  guests: [],
  inviteOpen: false,
  speaker: "@host",     // quién está hablando (su aro reacciona a la voz)
  thinkingFor: null,    // a quién se le está esperando la respuesta
  // Frase que quedó a medias ("busca en internet…", "¿cuál es la capital de…"):
  // se espera el resto en vez de mandarla incompleta.
  pending: "",
  pendingLang: null,
  // Pausa para pensar: la del asistente de la página (think_pause, en sus ajustes).
  get pauseMs() { return Math.round((Number(S.draft?.think_pause) || 1.5) * 1000); },
  // Invitaciones/salidas que pidió el modelo (herramientas de grupo).
  groupActions: [],
  // Adjuntos todavía sin mandar (ver "Adjuntos").
  attachments: [],
};

const chatLangs = () => (S.draft.languages.length ? S.draft.languages : allLangCodes());

// Cuánto silencio esperar antes de dar la frase por terminada (modo voz).
// Con 0,9 s fijos una pausa para pensar mandaba la pregunta a medias.
const PAUSE_OPTIONS = [1000, 1500, 2000, 3000, 4000];
function initialPause() {
  try {
    const saved = Number(localStorage.getItem("voice-pause"));
    if (PAUSE_OPTIONS.includes(saved)) return saved;
  } catch { /* sin almacenamiento local */ }
  return 2000;
}

// ── Varios asistentes en la conversación ──────────────────────────────
const HOST = "@host"; // el asistente de esta página (puede ser un borrador sin nombre)

function participantCfg(key) {
  return key === HOST ? S.draft : S.data.assistants.find((a) => a.name === key);
}

function participants() {
  return [HOST, ...CHAT.guests.filter((g) => participantCfg(g))];
}

const sameModel = (a) => a.base_model === S.draft.base_model;

// Saca a los invitados que ya no comparten modelo (si se cambió el de la página).
function pruneGuests() {
  const before = CHAT.guests.length;
  CHAT.guests = CHAT.guests.filter((g) => {
    const a = participantCfg(g);
    return a && sameModel(a) && g !== S.view?.name;
  });
  return before !== CHAT.guests.length;
}

function toggleGuest(name, on) {
  CHAT.guests = CHAT.guests.filter((g) => g !== name);
  if (on) CHAT.guests.push(name);
  pruneGuests();
  renderChat();
}

// Quién tiene que responder: los asistentes a los que les HABLASTE
// ("Bella, ¿qué opinas?", "¿y tú, Jarvis?") — nombrarlos para hablar DE
// ellos no cuenta — o, si les preguntaste a TODOS ("¿qué opinan?",
// "everyone", "вы оба"…), todos por turnos, empezando por el que digas y el
// resto al azar. Lo decide el modelo leyendo la conversación (ver
// chat_runtime.route_addressees), en cualquier idioma; antes se buscaban
// palabras ("todos", "ustedes", "guys", "vocês"…) en tres idiomas. Si no le
// hablaste a nadie en particular, responde el de la página.
function shuffled(list) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

// Asistentes que se podrían sumar (mismo modelo, no están) y que se
// nombran en `text` (los nombres llegan ya bien escritos: el servidor los
// corrige al transcribir, "Harvis" → "Jarvis").
function mentionedOutsiders(text) {
  if (S.view?.kind !== "assistant") return [];
  const words = new Set(String(text || "").split(/[^\p{L}\p{N}]+/u).map(normWord).filter(Boolean));
  return S.data.assistants.filter((a) => a.name !== S.view.name && !CHAT.guests.includes(a.name) && sameModel(a)
    && [a.name, normWord(a.label), ...(a.aliases || [])].some((n) => n && words.has(n)));
}

// Le pregunta al modelo a quién le habló el usuario en `history` (la
// conversación con el último mensaje), entre los participantes y, si se
// pasan, asistentes que todavía no están (`outsiders`).
async function routeWith(history, outsiders = []) {
  try {
    return await api("POST", "/api/chat/route", {
      assistant: S.draft,
      // Sin adjuntos: para decidir a quién le hablaron basta lo escrito.
      history: history.slice(-8).map(({ images, attachments, ...m }) => m),
      group: participants().map((k) => ({ key: k, label: displayName(participantCfg(k)) })),
      outsiders: outsiders.map((a) => ({ key: a.name, label: displayName(a) })),
    });
  } catch {
    return { keys: [], all: false }; // sin respuesta: responde el de la página
  }
}

// Devuelve { keys: quiénes responden y en qué orden, all: si es una ronda
// en la que responden todos }. Si le hablaste a un asistente que no está
// (mismo modelo), se suma a la conversación y responde él.
async function addressees(text) {
  const outsiders = mentionedOutsiders(text);
  if (participants().length === 1 && !outsiders.length) return { keys: [HOST], all: false };
  const route = await routeWith(CHAT.history, outsiders);
  for (const a of outsiders) {
    if ((route.keys || []).includes(a.name)) {
      toggleGuest(a.name, true);
      hfNote(t("hf.joined", { name: displayName(a) }));
    }
  }
  const keys = participants();
  const found = (route.keys || []).filter((k) => keys.includes(k));
  if (!route.all) return { keys: found.length ? found : [HOST], all: false };
  return { keys: [...found, ...shuffled(keys.filter((k) => !found.includes(k)))], all: true };
}

// Tocar el aro de un invitado lo convierte en el asistente de la página
// (el panel muestra SU configuración) y el anterior pasa a invitado. La
// conversación sigue igual: cada frase queda atribuida a quien la dijo.
async function switchHost(name) {
  if (S.view?.kind !== "assistant") {
    toast(t("group.switch_new"), "warn");
    return;
  }
  if (CHAT.busy) {
    toast(t("group.switch_busy"), "warn");
    return;
  }
  if (!(await guardDirty())) return;
  const old = S.view.name;
  const swap = (key) => (key === HOST ? old : key === name ? HOST : key);
  for (const m of [...CHAT.history, ...CHAT.messages]) {
    if (m.role === "assistant") m.speaker = swap(m.speaker || HOST);
  }
  CHAT.guests = CHAT.guests.map((g) => (g === name ? old : g));
  CHAT.speaker = swap(CHAT.speaker);
  CHAT.thinkingFor = null;
  await select({ kind: "assistant", name }, { force: true, keepChat: true });
}

function speakerTag(key, cls = "who") {
  const cfg = participantCfg(key) || S.draft;
  return `<span class="${cls}" style="${colorStyle(cfg)}">${esc(displayName(cfg))}</span>`;
}

function inviteMenu() {
  const others = S.data.assistants.filter((a) => a.name !== S.view?.name);
  if (!others.length) return "";
  const items = others.map((a) => {
    const ok = sameModel(a);
    return `<label class="invite-item ${ok ? "" : "disabled"}">
      <input type="checkbox" data-invite="${esc(a.name)}" ${CHAT.guests.includes(a.name) ? "checked" : ""} ${ok ? "" : "disabled"}>
      ${orbAvatar(a, "sm")}
      <span class="ii-text"><strong>${esc(displayName(a))}</strong><small>${esc(ok ? t("group.same_model") : t("group.other_model", { model: a.base_model }))}</small></span>
    </label>`;
  }).join("");
  return `<details class="invite" id="invite" ${CHAT.inviteOpen ? "open" : ""}>
    <summary class="btn btn-sm btn-quiet">${ICON.people} ${esc(t("group.invite"))}${CHAT.guests.length ? ` (${CHAT.guests.length})` : ""}</summary>
    <div class="invite-menu">
      <p class="note">${esc(t("group.help", { model: S.draft.base_model || "?" }))}</p>
      ${items}
    </div>
  </details>`;
}

// Frase que suena a cortada: Whisper la termina en "..." o "…" (o en una
// coma) cuando la persona hace una pausa a mitad de la idea. Antes además
// se miraba si terminaba en "y", "de", "the"… (lista de palabras en tres
// idiomas); ahora, si la frase quedó incompleta sin esa marca, el propio
// modelo pide lo que falta.
function looksUnfinished(text) {
  return /(\.\.\.|…|,|;|:)\s*$/u.test(text.trim());
}

// Conversación nueva (al cambiar de asistente o "Reiniciar").
function resetChat() {
  stopConversation();
  stopSpeaking();
  CHAT.chatAbort?.abort();
  CHAT.epoch++;
  CHAT.busy = false;
  CHAT.history = [];
  CHAT.summary = "";
  CHAT.messages = [];
  CHAT.lang = "auto";
  CHAT.lastLang = null;
  CHAT.guests = [];
  CHAT.speaker = HOST;
  CHAT.thinkingFor = null;
  CHAT.pending = "";
  CHAT.lastActivity = 0;
  CHAT.groupActions = [];
  CHAT.attachments = [];
  stopVideoCall();
}

// El escenario: cabecera del asistente, modos y, debajo, el chat escrito o
// el aro de la conversación por voz.
function renderChat() {
  const box = $("#stage");
  if (!box) return;
  CHAT.shown = CHAT.messages.length; // al abrir o cambiar de modo, sin animar lo que ya estaba
  const voiceMode = CHAT.mode === "voice";
  const tab = (mode, icon, help) => `<button type="button" role="tab" data-chat-mode="${mode}" class="${CHAT.mode === mode ? "active" : ""}"
    aria-selected="${CHAT.mode === mode}" title="${esc(t(help))}">${icon}<span>${esc(t(`chat.mode_${mode}`))}</span></button>`;
  box.className = `stage mode-${CHAT.mode}`;
  box.innerHTML = `
    <header class="stage-head">
      <button class="icon-btn" type="button" data-act="go-gallery" aria-label="${esc(t("nav.back"))}" title="${esc(t("nav.back"))}">${ICON.back}</button>
      <span class="avatar orb-avatar js-assistant-avatar" id="head-avatar" aria-hidden="true"></span>
      <div class="head-text"><h1 id="head-title"></h1><p id="head-sub"></p></div>
      <div class="segmented" role="tablist">${tab("text", ICON.chat, "chat.mode_text_help")}${tab("voice", ICON.wave, "chat.mode_voice_help")}</div>
      <details class="menu chat-more">
        <summary class="icon-btn" aria-label="${esc(t("chat.more"))}" title="${esc(t("chat.more"))}">${ICON.more}</summary>
        <div class="menu-pop">
          ${voiceMode ? "" : `<label class="menu-item"><span>${esc(t("chat.voice_on"))}</span>
            <span class="switch small"><input type="checkbox" id="chat-voice" ${CHAT.voiceOn ? "checked" : ""}><span class="track" aria-hidden="true"></span></span></label>`}
          ${inviteMenu()}
          <button class="menu-item" type="button" data-chat-act="reset">${esc(t("chat.reset"))}</button>
          <button class="menu-item" type="button" data-chat-act="unload">${esc(t("chat.unload"))}</button>
        </div>
      </details>
      <button class="icon-btn panel-toggle" type="button" data-act="toggle-panel" aria-pressed="${S.panelOpen}"
        aria-label="${esc(t("panel.toggle"))}" title="${esc(t("panel.toggle"))}">${ICON.sliders}</button>
    </header>
    ${voiceMode ? `
    <div class="voice-stage">
      ${orbRow()}
      <div class="voice-status" aria-live="polite"><strong id="conv-state"></strong><small id="conv-note"></small></div>
      <div class="voice-captions" id="chat-log" aria-live="polite"></div>
      <div class="att-tray voice-tray" id="att-tray" hidden></div>
      <div class="voice-controls" id="chat-foot"></div>
      <div class="video-pip" id="video-pip" hidden></div>
      <input type="file" id="att-input" multiple hidden>
      <input type="file" id="cam-input" accept="image/*" capture="environment" hidden>
    </div>` : `
    <div class="chat-log" id="chat-log" aria-live="polite"></div>
    <footer class="chat-foot" id="chat-foot"></footer>`}`;
  box.onclick = onChatClick;
  box.onchange = onChatChange;
  box.onkeydown = onChatKey;
  // Adjuntos: arrastrar archivos sobre el chat o pegar una imagen.
  box.ondragover = (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    box.classList.add("dropping");
  };
  box.ondragleave = (e) => { if (!box.contains(e.relatedTarget)) box.classList.remove("dropping"); };
  box.ondrop = (e) => {
    box.classList.remove("dropping");
    if (!e.dataTransfer?.files?.length) return;
    e.preventDefault();
    addFiles(e.dataTransfer.files);
  };
  box.onpaste = (e) => {
    if (e.target.id !== "chat-input" || !e.clipboardData?.files?.length) return;
    e.preventDefault();
    addFiles(e.clipboardData.files);
  };
  box.oninput = (e) => {
    // El cuadro de texto crece con lo escrito (hasta un límite).
    if (e.target.id !== "chat-input") return;
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
  };
  // Cualquier gesto en el escenario habilita el audio analizado (el aro).
  box.onpointerdown = ensureOutputAnalyser;
  $("#invite")?.addEventListener("toggle", (e) => { CHAT.inviteOpen = e.target.open; });
  renderChatLangSelect();
  updateHead();
  if (voiceMode) {
    new VoiceOrb($("#orb"), orbSourceFor(HOST));
    participants().slice(1).forEach((g) => new VoiceOrb($(`#orb-g-${g}`), orbSourceFor(g)));
    updateOrbStates();
  }
  renderChatLog();
  renderChatFoot();
  setSpeakingClass();
  if (voiceMode) renderAttachTray();
  syncVideoCall(); // videollamada (features.js): se mantiene o se apaga al salir del modo voz
}

// En modo voz: el aro del asistente de la página al centro y los invitados a
// los costados, cada uno con su color; el que habla reacciona a su voz.
function orbRow() {
  const guests = participants().slice(1);
  const guestOrb = (g) => {
    const cfg = participantCfg(g);
    const name = displayName(cfg);
    return `<div class="guest" data-guest="${esc(g)}" data-chat-act="switch-host" style="${colorStyle(cfg)}"
      title="${esc(t("group.open", { name }))}">
      <div class="orb guest-orb" id="orb-g-${esc(g)}"></div>
      <span class="guest-name">${esc(name)}</span>
      <button class="guest-remove" type="button" data-chat-act="remove-guest" data-guest="${esc(g)}"
        aria-label="${esc(t("group.remove", { name }))}" title="${esc(t("group.remove", { name }))}">${ICON.close}</button>
    </div>`;
  };
  return `<div class="orb-row ${guests.length ? "has-guests" : ""}" style="--n:${guests.length + 1}">
    ${guests.filter((_, i) => i % 2 === 1).map(guestOrb).join("")}
    <div class="host-orb" data-guest="${HOST}">
      <button class="orb" id="orb" type="button" data-chat-act="conv-start">
        <span class="orb-icon" aria-hidden="true">${ICON.mic}</span>
      </button>
      ${guests.length ? `<span class="guest-name js-host-name">${esc(displayName(S.draft))}</span>` : ""}
    </div>
    ${guests.filter((_, i) => i % 2 === 0).map(guestOrb).join("")}
  </div>`;
}

// Resalta al que está hablando o pensando.
function updateOrbStates() {
  $$(".orb-row [data-guest]").forEach((el) => {
    el.classList.toggle("is-speaking", CHAT.speaking && CHAT.speaker === el.dataset.guest);
    el.classList.toggle("is-thinking", CHAT.thinkingFor === el.dataset.guest);
  });
}

// Idioma del chat. Escrito: "Responde en" el idioma en que escribas (entre
// los del asistente) o uno fijo. Voz: "Entiende y habla" todos los idiomas
// del asistente o solo uno.
// Ya no hay selector: se entiende y se responde en cualquiera de los idiomas
// configurados en el asistente (con uno solo, ese). Era redundante con los
// "Idiomas" de su configuración.
function renderChatLangSelect() {
  if (!S.draft) return;
  const langs = chatLangs();
  CHAT.lang = langs.length === 1 ? langs[0] : "auto";
  const sel = $("#chat-lang");
  if (!sel) return;
  if (CHAT.lang !== "auto" && !langs.includes(CHAT.lang)) CHAT.lang = "auto";
  if (langs.length === 1) CHAT.lang = langs[0];
  const voice = CHAT.mode === "voice";
  $("#chat-lang-label").textContent = t(voice ? "chat.lang_voice" : "chat.lang_text");
  const opt = (value, label) => `<option value="${value}" ${value === CHAT.lang ? "selected" : ""}>${esc(label)}</option>`;
  const auto = langs.length > 1
    ? opt("auto", voice ? t("chat.lang_auto_voice", { list: langs.slice(0, 4).map(langName).join(", ") + (langs.length > 4 ? "…" : "") })
      : t("chat.lang_auto_text"))
    : "";
  sel.innerHTML = auto + langs.map((c) => opt(c, voice ? t("chat.lang_only", { lang: langName(c) }) : langName(c))).join("");
}

// Idioma concreto para lo que se dice en voz (anuncios, respuestas) cuando
// el chat está en automático.
const spokenLang = (lang) => (lang && lang !== "auto" ? lang : CHAT.lastLang || S.draft.language);

function renderChatLog() {
  persistChat();
  const log = $("#chat-log");
  if (!log) return;
  if (CHAT.mode === "voice") return renderCaptions(log);
  const group = participants().length > 1;
  const lastUser = CHAT.messages.map((m) => m.role).lastIndexOf("user");
  let html = CHAT.messages.map((m, i) => {
    if (m.role === "event") {
      const ev = eventIcon(m); // icono delineado en vez de emoji (icons.js)
      return `<div class="msg event">${ev.html}${esc(ev.text)}</div>`;
    }
    if (m.role === "error") {
      const retry = i === CHAT.messages.length - 1 && !CHAT.busy && lastUser >= 0
        ? ` <button class="link" type="button" data-resend="${lastUser}">${esc(t("chat.retry"))}</button>` : "";
      return `<div class="msg error">${esc(m.text)}${retry}</div>`;
    }
    if (m.role === "places") return placesCard(m, i);
    if (m.role === "file") return fileCard(m);
    if (FEATURE_ROLES[m.role]) return FEATURE_ROLES[m.role](m, i); // p. ej. la imagen de ComfyUI (features.js)
    const replay = m.role === "assistant" && !m.streaming
      ? `<button class="icon-btn small" type="button" data-replay="${i}" aria-label="${esc(t("chat.replay"))}" title="${esc(t("chat.replay"))}">${ICON.speaker}</button>` : "";
    const who = m.role === "assistant" && (group || (m.speaker && m.speaker !== HOST)) ? speakerTag(m.speaker || HOST) : "";
    // Las respuestas, con su formato (markdown); lo del usuario, tal cual.
    const body = m.role === "assistant" ? `<div class="md">${renderMarkdown(m.text)}</div>` : esc(m.text);
    if (m.role === "user" && CHAT.editing === i) {
      return `<div class="msg user editing"><div class="bubble edit-box">
        <textarea id="edit-input" rows="2">${esc(m.text)}</textarea>
        <div class="edit-acts"><button class="btn btn-sm btn-quiet" type="button" data-edit-cancel>${esc(t("chat.cancel"))}</button>
          <button class="btn btn-sm btn-primary" type="button" data-edit-send="${i}">${esc(t("chat.send"))}</button></div></div></div>`;
    }
    // Tus mensajes: editar y reintentar desde ahí (borra lo que vino después).
    const userActs = m.role === "user" && !CHAT.busy
      ? `<button class="icon-btn small" type="button" data-edit="${i}" aria-label="${esc(t("chat.edit"))}" title="${esc(t("chat.edit"))}">${ICON.edit}</button>
         <button class="icon-btn small" type="button" data-resend="${i}" aria-label="${esc(t("chat.retry_from"))}" title="${esc(t("chat.retry_from"))}">${ICON.retry}</button>` : "";
    return `<div class="msg ${m.role}${m.files?.length ? " with-files" : ""}" data-msg="${i}"><div class="bubble">${who}${attachmentsHtml(m.files, i)}${body}</div><div class="msg-acts">${replay}${userActs}</div></div>`;
  }).join("");
  // Mientras la respuesta se va escribiendo, ya no hace falta el "pensando".
  if (CHAT.busy && !CHAT.messages[CHAT.messages.length - 1]?.streaming) {
    const label = group && CHAT.thinkingFor ? t("chat.thinking_who", { name: displayName(participantCfg(CHAT.thinkingFor) || S.draft) }) : t("chat.thinking");
    html += `<div class="msg assistant pending"><div class="bubble"><span class="dots"><i></i><i></i><i></i></span> ${esc(label)}</div></div>`;
  }
  if (!html) {
    html = `<div class="chat-empty">
      <span class="avatar orb-avatar xl js-assistant-avatar" aria-hidden="true"></span>
      <h2 id="chat-empty-title"></h2>
      <p>${esc(t("chat.empty"))}</p>
      <small>${esc(t("chat.sub"))}</small>
    </div>`;
  }
  clearPlaceMaps();
  log.innerHTML = html;
  // Solo los mensajes nuevos entran con animación (el chat se redibuja entero).
  const shown = CHAT.shown ?? CHAT.messages.length;
  [...log.children].forEach((n, k) => { if (k >= shown && k < CHAT.messages.length) n.classList.add("fresh"); });
  CHAT.shown = CHAT.messages.length;
  log.scrollTop = log.scrollHeight;
  mountPlaceMaps(log);
  updateHead();
}

// La respuesta que llega en streaming: solo se repinta su burbuja (o el
// subtítulo, en modo voz), una vez por cuadro, sin redibujar todo el chat
// (que vuelve a montar los mapas).
function paintLive(msg) {
  if (CHAT.livePaint) return;
  CHAT.livePaint = requestAnimationFrame(() => {
    CHAT.livePaint = 0;
    const i = CHAT.messages.indexOf(msg);
    const log = $("#chat-log");
    if (i < 0 || !log) return;
    if (CHAT.mode === "voice") {
      const caps = log.querySelectorAll(".cap.assistant");
      const cap = caps[caps.length - 1];
      if (!cap || participants().length > 1) return renderCaptions(log);
      cap.textContent = speakable(msg.text);
      log.scrollTop = log.scrollHeight;
      return;
    }
    const box = log.querySelector(`[data-msg="${i}"] .md`);
    if (!box) return renderChatLog();
    box.innerHTML = renderMarkdown(msg.text);
    log.scrollTop = log.scrollHeight;
  });
}

// En modo voz, debajo del aro: lo último que dijiste y lo último que
// respondió (más avisos y errores), como subtítulos.
function renderCaptions(box) {
  const msgs = CHAT.messages;
  let lastUser = -1;
  for (let i = msgs.length - 1; i >= 0; i--) if (msgs[i].role === "user") { lastUser = i; break; }
  let shown = lastUser >= 0 ? msgs.slice(lastUser) : msgs.slice(-2);
  const lastReply = shown.map((m) => m.role).lastIndexOf("assistant");
  shown = shown.filter((m, i) => m.role !== "assistant" || i === lastReply);
  const html = shown.map((m) => {
    if (m.role === "places") return placesCard(m, msgs.indexOf(m));
    if (m.role === "file") return fileCard(m);
    if (FEATURE_ROLES[m.role]) return FEATURE_ROLES[m.role](m, msgs.indexOf(m));
    const lang = m.role === "user" && m.lang && m.lang !== "auto" ? `<span class="msg-lang">${esc(m.lang)}</span>` : "";
    const who = m.role === "assistant" && participants().length > 1 ? speakerTag(m.speaker || HOST, "who-cap") : "";
    if (m.role === "event") {
      const ev = eventIcon(m);
      return `<p class="cap event">${ev.html}${esc(ev.text)}</p>`;
    }
    const text = m.role === "assistant" ? speakable(m.text) : m.text;
    return `<p class="cap ${m.role}">${who}${esc(text)}${lang}</p>`;
  }).join("");
  clearPlaceMaps();
  requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; });
  box.innerHTML = html || `<p class="cap hint-cap">${esc(hfUsable() ? t("hf.idle", { names: wakeNames(participants()) || displayName(S.draft) }) : t("conv.idle"))}</p>`;
  mountPlaceMaps(box);
}

// ── Mapa de lugares cercanos (resultado de find_nearby_places) ─────────
// El servidor manda los lugares con coordenadas; aquí se muestran en un
// mapa de OpenStreetMap (Leaflet, el mismo del mapa de Ajustes
// compartidos) junto con la lista y un enlace para llegar a cada uno.
let PLACE_MAPS = [];

function placesCard(m, index) {
  const d = m.data;
  const items = d.places.map((p, k) => `<li>
      <button type="button" class="place-item" data-place="${index}:${k}"><span class="pin-n">${k + 1}</span>
        <span class="pl-name">${esc(p.name)}</span><span class="pl-dist">${esc(t("places.km", { km: p.dist.toFixed(1) }))}</span></button>
      <a class="pl-route" href="https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lon}" target="_blank" rel="noopener noreferrer">${esc(t("places.route"))}</a>
    </li>`).join("");
  return `<div class="msg places"><div class="places-card">
    <div class="places-title">${ICON.pin} ${esc(t(d.kind === "place" ? "places.title_place" : "places.title", { cat: d.categoria }))}</div>
    <div class="places-map" data-places-map="${index}"></div>
    <ol class="places-list">${items}</ol>
  </div></div>`;
}

function clearPlaceMaps() {
  PLACE_MAPS.forEach((m) => m.map.remove());
  PLACE_MAPS = [];
}

async function mountPlaceMaps(root) {
  const boxes = $$("[data-places-map]", root);
  if (!boxes.length) return;
  try {
    await loadLeaflet();
  } catch (e) {
    boxes.forEach((b) => { b.textContent = e.message; });
    return;
  }
  for (const box of boxes) {
    if (!box.isConnected || box.dataset.ready) continue;
    box.dataset.ready = "1";
    const d = CHAT.messages[Number(box.dataset.placesMap)]?.data;
    if (!d) continue;
    const map = L.map(box, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    }).addTo(map);
    const points = [];
    if (d.origin) {
      L.circleMarker(d.origin, { radius: 8, color: "#fff", weight: 3, fillColor: "#3b82f6", fillOpacity: 1 })
        .bindTooltip(t("places.you")).addTo(map);
      points.push(d.origin);
    }
    const markers = d.places.map((p, k) => {
      const icon = L.divIcon({ className: "place-pin", html: `<span>${k + 1}</span>`, iconSize: [26, 26], iconAnchor: [13, 13] });
      points.push([p.lat, p.lon]);
      return L.marker([p.lat, p.lon], { icon, title: p.name })
        .bindPopup(`<strong>${esc(p.name)}</strong><br>${esc(t("places.km", { km: p.dist.toFixed(1) }))}`)
        .addTo(map);
    });
    map.fitBounds(points, { padding: [24, 24], maxZoom: 16 });
    PLACE_MAPS.push({ map, markers, index: Number(box.dataset.placesMap) });
  }
}

function focusPlace(ref) {
  const [index, k] = ref.split(":").map(Number);
  const entry = PLACE_MAPS.find((m) => m.index === index);
  const marker = entry?.markers[k];
  if (!marker) return;
  entry.map.setView(marker.getLatLng(), Math.max(entry.map.getZoom(), 16));
  marker.openPopup();
}

function renderChatFoot() {
  const foot = $("#chat-foot");
  if (!foot) return;
  if (CHAT.mode === "text") {
    foot.innerHTML = `
      ${CHAT.speaking ? `<button class="btn btn-sm stop-voice" type="button" data-chat-act="stop-voice">${ICON.stop} ${esc(t("chat.stop_voice"))}</button>` : ""}
      <div class="att-tray" id="att-tray" hidden></div>
      <div class="composer">
        <details class="menu attach-more">
          <summary class="attach-btn" aria-label="${esc(t("att.add"))}" title="${esc(t("att.add"))}">${ICON.plus}</summary>
          <div class="menu-pop up">
            <button class="menu-item" type="button" data-chat-act="attach">${ICON.clip}<span>${esc(t("att.files"))}</span></button>
            ${!isGuest() ? `<button class="menu-item" type="button" data-chat-act="library">${ICON.library}<span>${esc(t("att.from_library"))}</span></button>` : ""}
            ${canSeeImages() ? `<button class="menu-item" type="button" data-chat-act="camera">${ICON.camera}<span>${esc(t("cam.open"))}</span></button>` : ""}
          </div>
        </details>
        <button class="attach-btn wide-only" type="button" data-chat-act="attach" ${CHAT.busy ? "disabled" : ""}
          aria-label="${esc(t("att.add"))}" title="${esc(t(canSeeImages() ? "att.help_vision" : "att.help_novision"))}">${ICON.clip}</button>
        ${!isGuest() ? `<button class="attach-btn wide-only" type="button" data-chat-act="library" ${CHAT.busy ? "disabled" : ""}
          aria-label="${esc(t("att.from_library"))}" title="${esc(t("att.from_library"))}">${ICON.library}</button>` : ""}
        <input type="file" id="att-input" multiple hidden>
        ${canSeeImages() ? `<button class="attach-btn cam-btn wide-only" type="button" data-chat-act="camera" ${CHAT.busy ? "disabled" : ""}
          aria-label="${esc(t("cam.open"))}" title="${esc(t("cam.open"))}">${ICON.camera}</button>
        <input type="file" id="cam-input" accept="image/*" capture="environment" hidden>` : ""}
        <textarea id="chat-input" rows="1" placeholder="${esc(t(window.matchMedia("(max-width: 860px), (pointer: coarse)").matches ? "chat.ph_short" : "chat.ph"))}" ${CHAT.busy ? "disabled" : ""}></textarea>
        <button class="send-btn" type="button" data-chat-act="send" ${CHAT.busy || attachBusy() ? "disabled" : ""} aria-label="${esc(t("chat.send"))}" title="${esc(t("chat.send"))}">${ICON.send}</button>
      </div>`;
    renderAttachTray();
    return;
  }
  const active = !!CHAT.conv;
  const act = active ? "conv-stop" : "conv-start";
  const label = t(active ? "conv.stop" : "conv.start");
  const orb = $("#orb");
  if (orb) {
    // Tocar el aro: mientras habla lo interrumpe; si no, abre o termina la conversación.
    orb.dataset.chatAct = CHAT.speaking ? "stop-voice" : act;
    orb.dataset.active = active || CHAT.speaking ? "1" : "0";
    orb.setAttribute("aria-label", label);
    orb.title = label;
  }
  $("#conv-state").textContent = active ? t(CHAT.micMuted && CHAT.convState !== "speaking" && CHAT.convState !== "thinking" ? "conv.muted" : `conv.${CHAT.convState}`)
    : CHAT.speaking ? t("conv.speaking") : t("orb.start");
  $("#conv-note").textContent = CHAT.convNote;
  // Un solo botón: con la conversación abierta es la X; si el asistente
  // está hablando, la X lo interrumpe
  // y la siguiente la termina.
  // Con la conversación abierta (micrófono de esta página) el único botón
  // es el micrófono: lo silencia o lo activa. Para interrumpirlo se le habla
  // encima (barge-in); para terminar, se le pide por voz o se sale del modo voz.
  if (active && !CHAT.conv.hf) {
    const muted = !!CHAT.micMuted;
    const mlabel = t(muted ? "conv.unmute" : "conv.mute");
    // El aviso va debajo: así el botón no se corre de lugar al cambiar el texto.
    foot.innerHTML = voiceSides(`<div class="mic-wrap">
      <button class="round-btn mic-toggle ${muted ? "mic-off" : "mic-on"}" type="button" data-chat-act="conv-mute" aria-pressed="${muted}" aria-label="${esc(mlabel)}" title="${esc(mlabel)}">
        ${muted ? ICON.micMuted : ICON.mic}</button>
      <small class="round-hint">${esc(t(muted ? "conv.muted_hint" : CHAT.speaking ? "conv.barge_hint" : "conv.mute_hint"))}</small></div>`);
    return;
  }
  const interrupt = CHAT.speaking;
  const btnAct = interrupt ? "stop-voice" : act;
  const btnLabel = interrupt ? t("conv.interrupt") : label;
  foot.innerHTML = voiceSides(`<div class="mic-wrap">
    <button class="round-btn ${active || interrupt ? "end" : "start"} ${interrupt ? "interrupt" : ""}" type="button" data-chat-act="${btnAct}" aria-label="${esc(btnLabel)}" title="${esc(btnLabel)}">
      ${active || interrupt ? ICON.close : ICON.mic}</button>
    <small class="round-hint">${interrupt ? esc(t("conv.interrupt_hint")) : ""}</small></div>`);
}

function setConvState(state, note = "") {
  CHAT.convState = state;
  CHAT.convNote = note;
  if (CHAT.mode !== "voice") return;
  renderChatFoot();
}

async function onChatClick(e) {
  const resend = e.target.closest("[data-resend]");
  if (resend) return resendFrom(Number(resend.dataset.resend));
  const edit = e.target.closest("[data-edit]");
  if (edit) return startEdit(Number(edit.dataset.edit));
  if (e.target.closest("[data-edit-cancel]")) {
    CHAT.editing = null;
    return renderChatLog();
  }
  const editSend = e.target.closest("[data-edit-send]");
  if (editSend) {
    const text = $("#edit-input")?.value.trim();
    if (text) resendFrom(Number(editSend.dataset.editSend), text);
    return;
  }
  // En pantallas táctiles, tocar un mensaje muestra sus botones.
  const bubble = e.target.closest(".msg.user[data-msg] .bubble");
  if (bubble && !e.target.closest("button, a, summary, details")) {
    const msg = bubble.parentElement;
    $$(".msg.show-acts").forEach((x) => { if (x !== msg) x.classList.remove("show-acts"); });
    msg.classList.toggle("show-acts");
  }
  const openAtt = e.target.closest("[data-att-open]");
  if (openAtt) {
    e.preventDefault(); // dentro de un <summary>: que no se despliegue
    return openAttachment(openAtt.dataset.attOpen);
  }
  const removeAtt = e.target.closest("[data-att-remove]");
  if (removeAtt) return removeAttachment(Number(removeAtt.dataset.attRemove));
  const place = e.target.closest("[data-place]");
  if (place) return focusPlace(place.dataset.place);
  const replay = e.target.closest("[data-replay]");
  if (replay) {
    const m = CHAT.messages[Number(replay.dataset.replay)];
    // Con los mismos parámetros con que se generó: sale de la caché, no se
    // vuelve a sintetizar.
    if (m) {
      CHAT.speaker = m.speaker || HOST;
      speakText(m.text, m.lang, m.tts);
    }
    return;
  }
  const mode = e.target.closest("[data-chat-mode]");
  if (mode && mode.dataset.chatMode !== CHAT.mode) {
    stopConversation();
    stopSpeaking();
    CHAT.mode = mode.dataset.chatMode;
    renderChat();
    return;
  }
  const act = e.target.closest("[data-chat-act]")?.dataset.chatAct;
  if (!act) return;
  if (act === "send") sendFromComposer();
  else if (act === "retry") {
    const lu = CHAT.messages.map((m) => m.role).lastIndexOf("user");
    if (lu >= 0) resendFrom(lu);
  }
  else if (act === "camera") openCamera();
  else if (act === "library") {
    e.target.closest("details")?.removeAttribute("open");
    window.openLibraryPickerModal?.();
  }
  else if (act === "attach") {
    const input = $("#att-input");
    input.accept = attachAccept(); // según el modelo elegido en este momento
    input.click();
  } else if (act === "stop-voice") {
    if (CHAT.mode === "voice" && CHAT.busy) CHAT.roundStopped = true;
    stopSpeaking();
  }
  else if (act === "conv-start") startConversation();
  else if (act === "conv-stop") stopConversation();
  else if (act === "conv-mute") {
    CHAT.micMuted = !CHAT.micMuted;
    CHAT.conv?.cancel?.(); // deja de grabar ya
    setConvState(CHAT.micMuted ? "listening" : "listening", "");
    updateOrbStates();
  }
  else if (act === "remove-guest") toggleGuest(e.target.closest("[data-guest]").dataset.guest, false);
  else if (act === "switch-host") switchHost(e.target.closest("[data-guest]").dataset.guest);
  else if (act === "reset") {
    const { lang, guests } = CHAT;
    // Los archivos compartidos en este chat se borran con él: el servidor lo
    // hace al guardarlo vacío; los del invitado (su chat vive en el
    // navegador) se piden borrar aquí.
    const fileIds = [...new Set(JSON.stringify([CHAT.messages, CHAT.history]).match(/\/api\/files\/[0-9a-f]{24}(?:\.[a-z0-9]{1,8})?/g) || [])]
      .map((u) => u.slice("/api/files/".length));
    if (isGuest() && fileIds.length) api("POST", "/api/files/forget", { ids: fileIds }).catch(() => {});
    resetChat();
    Object.assign(CHAT, { lang, guests });
    renderChat();
    persistChat(true, { clear: true }); // vacía: se borra la guardada
  } else if (act === "unload") {
    stopConversation();
    stopSpeaking();
    try {
      await api("POST", "/api/chat/unload", { models: [S.draft.base_model] });
      toast(t("chat.unloaded"));
    } catch (err) {
      toast(err.message, "error");
    }
  }
}

function onChatChange(e) {
  if (e.target.dataset.invite) return toggleGuest(e.target.dataset.invite, e.target.checked);
  if (e.target.id === "att-input" || e.target.id === "cam-input") {
    addFiles(e.target.files);
    e.target.value = "";
    return;
  }
  if (e.target.id === "chat-lang") {
    CHAT.lang = e.target.value;
    hfReport();
  }
  else if (e.target.id === "chat-voice") {
    CHAT.voiceOn = e.target.checked;
    if (!CHAT.voiceOn) stopSpeaking();
  }
}

function onChatKey(e) {
  if (e.target.id === "edit-input") {
    if (e.key === "Escape") { CHAT.editing = null; renderChatLog(); }
    else if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = e.target.value.trim();
      if (text && CHAT.editing != null) resendFrom(CHAT.editing, text);
    }
    return;
  }
  if (e.target.id === "chat-input" && e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendFromComposer();
  }
}

function sendFromComposer() {
  const input = $("#chat-input");
  const text = input?.value.trim() || "";
  const hasFiles = CHAT.attachments.some((a) => a.status === "ready");
  if ((!text && !hasFiles) || CHAT.busy) return;
  if (attachBusy()) return toast(t("att.wait"));
  if (CHAT.attachments.some((a) => a.kind === "image") && !canSeeImages()) {
    toast(t("att.no_vision", { model: S.draft.base_model }), "error", 7000);
  }
  ensureOutputAnalyser();
  input.value = "";
  input.style.height = "auto";
  stopSpeaking();
  sendChat(text, CHAT.lang, null, takeAttachments());
}

// ── Adjuntos (chat escrito) ────────────────────────────────────────────
// Imágenes (solo si el modelo tiene "visión"), documentos (el servidor saca
// el texto de Word, Excel, PowerPoint, OpenDocument, RTF, HTML, texto y
// código; los PDF se leen aquí con pdf.js) y audio o video (Whisper lo pasa
// a texto). Al modelo le llega el texto de cada archivo junto con el
// mensaje y las imágenes aparte (ver _with_attachments en config_ui.py).
const ATT = {
  maxImages: 4,          // por mensaje (igual que MAX_IMAGES del servidor)
  maxChars: 24000,       // texto de un archivo para el modelo (attachments.MAX_CHARS)
  imageSide: 1536,       // lado mayor al que se reduce una imagen
  pdfScanPages: 4,       // páginas de un PDF escaneado que van como imágenes
  maxDoc: 40 * 1024 ** 2,
  maxAudio: 150 * 1024 ** 2,
  seq: 0,
};
const IMAGE_EXT = ["png", "jpg", "jpeg", "webp", "gif", "bmp", "avif"];
const MEDIA_EXT = ["mp3", "wav", "m4a", "aac", "ogg", "oga", "opus", "flac", "wma", "amr", "3gp", "webm", "mp4", "m4v", "mov", "mkv", "avi"];
const DOC_EXT = ["pdf", "docx", "docm", "xlsx", "xlsm", "pptx", "pptm", "odt", "ods", "odp", "epub", "rtf", "html", "htm",
  "txt", "md", "csv", "tsv", "json", "jsonl", "xml", "yaml", "yml", "toml", "ini", "log", "srt", "vtt", "tex", "sql",
  "py", "js", "ts", "tsx", "jsx", "css", "java", "c", "h", "cpp", "hpp", "cs", "go", "rs", "rb", "php", "sh", "ps1", "bat",
  "kt", "swift", "dart", "lua", "r", "ipynb", "vue", "svelte"];
const PDFJS = {
  js: ["https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js", "sha512-q+4liFwdPC/bNdhUpZx6aXDx/h77yEQtn4I1slHydcbZK34nLaR3cAeYSJshoxIOq3mjEf7xJE8YWIUHMn+oCQ=="],
  worker: "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js",
  loading: null,
};

const extOf = (name) => (String(name).toLowerCase().match(/\.([a-z0-9]+)$/) || [])[1] || "";

// Capacidades del modelo del asistente (null = Ollama no las informa).
function modelCaps(name = S.draft.base_model) {
  const m = (S.models?.models || []).find((x) => x.name === name || (!String(name).includes(":") && x.name === `${name}:latest`));
  return m ? m.capabilities : null;
}
const canSeeImages = () => { const caps = modelCaps(); return caps == null || caps.includes("vision"); };

function attachKind(file) {
  const ext = extOf(file.name);
  if (file.type.startsWith("image/") || IMAGE_EXT.includes(ext)) return "image";
  if (ext === "pdf" || file.type === "application/pdf") return "pdf";
  if (file.type.startsWith("audio/") || file.type.startsWith("video/") || MEDIA_EXT.includes(ext)) return "audio";
  return "file";
}

function attachAccept() {
  const exts = [...(canSeeImages() ? IMAGE_EXT : []), ...MEDIA_EXT, ...DOC_EXT];
  return [...exts.map((e) => `.${e}`), ...(canSeeImages() ? ["image/*"] : []), "audio/*", "video/*", "text/*"].join(",");
}

const attachBusy = () => CHAT.attachments.some((a) => a.status === "loading");

function addFiles(list) {
  const files = [...(list || [])];
  if (!files.length) return; // también en modo voz: van con lo próximo que digas
  for (const file of files) {
    const kind = attachKind(file);
    if (kind === "image" && !canSeeImages()) {
      toast(t("att.no_vision", { model: S.draft.base_model }), "error", 7000);
      continue;
    }
    if (kind === "image" && CHAT.attachments.filter((a) => a.kind === "image").length >= ATT.maxImages) {
      toast(t("att.too_many_images", { n: ATT.maxImages }), "error");
      continue;
    }
    const max = kind === "audio" ? ATT.maxAudio : ATT.maxDoc;
    if (file.size > max) {
      toast(t("att.too_big", { name: file.name, max: fmtSize(max) }), "error");
      continue;
    }
    const att = { id: ++ATT.seq, kind: kind === "pdf" ? "file" : kind, name: file.name, size: file.size, status: "loading" };
    CHAT.attachments.push(att);
    const read = kind === "image" ? readImage(file, att) : kind === "pdf" ? readPdf(file, att)
      : kind === "audio" ? readAudio(file, att) : readDocument(file, att);
    // El original, para poder abrirlo desde el chat (si falla, no importa).
    const keep = fetch(`/api/files?name=${encodeURIComponent(file.name)}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream", "X-UI-Lang": S.lang }, body: file,
    }).then((r) => (r.ok ? r.json() : null)).then((d) => { if (d?.url) att.url = d.url; }).catch(() => {});
    const job = Promise.all([read, keep]);
    job.then(() => { att.status = "ready"; }, (e) => {
      att.status = "error";
      att.error = e.message;
      toast(e.message, "error", 7000);
    }).finally(renderAttachTray);
  }
  renderAttachTray();
}

function removeAttachment(id) {
  CHAT.attachments = CHAT.attachments.filter((a) => a.id !== id && a.parent !== id);
  renderAttachTray();
}

async function attachLibraryItemToChat(item) {
  if (!item || !item.url) return;
  if (CHAT.attachments.some((a) => a.url === item.url)) {
    toast(t("lib.attached_toast", { name: item.name }));
    return;
  }
  const ext = extOf(item.name || item.id || "");
  const isVid = item.media_type === "video" || item.kind === "video" || ["mp4", "webm", "mov", "mkv", "avi"].includes(ext);
  const isImg = !isVid && (item.kind === "image" || item.kind === "edit" || IMAGE_EXT.includes(ext));
  const isAud = item.kind === "audio" || ["mp3", "wav", "ogg", "m4a", "flac", "aac", "opus"].includes(ext);
  const isPdf = item.kind === "pdf" || ext === "pdf";

  if (isImg) {
    if (!canSeeImages()) {
      toast(t("att.no_vision", { model: S.draft?.base_model || "" }), "error", 7000);
      return;
    }
    if (CHAT.attachments.filter((a) => a.kind === "image").length >= ATT.maxImages) {
      toast(t("att.too_many_images", { n: ATT.maxImages }), "error");
      return;
    }
    const att = { id: ++ATT.seq, kind: "image", name: item.name, size: item.size || 0, url: item.url, status: "loading" };
    CHAT.attachments.push(att);
    renderAttachTray();
    try {
      const res = await fetch(item.url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const file = new File([blob], item.name, { type: blob.type || "image/png" });
      await readImage(file, att);
      att.status = "ready";
      toast(t("lib.attached_toast", { name: item.name }));
    } catch (e) {
      att.status = "error";
      att.error = e.message;
      toast(e.message, "error");
    }
    renderAttachTray();
    return;
  }

  if (isVid) {
    CHAT.attachments.push({
      id: ++ATT.seq,
      kind: "file",
      name: item.name,
      size: item.size || 0,
      url: item.url,
      status: "ready",
      info: item.info || item.workflow || t("att.video_ref_info"),
      text: item.prompt ? `Video prompt: ${item.prompt}` : "",
    });
    renderAttachTray();
    toast(t("lib.attached_toast", { name: item.name }));
    return;
  }

  if (isAud) {
    if (item.preview_text) {
      CHAT.attachments.push({
        id: ++ATT.seq,
        kind: "audio",
        name: item.name,
        size: item.size || 0,
        url: item.url,
        status: "ready",
        info: item.info || "",
        text: item.preview_text,
      });
      renderAttachTray();
      toast(t("lib.attached_toast", { name: item.name }));
      return;
    }
    const att = { id: ++ATT.seq, kind: "audio", name: item.name, size: item.size || 0, url: item.url, status: "loading" };
    CHAT.attachments.push(att);
    renderAttachTray();
    try {
      const res = await fetch(item.url);
      const blob = await res.blob();
      const file = new File([blob], item.name, { type: blob.type || "audio/wav" });
      await readAudio(file, att);
      att.status = "ready";
      toast(t("lib.attached_toast", { name: item.name }));
    } catch (e) {
      att.status = "error";
      att.error = e.message;
      toast(e.message, "error");
    }
    renderAttachTray();
    return;
  }

  if (isPdf && !item.preview_text) {
    const att = { id: ++ATT.seq, kind: "file", name: item.name, size: item.size || 0, url: item.url, status: "loading" };
    CHAT.attachments.push(att);
    renderAttachTray();
    try {
      const res = await fetch(item.url);
      const blob = await res.blob();
      const file = new File([blob], item.name, { type: "application/pdf" });
      await readPdf(file, att);
      att.status = "ready";
      toast(t("lib.attached_toast", { name: item.name }));
    } catch (e) {
      att.status = "error";
      att.error = e.message;
      toast(e.message, "error");
    }
    renderAttachTray();
    return;
  }

  // Documentos, hojas de cálculo, código, texto o PDF con texto ya extraído
  const att = {
    id: ++ATT.seq,
    kind: "file",
    name: item.name,
    size: item.size || 0,
    url: item.url,
    status: item.preview_text ? "ready" : "loading",
    info: item.info || "",
    text: item.preview_text || "",
  };
  CHAT.attachments.push(att);
  renderAttachTray();
  if (item.preview_text) {
    toast(t("lib.attached_toast", { name: item.name }));
    return;
  }
  try {
    const prev = await api("GET", `/api/files/${encodeURIComponent(item.id)}/preview`);
    att.text = prev?.text || "";
    att.info = prev?.format || item.info || "";
    att.status = "ready";
    toast(t("lib.attached_toast", { name: item.name }));
  } catch (e) {
    att.status = "ready";
    toast(t("lib.attached_toast", { name: item.name }));
  }
  renderAttachTray();
}
window.attachLibraryItemToChat = attachLibraryItemToChat;

// Una imagen reducida a ATT.imageSide y pasada a JPEG (con fondo blanco por
// si tenía transparencia): así cualquier formato que abra el navegador
// llega en uno que Ollama acepta, y pesa poco.
async function imageToJpeg(source, width, height) {
  const scale = Math.min(1, ATT.imageSide / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.88);
}

async function readImage(file, att) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error(t("att.image_bad", { name: file.name }));
  }
  att.thumb = await imageToJpeg(bitmap, bitmap.width, bitmap.height);
  att.image = att.thumb.split(",")[1];
  att.info = `${bitmap.width}×${bitmap.height}`;
  bitmap.close?.();
}

async function readDocument(file, att) {
  let res;
  try {
    res = await fetch(`/api/chat/extract?name=${encodeURIComponent(file.name)}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream", "X-UI-Lang": S.lang }, body: file,
    });
  } catch {
    throw new Error(t("net.down"));
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.error || `HTTP ${res.status}`);
  att.text = data.text;
  att.info = [data.format, data.truncated ? t("att.truncated", { n: ATT.maxChars.toLocaleString() }) : ""].filter(Boolean).join(", ");
}

function loadPdfJs() {
  if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
  if (PDFJS.loading) return PDFJS.loading;
  PDFJS.loading = new Promise((resolve, reject) => {
    const script = Object.assign(document.createElement("script"), { src: PDFJS.js[0], integrity: PDFJS.js[1], crossOrigin: "anonymous", referrerPolicy: "no-referrer" });
    script.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS.worker;
      resolve(window.pdfjsLib);
    };
    script.onerror = () => { PDFJS.loading = null; reject(new Error(t("att.pdf_load_failed"))); };
    document.head.append(script);
  });
  return PDFJS.loading;
}

// El texto de cada página; si casi no tiene (PDF escaneado), las primeras
// páginas van como imágenes a un modelo con visión.
async function readPdf(file, att) {
  const lib = await loadPdfJs();
  let pdf;
  try {
    pdf = await lib.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  } catch (e) {
    throw new Error(t("att.pdf_failed", { name: file.name, error: e.message }));
  }
  const pages = [];
  let total = 0;
  for (let n = 1; n <= pdf.numPages && total < ATT.maxChars * 1.2; n++) {
    const content = await (await pdf.getPage(n)).getTextContent();
    let text = "";
    for (const item of content.items) text += item.str + (item.hasEOL ? "\n" : item.str ? " " : "");
    text = text.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    total += text.length;
    pages.push(text);
  }
  const chars = pages.reduce((s, p) => s + p.length, 0);
  att.info = t("att.pdf_info", { n: pdf.numPages });
  if (chars < 40 * Math.min(pdf.numPages, pages.length)) {
    // Escaneado: sin texto que leer.
    if (!canSeeImages()) throw new Error(t("att.pdf_scanned_novision", { name: file.name }));
    const room = ATT.maxImages - CHAT.attachments.filter((a) => a.kind === "image").length;
    const count = Math.max(0, Math.min(ATT.pdfScanPages, pdf.numPages, room));
    if (!count) throw new Error(t("att.too_many_images", { n: ATT.maxImages }));
    for (let n = 1; n <= count; n++) {
      const page = await pdf.getPage(n);
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: Math.min(2, ATT.imageSide / Math.max(base.width, base.height)) });
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(viewport.width);
      canvas.height = Math.round(viewport.height);
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      const thumb = await imageToJpeg(canvas, canvas.width, canvas.height);
      CHAT.attachments.push({ id: ++ATT.seq, parent: att.id, kind: "image", name: `${file.name} · ${t("att.page", { n })}`,
        status: "ready", thumb, image: thumb.split(",")[1], info: "" });
    }
    att.info = t("att.pdf_scanned_images", { n: count, total: pdf.numPages });
    att.text = "";
    att.scanned = true;
    return;
  }
  let text = pages.map((p, i) => (pdf.numPages > 1 ? `--- ${t("att.page", { n: i + 1 })} ---\n${p}` : p)).join("\n\n");
  if (text.length > ATT.maxChars || pages.length < pdf.numPages) {
    text = text.slice(0, ATT.maxChars);
    att.info += `, ${t("att.truncated", { n: ATT.maxChars.toLocaleString() })}`;
  }
  att.text = text;
}

const fmtDuration = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

async function readAudio(file, att) {
  att.transcribing = true;
  const type = file.type.startsWith("audio/") ? file.type : "audio/x-file";
  let res;
  try {
    res = await fetch(`/api/chat/transcribe?file=1&name=${encodeURIComponent(file.name)}`, {
      method: "POST", headers: { "Content-Type": type, "X-UI-Lang": S.lang }, body: file,
    });
  } catch {
    throw new Error(t("net.down"));
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.error || `HTTP ${res.status}`);
  if (!data.text) throw new Error(t("att.audio_empty", { name: file.name }));
  att.text = data.text;
  att.info = t("att.audio_info", { dur: fmtDuration(data.seconds || 0), lang: (data.lang || "?").toUpperCase() });
}

const attIcon = (a) => (a.kind === "audio" ? ICON.wave : ICON.file);

// Bandeja de adjuntos pendientes, encima del cuadro de texto. Se dibuja
// aparte para no borrar lo que se está escribiendo.
function renderAttachTray() {
  const tray = $("#att-tray");
  if (!tray) return;
  tray.hidden = !CHAT.attachments.length;
  tray.innerHTML = CHAT.attachments.map((a) => {
    const state = a.status === "loading" ? `<span class="att-state">${esc(t(a.kind === "audio" ? "att.transcribing" : "att.reading"))}</span>`
      : a.status === "error" ? `<span class="att-state err">${esc(a.error || "")}</span>` : a.info ? `<span class="att-state">${esc(a.info)}</span>` : "";
    const media = a.thumb ? `<img src="${a.thumb}" alt="">` : `<span class="att-ico">${attIcon(a)}</span>`;
    return `<div class="att-chip ${a.status}" title="${esc(a.name)}">${media}
      <span class="att-text"><span class="att-name">${esc(a.name)}</span>${state}</span>
      ${a.parent ? "" : `<button class="icon-btn small" type="button" data-att-remove="${a.id}" aria-label="${esc(t("att.remove"))}" title="${esc(t("att.remove"))}">${ICON.close}</button>`}
    </div>`;
  }).join("");
  const send = $("#chat-foot [data-chat-act=send]");
  if (send) send.disabled = CHAT.busy || attachBusy();
}

// Lo que se manda con el mensaje: para mostrar en el chat y para el modelo.
function takeAttachments() {
  const ready = CHAT.attachments.filter((a) => a.status === "ready" && !(a.kind === "image" && !canSeeImages()));
  CHAT.attachments = [];
  renderAttachTray();
  if (!ready.length) return null;
  return {
    display: ready.filter((a) => !a.scanned || !ready.some((x) => x.parent === a.id))
      .map(({ kind, name, info, thumb, text, url }) => ({ kind, name, info, thumb, text, url })),
    history: {
      attachments: ready.filter((a) => !a.scanned).map(({ kind, name, info, text, url }) => ({ kind, name, info, text, url })),
      images: ready.filter((a) => a.kind === "image").map((a) => a.image),
    },
  };
}

// Adjuntos de un mensaje ya enviado: miniaturas de las imágenes y, de los
// archivos y audios, su nombre con el texto desplegable.
function attachmentsHtml(list, index) {
  if (!list?.length) return "";
  const ref = (a) => `${index}:${list.indexOf(a)}`;
  const images = list.filter((a) => a.kind === "image" && (a.thumb || a.url))
    .map((a) => `<button class="att-img-btn" type="button" data-att-open="${ref(a)}" title="${esc(t("att.view", { name: a.name }))}">
      <img class="att-img" src="${esc(a.thumb || a.url)}" alt="${esc(a.name)}"></button>`).join("");
  const files = list.filter((a) => a.kind !== "image").map((a) => {
    const head = `<span class="att-ico">${attIcon(a)}</span><span class="att-name">${esc(a.name)}</span>${a.info ? `<span class="att-state">${esc(a.info)}</span>` : ""}`;
    const open = `<button class="att-open" type="button" data-att-open="${ref(a)}">${esc(t(a.kind === "audio" ? "att.listen" : "att.open"))}</button>`;
    return a.text
      ? `<details class="att-file"><summary>${head}${open}</summary><div class="att-body">${esc(a.text.length > 4000 ? `${a.text.slice(0, 4000)}…` : a.text)}</div></details>`
      : `<div class="att-file"><div class="att-sum">${head}${a.url ? open : ""}</div></div>`;
  }).join("");
  return `<div class="att-list">${images ? `<div class="att-imgs">${images}</div>` : ""}${files}</div>`;
}


const toolLabel = (name) =>
  STRINGS[S.lang][`chat.tool.${name}`] ? t(`chat.tool.${name}`) : t("chat.tool.other", { name });

// Si el asistente tiene que hablar: en modo texto según el interruptor, en
// modo voz solo mientras la conversación siga activa.
const voiceActive = () => (CHAT.mode === "voice" ? !!CHAT.conv : CHAT.voiceOn);

// `force`: quiénes responden, sin mirar a quién se nombró (push to talk de
// un asistente: lo dicho va a él).
// `files`: adjuntos del mensaje (ver takeAttachments).
async function sendChat(text, lang, force = null, files = null) {
  // Mientras ComfyUI dibuja con la GPU del asistente, lo que digas espera
  // su turno (ver featureHoldSend en features.js).
  if (featureHoldSend(() => sendChat(text, lang, force, files), text)) return;
  const epoch = CHAT.epoch;
  const id = uid();
  CHAT.messages.push({ role: "user", id, text, lang, files: files?.display });
  CHAT.history.push({ role: "user", id, content: text, ...(files?.history || {}) });
  CHAT.busy = true;
  if (!CHAT.noticeShown) {
    toast(t("chat.first_load"), "ok", 5000);
    CHAT.noticeShown = true;
  }
  renderChatLog();
  renderChatFoot();
  hfReport();

  // Responde el de la página, los que nombraste o, si le hablaste a todos,
  // todos por turnos: cada uno ya escucha lo que dijeron los anteriores.
  const forced = force && force.filter((k) => participants().includes(k));
  const { keys: order, all } = forced?.length ? { keys: forced, all: false } : await addressees(text);
  if (epoch !== CHAT.epoch) return;
  const group = participants(); // ya con quien se haya sumado al nombrarlo
  const answered = [];
  CHAT.roundStopped = false;
  for (const key of order) {
    // Lo sacaron en este mismo turno ("Jarvis, saca a Bella"): ya no responde.
    const name = key === HOST ? S.view?.name : key;
    if (CHAT.groupActions.some((g) => g.action === "remove" && g.name === name)) continue;
    const round = all ? { all: true, answered: [...answered], total: order.length } : null;
    if (!(await askAssistant(key, lang, group, epoch, round)) || epoch !== CHAT.epoch || CHAT.roundStopped || HF.queued) break;
    answered.push(displayName(participantCfg(key)));
  }
  if (epoch !== CHAT.epoch) { // se reinició o se cambió de asistente mientras respondía
    CHAT.groupActions = [];
    hfAfterTurn();
    return;
  }
  // El que entró saluda y el que salió se despide, dentro del mismo turno.
  await applyGroupActions(lang, epoch);
  if (epoch !== CHAT.epoch) {
    hfAfterTurn();
    return;
  }
  CHAT.busy = false;
  CHAT.thinkingFor = null;
  const now = participants();
  const maxHistory = Math.max(...now.map((k) => participantCfg(k)?.max_history || 20)) * (now.length > 1 ? 2 : 1);
  // Lo que pasa del límite lo resume el servidor en el próximo turno (evento
  // "summary"); por si no pudo, nunca más del doble.
  CHAT.history = CHAT.history.slice(-maxHistory * 2);
  CHAT.lastActivity = Date.now();
  if (CHAT.conv) CHAT.conv.lastHeard = Date.now();
  renderChatLog();
  renderChatFoot();
  updateOrbStates();
  hfReport();
  hfAfterTurn();
}

// Una respuesta de uno de los asistentes de la conversación. false si falló.
// `cue`: "join" (acaba de entrar: saluda) o "leave" (se va: se despide).
async function askAssistant(key, lang, group, epoch, round = null, cue = null) {
  const cfg = participantCfg(key);
  CHAT.thinkingFor = key;
  updateOrbStates();
  renderChatLog();
  let reply = null;
  let replyLang = lang;
  let error = null;
  let silent = false; // lo interrumpiste solo para que se callara: no responde
  let interrupted = false; // lo cortaste hablando (barge-in) mientras respondía
  CHAT.announce = null;
  const turnFiles = [];
  // Respuesta en streaming: el texto aparece mientras se genera ("delta") y,
  // en modo voz, cada frase suena apenas está lista ("say"), en cola, sin
  // esperar el resto. "reset": lo mostrado/dicho se descarta (el servidor
  // pidió otra respuesta) y llega de nuevo.
  const ctrl = new AbortController();
  CHAT.chatAbort = ctrl;
  let live = null; // el mensaje que se va escribiendo
  let speech = null; // la cola de voz de esta respuesta
  const dropLive = () => {
    if (live) CHAT.messages.splice(CHAT.messages.indexOf(live), 1);
    live = null;
  };
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", "X-UI-Lang": S.lang },
      // El modo decide el largo de las respuestas: escrito = detallado si hace
      // falta; voz = corto y natural (ver RESPONSE_STYLES en assistant_common.py).
      body: JSON.stringify({
        assistant: cfg, history: CHAT.history, lang, mode: CHAT.mode,
        speaker: key, host_name: S.view?.kind === "assistant" ? S.view.name : null,
        group: group.length > 1 ? group.map((k) => ({ key: k, label: displayName(participantCfg(k)) })) : [],
        round,
        cue,
        user_context: isGuest() ? S.data.user_context : undefined,
        // Lo que el invitado tiene en su navegador (memoria…) y el resumen
        // de lo viejo de la conversación (ver features.js).
        ...featureChatBody(key),
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.error || `HTTP ${res.status}`);
    }
    // Respuesta en streaming: una línea JSON por evento.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line) continue;
        const ev = JSON.parse(line);
        if (ev.type === "tool" && epoch === CHAT.epoch) {
          CHAT.messages.push({ role: "event", icon: toolIconName(ev.name), text: toolLabel(ev.name) });
          renderChatLog();
          if (ev.name === "web_search" && voiceActive() && cfg.search_announcement) {
            CHAT.speaker = key;
            CHAT.announce = speakText(cfg.search_announcement, spokenLang(lang), ttsParamsFor(key, spokenLang(lang)));
          }
        } else if (ev.type === "places" && epoch === CHAT.epoch) {
          CHAT.messages.push({ role: "places", data: { categoria: ev.categoria, origin: ev.origin, places: ev.places, kind: ev.kind } });
          renderChatLog();
        } else if (ev.type === "file" && epoch === CHAT.epoch) {
          // Archivo convertido: tarjeta en el chat y queda en el historial de la respuesta.
          CHAT.messages.push({ role: "file", data: { name: ev.name, url: ev.url, size: ev.size, from: ev.from } });
          turnFiles.push({ name: ev.name, url: ev.url });
          renderChatLog();
        } else if (ev.type === "group" && epoch === CHAT.epoch) {
          // El modelo invitó o sacó a alguien: se aplica al terminar el turno.
          CHAT.groupActions.push({ action: ev.action, name: ev.assistant, by: key === HOST ? S.view?.name : key });
        } else if (ev.type === "delta" && epoch === CHAT.epoch) {
          if (!live) {
            live = { role: "assistant", speaker: key, text: ev.text, streaming: true };
            CHAT.messages.push(live);
            renderChatLog();
          } else {
            live.text += ev.text;
            paintLive(live);
          }
        } else if (ev.type === "say" && epoch === CHAT.epoch) {
          if (voiceActive() && !HF.queued) {
            const sayLang = ev.lang || spokenLang(lang);
            if (!speech) {
              CHAT.speaker = key;
              speech = speechStream();
            }
            speech.push(ev.text, sayLang, ttsParamsFor(key, sayLang));
          }
        } else if (ev.type === "reset" && epoch === CHAT.epoch) {
          dropLive();
          renderChatLog();
          if (speech) {
            stopSpeaking();
            speech = null;
          }
        } else if (ev.type === "silent") {
          silent = true;
        } else if (FEATURE_EVENTS[ev.type]) {
          // Memoria, recordatorios, listas, resumen… (ver features.js)
          FEATURE_EVENTS[ev.type](ev, { key, epoch });
        } else if (ev.type === "reply") {
          reply = ev.text;
          replyLang = ev.lang || spokenLang(lang);
        } else if (ev.type === "error") {
          error = ev.message;
        }
      }
    }
  } catch (e) {
    if (ctrl.signal.aborted) interrupted = true;
    else error = e.message;
  }
  if (CHAT.chatAbort === ctrl) CHAT.chatAbort = null;

  if (epoch !== CHAT.epoch) return false;
  CHAT.thinkingFor = null;
  if (interrupted) {
    // Barge-in a mitad de la respuesta: el servidor dejó de generar y queda
    // en la conversación lo que alcanzó a escribir.
    const text = live?.text.trim();
    if (text) {
      Object.assign(live, { text, lang: replyLang, tts: ttsParamsFor(key, replyLang) });
      delete live.streaming;
      CHAT.history.push({ role: "assistant", content: text, speaker: key });
    } else dropLive();
    renderChatLog();
    renderChatFoot();
    return false;
  }
  if (silent && !error) {
    CHAT.messages.push({ role: "event", text: t("conv.stopped_quiet") });
    renderChatLog();
    renderChatFoot();
    return false; // no siguen los demás de la ronda
  }
  if (error || reply == null) {
    dropLive();
    if (speech) stopSpeaking();
    if (CHAT.history[CHAT.history.length - 1]?.role === "user") CHAT.failedTurn = CHAT.history.pop();
    CHAT.messages.push({ role: "error", text: t("chat.error", { error: error || "?" }) });
    renderChatLog();
    renderChatFoot();
    return false;
  }
  CHAT.lastLang = replyLang;
  const msg = live || { role: "assistant", speaker: key };
  Object.assign(msg, { text: reply, lang: replyLang, tts: ttsParamsFor(key, replyLang) });
  delete msg.streaming;
  if (!live) CHAT.messages.push(msg);
  CHAT.history.push({ role: "assistant", content: reply, speaker: key, ...(turnFiles.length ? { files: turnFiles } : {}) });
  renderChatLog();
  renderChatFoot();
  // Si mientras pensaba lo llamaron otra vez (manos libres), no se dice
  // esta respuesta: se atiende la llamada nueva.
  if (voiceActive() && !HF.queued) {
    if (speech) {
      // Ya está sonando frase por frase: se espera a que termine la cola.
      speech.close();
      await speech.done;
    } else {
      if (CHAT.announce) await CHAT.announce;
      CHAT.speaker = key;
      await speakText(reply, replyLang, msg.tts);
    }
  } else if (speech) stopSpeaking();
  return true;
}

// Voz de las respuestas: se trocea por oraciones y se pide la siguiente
// mientras suena la actual (igual que voice_loop.py), así el primer audio
// empieza antes. Si la primera oración es muy larga se corta en su primera
// coma: es la única que se espera entera antes de oír algo.
// ── Markdown de las respuestas del chat escrito ────────────────────────
// En el chat escrito el modelo responde con formato (negritas, listas,
// tablas, emojis; ver RESPONSE_STYLES en assistant_common.py). Se escapa
// TODO primero y después se convierte un subconjunto conocido de markdown
// en etiquetas fijas: nunca entra HTML del modelo, y los enlaces solo si son
// http(s).
function mdInline(text) {
  const codes = [];
  let s = esc(text).replace(/`([^`\n]+)`/g, (_, c) => `\u0000${codes.push(c) - 1}\u0000`);
  s = s
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\*\*(?=\S)([^\n]*?\S)\*\*/g, "<strong>$1</strong>")
    .replace(/__(?=\S)([^\n]*?\S)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*(?=\S)([^*\n]*?\S)\*(?![*\w])/g, "$1<em>$2</em>")
    .replace(/~~(?=\S)([^\n]*?\S)~~/g, "<del>$1</del>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
}

const MD_TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const mdCells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

function renderMarkdown(text) {
  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let para = [];
  const flush = () => {
    if (para.length) out.push(`<p>${para.map(mdInline).join("<br>")}</p>`);
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = /^\s*```/.exec(line);
    if (fence) {
      flush();
      const code = [];
      while (++i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i]);
      out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    const head = /^\s*(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (head) {
      flush();
      const level = Math.min(head[1].length + 2, 6); // dentro de una burbuja: h3 para abajo
      out.push(`<h${level}>${mdInline(head[2])}</h${level}>`);
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); out.push("<hr>"); continue; }
    if (line.includes("|") && i + 1 < lines.length && MD_TABLE_SEP.test(lines[i + 1])) {
      flush();
      const header = mdCells(line);
      const rows = [];
      i += 1;
      while (i + 1 < lines.length && lines[i + 1].includes("|") && lines[i + 1].trim()) rows.push(mdCells(lines[++i]));
      out.push(`<div class="md-table"><table><thead><tr>${header.map((c) => `<th>${mdInline(c)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr>${header.map((_, k) => `<td>${mdInline(r[k] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    const item = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/.exec(line);
    if (item) {
      flush();
      // Una lista (con un nivel de sangría para sub-elementos).
      const ordered = /\d/.test(item[2]);
      const items = [];
      for (; i < lines.length; i++) {
        const m = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/.exec(lines[i]);
        if (m) {
          const nested = m[1].length >= 2 && items.length;
          if (nested) (items[items.length - 1].sub ||= []).push(m[3]);
          else items.push({ text: m[3], n: Number.parseInt(m[2], 10) });
        } else if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) {
          items[items.length - 1].text += `\n${lines[i].trim()}`; // continuación del elemento
        } else break;
      }
      i -= 1;
      const tag = ordered ? "ol" : "ul";
      const start = ordered && items[0].n > 1 ? ` start="${items[0].n}"` : "";
      out.push(`<${tag}${start}>${items.map((it) => `<li>${it.text.split("\n").map(mdInline).join("<br>")}${
        it.sub ? `<ul>${it.sub.map((s) => `<li>${mdInline(s)}</li>`).join("")}</ul>` : ""}</li>`).join("")}</${tag}>`);
      continue;
    }
    const quote = /^\s*>\s?(.*)$/.exec(line);
    if (quote) { flush(); out.push(`<blockquote>${mdInline(quote[1])}</blockquote>`); continue; }
    para.push(line.trim());
  }
  flush();
  return out.join("");
}

// Lo que se lee en voz alta de una respuesta con formato: sin markdown,
// sin emojis, las tablas como frases y los elementos de una lista como
// oraciones; las unidades más comunes con su nombre (Supertonic leería
// "km/h" letra por letra).
const SPOKEN_UNITS = {
  es: { "°C": "grados", "°F": "grados Fahrenheit", "km/h": "kilómetros por hora", "km": "kilómetros", "m": "metros", "cm": "centímetros", "mm": "milímetros", "kg": "kilos", "g": "gramos", "%": "por ciento", "h": "horas", "min": "minutos", "GB": "gigas", "MB": "megas" },
  en: { "°C": "degrees", "°F": "degrees Fahrenheit", "km/h": "kilometers per hour", "km": "kilometers", "m": "meters", "cm": "centimeters", "mm": "millimeters", "kg": "kilograms", "g": "grams", "%": "percent", "h": "hours", "min": "minutes", "GB": "gigabytes", "MB": "megabytes" },
  pt: { "°C": "graus", "°F": "graus Fahrenheit", "km/h": "quilômetros por hora", "km": "quilômetros", "m": "metros", "cm": "centímetros", "mm": "milímetros", "kg": "quilos", "g": "gramas", "%": "por cento", "h": "horas", "min": "minutos", "GB": "gigas", "MB": "megas" },
};

function speakable(text, lang) {
  let s = String(text || "").replace(/\r\n?/g, "\n").replace(/```[\s\S]*?```/g, " ");
  s = s.split("\n").map((line) => {
    if (MD_TABLE_SEP.test(line) || /^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) return "";
    if (line.includes("|") && /^\s*\|/.test(line)) line = mdCells(line).filter(Boolean).join(", ");
    line = line.replace(/^\s*#{1,6}\s+/, "").replace(/^\s*>\s?/, "").replace(/^\s*([-*+•]|\d{1,3}[.)])\s+/, "");
    line = line.trim();
    // Cada línea (título, elemento de lista, fila) como una oración.
    return line && !/[.!?…:;,]$/.test(line) ? `${line}.` : line;
  }).filter(Boolean).join(" ");
  s = s
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/(\*\*|__|~~|`)/g, "")
    .replace(/(^|\s)\*(\S[^*]*?)\*/g, "$1$2")
    .replace(/[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\uFE0F\u200D\u20E3]/gu, "")
    .replace(/\s*(→|⇒|->)\s*/g, ", ");
  const units = SPOKEN_UNITS[String(lang || "").slice(0, 2)];
  if (units) {
    const keys = Object.keys(units).sort((a, b) => b.length - a.length).map((k) => k.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&"));
    s = s.replace(new RegExp(`(\\d)\\s?(${keys.join("|")})(?![\\p{L}\\d])`, "gu"), (_, d, u) => `${d} ${units[u]}`);
  }
  return s.replace(/\s+([.,;:!?])/g, "$1").replace(/([.!?])\.+/g, "$1").replace(/\s{2,}/g, " ").trim();
}

// ── Historial persistente (ver chat_store.py) ─────────────────────────
// La conversación de cada asistente se guarda en el servidor al cambiar y
// se recupera al volver a abrirlo: no se pierde al ir a la galería, al
// recargar la página ni al abrirla desde otro dispositivo de la red.
const CHAT_SAVE = { timer: null, sig: "", savedAt: 0, pending: null };

const chatSig = () => {
  const last = CHAT.messages[CHAT.messages.length - 1];
  return `${CHAT.owner}|${CHAT.messages.length}|${CHAT.history.length}|${CHAT.guests.join(",")}|${CHAT.lang}|${last?.text?.length || 0}|${CHAT.summary.length}`;
};

// Los cambios se juntan (800 ms) y se mandan de una vez; `now` (al salir
// del asistente o reiniciar) manda ya lo pendiente. Una conversación vacía
// solo se manda (= se borra la guardada) con `clear`, al reiniciar: antes,
// al volver de la galería, la página guardaba el chat vacío antes de que
// llegara el guardado y lo borraba.
function persistChat(now = false, { clear = false } = {}) {
  const empty = !CHAT.messages.length && !CHAT.history.length;
  if (CHAT.owner && !CHAT.restoring && (!empty || clear)) {
    const sig = chatSig();
    if (sig !== CHAT_SAVE.sig || clear) {
      CHAT_SAVE.sig = sig;
      // Las listas de ahora (resetChat crea otras): se guarda lo de este asistente.
      CHAT_SAVE.pending = { owner: CHAT.owner, data: { messages: CHAT.messages, history: CHAT.history, guests: CHAT.guests, lang: CHAT.lang, summary: CHAT.summary } };
    }
  }
  if (!CHAT_SAVE.pending) return;
  clearTimeout(CHAT_SAVE.timer);
  if (now) flushChat();
  else CHAT_SAVE.timer = setTimeout(flushChat, 800);
}

function flushChat() {
  const p = CHAT_SAVE.pending;
  CHAT_SAVE.pending = null;
  clearTimeout(CHAT_SAVE.timer);
  if (!p) return;
  if (isGuest()) {
    guestSaveChat(p.owner, p.data);
    return;
  }
  api("PUT", `/api/chats/${p.owner}`, p.data)
    .then((r) => { CHAT_SAVE.savedAt = r?.updated_at || Date.now() / 1000; })
    .catch(() => { CHAT_SAVE.sig = ""; }); // se reintenta en el próximo cambio
}

// Al abrir un asistente: su conversación guardada (si la hay).
async function restoreChat(name, { onlyIfNewer = false } = {}) {
  let data;
  if (!onlyIfNewer) CHAT.restoring = true; // mientras llega, no se guarda nada
  try {
    data = isGuest() ? guestGet(`chat:${name}`, {}) : await api("GET", `/api/chats/${name}`);
  } catch {
    if (CHAT.owner === name) CHAT.restoring = false;
    return;
  }
  if (CHAT.owner !== name) return;
  CHAT.restoring = false;
  if (CHAT.busy || !data?.messages) return;
  if (onlyIfNewer && !(data.updated_at > CHAT_SAVE.savedAt + 0.5)) return;
  if (!onlyIfNewer && CHAT.messages.length) return persistChat(); // ya se empezó a escribir
  // Lo pendiente era de antes de cargar (vacío): no se manda.
  if (CHAT_SAVE.pending?.owner === name) {
    CHAT_SAVE.pending = null;
    clearTimeout(CHAT_SAVE.timer);
  }
  CHAT.restoring = true;
  CHAT.messages = data.messages;
  CHAT.history = data.history || [];
  CHAT.summary = data.summary || "";
  CHAT.lang = data.lang || CHAT.lang;
  CHAT.guests = (data.guests || []).filter((g) => S.data.assistants.some((a) => a.name === g && sameModel(a)));
  const lastLang = [...CHAT.messages].reverse().find((m) => m.lang && m.lang !== "auto");
  CHAT.lastLang = lastLang?.lang || CHAT.lastLang;
  CHAT_SAVE.savedAt = data.updated_at || 0;
  CHAT_SAVE.sig = chatSig();
  CHAT.restoring = false;
  if (S.view?.kind === "assistant" && S.view.name === name) renderChat();
}

// ── Cámara: tomar una foto y adjuntarla (modelos con visión) ──────────
// En el celular se usa la cámara del sistema (input con `capture`, no
// necesita permisos de la página); en la computadora, una vista previa con
// getUserMedia (exige HTTPS o localhost) con botón para disparar y para
// cambiar de cámara.
const CAM = { stream: null, facing: "environment", devices: [] };
const isTouch = () => window.matchMedia("(pointer: coarse)").matches;

function openCamera() {
  if (!canSeeImages()) return toast(t("att.no_vision", { model: S.draft.base_model }), "error", 7000);
  if (isTouch() || !navigator.mediaDevices?.getUserMedia) {
    const input = $("#cam-input");
    input.value = "";
    return input.click();
  }
  let dlg = $("#cam-dialog");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "cam-dialog";
    dlg.className = "cam-dialog";
    dlg.innerHTML = `
      <div class="cam-view"><video id="cam-video" autoplay playsinline muted></video><p class="cam-msg" id="cam-msg"></p></div>
      <div class="cam-bar">
        <button class="btn" type="button" data-cam="close">${esc(t("cam.cancel"))}</button>
        <button class="cam-shoot" type="button" data-cam="shoot" aria-label="${esc(t("cam.shoot"))}" title="${esc(t("cam.shoot"))}"></button>
        <button class="btn" type="button" data-cam="flip" id="cam-flip">${esc(t("cam.flip"))}</button>
      </div>`;
    document.body.append(dlg);
    dlg.addEventListener("click", (e) => {
      const act = e.target.closest("[data-cam]")?.dataset.cam;
      if (act === "close") dlg.close();
      else if (act === "shoot") shootPhoto();
      else if (act === "flip") { CAM.facing = CAM.facing === "user" ? "environment" : "user"; startCamera(); }
    });
    dlg.addEventListener("close", stopCamera);
  }
  dlg.showModal();
  startCamera();
}

async function startCamera() {
  stopCamera();
  const msg = $("#cam-msg");
  msg.textContent = t("cam.starting");
  try {
    CAM.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: CAM.facing, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
    $("#cam-video").srcObject = CAM.stream;
    msg.textContent = "";
    CAM.devices = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
    $("#cam-flip").hidden = CAM.devices.length < 2;
  } catch (e) {
    msg.textContent = t(window.isSecureContext ? "cam.denied" : "cam.insecure", { error: e.message });
    $("#cam-flip").hidden = true;
  }
}

function stopCamera() {
  CAM.stream?.getTracks().forEach((tr) => tr.stop());
  CAM.stream = null;
}

async function shootPhoto() {
  const video = $("#cam-video");
  if (!CAM.stream || !video.videoWidth) return;
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
  const stamp = new Date().toTimeString().slice(0, 8).replace(/:/g, "");
  $("#cam-dialog").close();
  addFiles([new File([blob], `${t("cam.photo")}-${stamp}.jpg`, { type: "image/jpeg" })]);
}

// ── Reintentar la respuesta ────────────────────────────────────────────
// Borra lo que respondieron al último mensaje (o el error) y se lo vuelve a
// pedir a los mismos asistentes, con el mismo mensaje y sus adjuntos.
async function retryLast() {
  if (CHAT.busy) return;
  const lu = CHAT.messages.map((m) => m.role).lastIndexOf("user");
  if (lu < 0) return;
  stopSpeaking();
  const after = CHAT.messages.slice(lu + 1);
  const keys = [...new Set(after.filter((m) => m.role === "assistant").map((m) => m.speaker || HOST))]
    .filter((k) => participants().includes(k));
  CHAT.messages.splice(lu + 1);
  const hu = CHAT.history.map((m) => m.role).lastIndexOf("user");
  const lastIsUser = CHAT.history.length && CHAT.history[CHAT.history.length - 1].role === "user";
  if (!lastIsUser && after.some((m) => m.role === "error") && CHAT.failedTurn) {
    CHAT.history.push(CHAT.failedTurn); // el mensaje que falló (se había quitado del historial)
  } else if (hu >= 0) {
    CHAT.history.splice(hu + 1);
  }
  CHAT.failedTurn = null;
  const lang = CHAT.messages[lu].lang || CHAT.lang;
  const epoch = CHAT.epoch;
  const group = participants();
  CHAT.busy = true;
  renderChatLog();
  renderChatFoot();
  for (const key of keys.length ? keys : [HOST]) {
    if (!(await askAssistant(key, lang, group, epoch)) || epoch !== CHAT.epoch) break;
  }
  if (epoch !== CHAT.epoch) return;
  CHAT.busy = false;
  CHAT.thinkingFor = null;
  renderChatLog();
  renderChatFoot();
  updateOrbStates();
}

// ── Ver los adjuntos de un mensaje ─────────────────────────────────────
// Las imágenes en grande (la original si se guardó, si no la que se mandó
// al modelo); los archivos y audios se abren con su original (visor del
// navegador, reproductor) o, si no está, se muestra su texto.
function openAttachment(ref) {
  const [i, k] = ref.split(":").map(Number);
  const a = CHAT.messages[i]?.files?.[k];
  if (!a) return;
  let dlg = $("#att-viewer");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "att-viewer";
    dlg.className = "att-viewer";
    document.body.append(dlg);
    dlg.addEventListener("click", (e) => {
      if (e.target === dlg || e.target.closest("[data-viewer-close]")) dlg.close();
    });
  }
  const open = a.url ? `<a class="btn btn-sm" href="${esc(a.url)}" target="_blank" rel="noopener">${esc(t("att.open_original"))}</a>` : "";
  let body;
  if (a.kind === "image") return openImageViewer(a.url || a.thumb || "", a.name); // con zoom (features.js)
  if (a.kind === "audio" && a.url) body = `<audio controls autoplay src="${esc(a.url)}"></audio><div class="viewer-text">${esc(a.text || "")}</div>`;
  else body = `<div class="viewer-text">${esc(a.text || t("att.no_text"))}</div>`;
  dlg.innerHTML = `<div class="viewer-head"><strong>${esc(a.name)}</strong>${a.info ? `<small>${esc(a.info)}</small>` : ""}
      <span class="spacer"></span>${open}<button class="icon-btn" type="button" data-viewer-close aria-label="${esc(t("cam.cancel"))}">${ICON.close}</button></div>
    <div class="viewer-body ${a.kind}">${body}</div>`;
  dlg.showModal();
}

// ── Editar y reintentar mensajes (cualquiera, no solo el último) ──────
// Desde un mensaje tuyo: se borra lo que vino después (respuestas y
// mensajes siguientes) y se vuelve a mandar, igual o editado, con sus
// adjuntos. Cada mensaje lleva un `id` también en el historial para
// encontrarlo; los de antes (sin id) se ubican por orden.
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

function historyIndexOf(mi) {
  const m = CHAT.messages[mi];
  if (m.id) {
    const byId = CHAT.history.findIndex((h) => h.id === m.id);
    if (byId >= 0) return byId;
  }
  const ordinal = CHAT.messages.slice(0, mi).filter((x) => x.role === "user").length;
  let seen = -1;
  return CHAT.history.findIndex((h) => h.role === "user" && !String(h.content || "").startsWith("[") && ++seen === ordinal);
}

// Los adjuntos del mensaje como los manda sendChat (para volver a enviarlo).
function filesOf(m, entry) {
  if (!m.files?.length) return null;
  return {
    display: m.files,
    history: entry?.attachments || entry?.images
      ? { attachments: entry.attachments, images: entry.images }
      : {
        attachments: m.files.map(({ kind, name, info, text }) => ({ kind, name, info, text })),
        images: m.files.filter((f) => f.kind === "image" && f.thumb).map((f) => f.thumb.split(",")[1]),
      },
  };
}

async function resendFrom(mi, text = null) {
  const m = CHAT.messages[mi];
  if (!m || m.role !== "user" || CHAT.busy) return;
  stopSpeaking();
  const hi = historyIndexOf(mi);
  const entry = hi >= 0 ? CHAT.history[hi] : (CHAT.failedTurn?.id && CHAT.failedTurn.id === m.id ? CHAT.failedTurn : null);
  const files = filesOf(m, entry);
  CHAT.messages.splice(mi);
  if (hi >= 0) CHAT.history.splice(hi);
  CHAT.failedTurn = null;
  CHAT.editing = null;
  await sendChat(text ?? m.text, m.lang || CHAT.lang, null, files);
}

function startEdit(mi) {
  if (CHAT.busy) return;
  CHAT.editing = mi;
  renderChatLog();
  const ta = $("#edit-input");
  if (ta) {
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    ta.style.height = `${Math.min(ta.scrollHeight, 240)}px`;
  }
}

// Menús desplegables (⋯ del chat, de la barra superior, + del cuadro de
// texto): se cierran al tocar fuera o al elegir algo.
document.addEventListener("click", (e) => {
  $$("details.menu[open]").forEach((d) => {
    if (!d.contains(e.target) || e.target.closest(".menu-pop button:not([data-keep-open]), .menu-pop a")) d.open = false;
  });
});

// ── Recarga en caliente (ver dev_reload.py) ───────────────────────────
// Cada pocos segundos se pregunta si cambió la página o se reinició el
// servidor. El CSS se cambia al vuelo; lo demás recarga la página cuando no
// se está usando (la conversación está guardada en el servidor).
const DEV = { base: null, pending: false, noticed: false };

async function devPoll() {
  try {
    const r = await fetch("/api/dev/version", { cache: "no-store" });
    if (r.ok) {
      const v = await r.json();
      if (!DEV.base) DEV.base = v;
      else {
        if (v.css !== DEV.base.css) {
          swapStylesheet(v.css);
          DEV.base.css = v.css;
        }
        if (v.assets !== DEV.base.assets || v.boot !== DEV.base.boot) DEV.pending = true;
      }
    }
  } catch { /* el servidor se está reiniciando: se reintenta */ }
  if (DEV.pending) tryDevReload();
  setTimeout(devPoll, document.visibilityState === "visible" ? 2000 : 8000);
}

function swapStylesheet(version) {
  const link = $('link[rel="stylesheet"][href^="/static/style.css"]');
  if (!link) return;
  const fresh = link.cloneNode();
  fresh.href = `/static/style.css?v=${version}`;
  fresh.onload = () => link.remove();
  link.after(fresh);
}

const devBusy = () => CHAT.busy || !!CHAT.conv || CHAT.speaking || isDirty() || !!$("#chat-input")?.value.trim()
  || CHAT.attachments.length || CHAT.editing != null || !!$("dialog[open]") || !!CAM.stream || S.pull?.state === "running";

function tryDevReload() {
  if (!devBusy()) {
    persistChat(true);
    setTimeout(() => location.reload(), 250);
  } else if (!DEV.noticed) {
    DEV.noticed = true;
    toast(t("dev.pending"), "ok", 5000);
  }
}

// Archivo que mandó el asistente (convert_file): tarjeta para abrirlo o descargarlo.
function fileCard(m) {
  const d = m.data || {};
  const ext = (String(d.name).match(/\.([a-z0-9]+)$/i) || [])[1]?.toLowerCase() || "";
  const isImage = ["png", "jpg", "jpeg", "webp", "gif", "bmp"].includes(ext);
  const size = d.size ? (d.size < 1024 ** 2 ? `${Math.max(1, Math.round(d.size / 1024))} KB` : `${(d.size / 1024 ** 2).toFixed(1)} MB`) : "";
  return `<div class="msg file"><div class="file-card">
    ${isImage ? `<button class="cj-view" type="button" data-iv-open="${esc(d.url)}" data-iv-name="${esc(d.name)}"><img src="${esc(d.url)}" alt=""></button>` : `<span class="file-ext">${esc(ext.toUpperCase() || "?")}</span>`}
    <div class="file-info"><strong>${esc(d.name)}</strong><small>${esc([size, d.from ? t("file.from", { name: d.from }) : ""].filter(Boolean).join(" · "))}</small></div>
    <div class="file-acts">
      <a class="btn btn-sm" href="${esc(d.url)}" target="_blank" rel="noopener">${esc(t("att.open"))}</a>
      <a class="btn btn-sm btn-primary" href="${esc(d.url)}" download="${esc(d.name)}">${esc(t("file.download"))}</a>
    </div></div></div>`;
}

function splitSpeech(text) {
  const chunks = splitSentences(text);
  if (chunks.length && chunks[0].length > 120) {
    const m = /^(.{40,120}?[,;:])\s+(.+)$/s.exec(chunks[0]);
    if (m) chunks.splice(0, 1, m[1], m[2]);
  }
  return chunks;
}

function splitSentences(text) {
  const sentences = text.trim().split(/(?<=[.!?…])\s+/).filter(Boolean);
  const chunks = [];
  let buf = "";
  for (const s of sentences) {
    buf = buf ? `${buf} ${s}` : s;
    if (buf.length >= 15) {
      chunks.push(buf);
      buf = "";
    }
  }
  if (buf) {
    if (chunks.length) chunks[chunks.length - 1] += ` ${buf}`;
    else chunks.push(buf);
  }
  return chunks;
}

// Voz y velocidad de cada asistente de la conversación.
const ttsParamsFor = (key, lang) => {
  const cfg = participantCfg(key) || S.draft;
  return { voice: cfg.voice, speed: cfg.speed, lang };
};
const ttsParams = (lang) => ttsParamsFor(HOST, lang);

// Audios ya generados en esta página (trozo + voz + velocidad + idioma →
// URL del blob): "escuchar de nuevo" y los anuncios repetidos salen de
// aquí sin pedir nada al servidor (que además tiene su propia caché).
const TTS_CACHE = new Map();
const TTS_CACHE_MAX = 150;

async function ttsUrl(text, tts) {
  const key = JSON.stringify([text, tts.voice, tts.speed, tts.lang]);
  if (TTS_CACHE.has(key)) {
    const url = TTS_CACHE.get(key);
    TTS_CACHE.delete(key);
    TTS_CACHE.set(key, url);
    return url;
  }
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-UI-Lang": S.lang },
    body: JSON.stringify({ text, ...tts }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.error || `HTTP ${res.status}`);
  }
  const url = URL.createObjectURL(await res.blob());
  TTS_CACHE.set(key, url);
  while (TTS_CACHE.size > TTS_CACHE_MAX) {
    const [oldKey, oldUrl] = TTS_CACHE.entries().next().value;
    TTS_CACHE.delete(oldKey);
    URL.revokeObjectURL(oldUrl);
  }
  return url;
}

// Las respuestas suenan siempre por el mismo <audio>, conectado a un
// analizador de Web Audio: de ahí el aro del modo voz saca el espectro de
// la voz del asistente. El AudioContext se crea en un gesto del usuario
// (clic o tecla en el chat) para que el navegador lo deje sonar.
const OUT = { el: null, ctx: null, analyser: null };

function chatAudioEl() {
  if (!OUT.el) OUT.el = new Audio();
  return OUT.el;
}

function ensureOutputAnalyser() {
  if (OUT.ctx) {
    if (OUT.ctx.state === "suspended") OUT.ctx.resume().catch(() => {});
    return;
  }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  try {
    const ctx = new Ctx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.75;
    analyser.minDecibels = -90;
    analyser.maxDecibels = -20;
    ctx.createMediaElementSource(chatAudioEl()).connect(analyser);
    analyser.connect(ctx.destination);
    Object.assign(OUT, { ctx, analyser });
  } catch { /* sin Web Audio: suena igual, el aro se anima solo */ }
}

// Qué "escucha" el aro de cada asistente en cada momento (ver orb.js): el
// que habla reacciona a su voz, el que piensa gira, y mientras te escuchan
// todos reaccionan a tu voz, cada uno con su color.
function orbSourceFor(key) {
  return () => {
    const { h: hue, s: sat } = assistantColor(participantCfg(key) || S.draft);
    if (CHAT.speaking && CHAT.speaker === key) {
      return { mode: "speaking", analyser: OUT.ctx?.state === "running" ? OUT.analyser : null, gate: 0.12, hue, sat };
    }
    if (CHAT.thinkingFor === key) return { mode: "thinking", hue, sat };
    if (CHAT.conv) {
      const st = CHAT.convState;
      if (st === "listening" || st === "hearing") return { mode: st, analyser: CHAT.conv.analyser, gate: 0.28, hue, sat };
      if (st === "transcribing" && key === HOST) return { mode: "thinking", hue, sat };
    }
    return { mode: "idle", hue, sat };
  };
}

function playUrl(url) {
  return new Promise((resolve) => {
    const a = chatAudioEl();
    const done = () => {
      if (CHAT.audioDone === done) {
        CHAT.audio = null;
        CHAT.audioDone = null;
        a.onended = a.onerror = null;
      }
      resolve();
    };
    CHAT.audio = a;
    CHAT.audioDone = done;
    a.onended = done;
    a.onerror = done;
    a.src = url;
    if (OUT.ctx?.state === "suspended") OUT.ctx.resume().catch(() => {});
    a.play().catch((e) => {
      if (e?.name === "NotAllowedError") audioBlocked();
      done();
    });
  });
}

function setSpeaking(on) {
  if (CHAT.speaking === on) return;
  CHAT.speaking = on;
  if (on && CHAT.conv) CHAT.convState = "speaking";
  else if (!on && CHAT.conv?.hf && !CHAT.busy) CHAT.convState = "listening";
  renderChatFoot();
  setSpeakingClass();
  updateOrbStates();
  hfReport();
}

// En modo texto el avatar de la cabecera "respira" mientras habla.
function setSpeakingClass() {
  $("#head-avatar")?.classList.toggle("speaking", CHAT.speaking);
}

async function speakText(text, lang, tts = null) {
  const gen = ++CHAT.speakGen;
  haltAudio();
  const chunks = splitSpeech(speakable(text, lang));
  if (!chunks.length) return;
  tts = tts || ttsParams(lang);
  setSpeaking(true);
  let next = ttsUrl(chunks[0], tts).catch((e) => { toast(e.message, "error"); return null; });
  for (let i = 0; i < chunks.length; i++) {
    const url = await next;
    // Mientras suena este trozo se genera el siguiente.
    if (i + 1 < chunks.length) next = ttsUrl(chunks[i + 1], tts).catch(() => null);
    if (gen !== CHAT.speakGen) return;
    if (url) await playUrl(url);
    if (gen !== CHAT.speakGen) return;
  }
  setSpeaking(false);
}

// Voz de una respuesta en streaming: cada frase que llega ("say") se
// sintetiza enseguida (en paralelo con lo que suena) y se reproduce en
// orden. stopSpeaking() (barge-in, la X, "reset") la corta y vacía: cambia
// CHAT.speakGen y lo pendiente se descarta. Si hay un anuncio sonando
// ("Buscando en internet…"), empieza cuando termina.
function speechStream() {
  const announce = CHAT.announce;
  if (!announce) {
    CHAT.speakGen++;
    haltAudio();
  }
  const gen = CHAT.speakGen;
  const st = { items: [], wake: null, closed: false };
  st.push = (text, lang, tts) => {
    const clean = speakable(text, lang);
    if (!clean || gen !== CHAT.speakGen) return;
    st.items.push(ttsUrl(clean, tts).catch((e) => { toast(e.message, "error"); return null; }));
    st.wake?.();
  };
  st.close = () => {
    st.closed = true;
    st.wake?.();
  };
  st.done = (async () => {
    if (announce) await announce;
    let speaking = false;
    for (;;) {
      if (gen !== CHAT.speakGen) return;
      if (!st.items.length) {
        if (st.closed) break;
        await new Promise((r) => { st.wake = r; });
        st.wake = null;
        continue;
      }
      const url = await st.items.shift();
      if (gen !== CHAT.speakGen) return;
      if (!speaking) {
        setSpeaking(true);
        speaking = true;
      }
      if (url) await playUrl(url);
    }
    if (speaking && gen === CHAT.speakGen) setSpeaking(false);
  })();
  return st;
}

function haltAudio() {
  if (CHAT.audio) CHAT.audio.pause();
  if (CHAT.audioDone) CHAT.audioDone();
}

function stopSpeaking() {
  CHAT.speakGen++;
  haltAudio();
  setSpeaking(false);
}

// Conversación por voz con el micrófono del NAVEGADOR (con cancelación de
// eco): mientras dura, la escucha manos libres del servidor queda en pausa
// (su micrófono se cierra) y vuelve al terminar. `auto`: la abrió una
// llamada por nombre; se cierra sola tras HF_AUTO_CLOSE_MS de silencio
// después de la última respuesta (empezada desde el aro, sigue hasta que
// la termines).
const HF_AUTO_CLOSE_MS = 8000;

function startServerConversation() {
  // Respaldo: el micrófono del servidor (sin un clic en la página el
  // navegador no deja analizar el micrófono ni sonar).
  hfEnsureConv();
  api("POST", "/api/voice/session", { client: HF.client, open: true, assistant: S.view?.kind === "assistant" ? S.view.name : null })
    .then(applyHfState).catch((e) => toast(e.message, "error"));
}

async function startConversation({ auto = false } = {}) {
  // El botón de silenciar de la barra superior solo apaga la escucha manos
  // libres (el micrófono de la PC); la conversación desde el aro usa el del
  // navegador y sigue funcionando.
  if (!CHAT.sttNoticeShown) {
    toast(t("conv.first_load"), "ok", 5000);
    CHAT.sttNoticeShown = true;
  }
  const browserMic = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  const activated = navigator.userActivation ? navigator.userActivation.hasBeenActive : true;
  const serverOk = HF.enabled && HF.status !== "error" && !HF.muted;
  if (serverOk && (!browserMic || !activated)) {
    if (!HF.controller) await hfClaim();
    if (!activated) audioBlocked();
    startServerConversation();
    return;
  }
  if (!browserMic) {
    toast(t("conv.unsupported"), "error");
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (e) {
    toast(t("conv.mic_denied", { error: e.message }), "error", 7000);
    if (serverOk) startServerConversation();
    return;
  }
  ensureOutputAnalyser();
  const ctx = new AudioContext();
  if (ctx.state === "suspended") await ctx.resume().catch(() => {});
  if (ctx.state !== "running" && serverOk) {
    stream.getTracks().forEach((tr) => tr.stop());
    ctx.close().catch(() => {});
    audioBlocked();
    startServerConversation();
    return;
  }
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  // Rango para el espectro del aro (no afecta la detección de voz, que usa la onda).
  analyser.minDecibels = -80;
  analyser.maxDecibels = -25;
  ctx.createMediaStreamSource(stream).connect(analyser);
  CHAT.conv = {
    active: true, stream, ctx, analyser, buf: new Float32Array(analyser.fftSize), cancel: null,
    autoClose: auto ? HF_AUTO_CLOSE_MS : 0, lastHeard: Date.now(),
  };
  if (HF.enabled) {
    if (!HF.controller) await hfClaim();
    api("POST", "/api/voice/pause", { client: HF.client, paused: true }).then(applyHfState).catch(() => {});
  }
  renderChatLog();
  renderChatFoot();
  updateOrbStates();
  convLoop(CHAT.conv);
}

function stopConversation() {
  const conv = CHAT.conv;
  if (!conv) return;
  conv.active = false;
  conv.cancel?.();
  if (conv.hf) {
    if (!HF.keepSession) api("POST", "/api/voice/session", { client: HF.client, open: false }).catch(() => {});
  } else {
    conv.stream.getTracks().forEach((tr) => tr.stop());
    conv.ctx.close().catch(() => {});
    // Fuera de la conversación por voz vuelve la escucha manos libres.
    if (HF.enabled) api("POST", "/api/voice/pause", { client: HF.client, paused: false }).then(applyHfState).catch(() => {});
  }
  CHAT.conv = null;
  CHAT.micMuted = false;
  CHAT.convState = "idle";
  CHAT.convNote = "";
  renderChatFoot();
  updateOrbStates();
  hfReport();
}

async function convLoop(conv) {
  while (conv.active) {
    // No se escucha mientras piensa o habla (p. ej. la frase con que lo
    // llamaste por su nombre, que llegó del servidor).
    // Mientras habla, si empiezas a hablar se calla y te escucha (barge-in).
    const barged = await waitTurn(conv);
    if (!conv.active) break;
    // Micrófono silenciado desde el botón: la conversación sigue abierta pero no escucha.
    if (CHAT.micMuted) {
      await new Promise((r) => setTimeout(r, 200));
      continue;
    }
    const blob = await captureUtterance(conv, { barge: barged });
    if (!conv.active) break;
    if (!blob) {
      // Quedó una frase a medias y no siguió hablando: se manda como está.
      if (CHAT.pending) {
        const text = CHAT.pending;
        CHAT.pending = "";
        setConvState("thinking");
        sendChat(text, CHAT.pendingLang || spokenLang(CHAT.lang)).catch((e) => console.error(e)); // como heard(), sin esperar
      } else if (conv.autoClose && !CHAT.busy && Date.now() - conv.lastHeard >= conv.autoClose) {
        // La abrió una llamada por nombre: se cierra sola tras el silencio.
        stopConversation();
        setConvState("idle", t("hf.closed", { names: wakeNames(participants()) || "" }));
        break;
      }
      continue;
    }
    setConvState("transcribing");
    let text = "";
    let lang = null;
    try {
      // hint: el idioma elegido / en que va la conversación; Whisper lo usa
      // para desempatar cuando duda (acento, frase corta) en vez de forzar
      // un idioma por defecto (eso le hacía traducir lo dicho).
      // "Todos los configurados": Whisper elige entre los idiomas del
      // asistente; "Solo X": entiende y responde solo en X.
      const langs = CHAT.lang === "auto" ? chatLangs() : [CHAT.lang];
      const query = `langs=${encodeURIComponent(langs.join(","))}&hint=${encodeURIComponent(spokenLang(CHAT.lang))}`;
      const res = await fetch(`/api/chat/transcribe?${query}`, {
        method: "POST",
        headers: { "Content-Type": blob.type || "audio/webm", "X-UI-Lang": S.lang },
        body: blob,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      text = data.text || "";
      // Whisper dudó del idioma: lo decide el modelo por lo que dijiste ("auto").
      lang = data.confident === false && CHAT.lang === "auto" && chatLangs().length > 1 ? "auto" : data.lang || null;
    } catch (e) {
      CHAT.messages.push({ role: "error", text: t("chat.error", { error: e.message }) });
      renderChatLog();
      continue;
    }
    if (!conv.active) break;
    if (!text) {
      setConvState("listening", CHAT.pending ? t("conv.go_on", { text: CHAT.pending }) : t("conv.not_understood"));
      continue;
    }
    // Solo cuenta como actividad lo que se entendió (no un ruido): si no,
    // la conversación abierta por nombre nunca se cerraba sola.
    conv.lastHeard = Date.now();
    // Si lo interrumpiste, el servidor mira si solo le pediste que se calle
    // (entonces no responde nada; ver config_ui._chat, "barge"). Vale para
    // todo este turno; el próximo lo vuelve a fijar.
    CHAT.bargeTurn = barged;
    // Sin esperar a que termine el turno: el bucle vuelve enseguida a
    // waitTurn, que es quien detecta que hablas mientras responde. Antes se
    // esperaba aquí la respuesta entera (incluida la voz) y el barge-in solo
    // se miraba cuando ya había terminado de hablar: nunca saltaba.
    // (sendChat marca CHAT.busy antes de su primer await, así que waitTurn
    // ya lo ve ocupado.)
    heard(text, lang).catch((e) => console.error(e));
  }
}

// ── Interrumpir hablando (barge-in) ───────────────────────────────────
// Mientras el asistente piensa o habla se espera el turno; pero si habla y
// tú empiezas a hablar, se calla y te escucha. Para no confundir su propia
// voz (que entra por el micrófono desde el altavoz) con la tuya, se mide al
// principio cuánto del altavoz llega al micrófono (eco) y solo cuenta como
// interrupción algo bastante más fuerte que eso. El navegador además resta
// el eco (echoCancellation) y, mientras suena el altavoz, también atenúa
// mucho lo que dices (medido en Chrome: tu voz llega a 0,01–0,1 en vez de
// 0,1–0,3). Por eso el umbral parte bajo (0,012) y basta con voz en ~6 de
// las últimas 16 mediciones (~0,2 s de ~0,5 s), aunque venga a ráfagas:
// antes se pedían 0,035 durante 0,25 s seguidos y no saltaba nunca.
// Devuelve true si se interrumpió.
const BARGE = { floor: 0.012, every: 30, window: 16, need: 6, calibrateMs: 700 };

async function waitTurn(conv) {
  let start = 0;
  let ratios = [];
  let echo = null;
  let recent = [];
  const outBuf = OUT.analyser ? new Float32Array(OUT.analyser.fftSize) : null;
  while (conv.active && (CHAT.busy || CHAT.speaking)) {
    await new Promise((r) => setTimeout(r, BARGE.every));
    if (!CHAT.speaking || CHAT.micMuted || !conv.analyser || conv.hf) {
      start = 0;
      ratios = [];
      echo = null;
      recent = [];
      continue;
    }
    const now = performance.now();
    if (!start) start = now;
    const mic = micLevel(conv);
    let out = 0;
    if (outBuf && OUT.ctx?.state === "running") {
      OUT.analyser.getFloatTimeDomainData(outBuf);
      let s = 0;
      for (const v of outBuf) s += v * v;
      out = Math.sqrt(s / outBuf.length);
    }
    if (now - start < BARGE.calibrateMs) {
      if (out > 0.01) ratios.push(mic / out);
      continue;
    }
    if (echo == null) {
      // La mediana alta (no el máximo): si ya hablabas al empezar a medir,
      // no queda un umbral imposible.
      ratios.sort((a, b) => a - b);
      echo = ratios.length ? ratios[Math.floor(ratios.length * 0.75)] : 0.3;
    }
    const threshold = Math.max(BARGE.floor, (conv.noise || 0.004) * 2.5, out * echo * 2.5);
    recent.push(mic > threshold);
    if (recent.length > BARGE.window) recent.shift();
    if (recent.filter(Boolean).length >= BARGE.need) {
      CHAT.roundStopped = true; // en una ronda de opiniones, no siguen los demás
      stopSpeaking();
      CHAT.chatAbort?.abort(); // si todavía estaba generando, el servidor para
      return true;
    }
  }
  return false;
}

// Una frase entendida en la conversación por voz (micrófono del navegador
// o del servidor): responde en el idioma en que se habló (si el asistente
// lo tiene) y, si quedó a medias, espera el resto.
async function heard(text, lang, force = null) {
  if (lang && chatLangs().includes(lang)) CHAT.lastLang = lang;
  const replyLang = lang === "auto" ? "auto" : lang && chatLangs().includes(lang) ? lang : spokenLang(CHAT.lang);
  if (CHAT.pending) {
    text = `${CHAT.pending} ${text}`;
    CHAT.pending = "";
  }
  // Pausa para pensar a mitad de la pregunta: se espera el resto.
  if (looksUnfinished(text)) {
    CHAT.pending = text;
    CHAT.pendingLang = replyLang;
    setConvState("listening", t("conv.go_on", { text }));
    return;
  }
  setConvState("thinking");
  // Lo adjuntado en modo voz y, en videollamada, lo que ve la cámara ahora.
  await sendChat(text, replyLang, force, voiceFiles());
}

function micLevel(conv) {
  conv.analyser.getFloatTimeDomainData(conv.buf);
  let sum = 0;
  for (const v of conv.buf) sum += v * v;
  return Math.sqrt(sum / conv.buf.length);
}

// Graba una frase: mide el ruido de fondo, empieza cuando el volumen supera
// el umbral y termina tras CHAT.pauseMs de silencio ("Pausa para pensar",
// 2 s por defecto; antes 0,9 s fijos cortaban la pregunta al pensar). VAD
// por energía, como stt_whisper.py. La grabación arranca antes de detectar
// voz para no cortar el principio de la frase.
function captureUtterance(conv, { barge = false } = {}) {
  return new Promise((resolve) => {
    setConvState(barge ? "hearing" : "listening", barge ? t("conv.barged") : CHAT.convNote);
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find((m) => MediaRecorder.isTypeSupported(m));
    const rec = new MediaRecorder(conv.stream, mime ? { mimeType: mime } : undefined);
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    rec.start();
    const startedAt = performance.now();
    // Sin voz durante este tiempo se reinicia la grabación (o, si la abrió
    // una llamada por nombre, se cierra la conversación: ver convLoop).
    const silenceLimit = CHAT.pending ? 6000
      : conv.autoClose ? Math.max(1500, conv.autoClose - (Date.now() - conv.lastHeard)) : 12000;
    let noise = 0;
    let samples = 0;
    let loud = 0;
    // Interrumpió hablando: ya está hablando (sin medir el ruido, que sería su voz).
    let speaking = barge;
    let speechAt = barge ? performance.now() : 0;
    let silentMs = 0;
    let finished = false;

    const finish = (keep) => {
      if (finished) return;
      finished = true;
      clearInterval(timer);
      conv.cancel = null;
      rec.onstop = () => resolve(keep && chunks.length ? new Blob(chunks, { type: rec.mimeType || "audio/webm" }) : null);
      if (rec.state !== "inactive") rec.stop();
      else rec.onstop();
    };
    conv.cancel = () => finish(false);

    const timer = setInterval(() => {
      if (!conv.active || CHAT.micMuted) return finish(false);
      const level = micLevel(conv);
      const now = performance.now();
      if (!barge && now - startedAt < 350) {
        noise += level;
        samples++;
        return;
      }
      const floor = barge ? (conv.noise || 0.01) : noise / Math.max(samples, 1);
      if (!barge) conv.noise = floor; // lo usa el barge-in (ver waitTurn)
      const threshold = Math.min(0.05, Math.max(0.012, floor * 2.5));
      if (!speaking) {
        loud = level > threshold ? loud + 1 : 0;
        if (loud >= 3) {
          speaking = true;
          speechAt = now;
          setConvState("hearing");
        } else if (CHAT.busy || CHAT.speaking || now - startedAt > silenceLimit) {
          finish(false); // sin voz: se reinicia la grabación para no acumular silencio
        }
      } else {
        silentMs = level > threshold * 0.8 ? 0 : silentMs + 50;
        if (silentMs >= CHAT.pauseMs || now - speechAt > 30000) finish(true);
      }
    }, 50);
  });
}

// ── Manos libres: el micrófono del servidor ────────────────────────────
// El servidor (voice_listener.py) escucha siempre, reconoce el nombre de
// cualquier asistente que se llame por voz (o su tecla de push to talk) y
// las órdenes de invitar/sacar asistentes, y avisa aquí. Esta página abre
// al asistente que llamaste (su aura) y conversa como siempre. Mientras
// piensa o habla, el servidor solo atiende frases que empiecen con un
// nombre (así no se toma su propia voz como una pregunta). Con varias
// pestañas abiertas responde una sola: la última que se usó.
const HF = {
  client: newClientId(),
  enabled: false,       // el servidor tiene la escucha manos libres
  muted: false,         // micrófono silenciado (también el del navegador)
  status: "off",        // idle | loading | listening | hearing | transcribing | muted | error | disabled
  error: "",
  controller: false,    // esta pestaña es la que responde
  after: null,          // último evento visto (null = todavía no se consultó)
  queued: null,         // llamada que llegó mientras respondía: se atiende al terminar
  endAfterTurn: false,  // la conversación se cerró mientras respondía
  keepSession: false,   // cambiando de página por una llamada: no cerrar la conversación del servidor
  reported: "",
};

function newClientId() {
  try {
    return crypto.randomUUID().replace(/-/g, "");
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
}

const hfUsable = () => HF.enabled && !HF.muted && HF.controller && HF.status !== "error";
const assistantByName = (name) => S.data?.assistants.find((a) => a.name === name);
// "@host" para el de la página; el nombre para los invitados.
const keyOf = (name) => (S.view?.kind === "assistant" && S.view.name === name ? HOST : name);

// Cómo se llama a los de esta lista por voz («Jarvis» / «Bella»).
function wakeNames(keys = null) {
  const list = keys ? keys.map(participantCfg).filter(Boolean) : S.data.assistants;
  return list.filter((a) => a.wake_word && a.name).map(displayName).map((n) => `«${n}»`).join(" / ");
}

let audioBlockedShown = false;
function audioBlocked() {
  if (audioBlockedShown) return;
  audioBlockedShown = true;
  toast(t("hf.audio_blocked"), "warn", 9000);
}

function applyHfState(st) {
  if (!st) return;
  const was = { ...HF };
  Object.assign(HF, {
    enabled: !!st.enabled,
    muted: st.enabled ? !!st.muted : HF.muted,
    status: st.status,
    error: st.error || "",
    controller: st.controller === HF.client,
  });
  renderMicButton();
  if ((HF.muted && !was.muted && CHAT.conv?.hf) || (was.controller && !HF.controller && CHAT.conv?.hf)) {
    HF.keepSession = !HF.muted; // otra pestaña tomó la conversación: no se la cierra
    stopConversation();
    HF.keepSession = false;
  }
  if (CHAT.conv?.hf && !CHAT.busy && !CHAT.speaking && ["listening", "hearing", "transcribing"].includes(HF.status)
      && CHAT.convState !== HF.status) {
    setConvState(HF.status, HF.status === "listening" ? CHAT.convNote : "");
    updateOrbStates();
  }
  if (was.enabled !== HF.enabled || was.muted !== HF.muted || was.controller !== HF.controller) {
    renderHfHint();
    if (CHAT.mode === "voice" && !CHAT.messages.length) renderChatLog();
    hfReport();
  }
}

function renderMicButton() {
  const b = $("#btn-mic");
  if (!b) return;
  let state;
  let title;
  if (HF.muted) [state, title] = ["muted", t("mic.title_muted")];
  else if (!HF.enabled) [state, title] = ["browser", t("mic.title_browser")];
  else if (HF.status === "error") [state, title] = ["error", t("mic.title_error", { error: HF.error })];
  else if (!HF.controller) [state, title] = ["other", t("mic.title_other")];
  else if (HF.status === "paused") [state, title] = ["paused", t("mic.title_paused")];
  else if (HF.status === "loading") [state, title] = ["loading", t("mic.title_on")];
  else [state, title] = [HF.status === "hearing" || HF.status === "transcribing" ? "hearing" : "on", t("mic.title_on")];
  b.dataset.state = state;
  b.title = title;
  b.setAttribute("aria-label", title);
  b.setAttribute("aria-pressed", String(HF.muted));
  $(".mic-icon", b).innerHTML = HF.muted ? ICON.micOff : ICON.micSmall;
  $(".top-label", b).textContent = t(`mic.${state}`);
}

function renderHfHint() {
  const el = $("#hf-hint");
  if (!el) return;
  const names = S.data ? wakeNames() : "";
  el.hidden = !(hfUsable() && names);
  el.textContent = names ? t("hf.gallery", { names }) : "";
}

async function setMuted(muted) {
  if (!HF.enabled) {
    // Sin escucha en el servidor (--no-voice): silencia el micrófono del navegador.
    HF.muted = muted;
    try { localStorage.setItem("mic-muted", muted ? "1" : "0"); } catch { /* sin almacenamiento local */ }
    renderMicButton();
    return;
  }
  try {
    applyHfState(await api("POST", "/api/voice/mute", { client: HF.client, muted }));
  } catch (e) {
    toast(e.message, "error");
  }
  toast(t(muted ? "mic.muted_toast" : "mic.on_toast"));
}

async function hfClaim() {
  if (!HF.enabled) return;
  try {
    applyHfState(await api("POST", "/api/voice/claim", { client: HF.client }));
  } catch { /* servidor caído: lo retoma el sondeo */ }
}

// Le cuenta al servidor qué hace la página: si piensa o habla (solo se le
// puede interrumpir llamándolo por su nombre), en qué idiomas va la
// conversación y la pausa para pensar elegida.
function hfReport() {
  if (!HF.enabled || !HF.controller) return;
  const busy = CHAT.speaking ? "speaking" : CHAT.busy ? "thinking" : null;
  const conv = !!(CHAT.conv?.hf && S.draft);
  const body = {
    client: HF.client,
    busy,
    langs: conv ? (CHAT.lang === "auto" ? chatLangs() : [CHAT.lang]) : [],
    hint: conv ? spokenLang(CHAT.lang) : null,
    pause_ms: CHAT.pauseMs,
  };
  const key = JSON.stringify(body);
  if (key === HF.reported) return;
  HF.reported = key;
  api("POST", "/api/voice/client", body).catch(() => { HF.reported = ""; });
}

async function hfLoop() {
  for (;;) {
    try {
      const first = HF.after === null;
      const r = await api("GET", `/api/voice/events?client=${HF.client}&after=${HF.after ?? 0}&wait=${first ? 0 : 20}`);
      applyHfState(r.state);
      if (!first) {
        for (const ev of r.events) {
          if (ev.controller === HF.client) hfEvent(ev);
        }
      }
      HF.after = r.last;
      if (!r.state.enabled) return; // sin escucha en el servidor: nada que sondear
    } catch {
      await new Promise((res) => setTimeout(res, 2000)); // servidor caído o reiniciándose
    }
  }
}

function hfEvent(ev) {
  if (!S.data) return;
  if (ev.type === "session_end") return hfSessionEnded(ev);
  if (!["wake", "utterance"].includes(ev.type)) return;
  if (CHAT.busy) {
    // Pensando o hablando: el servidor solo manda llamadas por nombre. Se
    // corta lo que estaba diciendo y se atiende al terminar el turno.
    if (ev.type === "utterance") return;
    HF.queued = ev;
    CHAT.roundStopped = true;
    stopSpeaking();
    return;
  }
  if (CHAT.speaking) stopSpeaking(); // "escuchar de nuevo" o un anuncio
  hfHandle(ev);
}

function hfAfterTurn() {
  const ev = HF.queued;
  HF.queued = null;
  if (ev) {
    HF.endAfterTurn = false; // la llamada nueva vuelve a abrir la conversación
    hfHandle(ev);
  } else if (HF.endAfterTurn) {
    HF.endAfterTurn = false;
    hfSessionEnded({ reason: "silence" });
  }
}

async function hfHandle(ev) {
  if (ev.type === "utterance") {
    if (!CHAT.conv?.hf || S.view?.kind !== "assistant" && S.view?.kind !== "new") return;
    return heard(ev.text, ev.lang);
  }
  // "wake": nombraste a un asistente (o apretaste su tecla)
  const name = ev.assistant;
  const a = assistantByName(name);
  if (!a) return;
  let target = name;
  const here = S.view?.kind === "assistant" && (S.view.name === name || CHAT.guests.includes(name));
  if (!here && !ev.ptt && conversationRecent()) {
    // No está en la conversación que tienes abierta: ¿le hablas a él, o es
    // un pedido para esta conversación ("invita a Jarvis")? Lo decide el
    // modelo. Si le hablas a él y usa el mismo modelo, se suma; si usa
    // otro, se abre su página.
    const route = await routeWith([...CHAT.history, { role: "user", content: ev.text }], [a]);
    if (!(route.keys || []).includes(name)) {
      target = S.view.name;
    } else if (sameModel(a)) {
      toggleGuest(name, true);
      hfNote(t("hf.joined", { name: displayName(a) }));
      target = S.view.name;
    }
  }
  if (!(await hfBringUp(target))) return;
  if (!ev.remainder) {
    setConvState("listening", t("hf.called", { name: displayName(a) }));
    return;
  }
  // Con su tecla, lo dicho va a él aunque no lo nombres.
  await heard(ev.text, ev.lang, ev.ptt ? [keyOf(name)] : null);
}

// Hay una conversación en curso en la página (o la hubo hace poco).
const conversationRecent = () => S.view?.kind === "assistant"
  && (!!CHAT.conv || (CHAT.lastActivity && Date.now() - CHAT.lastActivity < 120000));

// Muestra la conversación por voz en la que está `name` (si no está en la
// de la página, abre la suya) y empieza a escuchar. false si no se pudo
// (cambios sin guardar).
async function hfBringUp(name) {
  const a = assistantByName(name);
  if (!a) return false;
  const here = S.view?.kind === "assistant" && (S.view.name === name || CHAT.guests.includes(name));
  if (!here) {
    if (isDirty()) {
      toast(t("hf.dirty", { name: displayName(a) }), "warn", 7000);
      return false;
    }
    HF.keepSession = true;
    try {
      await select({ kind: "assistant", name }, { force: true, mode: "voice" });
    } finally {
      HF.keepSession = false;
    }
  } else if (CHAT.mode !== "voice") {
    CHAT.mode = "voice";
    renderChat();
  }
  if (!CHAT.conv) await startConversation({ auto: true });
  else hfEnsureConv();
  return !!CHAT.conv;
}

function hfEnsureConv() {
  if (!CHAT.conv) CHAT.conv = { hf: true, active: true, analyser: null, cancel: null };
  if (!CHAT.conv.hf) {
    renderChatFoot();
    return;
  }
  if (CHAT.mode === "voice" && !CHAT.busy && !CHAT.speaking) setConvState("listening");
  renderChatLog();
  renderChatFoot();
  updateOrbStates();
  hfReport();
}

function hfSessionEnded(ev) {
  if (!CHAT.conv?.hf) return;
  if (CHAT.busy) {
    HF.endAfterTurn = true; // que termine de responder primero
    return;
  }
  // Quedó una frase a medias y no siguió hablando: se manda como está.
  if (CHAT.pending) {
    const text = CHAT.pending;
    CHAT.pending = "";
    sendChat(text, CHAT.pendingLang || spokenLang(CHAT.lang));
    HF.endAfterTurn = true;
    return;
  }
  HF.keepSession = true; // ya está cerrada en el servidor
  stopConversation();
  HF.keepSession = false;
  if (ev.reason === "silence") setConvState("idle", t("hf.closed", { names: wakeNames(participants()) || "" }));
}

function hfNote(text) {
  CHAT.messages.push({ role: "event", text });
  renderChatLog();
  toast(text);
}

// El modelo usó invite_to_conversation / remove_from_conversation ("Jarvis,
// invita a Bella", "Bella, déjanos solos"…, en cualquier idioma): se arma
// la conversación cuando terminó de responder. El que entra saluda y el que
// sale se despide (si no se sacó él mismo: ya se despidió al responder).
async function applyGroupActions(lang, epoch) {
  const actions = CHAT.groupActions;
  CHAT.groupActions = [];
  for (const { action, name, by } of actions) {
    if (epoch !== CHAT.epoch) return;
    const a = assistantByName(name);
    if (!a || S.view?.kind !== "assistant") continue;
    if (action === "invite") {
      if (name === S.view.name || CHAT.guests.includes(name)) continue;
      if (!sameModel(a)) {
        hfNote(t("hf.other_model", { name: displayName(a), model: a.base_model }));
        continue;
      }
      toggleGuest(name, true);
      hfNote(t("hf.joined", { name: displayName(a) }));
      await askAssistant(name, lang, participants(), epoch, null, "join");
      continue;
    }
    const isHost = name === S.view.name;
    if (!isHost && !CHAT.guests.includes(name)) continue;
    if (by !== name) await askAssistant(keyOf(name), lang, participants(), epoch, null, "leave");
    if (epoch !== CHAT.epoch) return;
    if (!isHost) {
      toggleGuest(name, false);
      hfNote(t("hf.left", { name: displayName(a) }));
    } else if (CHAT.guests.length && !isDirty()) {
      // Sigue la conversación con el primer invitado como asistente de la página.
      const conv = CHAT.conv;
      CHAT.busy = false; // switchHost no cambia de asistente en medio de una respuesta
      await switchHost(CHAT.guests[0]);
      CHAT.busy = true;
      toggleGuest(name, false);
      if (conv?.hf) hfEnsureConv();
      hfNote(t("hf.left", { name: displayName(a) }));
    } else {
      hfNote(t("hf.left_end", { name: displayName(a) }));
      stopConversation();
    }
  }
}

function initHandsFree() {
  if (!S.data.voice_listener) {
    try { HF.muted = localStorage.getItem("mic-muted") === "1"; } catch { /* sin almacenamiento local */ }
  }
  $("#btn-mic").onclick = () => {
    if (HF.enabled && !HF.controller && !HF.muted) return hfClaim();
    return setMuted(!HF.muted);
  };
  // Cualquier clic habilita el audio de las respuestas (el navegador no deja
  // sonar nada en una página en la que todavía no se hizo ningún gesto).
  document.addEventListener("pointerdown", ensureOutputAnalyser, { once: true });
  // La pestaña que se está usando es la que responde.
  window.addEventListener("focus", hfClaim);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") hfClaim(); });
  renderMicButton();
  if (S.data.voice_listener && LOCAL_PAGE) {
    HF.enabled = true;
    hfClaim().then(hfLoop);
  }
  if (!LOCAL_PAGE) $("#btn-mic").hidden = true;
  // Otro dispositivo pudo seguir la conversación: al volver a la pestaña, lo último.
  // Al salir de la pestaña (o cerrar/recargar) se guarda lo pendiente.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") return persistChat(true);
    if (CHAT.owner && !CHAT.busy) restoreChat(CHAT.owner, { onlyIfNewer: true });
  });
}

const LOCAL_PAGE = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);

// ── Eventos (delegados en <main>) ──────────────────────────────────────
const ACTIONS = {
  save: () => (S.view.kind === "shared" ? saveShared() : saveAssistant()),
  discard,
  duplicate: duplicateAssistant,
  delete: deleteAssistant,
  "go-gallery": () => select({ kind: "gallery" }),
  "go-shared": () => {
    if (S.view?.kind === "assistant" || S.view?.kind === "new") {
      if (S.asstCat === "sec-voice") S.settingsCat = "voice";
      else if (S.asstCat === "sec-personality") S.settingsCat = "rules";
    }
    return select({ kind: "shared" });
  },
  "toggle-panel": () => setPanelOpen(!S.panelOpen),
  "close-panel": () => setPanelOpen(false),
  "refresh-models": async () => {
    await loadModels();
    renderModelList();
  },
  "measure-model": measureModel,
  "update-model": updateModel,
  "check-model-update": () => {
    S.updates = { ...(S.updates || {}), checking: true };
    renderUpdateBox();
    loadUpdates(true, S.draft.base_model);
  },
  pull: () => startPull($("#pull-input").value),
  "pull-current": () => {
    $("#pull-input").value = S.draft.base_model;
    startPull(S.draft.base_model);
  },
  "lang-es-en": () => setLanguages(["es", "en"]),
  "reset-behavior": resetBehavior,
  "exclude-all": () => excludeWords($$("[data-exclude]").map((b) => b.dataset.exclude)),
  "capture-key": startKeyCapture,
  "cancel-capture": cancelKeyCapture,
  "open-map": openMap,
  "save-pin": savePinDirect,
  "clear-pin": clearPinDirect,
};

function bindMain() {
  const main = $("#main");
  main.oninput = (e) => {
    if (e.target.dataset.field) onFieldInput(e.target);
    else if (e.target.id === "color-custom") setColor(e.target.value);
  };
  main.onchange = (e) => {
    const target = e.target;
    if (target.name === "model") {
      setPath(S.draft, "base_model", target.value);
      renderModelList();
      afterChange("base_model");
    } else if (target.dataset.lang) {
      toggleLang(target.dataset.lang, target.checked);
    } else if (target.id === "lang-all") {
      setLanguages(target.checked ? allLangCodes() : [S.draft.language]);
    } else if (target.id === "act-wake") {
      S.draft.wake_word = target.checked;
      renderActivation();
      afterChange("wake_word");
      scheduleWakeCheck(0);
    } else if (target.id === "act-ptt") {
      if (target.checked) {
        startKeyCapture();
      } else {
        cancelKeyCapture();
        S.draft.push_to_talk_key = "";
        renderActivation();
        afterChange("push_to_talk_key");
      }
    } else if (target.id === "f-shared") {
      S.draft.shared = target.checked;
      afterChange("shared");
    } else if (target.id === "color-custom") {
      setColor(target.value);
      renderColorPicker();
    } else if (target.dataset.num && target.value === "") {
      target.value = getPath(S.draft, target.dataset.field); // se vació el número: vuelve al último valor válido
    }
  };
  main.onclick = (e) => {
    const target = e.target;
    const swatch = target.closest("[data-color]");
    if (swatch) return setColor(swatch.dataset.color);
    const cfgBtn = target.closest("[data-cfg-cat]");
    if (cfgBtn) return selectSettingsCat(cfgBtn.dataset.cfgCat);
    const jump = target.closest("[data-jump]");
    if (jump) return selectAssistantCat(jump.dataset.jump);
    const play = target.closest("[data-play]");
    if (play) return playPreview(play.dataset.play);
    const card = target.closest("[data-voice]");
    if (card) return selectVoice(card.dataset.voice);
    const act = target.closest("[data-act]");
    if (act) return ACTIONS[act.dataset.act]?.();
    const ex = target.closest("[data-exclude]");
    if (ex) return excludeWords([ex.dataset.exclude]);
    const unex = target.closest("[data-unexclude]");
    if (unex) {
      S.draft.add_exclusions = S.draft.add_exclusions.filter((w) => w !== unex.dataset.unexclude);
      afterChange("add_exclusions");
      return scheduleWakeCheck(0);
    }
    const rmAlias = target.closest("[data-rm-alias]");
    if (rmAlias) {
      S.draft.aliases.splice(Number(rmAlias.dataset.rmAlias), 1);
      return afterAliasChange();
    }
    const rmExcl = target.closest("[data-rm-excl]");
    if (rmExcl) {
      S.draft.exclusions.splice(Number(rmExcl.dataset.rmExcl), 1);
      renderExclusionChips();
      return afterChange("exclusions");
    }
    const chipBox = target.closest(".chips-input");
    if (chipBox && target === chipBox) $("input", chipBox).focus();
  };
  main.onkeydown = (e) => {
    const card = e.target.closest?.("[data-voice]");
    if (card && e.target === card && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      selectVoice(card.dataset.voice);
    }
  };
}

// ── Consola (lo que el servidor va haciendo por debajo) ────────────────
const CONSOLE = { open: false, lastId: 0, timer: null, lines: [], max: 1500 };

function logRow(line) {
  const m = /^\[([^\]]+)\]\s?(.*)$/s.exec(line.text);
  const time = new Date(line.t * 1000).toLocaleTimeString(S.lang === "es" ? "es" : "en", { hour12: false });
  const text = m ? `<span class="cat">[${esc(m[1])}]</span> ${esc(m[2])}` : esc(line.text);
  return `<div class="log-line lvl-${line.level}"><time>${time}</time><span class="log-text">${text}</span></div>`;
}

function consoleVisible(line) {
  const level = $("#console-level").value;
  const filter = $("#console-filter").value.trim().toLowerCase();
  if (level === "warn" && line.level === "info") return false;
  return !filter || line.text.toLowerCase().includes(filter);
}

function renderConsole() {
  const body = $("#console-body");
  const shown = CONSOLE.lines.filter(consoleVisible);
  body.innerHTML = shown.length ? shown.map(logRow).join("") : `<p class="console-empty">${esc(t("console.empty"))}</p>`;
  if ($("#console-follow").checked) body.scrollTop = body.scrollHeight;
}

async function pollConsole() {
  clearTimeout(CONSOLE.timer);
  if (!CONSOLE.open) return;
  try {
    const r = await api("GET", `/api/logs?after=${CONSOLE.lastId}`);
    if (r.last < CONSOLE.lastId) CONSOLE.lastId = 0; // el servidor se reinició
    if (r.lines.length) {
      CONSOLE.lastId = r.lines[r.lines.length - 1].id;
      CONSOLE.lines.push(...r.lines);
      if (CONSOLE.lines.length > CONSOLE.max) CONSOLE.lines.splice(0, CONSOLE.lines.length - CONSOLE.max);
      const body = $("#console-body");
      const fresh = r.lines.filter(consoleVisible);
      if (fresh.length) {
        $(".console-empty", body)?.remove();
        body.insertAdjacentHTML("beforeend", fresh.map(logRow).join(""));
        while (body.children.length > CONSOLE.max) body.firstElementChild.remove();
        if ($("#console-follow").checked) body.scrollTop = body.scrollHeight;
      }
    }
  } catch { /* servidor caído: se reintenta */ }
  CONSOLE.timer = setTimeout(pollConsole, 1000);
}

function setConsoleOpen(open) {
  CONSOLE.open = open;
  $("#console").hidden = !open;
  document.body.classList.toggle("console-open", open);
  $("#btn-console").classList.toggle("active", open);
  try { localStorage.setItem("console-open", open ? "1" : "0"); } catch { /* sin almacenamiento local */ }
  if (open) {
    renderConsole();
    pollConsole();
  } else {
    clearTimeout(CONSOLE.timer);
  }
}

function initConsole() {
  $("#btn-console").onclick = () => setConsoleOpen(!CONSOLE.open);
  $("#console-close").onclick = () => setConsoleOpen(false);
  $("#console-clear").onclick = () => {
    CONSOLE.lines = [];
    renderConsole();
  };
  $("#console-filter").oninput = renderConsole;
  $("#console-level").onchange = renderConsole;
  $("#console-follow").onchange = renderConsole;
  // Arrastrar el borde superior cambia la altura del panel.
  $("#console-resize").onmousedown = (e) => {
    e.preventDefault();
    const move = (ev) => {
      const h = Math.min(window.innerHeight * 0.85, Math.max(120, window.innerHeight - ev.clientY));
      document.documentElement.style.setProperty("--console-h", `${h}px`);
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };
  let wasOpen = false;
  try { wasOpen = localStorage.getItem("console-open") === "1"; } catch { /* sin almacenamiento local */ }
  if (wasOpen && isAdmin()) setConsoleOpen(true);
}

// ── Perfiles (ver profiles.py) ─────────────────────────────────────────
// Cada persona entra con su perfil: admin (todo), normal (sus asistentes y
// sus datos) o invitado (los asistentes compartidos; sus datos y
// conversaciones solo en este navegador, sessionStorage: se pierden al
// salir o cerrar la pestaña).
const ME = () => S.data?.me || null;
const isAdmin = () => ME()?.role === "admin";
const isGuest = () => !!ME()?.guest;
const settingsKey = () => (isAdmin() ? "nav.shared" : "settings.title");
const GUEST_KEY = "auravox-guest";
const EMPTY_UC = { nombre: "", pais: "", ubicacion: "", latitud: null, longitud: null };

function guestGet(key, fallback) {
  try {
    const v = sessionStorage.getItem(`${GUEST_KEY}:${key}`);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

function guestSet(key, value) {
  try {
    sessionStorage.setItem(`${GUEST_KEY}:${key}`, JSON.stringify(value));
    return true;
  } catch {
    return false; // sin espacio (imágenes) o sin almacenamiento
  }
}

function guestClear() {
  try {
    Object.keys(sessionStorage).filter((k) => k.startsWith(GUEST_KEY)).forEach((k) => sessionStorage.removeItem(k));
  } catch { /* sin almacenamiento */ }
}

// sessionStorage tiene unos 5 MB: si no entra, sin las miniaturas y, si
// aún no entra, solo lo último.
function guestSaveChat(name, data) {
  const saved = { ...data, updated_at: Date.now() / 1000 };
  if (guestSet(`chat:${name}`, saved)) return;
  const light = {
    ...saved,
    messages: saved.messages.map((m) => (m.files ? { ...m, files: m.files.map((f) => ({ ...f, thumb: null })) } : m)),
    history: saved.history.map((m) => (m.images ? { ...m, images: undefined } : m)),
  };
  if (guestSet(`chat:${name}`, light)) return;
  guestSet(`chat:${name}`, { ...light, messages: light.messages.slice(-20), history: light.history.slice(-20) });
}

const num = (v) => (v === "" || v == null || !Number.isFinite(Number(v)) ? null : Number(v));

// Todo lo que llega de /api/state pasa por aquí: el invitado completa sus
// datos con los de su navegador.
function setData(st) {
  S.data = st;
  if (st?.me?.guest) {
    const uc = guestGet("user_context", {});
    S.data.user_context = { ...EMPTY_UC, ...uc, latitud: num(uc.latitud), longitud: num(uc.longitud) };
  }
  applyRole();
}

function applyRole() {
  document.body.dataset.role = ME()?.role || "";
  const admin = isAdmin();
  $("#btn-console").hidden = !admin;
  $("[data-top=console]").hidden = !admin;
  if (!admin && CONSOLE.open) setConsoleOpen(false);
  $$("#btn-shared .top-label, [data-top=shared] span").forEach((el) => {
    el.dataset.i18n = settingsKey();
    el.textContent = t(settingsKey());
  });
  renderProfileButton();
}

const profileAvatar = (p, cls = "") =>
  `<span class="avatar orb-avatar ${cls}" style="${colorStyle({ name: p.name || "?", color: p.color })}" aria-hidden="true">${esc((p.name || "?")[0].toUpperCase())}</span>`;

function renderProfileButton() {
  const box = $("#profile-menu");
  if (!box) return;
  const me = ME();
  box.hidden = !me;
  if (!me) return;
  const name = me.guest ? t("prof.guest") : me.name;
  box.innerHTML = `
    <summary class="top-btn profile-btn" aria-label="${esc(name)}">${me.guest ? `<span class="avatar orb-avatar pf-guest" aria-hidden="true">?</span>` : profileAvatar(me)}
      <span class="top-label">${esc(name)}</span></summary>
    <div class="menu-pop">
      <div class="menu-note"><strong>${esc(name)}</strong><small>${esc(t("prof.role_is", { role: t(`prof.role_${me.role}`) }))}</small></div>
      <button class="menu-item" type="button" data-pf-menu="data">${esc(t("prof.my_data"))}</button>
      <button class="menu-item" type="button" data-pf-menu="logout">${esc(t(me.guest ? "prof.leave_guest" : "prof.switch"))}</button>
    </div>`;
  box.onclick = (e) => {
    const b = e.target.closest("[data-pf-menu]");
    if (!b) return;
    box.open = false;
    if (b.dataset.pfMenu === "data") select({ kind: "shared" });
    else logout();
  };
}

async function logout() {
  if (isGuest() && !(await confirmDialog(t("prof.guest_leave_title"), t("prof.guest_leave_text"), t("prof.guest_leave_ok")))) return;
  if (!(await guardDirty())) return;
  if (CHAT.conv) stopConversation();
  persistChat(true);
  try {
    await api("DELETE", "/api/session", {});
  } catch { /* igual se vuelve a elegir perfil */ }
  guestClear();
  history.replaceState(null, "", location.pathname);
  location.reload();
}

const guestBanner = () => (isGuest() ? `<div class="callout info guest-banner"><div>${esc(t("prof.guest_banner"))}</div></div>` : "");

function readOnlyNote() {
  if (isGuest()) return t("ro.guest");
  const a = S.draft;
  const owner = a.owner_name ? t("ro.owner_of", { name: a.owner_name }) : t("ro.owner_admin");
  return t("ro.note", { owner });
}

// Pantalla de entrada: elegir perfil (con su PIN si tiene) o entrar como
// invitado. La primera vez, crear el administrador.
function renderLogin(who) {
  S.login = who;
  document.body.classList.add("locked");
  const main = $("#main");
  main.dataset.view = "login";
  main.oninput = main.onchange = main.onkeydown = null;
  if (who.setup) {
    main.innerHTML = `
    <div class="login">
      <header class="login-head"><img src="/static/icon.svg" width="64" height="64" alt="">
        <h1>${esc(t("prof.setup_title"))}</h1><p>${esc(t("prof.setup_sub"))}</p></header>
      <form class="card login-form" id="setup-form" autocomplete="off">
        <div class="field"><label for="su-name">${esc(t("prof.setup_name"))}</label>
          <input type="text" id="su-name" maxlength="40" required autocomplete="name"></div>
        <div class="grid-2">
          <div class="field"><label for="su-pin">${esc(t("prof.setup_pin"))}</label>
            <input type="password" id="su-pin" autocomplete="new-password"></div>
          <div class="field"><label for="su-pin2">${esc(t("prof.setup_pin2"))}</label>
            <input type="password" id="su-pin2" autocomplete="new-password"></div>
        </div>
        <div class="err" id="su-err"></div>
        <button class="btn btn-primary" type="submit">${esc(t("prof.setup_go"))}</button>
        <small class="note">${esc(t("prof.setup_note"))}</small>
      </form>
    </div>`;
    $("#su-name").focus();
    $("#setup-form").onsubmit = async (e) => {
      e.preventDefault();
      const name = $("#su-name").value.trim();
      const pin = $("#su-pin").value;
      const err = $("#su-err");
      if (!name) return void (err.textContent = t("prof.name_required"));
      if (!/^\S{4,64}$/.test(pin)) return void (err.textContent = t("prof.pin_short"));
      if (pin !== $("#su-pin2").value) return void (err.textContent = t("prof.pin_mismatch"));
      try {
        await api("POST", "/api/profiles/setup", { name, pin });
        location.reload();
      } catch (ex) {
        err.textContent = ex.message;
      }
    };
    return;
  }
  const card = (p) => `<button class="l-card" type="button" data-login="${esc(p.id)}">
      ${profileAvatar(p, "l-orb")}
      <strong>${esc(p.name)}</strong>
      <span class="l-meta"><span class="badge ${p.role === "admin" ? "use" : ""}">${esc(t(`prof.role_${p.role}`))}</span>
        ${p.has_pin ? `<span class="l-lock" title="${esc(t("prof.locked"))}">${ICON.lock}</span>` : ""}</span>
    </button>`;
  main.innerHTML = `
  <div class="login">
    <header class="login-head"><img src="/static/icon.svg" width="64" height="64" alt="">
      <h1>${esc(t("prof.pick_title"))}</h1><p>${esc(t("prof.pick_sub"))}</p></header>
    <div class="login-grid" id="login-grid">
      ${who.profiles.map(card).join("")}
      <button class="l-card l-guest" type="button" data-guest>
        <span class="avatar orb-avatar l-orb pf-guest" aria-hidden="true">?</span>
        <strong>${esc(t("prof.guest"))}</strong>
        <small>${esc(t("prof.guest_sub"))}</small>
      </button>
    </div>
    <form class="card login-form login-pin" id="login-pin" hidden autocomplete="off">
      <div class="login-who" id="login-who"></div>
      <div class="field"><label for="login-pin-input">${esc(t("prof.pin"))}</label>
        <input type="password" id="login-pin-input" placeholder="${esc(t("prof.pin_ph"))}" autocomplete="current-password"></div>
      <div class="err" id="login-err"></div>
      <div class="login-actions">
        <button class="btn" type="button" data-back>${esc(t("prof.back"))}</button>
        <button class="btn btn-primary" type="submit">${esc(t("prof.pin_enter"))}</button>
      </div>
    </form>
  </div>`;
  let chosen = null;
  const enter = async (id, pin = "") => {
    try {
      await api("POST", "/api/session", { profile: id, pin });
      location.reload();
    } catch (ex) {
      if (!$("#login-pin").hidden) {
        $("#login-err").textContent = ex.message;
        $("#login-pin-input").select();
      } else {
        toast(ex.message, "error");
      }
    }
  };
  main.onclick = async (e) => {
    if (e.target.closest("[data-guest]")) {
      try {
        guestClear(); // un invitado empieza siempre de cero
        await api("POST", "/api/session/guest", {});
        location.reload();
      } catch (ex) {
        toast(ex.message, "error");
      }
      return;
    }
    if (e.target.closest("[data-back]")) {
      $("#login-pin").hidden = true;
      $("#login-grid").hidden = false;
      return;
    }
    const b = e.target.closest("[data-login]");
    if (!b) return;
    chosen = who.profiles.find((p) => p.id === b.dataset.login);
    if (!chosen.has_pin) return enter(chosen.id);
    $("#login-who").innerHTML = `${profileAvatar(chosen, "l-orb")}<strong>${esc(chosen.name)}</strong>`;
    $("#login-err").textContent = "";
    $("#login-grid").hidden = true;
    $("#login-pin").hidden = false;
    $("#login-pin-input").value = "";
    $("#login-pin-input").focus();
  };
  $("#login-pin").onsubmit = (e) => {
    e.preventDefault();
    if (chosen) enter(chosen.id, $("#login-pin-input").value);
  };
}

// Ajustes → Tu perfil: nombre y rol propios.
function myProfileCard() {
  const d = S.draft.me;
  const me = ME();
  return `<section class="card" id="me-card">
    <div class="card-head">
      <div><h2>${esc(t("prof.mine_title"))}</h2><p>${esc(t("prof.mine_sub"))}</p></div>
      <div class="me-head-acts">
        <span class="badge ${me.role === "admin" ? "use" : ""}">${esc(t(`prof.role_${me.role}`))}</span>
        <button type="button" class="btn btn-sm" data-cfg-cat="security">${svgIcon("shield", 15)} ${esc(t("sec_card.jump"))}</button>
      </div>
    </div>
    <div class="grid-2">
      ${textField({ field: "me.name", label: esc(t("prof.name")), value: d.name, attrs: 'maxlength="40"' })}
    </div>
  </section>`;
}

// Ajustes → Contraseña y seguridad: cambiar PIN/contraseña sin pedir la anterior, pero con confirmación.
function mySecurityCard() {
  const me = ME();
  const pinField = (field, label, ph, help = "") => `<div class="field" data-wrap="${field}">
      <label for="f-${field}">${esc(label)}</label>
      <input type="password" id="f-${field}" class="text-input" data-field="${field}" value="${esc(getPath(S.draft, field) || "")}" placeholder="${esc(ph)}" autocomplete="new-password">
      ${help ? `<small>${esc(help)}</small>` : ""}
      <div class="err" data-err="${field}"></div>
    </div>`;
  return `<section class="card" id="security-card">
    <div class="card-head">
      <div><h2>${esc(t("sec_card.title"))}</h2><p>${esc(t("sec_card.sub"))}</p></div>
      <span class="badge ${me.has_pin ? "good" : ""}">${ICON.lock} ${esc(t(me.has_pin ? "sec_card.has_pin" : "sec_card.no_pin"))}</span>
    </div>
    <div class="grid-2">
      ${pinField("me.pin", t("sec_card.new_pin"), t("sec_card.pin_ph"), t("prof.pin_format"))}
      ${pinField("me.pin_confirm", t("sec_card.confirm_pin"), t("sec_card.confirm_ph"))}
    </div>
    <div class="sec-card-acts">
      <button type="button" class="btn btn-primary" data-act="save-pin">${svgIcon("shield", 16)} ${esc(t("sec_card.save_btn"))}</button>
      ${me.has_pin && me.role !== "admin" ? `<button type="button" class="btn btn-ghost-danger" data-act="clear-pin">${esc(t("sec_card.clear_btn"))}</button>` : ""}
    </div>
  </section>`;
}

// Ajustes → Perfiles (administrador): crear, cambiar rol/nombre/PIN, borrar.
function renderProfilesCard() {
  const box = $("#profiles-card");
  if (!box) return;
  const roleSelect = (attr, current) => `<select class="text-input" ${attr}>${["admin", "user"].map((r) =>
    `<option value="${r}" ${r === current ? "selected" : ""}>${esc(t(`prof.role_${r}`))}</option>`).join("")}</select>`;
  const rows = (S.data.profiles || []).map((p) => `<div class="pf-row" data-pf="${esc(p.id)}">
      ${profileAvatar(p)}
      <input class="text-input" data-pf-name value="${esc(p.name)}" maxlength="40" aria-label="${esc(t("prof.name"))}">
      ${roleSelect(`data-pf-role aria-label="${esc(t("prof.role_is", { role: "" }))}"`, p.role)}
      <input class="text-input" type="password" data-pf-pin placeholder="${esc(t("prof.new_pin_ph"))}" autocomplete="new-password" aria-label="${esc(t("prof.new_pin"))}">
      <div class="pf-acts">
        ${p.has_pin && p.role !== "admin" ? `<button class="btn btn-sm" type="button" data-pf-act="clear-pin">${esc(t("prof.clear_pin"))}</button>` : ""}
        <button class="btn btn-sm" type="button" data-pf-act="save">${esc(t("prof.save"))}</button>
        ${p.id === ME().id ? `<span class="badge">${esc(t("prof.you"))}</span>`
          : `<button class="btn btn-sm btn-ghost-danger" type="button" data-pf-act="delete">${esc(t("prof.delete"))}</button>`}
      </div>
    </div>`).join("");
  box.innerHTML = `
    <div class="card-head"><div><h2>${esc(t("prof.card_title"))}</h2><p>${esc(t("prof.card_sub"))}</p></div></div>
    <div class="pf-list">${rows}</div>
    <div class="pf-row pf-add">
      <span class="avatar orb-avatar pf-guest" aria-hidden="true">+</span>
      <input class="text-input" data-pf-new-name maxlength="40" placeholder="${esc(t("prof.add_name_ph"))}" aria-label="${esc(t("prof.add_name_ph"))}">
      ${roleSelect("data-pf-new-role", "user")}
      <input class="text-input" type="password" data-pf-new-pin placeholder="${esc(t("prof.new_pin_ph"))}" autocomplete="new-password" aria-label="${esc(t("prof.new_pin"))}">
      <div class="pf-acts"><button class="btn btn-sm btn-primary" type="button" data-pf-act="add">${esc(t("prof.add"))}</button></div>
    </div>
    <dl class="pf-roles">
      <dt>${esc(t("prof.role_admin"))}</dt><dd>${esc(t("prof.role_admin_help"))}</dd>
      <dt>${esc(t("prof.role_user"))}</dt><dd>${esc(t("prof.role_user_help"))}</dd>
      <dt>${esc(t("prof.role_guest"))}</dt><dd>${esc(t("prof.guest_sub"))}</dd>
    </dl>`;
  box.onclick = onProfilesClick;
}

async function onProfilesClick(e) {
  const b = e.target.closest("[data-pf-act]");
  if (!b) return;
  const act = b.dataset.pfAct;
  b.disabled = true;
  try {
    if (act === "add") {
      const name = $("[data-pf-new-name]").value.trim();
      if (!name) {
        toast(t("prof.name_required"), "warn");
        return;
      }
      const role = $("[data-pf-new-role]").value;
      setData((await api("POST", "/api/profiles", { name, role, pin: $("[data-pf-new-pin]").value })).state);
      toast(t("prof.added", { name }));
    } else {
      const row = b.closest("[data-pf]");
      const p = S.data.profiles.find((x) => x.id === row.dataset.pf);
      if (act === "save") {
        setData((await api("PUT", `/api/profiles/${p.id}`, {
          name: $("[data-pf-name]", row).value, role: $("[data-pf-role]", row).value, pin: $("[data-pf-pin]", row).value,
        })).state);
        toast(t("prof.saved"));
      } else if (act === "clear-pin") {
        setData((await api("PUT", `/api/profiles/${p.id}`, { name: p.name, role: p.role, clear_pin: true })).state);
        toast(t("prof.saved"));
      } else if (act === "delete") {
        if (!(await confirmDialog(t("prof.del_title", { name: p.name }), t("prof.del_text"), t("prof.delete")))) return;
        setData((await api("DELETE", `/api/profiles/${p.id}`, {})).state);
        toast(t("prof.del_done"));
      }
    }
    if (!isAdmin()) return void select({ kind: "gallery" }, { force: true }); // se quitó a sí mismo el rol
    renderProfilesCard();
  } catch (ex) {
    toast(ex.message, "error", 6000);
  } finally {
    if (b.isConnected) b.disabled = false;
  }
}

// ── Arranque ───────────────────────────────────────────────────────────
async function boot() {
  if (new URLSearchParams(location.search).has("key")) history.replaceState(null, "", location.pathname + location.hash);
  applyStaticI18n();
  $$("[data-ui-lang]").forEach((b) => { b.onclick = () => setUiLang(b.dataset.uiLang); });
  let who;
  try {
    who = await api("GET", "/api/profiles");
  } catch (e) {
    $("#main").innerHTML = `<div class="editor"><div class="callout warn"><div><b>${esc(t("load.failed"))}</b> ${esc(e.message)}</div></div></div>`;
    return;
  }
  if (who.api_version === API_VERSION && !who.me) {
    devPoll();
    renderLogin(who);
    return;
  }
  document.body.classList.remove("locked");
  try {
    await Promise.all([loadState(), loadModels()]);
  } catch (e) {
    $("#main").innerHTML = `<div class="editor"><div class="callout warn"><div><b>${esc(t("load.failed"))}</b> ${esc(e.message)}</div></div></div>`;
    return;
  }
  devPoll(); // recarga en caliente (también si esta página quedó vieja)
  if (S.data.api_version !== API_VERSION) {
    $("#main").innerHTML = `<div class="editor"><div class="callout warn"><div><b>${esc(t("api.mismatch_title"))}</b></div><div>${esc(t("api.mismatch"))}</div></div></div>`;
    return;
  }
  initConsole();
  initMapDialog();
  initHandsFree();
  initFeatures(); // avisos de recordatorios, etc. (ver features.js)
  $("#btn-home").onclick = () => select({ kind: "gallery" });
  $("#btn-shared").onclick = () => select({ kind: "shared" });
  // Menú de la barra superior (celular): las mismas acciones que sus botones.
  $$("[data-top]").forEach((b) => {
    b.onclick = () => $(`#btn-${b.dataset.top}`)?.click();
  });
  $("[data-top=mic]").hidden = !LOCAL_PAGE;
  window.addEventListener("popstate", onPopState);
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && (e.code === "Backquote" || e.key === "`") && !S.capturing && isAdmin()) {
      e.preventDefault();
      setConsoleOpen(!CONSOLE.open);
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if ($("#savebar") && !$("#savebar").hidden) ACTIONS.save();
    } else if (e.key === "Escape" && S.panelOpen && $("#workspace") && window.matchMedia(NARROW).matches
      && !S.capturing && !$("#dialog").open && !$("#map-dialog").open) {
      setPanelOpen(false); // en pantallas angostas el panel tapa el chat
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (isDirty()) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  await select(viewFromHash(), { force: true, push: false });
  pollPull();
}

boot();
