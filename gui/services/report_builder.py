"""
결과 리포트(HTML) 만들기

시뮬레이션 결과를 사람이 읽기 좋은 HTML 문서로 정리한다.
브라우저로 열어 인쇄하면 PDF로도 저장할 수 있다. (추가 라이브러리 필요 없음)

    build_report_html(result, images) → HTML 문자열
      images: {"map": "map.png", ...} 처럼 같은 폴더에 저장한 그림 파일 이름
"""

from __future__ import annotations

import html
from datetime import datetime

from services.result_loader import ALERT_KOREAN, SimulationResult, format_clock

STYLE = """
body { font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; margin: 32px auto; max-width: 980px;
       color: #222; line-height: 1.55; }
h1 { border-bottom: 3px solid #e8743b; padding-bottom: 6px; }
h2 { color: #c4561f; margin-top: 34px; border-left: 5px solid #e8743b; padding-left: 8px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 14px; }
th, td { border: 1px solid #ccc; padding: 5px 8px; text-align: center; }
th { background: #f6e3d8; }
.kpi { display: inline-block; background: #fbf1eb; border-radius: 8px; padding: 10px 16px; margin: 4px;
       min-width: 150px; }
.kpi b { display: block; font-size: 22px; color: #c4561f; }
.bad { color: #d32f2f; font-weight: bold; }
.good { color: #2e7d32; font-weight: bold; }
.note { color: #666; font-size: 13px; }
img { max-width: 100%; border: 1px solid #ddd; margin: 8px 0; }
"""

STATUS_KOREAN = {"HIKING": "경보 전", "EVACUATING": "대피 중", "SAFE": "대피 완료", "TRAPPED": "고립"}


def _esc(text) -> str:
    return html.escape(str(text))


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _kpi(label: str, value: str) -> str:
    return f'<div class="kpi">{_esc(label)}<b>{_esc(value)}</b></div>'


def _overview(result: SimulationResult) -> str:
    sc, r = result.summary["scenario"], result.summary["result"]
    ignitions = ", ".join(f"({x}, {y}) {t:g}분" for x, y, t in result.map.ignitions)
    weather = "직접 입력(고정값)" if sc["weather_mode"] == "fixed" else f"파일: {sc['weather_file'].split('/')[-1]}"
    rows = [["시나리오", _esc(sc["name"])], ["시작 시각", _esc(sc["start_datetime"])],
            ["진행 시간", f"{sc['duration_min']:g}분 (한 단계 {sc['time_step_min']:g}분)"],
            ["지도", f"{result.map.width} × {result.map.height}칸, 칸 {result.map.cell_size:g} m"],
            ["발화 지점", _esc(ignitions)], ["기상", _esc(weather)],
            ["난수 시드", str(sc["random_seed"])]]
    kpis = (_kpi("피해 면적", f"{r['burned_area_ha']:.1f} ha") + _kpi("최대 확산 속도", f"{r['max_spread_rate_m_min']:.1f} m/분")
            + _kpi("비화", f"{r['spot_fires']}회") + _kpi("종료", "자연 소멸" if r["fire_out"] else "연소 중"))
    return "<h2>1. 시나리오와 확산 결과</h2>" + _table(["항목", "값"], rows) + kpis


def _spread_table(result: SimulationResult) -> str:
    st = result.stats
    rows = []
    for i, t in enumerate(st["time_min"]):
        if int(round(t)) % 60 != 0 and i != len(st["time_min"]) - 1:
            continue
        clock = format_clock(result.map.start_time, t)
        rows.append([f"{t:.0f}분" + (f" ({clock})" if clock else ""), f"{st['burned_area_ha'][i]:.1f}",
                     f"{st['burning_cells'][i]:.0f}", f"{st['max_spread_rate_m_min'][i]:.2f}",
                     f"{st['wind_speed_ms'][i]:.1f} / {st['wind_dir_deg'][i]:.0f}°", f"{st['rh_pct'][i]:.0f}",
                     f"{st['dead_moisture_pct'][i]:.1f}"])
    return "<h3>시간별 확산</h3>" + _table(
        ["시각", "피해 면적 (ha)", "연소 중 셀", "최대 속도 (m/분)", "풍속 / 풍향", "습도 (%)", "연료 수분 (%)"], rows)


