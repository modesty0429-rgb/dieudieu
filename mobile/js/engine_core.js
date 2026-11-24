// ============================================================
// engine_core.js — C 엔진(wildfire.wasm)을 메모리 속 파일로 실행
//   C 코드를 WebAssembly(WASI)로 컴파일한 것을 그대로 돌린다. (tools/build_wasm.sh)
//   엔진은 PC 와 똑같이 fopen 으로 파일을 읽고 쓰는데, 그 파일들을 브라우저 메모리에 만들어 준다.
//   브라우저(Web Worker)와 Node(자동 테스트) 둘 다에서 쓴다.
// ============================================================

import WASI from '../vendor/browser_wasi_shim/wasi.js';
import { File, Directory, PreopenDirectory, OpenFile, ConsoleStdout } from '../vendor/browser_wasi_shim/fs_mem.js';

const enc = new TextEncoder();
const dec = new TextDecoder('utf-8');

/**
 * module : WebAssembly.Module (wildfire.wasm)
 * files  : { 'scenario.ini': 글 또는 Uint8Array, 'elev.asc': …, … }
 * args   : 엔진 명령줄 인자 (scenario.ini 다음부터), 예: ['--mode', 'evac']
 * onLine : 엔진이 한 줄 출력할 때마다 (진행률 표시용)
 * 반환   : { code, outputs: { 'summary.json': 글, … }, ms }
 */
export async function runEngine(module, files, args, onLine = () => {}) {
  const contents = new Map();
  for (const [name, data] of Object.entries(files)) {
    contents.set(name, new File(typeof data === 'string' ? enc.encode(data) : data, { readonly: true }));
  }
  const root = new PreopenDirectory('/w', contents);
  const fds = [
    new OpenFile(new File([])),                       // 표준입력 (안 씀)
    ConsoleStdout.lineBuffered((line) => onLine(line)),
    ConsoleStdout.lineBuffered((line) => onLine(line)),
    root,
  ];
  const wasi = new WASI(['wildfire', '/w/scenario.ini', ...args, '--out', '/w/out'], [], fds, { debug: false });
  const instance = await WebAssembly.instantiate(module, { wasi_snapshot_preview1: wasi.wasiImport });
  const t0 = Date.now();
  const code = wasi.start(instance);
  const outputs = {};
  const out = root.dir.contents.get('out');
  if (out instanceof Directory) {
    for (const [name, entry] of out.contents) {
      if (entry instanceof File) outputs[name] = dec.decode(entry.data);
    }
  }
  return { code, outputs, ms: Date.now() - t0 };
}
