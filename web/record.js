// VIPLAV Recorder: read a sentence aloud, keep the clip with its exact text.
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const { Mic, concat, encodeWav, rms } = window.ViplavMic;
  const LANGS = [
    ["lmn", "Lambadi (Gor Boli)"],
    ["te", "Telugu"],
    ["hi", "Hindi"],
    ["en", "English"],
  ];
  const token = new URLSearchParams(location.search).get("token");
  const api = (path) => path + (token ? `?token=${encodeURIComponent(token)}` : "");

  const store = {
    get: (k, d) => { try { return localStorage.getItem("viplav.rec." + k) ?? d; } catch (_) { return d; } },
    set: (k, v) => { try { localStorage.setItem("viplav.rec." + k, v); } catch (_) {} },
  };

  const speaker = $("speaker");
  const langSel = $("rec-lang");
  const sentences = $("sentences");
  const current = $("current");
  const recBtn = $("rec");
  const saveBtn = $("save");
  const preview = $("preview");
  const msg = $("msg");

  for (const [code, name] of LANGS) langSel.add(new Option(name, code));
  speaker.value = store.get("speaker", "");
  langSel.value = store.get("lang", "lmn");
  sentences.value = store.get("sentences", "");
  let index = Number(store.get("index", "0"));

  speaker.addEventListener("input", () => store.set("speaker", speaker.value));
  langSel.addEventListener("change", () => store.set("lang", langSel.value));
  sentences.addEventListener("input", () => {
    store.set("sentences", sentences.value);
    index = 0;
    store.set("index", "0");
    showSentence();
  });

  function lines() {
    return sentences.value.split("\n").map((s) => s.trim()).filter(Boolean);
  }

  function showSentence() {
    const all = lines();
    $("count").textContent = all.length;
    $("total").textContent = all.length;
    $("pos").textContent = all.length ? Math.min(index + 1, all.length) : 0;
    if (all.length) current.value = index < all.length ? all[index] : "";
    if (all.length && index >= all.length) setMsg("All sentences done. Paste more above, or type your own.");
  }

  function next() {
    if (mic) { mic.stop(); mic = null; document.body.dataset.state = "idle"; }
    index++;
    store.set("index", String(index));
    clearTake();
    showSentence();
  }

  // ---------- recording ----------
  let mic = null;
  let chunks = [];
  let take = null; // Float32Array of the last recording

  async function startRecording() {
    clearTake();
    chunks = [];
    mic = new Mic();
    try {
      await mic.start((chunk) => {
        chunks.push(chunk);
        $("meter-fill").style.width = `${Math.min(100, rms(chunk) * 600)}%`;
      }, { clean: false });
    } catch (_) {
      mic = null;
      return setMsg("Microphone access was blocked. Allow it in the address bar.");
    }
    document.body.dataset.state = "hearing";
    recBtn.textContent = "■ Stop";
    setMsg("Recording… read the sentence, then stop.");
  }

  function stopRecording() {
    if (!mic) return;
    mic.stop();
    mic = null;
    document.body.dataset.state = "idle";
    recBtn.innerHTML = "● Record again <kbd>R</kbd>";
    $("meter-fill").style.width = "0";
    take = concat(chunks);
    const seconds = take.length / 16000;
    if (seconds < 0.5) {
      take = null;
      return setMsg("That was too short. Try again.");
    }
    let peak = 0;
    for (let i = 0; i < take.length; i++) peak = Math.max(peak, Math.abs(take[i]));
    if (peak > 0.99) setMsg("That clipped (too loud). Move back a little and redo it.");
    else setMsg(`${seconds.toFixed(1)} s. Listen back, then save or redo.`);
    preview.src = URL.createObjectURL(new Blob([encodeWav(take)], { type: "audio/wav" }));
    preview.hidden = false;
    saveBtn.disabled = false;
  }

  function clearTake() {
    take = null;
    preview.hidden = true;
    preview.removeAttribute("src");
    saveBtn.disabled = true;
    recBtn.innerHTML = "● Record <kbd>R</kbd>";
  }

  async function save() {
    const text = current.value.trim();
    if (!take) return;
    if (!text) return setMsg("Type the exact words you said first. The text matters as much as the audio.");
    const wav = new Uint8Array(encodeWav(take));
    let bin = "";
    for (let i = 0; i < wav.length; i += 0x8000) bin += String.fromCharCode(...wav.subarray(i, i + 0x8000));
    saveBtn.disabled = true;
    try {
      const res = await fetch(api("/api/recordings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang: langSel.value, text, speaker: speaker.value, audio: btoa(bin) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      showStats(data.stats);
      setMsg("Saved.");
      next();
    } catch (err) {
      saveBtn.disabled = false;
      setMsg(`Couldn't save: ${err.message}`);
    }
  }

  function showStats(stats) {
    const names = Object.fromEntries(LANGS);
    const rows = Object.entries(stats).map(([code, s]) => `${names[code] || code}: ${s.clips} clips, ${s.minutes} min`);
    $("stats").textContent = rows.length ? rows.join(" · ") : "Nothing yet.";
  }

  function setMsg(text) {
    msg.textContent = text;
  }

  recBtn.addEventListener("click", () => (mic ? stopRecording() : startRecording()));
  saveBtn.addEventListener("click", save);
  $("skip").addEventListener("click", next);
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    if (e.key === "r" || e.key === "R") mic ? stopRecording() : startRecording();
    else if (e.key === "Enter" && !saveBtn.disabled) save();
    else if (e.key === "ArrowRight") next();
  });

  fetch(api("/api/recordings/stats")).then((r) => r.json()).then(showStats).catch(() => {});
  showSentence();
})();
