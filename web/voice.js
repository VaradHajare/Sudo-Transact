/*
 * voice.js: microphone capture and the listening sheet (spec 4.2 steps 1–2).
 *
 * getUserMedia + MediaRecorder record the user's speech; an AnalyserNode drives the orb and
 * detects end of speech (~1.5 s of silence). The recorded blob goes to the backend, which calls
 * Sarvam STT. The mic is on only while the sheet is visible. Nothing is stored in the browser.
 *
 * Browsers allow the mic only on localhost or HTTPS.
 */
(function () {
  "use strict";

  const supported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);

  function pickMime() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return types.find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
  }

  /** Start recording. Calls onLevel(0..1) every frame and onAutoStop() at end of speech / max length. */
  async function startRecorder({ onLevel, onAutoStop }) {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const mime = pickMime();
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };

    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);

    const started = performance.now();
    let heard = false;
    let lastLoud = started;
    let raf = 0;
    let done = false;

    const tick = () => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now();
      onLevel(Math.min(1, rms * 8));
      if (rms > VOICE.speechLevel) { heard = true; lastLoud = now; }
      if ((heard && now - lastLoud > VOICE.silenceMs) || now - started > VOICE.maxMs) {
        onAutoStop();
        return;
      }
      raf = requestAnimationFrame(tick);
    };

    const cleanup = () => {
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop()); // mic off as soon as the sheet closes
      ctx.close().catch(() => {});
    };

    rec.start(250);
    tick();

    return {
      get heard() { return heard; },
      /** Resolves with the recorded Blob. */
      stop() {
        return new Promise((resolve) => {
          if (done) return resolve(null);
          done = true;
          rec.onstop = () => { cleanup(); resolve(new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" })); };
          rec.stop();
        });
      },
      cancel() {
        if (done) return;
        done = true;
        rec.onstop = cleanup;
        rec.stop();
      },
    };
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

  const MIC_SVG = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/></svg>';

  /**
   * ListeningSheet: bottom sheet with the orb and live transcript.
   * props: { lang } (preview language: "en" | "hi" | "mr")
   * Resolves { blob, liveText } when the user finishes, null on cancel, or { error } if the mic is unavailable.
   */
  function listen({ lang }) {
    const host = document.querySelector(".phone") || document.body;
    const el = document.createElement("div");
    el.className = "sheet-backdrop";
    el.innerHTML = `
      <div class="sheet" role="dialog" aria-modal="true" aria-label="Listening">
        <div class="sheet__grip" aria-hidden="true"></div>
        <p class="sheet__hint" data-hint>Starting the microphone…</p>
        <button class="orb" data-orb aria-label="Stop listening and send"><span class="orb__core">${MIC_SVG}</span></button>
        <p class="sheet__transcript" data-transcript aria-live="polite"></p>
        <button class="btn-link" data-cancel>Cancel</button>
      </div>`;
    host.appendChild(el);
    requestAnimationFrame(() => el.classList.add("is-open"));
    const $hint = el.querySelector("[data-hint]");
    const $orb = el.querySelector("[data-orb]");
    const $text = el.querySelector("[data-transcript]");

    return new Promise((resolve) => {
      let rec = null;
      let preview = null;
      let liveText = "";
      let settled = false;

      const close = (result) => {
        if (settled) return;
        settled = true;
        if (preview) preview.stop();
        document.removeEventListener("keydown", onKey);
        el.classList.remove("is-open");
        setTimeout(() => el.remove(), 200);
        resolve(result);
      };
      const finish = async () => {
        if (!rec || settled) return;
        $hint.textContent = "Got it…";
        const heard = rec.heard;
        const blob = await rec.stop();
        if (!blob || blob.size < 1000 || (!heard && !liveText)) {
          close({ error: "I didn't hear anything. Tap the mic and try again, or type." });
          return;
        }
        close({ blob, liveText });
      };
      const cancel = () => { if (rec) rec.cancel(); close(null); };
      const onKey = (e) => { if (e.key === "Escape") cancel(); };

      document.addEventListener("keydown", onKey);
      el.querySelector("[data-cancel]").onclick = cancel;
      el.onclick = (e) => { if (e.target === el) cancel(); };
      $orb.onclick = finish;
      // swipe down on the sheet to cancel
      let startY = null;
      el.querySelector(".sheet").addEventListener("touchstart", (e) => { startY = e.touches[0].clientY; }, { passive: true });
      el.querySelector(".sheet").addEventListener("touchend", (e) => {
        if (startY !== null && e.changedTouches[0].clientY - startY > 80) cancel();
        startY = null;
      });

      startRecorder({
        onLevel: (lvl) => $orb.style.setProperty("--level", lvl.toFixed(3)),
        onAutoStop: finish,
      }).then((r) => {
        if (settled) { r.cancel(); return; }
        rec = r;
        $hint.textContent = "Listening… speak in English, हिंदी or मराठी";
        preview = startLivePreview(lang, (t) => { liveText = t; $text.textContent = t; });
      }).catch((err) => {
        const denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
        close({ error: denied ? "Microphone permission is blocked. Allow it in the browser, or type instead."
                              : "No microphone available. Please type instead." });
      });
    });
  }

  window.Voice = { supported, listen };
})();
