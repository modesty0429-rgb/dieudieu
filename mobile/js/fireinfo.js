// ============================================================
// fireinfo.js — "발화 정보" 주고받기
//   관제(PC GUI 의 '휴대폰으로 보내기' 또는 다른 휴대폰)가 보내는 아주 작은 정보:
//     산, 발화 지점 위경도, 발화 시각, (있으면) 바람·습도·기온
//   링크 예: https://…/mobile/#m=bukhansan&fire=37.65120,126.98010&t=2026-11-24T14:30&w=6,270,25,12
//   글자 수가 100자 남짓이라 문자(SMS)·카카오톡·QR 로도 보낼 수 있고, 데이터가 잠깐만 잡혀도 받는다.
//   받은 뒤의 계산(확산·대피·경보)은 전부 휴대폰 안의 C 엔진이 오프라인으로 한다.
// ============================================================

const pad = (n) => String(n).padStart(2, '0');

function localStamp(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 발화 정보 → 링크 뒤에 붙는 글 (m=…&fire=…) */
export function encodeFire(info) {
  const parts = [`m=${info.mountain}`, `fire=${info.lat.toFixed(5)},${info.lon.toFixed(5)}`, `t=${localStamp(info.time)}`];
  if (info.weather) {
    const w = info.weather;
    parts.push(`w=${w.windMs},${w.windDir},${w.rhPct},${w.tempC}`);
  }
  return parts.join('&');
}

/** 링크·문자 전체에서 발화 정보를 찾는다. 없거나 틀리면 null */
export function decodeFire(text) {
  if (!text) return null;
  const at = text.search(/[#?&]?m=/);
  if (at < 0) return null;
  const params = new URLSearchParams(text.slice(at).replace(/^[#?&]/, '').split(/\s/)[0]);
  const fire = (params.get('fire') || '').split(',').map(Number);
  const m = (params.get('t') || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
  if (!params.get('m') || fire.length !== 2 || fire.some((v) => !Number.isFinite(v)) || !m) return null;
  const info = {
    mountain: params.get('m'),
    lat: fire[0],
    lon: fire[1],
    time: new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]),
    weather: null,
  };
  const w = (params.get('w') || '').split(',').map(Number);
  if (w.length === 4 && w.every(Number.isFinite)) {
    info.weather = { windMs: w[0], windDir: w[1], rhPct: w[2], tempC: w[3] };
  }
  return info;
}

/** 화면 표시용 바람 방향 이름 (불어오는 방향) */
export function windName(deg) {
  const names = ['북', '북동', '동', '남동', '남', '남서', '서', '북서'];
  return names[Math.round((((deg % 360) + 360) % 360) / 45) % 8] + '풍';
}