def _evacuation(result: SimulationResult) -> str:
    evac = result.evacuation
    if evac is None:
        return ""
    names = {n.id: n.name for n in result.map.nodes}
    rows = []
    for h in evac.hikers:
        route = " → ".join(names.get(i, str(i)) for i in h.route_node_ids) if h.route_found else "경로 없음"
        margin = "제한 없음" if h.min_margin is None else f"{h.min_margin:+.0f}분"
        status = STATUS_KOREAN.get(h.status, h.status)
        status_html = f'<span class="bad">{status}</span>' if h.at_risk else status
        rows.append([f"H{h.id} {_esc(h.name)}", f"{h.group_size}명",
                     f"{h.depart_time:.0f}분" if h.needs_evacuation else "-", status_html,
                     _esc(route), margin])
    s = evac.summary
    text = (f"<p>{s['hikers']}팀 {s['people']}명 중 대피 {s['evacuated']}팀, 대피 완료 {s['safe']}팀, "
            f"<span class='{'bad' if s['trapped'] else 'good'}'>고립 {s['trapped']}팀</span>, "
            f"위험 {s['at_risk_hikers']}팀 {s['at_risk_people']}명</p>")
    cfg = evac.settings
    note = (f"<p class='note'>경보 기준: 주의 &lt; {cfg['caution_min']:.0f}분, 대피준비 &lt; {cfg['prepare_min']:.0f}분, "
            f"즉시대피 &lt; {cfg['immediate_min']:.0f}분 (반경 {cfg['check_radius_m']:.0f} m), "
            f"발화 후 {cfg['notify_delay_min']:.0f}분 경보 → 전원 하산. 경보 단계: {', '.join(ALERT_KOREAN.values())}</p>")
    extra = ""
    mc = result.montecarlo
    if mc is not None and mc.evacuation is not None:
        c = mc.evacuation.summary
        extra = (f"<p><b>보수적 예측</b>(몬테카를로 {mc.runs}회 중 가장 이른 10% 도착 시각 기준): "
                 f"고립 {c['trapped']}팀, 위험 {c['at_risk_hikers']}팀 {c['at_risk_people']}명</p>")
    return ("<h2>2. 등산객 대피 안내</h2>" + text +
            _table(["팀", "인원", "출발", "결과", "추천 경로", "최소 안전 여유"], rows) + extra + note)


def _suppression(result: SimulationResult) -> str:
    sup = result.suppression
    if sup is None:
        return ""
    rows = []
    for i, s in enumerate(sup.strategies):
        rows.append([_esc(s.name), f"{s.burned_area_ha:.1f}", "기준" if i == 0 else f"{s.reduction_pct:.1f}% 감소",
                     f"{s.trail_burned_km:.2f}", f"{s.at_risk_hikers}팀 / {s.at_risk_people}명",
                     f"{s.spot_fires}", f"{len(s.drops)}"])
    best = min(sup.strategies, key=lambda s: (s.at_risk_people, s.burned_area_ha))
    cfg = sup.settings
    return ("<h2>3. 진화 전략 비교</h2>"
            f"<p>방화선 {len(sup.firebreak_cells)}칸({len(sup.firebreak_steps)}개 조각, {cfg['firebreak_ready_min']:.0f}분 완성), "
            f"헬기 {cfg['helicopters']}대({cfg['heli_interval_min']:.0f}분 간격). {_esc(sup.combined_plan_text())}</p>"
            + _table(["전략", "피해 면적 (ha)", "감소율", "등산로 소실 (km)", "위험 팀 / 인원", "비화", "헬기 살수"], rows)
            + f"<p>위험 인원과 피해 면적이 가장 작은 전략: <span class='good'>{_esc(best.name)}</span></p>")


def _monte_carlo(result: SimulationResult) -> str:
    mc = result.montecarlo
    if mc is None:
        return ""
    a, sd = mc.summary["area_ha"], mc.summary["weather_error_sd"]
    kpis = (_kpi("평균 피해 면적", f"{a['mean']:.1f} ha") + _kpi("표준편차", f"{a['sd']:.1f} ha")
            + _kpi("10% ~ 90% 범위", f"{a['p10']:.0f} ~ {a['p90']:.0f} ha") + _kpi("최대", f"{a['max']:.0f} ha"))
    return ("<h2>4. 몬테카를로 반복 실험</h2>"
            f"<p>같은 조건을 {mc.runs}번 반복하며 비화 난수와 기상 오차(풍속 ±{sd['wind_speed_ms']:g} m/s, "
            f"풍향 ±{sd['wind_dir_deg']:g}°, 습도 ±{sd['rh_pct']:g}%, 표준편차)를 바꿨다.</p>" + kpis)


def build_report_html(result: SimulationResult, images: dict[str, str]) -> str:
    """리포트 HTML 전체를 만든다. images 에 있는 그림만 넣는다."""
    captions = {"map": "지도 (저장할 때 재생 중이던 시각의 불 모습, 등산객·대피 경로)",
                "suppression": "진화 전략 비교 (왼쪽: 대응 없음, 오른쪽: 방화선 + 헬기)",
                "stats": "통계 그래프와 연소 확률 지도"}
    figures = "".join(f"<h3>{_esc(captions.get(key, key))}</h3><img src='{_esc(name)}'>"
                      for key, name in images.items())
    parts = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>",
        f"<title>산불 시뮬레이션 리포트 - {_esc(result.map.name)}</title><style>{STYLE}</style></head><body>",
        "<h1>🔥 산불 확산 예측 · 대피 안내 리포트</h1>",
        f"<p class='note'>생성: {datetime.now():%Y-%m-%d %H:%M} · 계산 엔진 {_esc(result.summary['engine_version'])}</p>",
        _overview(result), _spread_table(result), _evacuation(result), _suppression(result), _monte_carlo(result),
        "<h2>그림</h2>" + figures if figures else "",
        "<h2>참고</h2><p class='note'>확산 모델은 Rothermel(1972)을 단순화했고, 연료 파라미터·경보 기준·진화 효과 등 "
        "여러 값이 가정값이다. 근거와 가정의 구분은 docs/model.md 를 참고. 이 결과는 교육용 시뮬레이션이며 "
        "실제 재난 대응 판단에 그대로 쓰면 안 된다.</p>",
        "</body></html>",
    ]
    return "\n".join(parts)
