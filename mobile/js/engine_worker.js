// ============================================================
// engine_worker.js — C 엔진을 화면과 따로(Web Worker) 돌린다
//   계산하는 0.3~2초 동안 지도·버튼이 멈추지 않게 하기 위해서다.
//   wildfire.wasm 은 처음 한 번만 컴파일해 두고 계속 쓴다.
// ============================================================

import { runEngine } from './engine_core.js';

let modulePromise = null;

function loadModule() {
  if (!modulePromise) {
    modulePromise = fetch(new URL('../engine/wildfire.wasm', import.meta.url))
      .then((r) => {
        if (!r.ok) throw new Error(`엔진 파일을 받지 못함 (${r.status})`);
        return r.arrayBuffer();
      })
      .then((bytes) => WebAssembly.compile(bytes));
  }
  return modulePromise;
}

self.onmessage = async (event) => {
  const { id, files, args } = event.data;
  try {
    const module = await loadModule();
    const result = await runEngine(module, files, args, (line) => {
      const m = line.match(/^\[PROGRESS\]\s+(\d+)\s*(.*)$/);
      if (m) self.postMessage({ id, progress: +m[1], text: m[2] });
      else if (line.startsWith('[ERROR]') || line.startsWith('[WARN]')) self.postMessage({ id, log: line });
    });
    self.postMessage({ id, done: true, ...result });
  } catch (error) {
    self.postMessage({ id, done: true, code: -1, error: String(error && error.message || error) });
  }
};
