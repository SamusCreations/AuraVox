"use strict";
// Aro con aura del modo "Conversación por voz": un anillo luminoso que se
// deforma con el espectro del audio (el micrófono mientras escucha, la voz
// del asistente mientras habla) y un halo difuminado que crece con el
// volumen. Sin audio (pensando, en reposo) se mueve solo, despacio.
//
//   const orb = new VoiceOrb(elemento, () => ({ mode, analyser, gate, hue, sat }));
//
// `mode`: idle | listening | hearing | thinking | speaking (elige colores y
// ritmo). `analyser`: AnalyserNode de Web Audio o null. `gate`: piso de
// ruido (0–1) que se descarta del espectro. `hue`/`sat`: el color del
// asistente (0–360 / 0–100); los colores del aro salen de ahí. El bucle se
// detiene solo cuando el elemento sale del documento.

const ORB_MODES = new Set(["idle", "listening", "hearing", "thinking", "speaking"]);

function hslRgb(h, s, l) {
  h = ((h % 360) + 360) % 360;
  s = Math.max(0, Math.min(1, s));
  const a = s * Math.min(l, 1 - l);
  const f = (n) => {
    const k = (n + h / 30) % 12;
    return 255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)));
  };
  return [f(0), f(8), f(4)];
}

// Cuatro colores alrededor del tono del asistente. Hablando: vivos y con
// tonos vecinos; escuchándote: el mismo tono, pastel (casi blanco), para
// que se note quién está hablando.
function orbPalette(mode, hue, sat) {
  const S = (sat ?? 85) / 100;
  const spec = {
    speaking: [[-24, 1, 0.62], [0, 1, 0.6], [24, 1, 0.62], [48, 0.95, 0.66]],
    listening: [[0, 0.55, 0.78], [18, 0.45, 0.84], [-18, 0.5, 0.8], [0, 0.3, 0.9]],
    hearing: [[0, 0.6, 0.76], [20, 0.5, 0.82], [-20, 0.55, 0.78], [0, 0.35, 0.88]],
    thinking: [[0, 1, 0.66], [22, 0.9, 0.62], [-22, 0.9, 0.7], [44, 0.8, 0.66]],
    idle: [[0, 0.9, 0.6], [30, 0.85, 0.58], [-30, 0.85, 0.62], [60, 0.8, 0.6]],
  }[mode];
  return spec.map(([dh, ks, l]) => hslRgb(hue + dh, S * ks, l));
}

class VoiceOrb {
  constructor(host, source) {
    this.host = host;
    this.source = source;
    host.insertAdjacentHTML("afterbegin",
      '<span class="orb-aura a1" aria-hidden="true"></span><span class="orb-aura a2" aria-hidden="true"></span>' +
      '<canvas class="orb-canvas" aria-hidden="true"></canvas>');
    this.canvas = host.querySelector(".orb-canvas");
    this.ctx = this.canvas.getContext("2d");
    this.N = 128; // puntos del anillo (la mitad se espeja)
    this.half = this.N / 2;
    this.bins = new Float32Array(this.half);
    this.target = new Float32Array(this.half);
    this.level = 0;
    this.rot = 0;
    const first = source() || {};
    this.colors = orbPalette("idle", first.hue ?? 262, first.sat);
    this.cssColors = "";
    this.freq = null;
    this.last = performance.now();
    this.reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    this.frame = this.frame.bind(this);
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(host);
    this.resize();
    this.raf = requestAnimationFrame(this.frame);
  }

  // El lienzo es más grande que el aro (ver .orb-canvas en style.css): así
  // el brillo y las ondas tienen lugar y no se corta en un cuadrado, que se
  // notaba sobre todo en los aros chicos de los invitados.
  resize() {
    const r = this.canvas.getBoundingClientRect();
    // Aros muy grandes: se limita la resolución del lienzo (el brillo es
    // borroso igual) para no dibujar millones de píxeles por cuadro.
    this.dpr = Math.min(2, window.devicePixelRatio || 1, 1800 / Math.max(1, r.width));
    this.canvas.width = Math.max(1, Math.round(r.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * this.dpr));
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
  }

