/*
 * voice.js: microphone capture, the listening sheet, and hands-free conversation support.
 *
 * getUserMedia + MediaRecorder record the user's speech; an AnalyserNode drives the orb and
 * detects end of speech (~1.5 s of silence) or no speech at all (ends a hands-free conversation).
 * The recorded blob goes to the backend, which calls Sarvam STT. The mic is on only while a
 * listening indicator is visible, and is released after every turn. Nothing is stored here.
 *
 * Browsers allow the mic only on localhost or HTTPS.
 */
(function () {
  "use strict";

  const supported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);

  // Level meter on the audio thread: reports RMS every ~43 ms (2048 samples at 48 kHz), so speech
  // isn't missed when the page is busy or requestAnimationFrame is throttled.
  const LEVEL_WORKLET = `
    class LevelMeter extends AudioWorkletProcessor {
      constructor() { super(); this.sum = 0; this.n = 0; }
      process(inputs) {
        const ch = inputs[0] && inputs[0][0];
        if (ch) {
          for (let i = 0; i < ch.length; i++) this.sum += ch[i] * ch[i];
          this.n += ch.length;
          if (this.n >= 2048) { this.port.postMessage(Math.sqrt(this.sum / this.n)); this.sum = 0; this.n = 0; }
        }
        return true;
      }
    }
    registerProcessor("level-meter", LevelMeter);`;
  let workletUrl = null;

  /** Calls onRms(rms) repeatedly for the stream. Returns a stop() function. */
  async function meter(ctx, stream, onRms) {
    const source = ctx.createMediaStreamSource(stream);
    if (ctx.audioWorklet && window.AudioWorkletNode) {
      try {
        workletUrl = workletUrl || URL.createObjectURL(new Blob([LEVEL_WORKLET], { type: "application/javascript" }));
        await ctx.audioWorklet.addModule(workletUrl);
        const node = new AudioWorkletNode(ctx, "level-meter");
        const mute = ctx.createGain();
        mute.gain.value = 0; // keep the node in the rendering graph without playing the mic back
        source.connect(node).connect(mute).connect(ctx.destination);
        node.port.onmessage = (e) => onRms(e.data);
        return () => { node.port.onmessage = null; source.disconnect(); };
      } catch { /* fall back to the analyser below */ }
    }
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const timer = setInterval(() => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      onRms(Math.sqrt(sum / buf.length));
    }, 40);
    return () => { clearInterval(timer); source.disconnect(); };
  }

  function pickMime() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return types.find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
  }

  /** Optional live preview of the words while the user talks (see VOICE.liveTranscript in data.js). */
  function startLivePreview(lang, onText) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!VOICE.liveTranscript || !SR) return null;
    const r = new SR();
    r.lang = LANG_TAG[lang] || "en-IN";
    r.interimResults = true;
    r.continuous = true;
    r.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      onText(text);
    };
    r.onerror = () => {};
    try { r.start(); } catch { return null; }
    return { stop() { try { r.stop(); } catch { /* already stopped */ } } };
  }

  /**
   * Listen once. Returns a controller:
   *   done   Promise resolving to one of
   *            { blob, liveText }   speech recorded (end of speech, or stop())
   *            { timeout: true }    nothing said within noSpeechMs
   *            { error: "..." }     mic unavailable / blocked
   *            null                 cancel()
   *   stop()   finish now and send what was said
   *   cancel() discard
   * opts: { lang, noSpeechMs, onLevel(0..1), onText(liveText), onStart() }
   */
  function capture({ lang, noSpeechMs = VOICE.noSpeechMs, onLevel = () => {}, onText = () => {}, onStart = () => {} }) {
    let resolveDone;
    const done = new Promise((r) => { resolveDone = r; });
    let settled = false;
    let rec = null;
    let stream = null;
    let ctx = null;
    let stopMeter = null;
    let guard = 0;
    let preview = null;
    let heard = false;
    let liveText = "";
    const chunks = [];

    const release = () => {
      clearTimeout(guard);
      if (stopMeter) stopMeter();
      if (preview) preview.stop();
      if (stream) stream.getTracks().forEach((t) => t.stop()); // mic off as soon as listening ends
      if (ctx) ctx.close().catch(() => {});
    };
    const settle = (value) => {
      if (settled) return;
      settled = true;
      resolveDone(value);
    };
    const finish = (timedOut) => {
      if (settled) return;
      if (!rec || rec.state === "inactive") { release(); settle(timedOut ? { timeout: true } : null); return; }
      rec.onstop = () => {
        release();
        const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        if (timedOut || (!heard && !liveText) || blob.size < 1000) settle({ timeout: true });
        else settle({ blob, liveText });
      };
      rec.stop();
    };

    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      .then(async (s) => {
        stream = s;
        if (settled) { release(); return; }
        const mime = pickMime();
        rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
        rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        if (ctx.state === "suspended") await ctx.resume().catch(() => {});
        const started = performance.now();
        let lastLoud = started;
        // Room noise = the quietest moment in the first ~0.4 s (robust even if the user starts
        // talking at once). Speech must clear it by VOICE.noiseFactor, so fans, traffic or the
        // tail of the agent's own voice don't count as the user speaking.
        let noiseFloor = Infinity;
        let threshold = VOICE.speechLevel;
        rec.start(250);
        stopMeter = await meter(ctx, stream, (rms) => {
          if (settled) return;
          const now = performance.now();
          onLevel(Math.min(1, rms * 8));
          if (now - started < 400) {
            noiseFloor = Math.min(noiseFloor, rms);
            threshold = Math.max(VOICE.speechLevel, noiseFloor * VOICE.noiseFactor);
          }
          if (rms > threshold) { heard = true; lastLoud = now; }
          if (heard && now - lastLoud > VOICE.silenceMs) finish(false); // end of speech
          else if (!heard && now - started > noSpeechMs) finish(true); // nobody spoke
          else if (now - started > VOICE.maxMs) finish(false);
        });
        // Safety net if the meter never reports (e.g. audio thread blocked): never leave the mic on.
        guard = setTimeout(() => finish(!heard), VOICE.maxMs + 1000);
        if (settled) { release(); return; }
        preview = startLivePreview(lang, (t) => { liveText = t; heard = heard || !!t; onText(t); });
        onStart();
      })
      .catch((err) => {
        const denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
        settle({ error: denied ? window.t("micBlocked") : window.t("noMic") });
      });

    return {
      done,
      stop: () => finish(false),
      cancel: () => {
        if (settled) return;
        if (rec && rec.state !== "inactive") { rec.onstop = release; rec.stop(); } else release();
        settle(null);
      },
    };
  }

  const MIC_SVG = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/></svg>';

  /**
   * ListeningSheet: bottom sheet with the orb and live transcript, used on a payment screen
   * (spec 4.2 step 1) before the chat opens. props: { lang }
   * Resolves { blob, liveText } | null (cancel) | { error } | { timeout }.
   */
  function listen({ lang }) {
    const host = document.querySelector(".phone") || document.body;
    const el = document.createElement("div");
    el.className = "sheet-backdrop";
    el.innerHTML = `
      <div class="sheet" role="dialog" aria-modal="true" aria-label="${window.t("listening")}">
        <div class="sheet__grip" aria-hidden="true"></div>
        <p class="sheet__hint" data-hint>${window.t("micStarting")}</p>
        <button class="orb" data-orb aria-label="${window.t("stopSend")}"><span class="orb__core">${MIC_SVG}</span></button>
        <p class="sheet__transcript" data-transcript aria-live="polite"></p>
        <button class="btn-link" data-cancel>${window.t("cancel")}</button>
      </div>`;
    host.appendChild(el);
    requestAnimationFrame(() => el.classList.add("is-open"));
    const $hint = el.querySelector("[data-hint]");
    const $orb = el.querySelector("[data-orb]");
    const $text = el.querySelector("[data-transcript]");

    const ctrl = capture({
      lang,
      onLevel: (lvl) => $orb.style.setProperty("--level", lvl.toFixed(3)),
      onText: (t) => { $text.textContent = t; },
      onStart: () => { $hint.textContent = window.t("listenHint"); },
    });
    const onKey = (e) => { if (e.key === "Escape") ctrl.cancel(); };
    document.addEventListener("keydown", onKey);
    el.querySelector("[data-cancel]").onclick = () => ctrl.cancel();
    el.onclick = (e) => { if (e.target === el) ctrl.cancel(); };
    $orb.onclick = () => { $hint.textContent = window.t("gotIt"); ctrl.stop(); };
    let startY = null; // swipe down to cancel
    const sheet = el.querySelector(".sheet");
    sheet.addEventListener("touchstart", (e) => { startY = e.touches[0].clientY; }, { passive: true });
    sheet.addEventListener("touchend", (e) => {
      if (startY !== null && e.changedTouches[0].clientY - startY > 80) ctrl.cancel();
      startY = null;
    });

    return ctrl.done.then((result) => {
      document.removeEventListener("keydown", onKey);
      el.classList.remove("is-open");
      setTimeout(() => el.remove(), 200);
      return result;
    });
  }

  window.Voice = { supported, capture, listen };
})();
