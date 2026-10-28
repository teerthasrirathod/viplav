// Microphone capture at 16 kHz, voice-activity detection, and WAV encoding.
// Shared by the main page (local Whisper listening) and the recorder page.
(() => {
  "use strict";

  const RATE = 16000;

  // Runs on the audio thread: hands ~20 ms blocks of raw samples to the page.
  const WORKLET = `
    class Tap extends AudioWorkletProcessor {
      constructor() { super(); this.buf = []; this.n = 0; }
      process(inputs) {
        const ch = inputs[0] && inputs[0][0];
        if (ch) {
          this.buf.push(ch.slice());
          this.n += ch.length;
          if (this.n >= 1024) {
            const out = new Float32Array(this.n);
            let o = 0;
            for (const b of this.buf) { out.set(b, o); o += b.length; }
            this.port.postMessage(out, [out.buffer]);
            this.buf = []; this.n = 0;
          }
        }
        return true;
      }
    }
    registerProcessor("viplav-tap", Tap);`;

  function downsample(input, fromRate) {
    if (fromRate === RATE) return input;
    const ratio = fromRate / RATE;
    const out = new Float32Array(Math.floor(input.length / ratio));
    for (let i = 0; i < out.length; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(input.length, Math.floor((i + 1) * ratio));
      let sum = 0;
      for (let j = start; j < end; j++) sum += input[j];
      out[i] = sum / Math.max(1, end - start);
    }
    return out;
  }

  class Mic {
    // clean: true (conversation) lets the browser cancel echo and noise. The recorder turns
    // it off, because training data should be the voice as it is, not the browser's cleanup.
    async start(onChunk, { clean = true } = {}) {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: clean, noiseSuppression: clean, autoGainControl: clean, channelCount: 1 },
      });
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await this.ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      this.source = this.ctx.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(this.ctx, "viplav-tap");
      const rate = this.ctx.sampleRate;
      this.node.port.onmessage = (e) => this.stream && onChunk(downsample(e.data, rate));
      // The worklet only runs while connected to the output; a silent gain keeps it running.
      const mute = this.ctx.createGain();
      mute.gain.value = 0;
      this.source.connect(this.node).connect(mute).connect(this.ctx.destination);
    }

    stop() {
      if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
      if (this.ctx) this.ctx.close();
      this.stream = this.ctx = this.node = this.source = null;
    }
  }

  function rms(chunk) {
    let sum = 0;
    for (let i = 0; i < chunk.length; i++) sum += chunk[i] * chunk[i];
    return Math.sqrt(sum / chunk.length);
  }

  // Finds where speech starts and stops, adapting to the room's background noise.
  class Utterances {
    constructor({ onStart, onEnd, hangMs = 800, minSpeechMs = 250, maxMs = 30000, preRollMs = 300, floor = 0.012 } = {}) {
      // floor: the quietest level counted as speech; raise it to ignore a voice from the speakers.
      Object.assign(this, { onStart, onEnd, hangMs, minSpeechMs, maxMs, preRollMs, floor });
      this.noise = 0.004;
      this.speaking = false;
      this.chunks = [];
      this.preRoll = [];
      this.voicedMs = 0;
      this.silentMs = 0;
      this.totalMs = 0;
      this.level = 0;
    }

    feed(chunk) {
      const ms = (chunk.length / RATE) * 1000;
      const level = rms(chunk);
      this.level = level;
      const voiced = level > Math.max(this.floor, this.noise * 3.2);
      if (!this.speaking) {
        this.noise = this.noise * 0.97 + level * 0.03;
        this.preRoll.push(chunk);
        while (this.preRoll.length * ms > this.preRollMs) this.preRoll.shift();
        this.voicedMs = voiced ? this.voicedMs + ms : 0;
        if (this.voicedMs >= this.minSpeechMs) {
          this.speaking = true;
          this.chunks = this.preRoll.slice();
          this.preRoll = [];
          this.silentMs = 0;
          this.totalMs = this.chunks.length * ms;
          if (this.onStart) this.onStart();
        }
        return;
      }
      this.chunks.push(chunk);
      this.totalMs += ms;
      this.silentMs = voiced ? 0 : this.silentMs + ms;
      if (this.silentMs >= this.hangMs || this.totalMs >= this.maxMs) this.finish();
    }

    finish() {
      if (!this.speaking) return;
      this.speaking = false;
      this.voicedMs = 0;
      const audio = concat(this.chunks);
      this.chunks = [];
      if (this.onEnd) this.onEnd(audio);
    }
  }

  function concat(chunks) {
    const out = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
    let o = 0;
    for (const c of chunks) { out.set(c, o); o += c.length; }
    return out;
  }

  function toPCM16(float32) {
    const out = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  function encodeWav(float32) {
    const pcm = toPCM16(float32);
    const buf = new ArrayBuffer(44 + pcm.length * 2);
    const v = new DataView(buf);
    const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
    str(0, "RIFF"); v.setUint32(4, 36 + pcm.length * 2, true); str(8, "WAVE");
    str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, RATE, true); v.setUint32(28, RATE * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    str(36, "data"); v.setUint32(40, pcm.length * 2, true);
    new Int16Array(buf, 44).set(pcm);
    return buf;
  }

  window.ViplavMic = { Mic, Utterances, concat, toPCM16, encodeWav, rms, RATE };
})();