  // Espectro → `this.target` (0–1 por punto) y volumen general.
  sample(src, now) {
    const t = this.target;
    const h = this.half;
    const a = src.analyser;
    if (a) {
      if (!this.freq || this.freq.length !== a.frequencyBinCount) this.freq = new Uint8Array(a.frequencyBinCount);
      a.getByteFrequencyData(this.freq);
      // Solo la zona de la voz (hasta ~5 kHz), más resolución en los graves.
      const nyquist = a.context.sampleRate / 2;
      const maxBin = Math.max(8, Math.min(this.freq.length - 1, Math.ceil((5000 / nyquist) * this.freq.length)));
      const gate = src.gate ?? 0.15;
      let sum = 0;
      for (let i = 0; i < h; i++) {
        const idx = 1 + Math.floor((maxBin - 1) * Math.pow(i / (h - 1), 1.35));
        const v = Math.max(0, (this.freq[idx] / 255 - gate) / (1 - gate));
        t[i] = Math.min(1, Math.pow(v, 1.15) * 1.25);
        sum += t[i];
      }
      return Math.min(1, (sum / h) * 2.2);
    }
    const s = now / 1000;
    if (src.mode === "speaking") {
      // Habla pero no hay analizador (navegador sin Web Audio): movimiento inventado.
      const env = 0.35 + 0.3 * Math.abs(Math.sin(s * 5.3)) * Math.abs(Math.sin(s * 2.1 + 1));
      for (let i = 0; i < h; i++) t[i] = env * (0.5 + 0.5 * Math.sin(s * 9 + i * 0.7) * Math.sin(s * 3.7 + i * 0.23));
      return env;
    }
    if (src.mode === "thinking") {
      // Un brillo que da vueltas alrededor del aro.
      for (let i = 0; i < h; i++) {
        const ang = (i / h) * Math.PI;
        t[i] = 0.05 + 0.22 * Math.pow(Math.max(0, Math.cos(ang - ((s * 2.4) % (Math.PI * 2)))), 8);
      }
      return 0.22 + 0.06 * Math.sin(s * 3);
    }
    // Reposo / escuchando en silencio: respiración lenta.
    const breath = 0.5 + 0.5 * Math.sin(s * 1.6);
    for (let i = 0; i < h; i++) t[i] = 0.025 + 0.02 * breath * (0.5 + 0.5 * Math.sin(i * 0.4 + s));
    return src.mode === "idle" ? 0.06 + 0.06 * breath : 0.1 + 0.05 * breath;
  }

  frame(now) {
    if (!this.host.isConnected) return this.destroy();
    this.raf = requestAnimationFrame(this.frame);
    const dt = Math.min(4, (now - this.last) / 16.67);
    this.last = now;
    const src = this.source() || { mode: "idle" };
    const mode = ORB_MODES.has(src.mode) ? src.mode : "idle";

    const targetLevel = this.sample(src, now);
    for (let i = 0; i < this.half; i++) {
      const d = this.target[i] - this.bins[i];
      this.bins[i] += d * Math.min(1, (d > 0 ? 0.45 : 0.13) * dt);
    }
    const dl = targetLevel - this.level;
    this.level += dl * Math.min(1, (dl > 0 ? 0.3 : 0.07) * dt);
    const level = this.level;

    // Los colores se funden hacia la paleta del estado actual (y hacia el
    // color nuevo si se cambia mientras está a la vista).
    const pal = orbPalette(mode, src.hue ?? 262, src.sat);
    for (let k = 0; k < 4; k++) {
      const goal = pal[k];
      for (let c = 0; c < 3; c++) this.colors[k][c] += (goal[c] - this.colors[k][c]) * Math.min(1, 0.06 * dt);
    }
    const rgb = this.colors.map((c) => `rgb(${c.map(Math.round).join(",")})`);

    const speed = (mode === "thinking" ? 0.022 : 0.005) + level * 0.02;
    this.rot = (this.rot + speed * dt * (this.reduced ? 0.25 : 1)) % (Math.PI * 2);

    const st = this.host.style;
    st.setProperty("--lvl", level.toFixed(3));
    st.setProperty("--rot", `${((this.rot * 180) / Math.PI).toFixed(1)}deg`);
    const css = rgb.join("|");
    if (css !== this.cssColors) {
      this.cssColors = css;
      rgb.forEach((c, k) => st.setProperty(`--c${k + 1}`, c));
    }
    this.draw(now, level, rgb);
  }

