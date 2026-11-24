// ============================================================
// 휴대폰 앱 자동 테스트 (Node 18 이상): node tools/mobile_test.mjs
//   앱이 쓰는 모듈(geo·ini·trails·fireinfo·engine_core)을 그대로 불러와,
//   휴대폰과 똑같은 방법으로 C 엔진(wildfire.wasm)을 실행해 본다.
//   tools/run_tests.py 가 이 파일도 실행한다.
// ============================================================
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const M = (p) => import(path.join(ROOT, 'mobile', 'js', p));
const { latLonToCell, cellToLatLon } = await M('geo.js');
const { parseIni, buildScenario, writeIni } = await M('ini.js');
const { parseTrails, attachMe, writeTrailFile, writeHikerFile, ME_NODE_ID } = await M('trails.js');
const { encodeFire, decodeFire } = await M('fireinfo.js');
const { runEngine } = await M('engine_core.js');

let pass = 0;
let fail = 0;
function check(name, ok, detail = '') {
  if (ok) { pass++; console.log(`  [통과] ${name}`); } else { fail++; console.log(`  [실패] ${name} ${detail}`); }
}
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

console.log('\n[휴대폰 앱] 모듈 + WebAssembly 엔진');
const meta = JSON.parse(read('mobile/assets/bukhansan/meta.json'));

// 1) 좌표 변환: 정상 위경도 → 칸 → 위경도
const s = latLonToCell(meta, meta.summit_latlon[0], meta.summit_latlon[1]);
const back = cellToLatLon(meta, s.x, s.y);
check('위경도 ↔ 칸 좌표 (북한산 백운대)', Math.round(s.x) === meta.summit_cell[0] && Math.round(s.y) === meta.summit_cell[1]
      && Math.abs(back.lat - meta.summit_latlon[0]) < 1e-9, `${s.x},${s.y}`);

// 2) 발화 정보 링크
const time = new Date(2026, 3, 5, 13, 0);
const link = 'https://example.github.io/dieudieu/mobile/#' + encodeFire({ mountain: 'bukhansan', lat: 37.64512, lon: 126.96001, time,
  weather: { windMs: 6, windDir: 270, rhPct: 25, tempC: 18 } });
const got = decodeFire('[산불 알림] 아래 링크를 누르세요 ' + link);
check('발화 정보 링크 만들기·읽기 (문자 속 링크도)', got && got.mountain === 'bukhansan' && got.time.getTime() === time.getTime()
      && got.weather.windDir === 270 && Math.abs(got.lat - 37.64512) < 1e-9, link);
check('틀린 링크는 무시', decodeFire('m=bukhansan&fire=abc&t=x') === null);

// 3) 내 위치를 등산로에 붙이기 (등산로 한가운데)
const graph = parseTrails(read(meta.files.trails.replace('../', '')));
const e = graph.edges.find((g) => g.points.length >= 2 && Math.hypot(g.points[0][0] - g.points.at(-1)[0], g.points[0][1] - g.points.at(-1)[1]) > 8);
const mid = [(e.points[0][0] + e.points.at(-1)[0]) / 2, (e.points[0][1] + e.points.at(-1)[1]) / 2];
const attached = attachMe(graph, mid[0] + 0.4, mid[1] - 0.3);
check('등산로 가운데의 내 위치 → 새 지점 + 간선 2개', attached && attached.startId === ME_NODE_ID
      && attached.graph.edges.length === graph.edges.length + 1);
check('등산로에서 먼 곳은 null', attachMe(graph, 5, 5) === null);

// 4) C 엔진을 휴대폰과 같은 방법으로 실행 (북한산, 봄 13:00, 정상 남서쪽 발화)
const module = await WebAssembly.compile(fs.readFileSync(path.join(ROOT, 'mobile/engine/wildfire.wasm')));
const base = parseIni(read(meta.files.scenario.replace('../', '')));
const fireCell = latLonToCell(meta, got.lat, got.lon);
const scenario = buildScenario(base, { fire: { cell: fireCell, time }, weather: got.weather, meta, noticeMin: 10 });
const files = {
  'scenario.ini': writeIni(scenario),
  'elev.asc': read(meta.files.elevation.replace('../', '')),
  'fuel.asc': read(meta.files.fuel.replace('../', '')),
  'fuel_models.csv': read('data/scenarios/fuel_models.csv'),
  'trails.txt': writeTrailFile(attached.graph),
  'hikers.txt': writeHikerFile(attached.startId, 3.5, 2),
};
const lines = [];
const r = await runEngine(module, files, ['--mode', 'evac'], (l) => lines.push(l));
check('WebAssembly 엔진 실행 (종료 코드 0)', r.code === 0, lines.filter((l) => l.includes('ERROR')).join(' / '));
if (r.code === 0) {
  const evac = JSON.parse(r.outputs['evacuation.json']);
  const summary = JSON.parse(r.outputs['summary.json']);
  const arrival = r.outputs['arrival_time.csv'].trim().split('\n');
  check('결과 파일 (대피·요약·도착 시각 300줄)', evac.hikers.length === 1 && arrival.length === meta.height
        && summary.result.burned_area_ha > 0, `${summary.result?.burned_area_ha} ha`);
  check('내 팀 대피 경로', evac.hikers[0].route.found && evac.hikers[0].route.nodes[0] === ME_NODE_ID,
        JSON.stringify(evac.hikers[0].route));
  check('낮/밤: 북한산 위치로 일몰 계산', summary.daylight && JSON.stringify(summary.daylight).includes('sunset'));
  console.log(`  (참고) 피해 ${summary.result.burned_area_ha} ha, 경로 ${evac.hikers[0].route.exit_name} ` +
              `${evac.hikers[0].route.travel_time_min.toFixed(0)}분, 엔진 ${r.ms} ms`);
}

// 5) 날씨를 못 받으면 계절 평년 날씨 + 겨울 눈
const winter = buildScenario(base, { fire: { cell: fireCell, time: new Date(2026, 0, 15, 13, 0) }, weather: null, meta, noticeMin: 0 });
const r2 = await runEngine(module, { ...files, 'scenario.ini': writeIni(winter) }, ['--mode', 'evac']);
const sum2 = r2.code === 0 ? JSON.parse(r2.outputs['summary.json']) : null;
check('날씨 없음 → 계절 평년 날씨 (1월 → 겨울, 북한산 눈 경계 600 m)',
      sum2 && sum2.season.key === 'winter' && sum2.season.weather_from_season && sum2.season.snow_line_m === 600,
      JSON.stringify(sum2?.season));

console.log(`\n결과: ${pass}/${pass + fail} 통과`);
process.exit(fail ? 1 : 0);
