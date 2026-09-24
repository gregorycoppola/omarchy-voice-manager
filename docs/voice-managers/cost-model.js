/* USD rate snapshot checked 2026-09-23. This file makes no network requests. */
(function (root) {
  'use strict';
  const pricing = 'https://developers.openai.com/api/docs/pricing';
  const models = [
    { id: 'local', name: 'Local speech + local rules / LLM', input: 0, cached: 0, output: 0,
      note: 'Zero API fee; local running and training costs are separate.' },
    { id: 'local-decision', name: 'Local speech + local Jev-style classifier (e.g. Kev)', input: 0, cached: 0, output: 0,
      source: 'https://github.com/jaredpalmer/kev',
      note: 'Runs on your machine; zero API fee. Distinct from hosted TypeSafe Jev.' },
    { id: 'nano', name: 'Local speech + GPT-5.4-nano', input: 0.20, cached: 0.02, output: 1.25,
      source: 'https://developers.openai.com/api/docs/models/gpt-5.4-nano' },
    { id: 'mini', name: 'Local speech + GPT-5.4-mini', input: 0.75, cached: 0.075, output: 4.50,
      source: 'https://developers.openai.com/api/docs/models/gpt-5.4-mini' },
    { id: 'jev', name: 'Local speech + TypeSafe Jev cloud API', input: 0.042, cached: 0.042, output: 0,
      source: 'https://typesafe.ai/blog/introducing-system-one-models-and-jev',
      note: 'Direct provider rate; no cache discount assumed. Not benchmarked here.' },
    { id: 'remote-two-stage', name: 'GPT-Transcribe + GPT-5.4-mini', input: 0.75, cached: 0.075, output: 4.50,
      perAudioMinute: 0.0045, source: pricing,
      note: 'Two hosted stages. Transcription priced by recorded audio duration.' },
    { id: 'realtime-mini', name: 'GPT-Realtime-2.1-mini · audio → intent', input: 0.60, cached: 0.06, output: 2.40,
      audioInput: 10, source: pricing,
      note: 'Integrated model; audio input and text output. Not benchmarked here.' },
    { id: 'realtime', name: 'GPT-Realtime-2.1 · audio → intent', input: 4, cached: 0.40, output: 24,
      audioInput: 32, source: pricing,
      note: 'Integrated model; audio input and text output. Not benchmarked here.' }
  ];
  function estimate(model, scenario) {
    const keys = ['commands', 'days', 'audioSeconds', 'textInput', 'textOutput', 'cachePercent', 'extraPercent'];
    for (const key of keys) {
      if (!Number.isFinite(scenario[key]) || scenario[key] < 0) throw new RangeError(`Invalid ${key}`);
    }
    if (scenario.cachePercent > 100) throw new RangeError('Cache share exceeds 100%');
    const cachedShare = scenario.cachePercent / 100;
    const text = (scenario.textInput * ((1 - cachedShare) * model.input + cachedShare * model.cached)
      + scenario.textOutput * model.output) / 1e6;
    // Duration conversion is an estimate; actual API usage includes special tokens.
    const audio = scenario.audioSeconds * 10 * (model.audioInput || 0) / 1e6
      + scenario.audioSeconds / 60 * (model.perAudioMinute || 0);
    const perAttempt = text + audio;
    const perCommand = perAttempt * (1 + scenario.extraPercent / 100);
    return { text, audio, perAttempt, perCommand, perThousand: perCommand * 1000,
      monthly: perCommand * scenario.commands * scenario.days };
  }
  const api = { models, estimate, checkedOn: '2026-09-23' };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.VoiceCosts = api;
})(globalThis);