  draw(now, level, rgb) {
    const ctx = this.ctx;
    const W = this.canvas.width;
    const H = this.canvas.height;
    const cx = W / 2;
    const cy = H / 2;
    const R = Math.min(W, H) * 0.2; // = 30% del aro (el lienzo mide 1,5 veces el aro)
    const k = Math.min(1, Math.max(0.55, R / (120 * this.dpr))); // trazos y brillo a escala del aro
    const dpr = this.dpr;
    ctx.clearRect(0, 0, W, H);

    // Brillo interior, más intenso con el volumen.
    const [r0, g0, b0] = this.colors[0].map(Math.round);
    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.05);
    glow.addColorStop(0, `rgba(${r0},${g0},${b0},${0.06 + level * 0.22})`);
    glow.addColorStop(0.7, `rgba(${r0},${g0},${b0},${0.03 + level * 0.08})`);
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, R * 1.05, 0, Math.PI * 2);
    ctx.fill();

    let stroke;
    if (ctx.createConicGradient) {
      stroke = ctx.createConicGradient(this.rot, cx, cy);
      [0, 0.25, 0.5, 0.75].forEach((p, k) => stroke.addColorStop(p, rgb[k]));
      stroke.addColorStop(1, rgb[0]);
    } else {
      stroke = ctx.createLinearGradient(0, 0, W, H);
      rgb.forEach((c, k) => stroke.addColorStop(k / 3, c));
    }

    const s = now / 1000;
    const wobbleK = this.reduced ? 0.3 : 1;
    const layers = [
      { amp: 1, width: (3.2 + level * 4.5) * k, alpha: 1, phase: 0 },
      { amp: 0.7, width: 1.6, alpha: 0.55, phase: 1.7 },
      { amp: 0.42, width: 1.1, alpha: 0.35, phase: 3.1 },
    ];
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.lineJoin = "round";
    ctx.strokeStyle = stroke;
    ctx.shadowColor = rgb[1];
    ctx.shadowBlur = R * (0.15 + level * 0.35);
    const pts = new Array(this.N);
    for (const L of layers) {
      for (let j = 0; j < this.N; j++) {
        const a = (j / this.N) * Math.PI * 2 - Math.PI / 2;
        const v = j < this.half ? this.bins[j] : this.bins[this.N - 1 - j];
        const wob = (Math.sin(a * 3 + s * 1.3 + L.phase) * 0.012 + Math.sin(a * 5 - s * 0.9 + L.phase) * 0.008) * (1 + level * 3) * wobbleK;
        const r = R * (1 + wob) + v * R * 0.34 * L.amp;
        pts[j] = [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
      }
      // Curva cerrada suave pasando por los puntos medios.
      ctx.beginPath();
      const mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
      let m = mid(pts[this.N - 1], pts[0]);
      ctx.moveTo(m[0], m[1]);
      for (let j = 0; j < this.N; j++) {
        const next = pts[(j + 1) % this.N];
        m = mid(pts[j], next);
        ctx.quadraticCurveTo(pts[j][0], pts[j][1], m[0], m[1]);
      }
      ctx.closePath();
      ctx.globalAlpha = L.alpha;
      ctx.lineWidth = L.width * dpr;
      ctx.stroke();
    }
    ctx.restore();
  }
}

window.VoiceOrb = VoiceOrb;
