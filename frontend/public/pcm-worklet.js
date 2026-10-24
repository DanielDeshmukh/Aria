// Captures mic input in an AudioWorklet scope, downsamples the AudioContext
// rate to 16000 Hz by linear interpolation (read position and last sample are
// carried across process() blocks), converts to PCM16 and emits 100 ms frames
// (1600 samples @ 16 kHz) on the node port for base64 framing in useMic.ts.
const TARGET_RATE = 16000;
const FRAME_SAMPLES = 1600;

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._step = sampleRate / TARGET_RATE;
    this._pos = 0;
    this._last = 0;
    this._frame = new Int16Array(FRAME_SAMPLES);
    this._filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || channel.length === 0) return true;
    const end = channel.length;
    let pos = this._pos;
    while (Math.floor(pos) <= end - 2) {
      const i0 = Math.floor(pos);
      const frac = pos - i0;
      const s0 = i0 < 0 ? this._last : channel[i0];
      const s1 = channel[i0 + 1];
      const v = s0 + (s1 - s0) * frac;
      const sample = Math.max(-32768, Math.min(32767, Math.round(v * 32767)));
      this._frame[this._filled++] = sample;
      if (this._filled === FRAME_SAMPLES) {
        this.port.postMessage({ pcm: this._frame.buffer }, [this._frame.buffer]);
        this._frame = new Int16Array(FRAME_SAMPLES);
        this._filled = 0;
      }
      pos += this._step;
    }
    this._pos = pos - end;
    this._last = channel[end - 1];
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
