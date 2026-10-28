// VIPLAV — browser side: listens, shows the face, plays the voice.
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const body = document.body;
  const statusEl = $("status");
  const captionEl = $("caption");
  const logEl = $("log");
  const micBtn = $("mic");
  const micLabel = $("mic-label");
  const langSel = $("lang");
  const mouth = $("mouth");
  const { Mic, Utterances, toPCM16 } = window.ViplavMic;

  const SEND_AFTER_SILENCE_MS = 900; // browser recognition: wait this long after you stop before sending
  const BARGE_IN_MIN_WORDS = 2;

  let ws = null;
  let sttMode = "browser"; // "browser" or "whisper", decided by the server
  let languages = []; // [{code, name, locale}] from the server
  let listening = false; // the user wants the mic on
  let bargeIn = true;
  let requested = 0; // utterances sent; the server numbers its turns the same way
  let ignoreBelow = 0; // drop server output from turns older than this (after an interrupt)
  let turnOpen = false; // server is still producing the current reply
  let replyEntry = null;
  let replyText = "";
  let mic = null; // local-Whisper mode: the microphone and the speech detector
  let utterances = null;

  const store = {
    get: (k) => { try { return localStorage.getItem("viplav." + k); } catch (_) { return null; } },
    set: (k, v) => { try { localStorage.setItem("viplav." + k, v); } catch (_) {} },
  };

  // ---------- face state ----------
  function setState(state) {
    body.dataset.state = state;
  }
  function setStatus(text) {
    statusEl.textContent = text;
  }
  function restingState() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return setState("offline");
    setState(listening ? "listening" : "idle");
    setStatus(listening ? "Listening" : "Tap to talk, or press Space");
  }

  // Blink at natural, irregular intervals.
  (function blinkLoop() {
    setTimeout(() => {
      for (const eye of document.querySelectorAll(".eye")) {
        eye.classList.remove("blink");
        void eye.getBBox();
        eye.classList.add("blink");
      }
      blinkLoop();
    }, 2200 + Math.random() * 4200);
  })();

  // ---------- audio playback ----------
  let ctx = null;
  let analyser = null;
  let levelData = null;
  let chain = Promise.resolve();
  let epoch = 0; // bumps on every stop, so queued items from before are dropped
  let pending = 0; // speech pieces queued or playing
  let currentSource = null;
  let browserSpeaking = false;
  const recentlySpoken = [];

  function ensureAudio() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.connect(ctx.destination);
      levelData = new Uint8Array(analyser.fftSize);
    }
    if (ctx.state === "suspended") ctx.resume();
  }

  function b64ToBuffer(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }

  function enqueueSpeech(msg) {
    const myEpoch = epoch;
    pending++;
    // Decode immediately so it's ready the moment the previous piece ends.
    const decoded = msg.audio && ctx ? ctx.decodeAudioData(b64ToBuffer(msg.audio)).catch(() => null) : Promise.resolve(null);
    chain = chain
      .then(async () => {
        if (myEpoch !== epoch) return;
        const buffer = await decoded;
        if (myEpoch !== epoch) return;
        setState("speaking");
        setStatus("");
        showCaption(msg.text, false);
        remember(msg.text);
        if (buffer) await playBuffer(buffer);
        else await speakWithBrowser(msg.text, msg.lang);
      })
      .catch((err) => console.warn("playback", err))
      .finally(() => {
        pending = Math.max(0, pending - 1);
        if (myEpoch === epoch) maybeFinish();
      });
  }

  function playBuffer(buffer) {
    return new Promise((resolve) => {
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(analyser);
      src.onended = () => {
        if (currentSource === src) currentSource = null;
        resolve();
      };
      currentSource = src;
      src.start();
    });
  }

  // The best installed voice for each language.
  const voices = {};
  function pickVoices() {
    const all = speechSynthesis.getVoices();
    const score = (v) => {
      const n = v.name.toLowerCase();
      return (/natural|neural|premium|enhanced/.test(n) ? 4 : 0) + (/google|microsoft/.test(n) ? 2 : 0) + (v.lang.endsWith("IN") ? 1 : 0);
    };
    for (const lang of ["en", "hi", "te"]) {
      voices[lang] = all.filter((v) => v.lang.toLowerCase().startsWith(lang)).sort((a, b) => score(b) - score(a))[0] || null;
    }
  }
  if ("speechSynthesis" in window) {
    pickVoices();
    speechSynthesis.onvoiceschanged = pickVoices;
  }

  function speakWithBrowser(text, lang) {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      const voice = voices[lang] || voices.en;
      if (voice) u.voice = voice;
      u.lang = voice ? voice.lang : { en: "en-IN", hi: "hi-IN", te: "te-IN" }[lang] || "en-IN";
      u.rate = 1.02;
      u.onstart = () => (browserSpeaking = true);
      u.onend = u.onerror = () => {
        browserSpeaking = false;
        resolve();
      };
      speechSynthesis.speak(u);
    });
  }

  function stopSpeaking() {
    epoch++;
    pending = 0;
    chain = Promise.resolve();
    if (currentSource) {
      try { currentSource.stop(); } catch (_) {}
      currentSource = null;
    }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    browserSpeaking = false;
  }

  function isBusy() {
    return turnOpen || pending > 0;
  }

  function maybeFinish() {
    if (!isBusy()) restingState();
  }

  // Mouth and halo follow the loudness of the voice (or of you, while you talk).
  let level = 0;
  (function animate() {
    let target = 0;
    if (currentSource && analyser) {
      analyser.getByteTimeDomainData(levelData);
      let sum = 0;
      for (const v of levelData) sum += ((v - 128) / 128) ** 2;
      target = Math.min(1, Math.sqrt(sum / levelData.length) * 4.5);
    } else if (browserSpeaking) {
      const t = performance.now() / 1000;
      target = 0.35 + 0.3 * Math.abs(Math.sin(t * 9.3) * Math.sin(t * 3.1 + 1));
    }
    level += (target - level) * (target > level ? 0.5 : 0.18);
    const open = level * 30;
    mouth.setAttribute("d", `M165 250 Q200 ${250 - open * 0.25} 235 250 Q200 ${254 + open * 1.6} 165 250`);
    const heard = utterances && utterances.speaking ? Math.min(1, utterances.level * 12) : 0;
    body.style.setProperty("--level", Math.max(level, heard * 0.6).toFixed(3));
    requestAnimationFrame(animate);
  })();

  // ---------- captions and transcript ----------
  function showCaption(text, isUser) {
    captionEl.textContent = text;
    captionEl.classList.toggle("user", !!isUser);
  }

  function addLog(who, text) {
    const p = document.createElement("div");
    p.className = "msg " + (who === "You" ? "you" : "viplav");
    renderMsg(p, who, text);
    logEl.appendChild(p);
    logEl.scrollTop = logEl.scrollHeight;
    return p;
  }

  function renderMsg(el, who, text) {
    el.replaceChildren();
    const b = document.createElement("b");
    b.textContent = who;
    el.appendChild(b);
    text.split("```").forEach((part, i) => {
      if (i % 2 === 1) {
        const pre = document.createElement("pre");
        pre.textContent = part.replace(/^[\w+-]*\n/, "");
        el.appendChild(pre);
      } else if (part) {
        el.appendChild(document.createTextNode(part));
      }
    });
  }

  function remember(text) {
    recentlySpoken.push(text);
    if (recentlySpoken.length > 3) recentlySpoken.shift();
  }

  // True when what the mic heard is mostly VIPLAV's own voice coming out of the speakers.
  function isEcho(heard) {
    const words = heard.toLowerCase().match(/[\p{L}\p{M}\p{N}']+/gu) || [];
    if (!words.length) return true;
    const spoken = new Set(recentlySpoken.join(" ").toLowerCase().match(/[\p{L}\p{M}\p{N}']+/gu) || []);
    return words.filter((w) => spoken.has(w)).length / words.length > 0.6;
  }

  // ---------- language choice ----------
  function fillLanguages() {
    langSel.replaceChildren();
    if (sttMode === "whisper") langSel.add(new Option("Auto-detect", "auto"));
    for (const lang of languages) langSel.add(new Option(lang.name, lang.code));
    const saved = store.get("lang");
    if (saved && [...langSel.options].some((o) => o.value === saved)) langSel.value = saved;
    sendLanguage();
  }

  function currentLocale() {
    const lang = languages.find((l) => l.code === langSel.value) || languages[0];
    return lang ? lang.locale : navigator.language || "en-IN";
  }

  function sendLanguage() {
    send({ type: "set_language", lang: langSel.value });
  }

  langSel.addEventListener("change", () => {
    store.set("lang", langSel.value);
    sendLanguage();
    if (listening && sttMode === "browser") {
      setListening(false);
      setListening(true); // restart recognition in the new language
    }
  });

  // ---------- listening: the browser's recognizer ----------
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  let finalText = "";
  let sendTimer = null;

  function startRecognition() {
    if (!Recognition) {
      setStatus("This browser can't recognize speech. Use Chrome, Edge or Safari, or type below.");
      return false;
    }
    rec = new Recognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = currentLocale();
    rec.onresult = onResult;
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setListening(false);
        setStatus("Microphone access was blocked. Allow it in the address bar, then tap again.");
      }
    };
    rec.onend = () => {
      // Browsers end recognition after silence; keep it going while the mic is on.
      if (listening) setTimeout(() => listening && rec && safeStart(), 150);
    };
    safeStart();
    return true;
  }

  function safeStart() {
    try { rec.start(); } catch (_) { /* already running */ }
  }

  function onResult(e) {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalText += r[0].transcript + " ";
      else interim += r[0].transcript;
    }
    const heard = (finalText + interim).trim();
    if (!heard) return;

    if (isBusy()) {
      if (!bargeIn || isEcho(heard)) {
        finalText = "";
        return;
      }
      if (heard.split(/\s+/).length < BARGE_IN_MIN_WORDS) return;
      interrupt(); // you started talking over VIPLAV: stop and listen
    }

    setState("hearing");
    showCaption(heard, true);
    clearTimeout(sendTimer);
    sendTimer = setTimeout(() => {
      const text = finalText.trim();
      if (!text) return;
      finalText = "";
      sendUserText(text);
    }, interim ? SEND_AFTER_SILENCE_MS + 600 : SEND_AFTER_SILENCE_MS);
  }

  // ---------- listening: local Whisper on the server ----------

  async function startWhisper() {
    utterances = new Utterances({
      onStart: () => {
        if (isBusy()) interrupt(); // only reached when barge-in is allowed (see feed below)
        setState("hearing");
        setStatus("Hearing you…");
      },
      onEnd: (audio) => {
        if (audio.length < 0.4 * 16000) return restingState(); // a cough, a click
        setState("thinking");
        setStatus("Understanding…");
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(toPCM16(audio).buffer);
      },
    });
    mic = new Mic();
    try {
      await mic.start((chunk) => {
        if (isBusy() && !utterances.speaking) {
          if (!bargeIn) return;
          // While VIPLAV talks, only a clearly louder, longer voice counts as you cutting in.
          utterances.floor = 0.04;
          utterances.minSpeechMs = 450;
        } else {
          utterances.floor = 0.012;
          utterances.minSpeechMs = 250;
        }
        utterances.feed(chunk);
      });
      return true;
    } catch (err) {
      mic = utterances = null;
      setStatus("Microphone access was blocked. Allow it in the address bar, then tap again.");
      return false;
    }
  }

  // ---------- mic button ----------
  async function setListening(on) {
    listening = on;
    micBtn.setAttribute("aria-pressed", String(on));
    micLabel.textContent = on ? "Listening — tap to stop" : "Tap to talk";
    if (on) {
      ensureAudio();
      const ok = sttMode === "whisper" ? await startWhisper() : startRecognition();
      if (!ok) {
        listening = false;
        micBtn.setAttribute("aria-pressed", "false");
        micLabel.textContent = "Tap to talk";
        return;
      }
    } else {
      if (rec) {
        rec.onend = null;
        rec.abort();
        rec = null;
        finalText = "";
      }
      if (mic) {
        mic.stop();
        mic = utterances = null;
      }
    }
    if (!isBusy()) restingState();
  }

  // ---------- talking to the server ----------
  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const token = new URLSearchParams(location.search).get("token");
    ws = new WebSocket(`${proto}//${location.host}/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => restingState();
    ws.onmessage = (e) => handle(JSON.parse(e.data));
    ws.onclose = (e) => {
      setState("offline");
      turnOpen = false;
      setStatus(e.code === 4401 ? "Access token missing or wrong (add ?token=… to the URL)." : "Disconnected. Reconnecting…");
      if (e.code !== 4401) setTimeout(connect, 1500);
    };
  }

  function send(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  }

  function interrupt() {
    stopSpeaking();
    turnOpen = false;
    ignoreBelow = requested + 1;
    send({ type: "interrupt" });
  }

  function beginReply(text) {
    addLog("You", text);
    replyEntry = null;
    replyText = "";
    turnOpen = true;
    requested++;
    setState("thinking");
    setStatus("Thinking…");
  }

  function sendUserText(text) {
    if (isBusy()) interrupt();
    ensureAudio();
    beginReply(text);
    send({ type: "user_text", text });
  }

  function handle(msg) {
    if (msg.turn !== undefined && msg.turn < ignoreBelow) return;
    switch (msg.type) {
      case "hello":
        sttMode = msg.stt;
        languages = msg.languages;
        fillLanguages();
        restingState();
        break;
      case "transcript":
        if (msg.text) {
          showCaption(msg.text, true);
          beginReply(msg.text); // the server starts this turn itself
        } else {
          restingState();
        }
        break;
      case "state":
        if (msg.state === "thinking" && turnOpen) setState("thinking");
        break;
      case "status":
        if (turnOpen) setStatus(msg.text);
        break;
      case "text_delta":
        replyText += msg.text;
        if (!replyEntry) replyEntry = addLog("VIPLAV", replyText);
        else renderMsg(replyEntry, "VIPLAV", replyText);
        logEl.scrollTop = logEl.scrollHeight;
        break;
      case "speech":
        enqueueSpeech(msg);
        break;
      case "turn_end":
        turnOpen = false;
        maybeFinish();
        break;
      case "error":
        turnOpen = false;
        setState("error");
        setStatus(msg.message);
        setTimeout(maybeFinish, 4000);
        break;
    }
  }

  // ---------- controls ----------
  micBtn.addEventListener("click", () => setListening(!listening));

  $("typed").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("typed-input");
    const text = input.value.trim();
    if (text) sendUserText(text);
    input.value = "";
  });

  $("toggle-log").addEventListener("click", (e) => {
    const show = logEl.hidden;
    logEl.hidden = !show;
    e.currentTarget.setAttribute("aria-pressed", String(show));
  });

  $("toggle-barge").addEventListener("click", (e) => {
    bargeIn = !bargeIn;
    e.currentTarget.setAttribute("aria-pressed", String(bargeIn));
  });

  $("reset").addEventListener("click", () => {
    interrupt();
    send({ type: "reset" });
    logEl.replaceChildren();
    showCaption("", false);
    restingState();
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (e.code === "Space") {
      e.preventDefault();
      setListening(!listening);
    } else if (e.code === "Escape" && isBusy()) {
      interrupt();
      restingState();
    }
  });

  connect();
})();
