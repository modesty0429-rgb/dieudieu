"""
통계·그래프 화면

    ┌──────────── 피해 면적 ──────────┬──── 확산 속도·연소 셀 ────┐   ┌──── 연소 확률 지도 ────┐
    ├──────────── 기상·연료 수분 ─────┼──── 몬테카를로 분포 ──────┤   │ (몬테카를로 N회 중      │
    └─────────────────────────────────┴───────────────────────────┘   │  탄 비율, 0 ~ 100%)    │
                                                                       └────────────────────────┘
시간 그래프에는 현재 재생 시각을 세로선으로 표시한다.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

import theme
from services import map_render
from services.result_loader import SimulationResult

CURVE_COLORS = ["#e8743b", "#5aa9f0", "#4caf7a", "#f0d43a", "#b05cf0"]


def styled_plot(title: str, left: str, bottom: str = "시간 (분)") -> pg.PlotItem:
    """다크 테마에 맞춘 그래프 하나"""
    plot = pg.PlotItem(title=f"<span style='color:{theme.TEXT}'>{title}</span>")
    plot.showGrid(x=True, y=True, alpha=0.15)
    plot.setLabel("left", left, color=theme.TEXT_DIM)
    plot.setLabel("bottom", bottom, color=theme.TEXT_DIM)
    for axis in ("left", "bottom"):
        plot.getAxis(axis).setTextPen(theme.TEXT_DIM)
        plot.getAxis(axis).setPen(theme.BORDER)
    plot.addLegend(offset=(10, 10), labelTextColor=theme.TEXT)
    return plot


class StatsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: SimulationResult | None = None

        self.graphs = pg.GraphicsLayoutWidget()
        self.graphs.setBackground(theme.BACKGROUND)
        self.area_plot = styled_plot("피해 면적", "면적 (ha)")
        self.rate_plot = styled_plot("최대 확산 속도 · 연소 중인 셀", "m/분 · 칸 ÷ 10")
        self.weather_plot = styled_plot("기상 · 연료 수분", "m/s · % ")
        self.mc_plot = styled_plot("몬테카를로 피해 면적 분포", "회차 수", "최종 피해 면적 (ha)")
        self.graphs.addItem(self.area_plot, 0, 0)
        self.graphs.addItem(self.rate_plot, 0, 1)
        self.graphs.addItem(self.weather_plot, 1, 0)
        self.graphs.addItem(self.mc_plot, 1, 1)

        self.time_lines: list[pg.InfiniteLine] = []

        # 연소 확률 지도
        self.prob_plot = pg.PlotWidget(background=theme.BACKGROUND,
                                       title=f"<span style='color:{theme.TEXT}'>연소 확률 지도 (몬테카를로)</span>")
        self.prob_plot.setAspectLocked(True)
        self.prob_plot.invertY(True)
        self.prob_plot.hideButtons()
        self.prob_plot.setMenuEnabled(False)
        self.terrain_item = pg.ImageItem()
        self.prob_item = pg.ImageItem()
        self.prob_item.setZValue(10)
        self.prob_plot.addItem(self.terrain_item)
        self.prob_plot.addItem(self.prob_item)
        self.colormap = pg.colormap.get("inferno")
        self.prob_note = QLabel("")
        self.prob_note.setObjectName("dim")
        self.prob_note.setWordWrap(True)

        right = QVBoxLayout()
        right.addWidget(self.prob_plot, 1)
        right.addLayout(self._gradient_legend())
        right.addWidget(self.prob_note)
        right_widget = QWidget()
        right_widget.setLayout(right)

        self.summary_label = QLabel("결과가 없습니다.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("infoBar")

        body = QHBoxLayout()
        body.addWidget(self.graphs, 3)
        body.addWidget(right_widget, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addLayout(body, 1)

    def _gradient_legend(self) -> QHBoxLayout:
        """연소 확률 색 막대: 0% ━━━━ 100%"""
        values = np.tile(np.linspace(0.0, 1.0, 256), (12, 1))
        rgba = np.ascontiguousarray(self.colormap.map(values, mode="byte"))
        image = QImage(rgba.data, 256, 12, 256 * 4, QImage.Format.Format_RGBA8888).copy()
        bar = QLabel()
        bar.setPixmap(QPixmap.fromImage(image))
        row = QHBoxLayout()
        row.addWidget(QLabel("연소 확률 0%"))
        row.addWidget(bar)
        row.addWidget(QLabel("100%"))
        row.addStretch(1)
        return row

    # ------------------------------------------------------------------
    def _reset_plots(self) -> None:
        """그래프 4개를 비우고, 시간 그래프에 현재 시각 세로선을 다시 넣는다."""
        self.time_lines.clear()
        for plot in (self.area_plot, self.rate_plot, self.weather_plot, self.mc_plot):
            plot.clear()
            if plot.legend is not None:
                plot.legend.clear()
        for plot in (self.area_plot, self.rate_plot, self.weather_plot):
            line = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.TEXT_DIM, width=1,
                                                          style=pg.QtCore.Qt.PenStyle.DashLine))
            plot.addItem(line)
            self.time_lines.append(line)

    def set_result(self, result: SimulationResult | None) -> None:
        self.result = result
        self._reset_plots()
        self.prob_item.clear()
        self.terrain_item.clear()
        if result is None:
            self.summary_label.setText("결과가 없습니다.")
            self.prob_note.setText("")
            return
        self._draw_time_series(result)
        self._draw_monte_carlo(result)
        self._update_summary(result)
        self.set_time(0.0)

    def set_time(self, t: float) -> None:
        for line in self.time_lines:
            line.setValue(t)

    # ------------------------------------------------------------------
    def _draw_time_series(self, result: SimulationResult) -> None:
        st = result.stats
        t = st["time_min"]
        self.area_plot.plot(t, st["burned_area_ha"], pen=pg.mkPen(CURVE_COLORS[0], width=2.5), name="기준 시뮬레이션")
        if result.suppression is not None:
            # 전략별 최종 면적을 점으로 (시간별 기록은 없으므로 끝 시각에 표시)
            for i, s in enumerate(result.suppression.strategies[1:], start=1):
                self.area_plot.plot([t[-1]], [s.burned_area_ha], pen=None, symbol="o", symbolSize=9,
                                    symbolBrush=CURVE_COLORS[i], name=f"{s.name} (최종)")

        self.rate_plot.plot(t, st["max_spread_rate_m_min"], pen=pg.mkPen(CURVE_COLORS[0], width=2),
                            name="최대 확산 속도 (m/분)")
        self.rate_plot.plot(t, st["burning_cells"] / 10.0, pen=pg.mkPen(CURVE_COLORS[1], width=2),
                            name="연소 중인 셀 ÷ 10")

        self.weather_plot.plot(t, st["wind_speed_ms"], pen=pg.mkPen(CURVE_COLORS[1], width=2), name="풍속 (m/s)")
        self.weather_plot.plot(t, st["rh_pct"] / 5.0, pen=pg.mkPen(CURVE_COLORS[2], width=2), name="습도 ÷ 5 (%)")
        self.weather_plot.plot(t, st["dead_moisture_pct"], pen=pg.mkPen(CURVE_COLORS[3], width=2),
                               name="연료 수분 (%)")

    def _draw_monte_carlo(self, result: SimulationResult) -> None:
        mc = result.montecarlo
        if mc is None:
            self.mc_plot.setTitle(f"<span style='color:{theme.TEXT_DIM}'>몬테카를로 결과 없음 "
                                  "(설정에서 '몬테카를로 포함'을 켜고 실행)</span>")
            self.prob_note.setText("몬테카를로 결과가 없습니다.")
            return
        self.mc_plot.setTitle(f"<span style='color:{theme.TEXT}'>몬테카를로 {mc.runs}회 피해 면적 분포</span>")
        counts, edges = np.histogram(mc.areas, bins=12)
        bars = pg.BarGraphItem(x0=edges[:-1], x1=edges[1:], height=counts,
                               brush=pg.mkBrush(232, 116, 59, 180), pen=pg.mkPen(theme.BACKGROUND))
        self.mc_plot.addItem(bars)
        area = mc.summary["area_ha"]
        # 세로선 이름이 겹치지 않도록 높이(position)를 다르게
        for value, label, color, height in ((result.summary["result"]["burned_area_ha"], "기준", "#ffffff", 0.95),
                                            (area["p10"], "10%", theme.TEXT_DIM, 0.82),
                                            (area["p90"], "90%", theme.TEXT_DIM, 0.70)):
            line = pg.InfiniteLine(pos=value, angle=90, pen=pg.mkPen(color, width=1.5,
                                                                     style=pg.QtCore.Qt.PenStyle.DashLine),
                                   label=label, labelOpts={"color": color, "position": height})
            self.mc_plot.addItem(line)

        # 연소 확률 지도: 어둡게 한 지형 위에 확률 0 은 투명, 나머지는 색
        m = result.map
        shade = map_render.terrain_image(m.elevation, m.fuel, m.cell_size, show_fuel=False)
        self.terrain_item.setImage((shade * 0.6).astype(np.uint8), levels=(0, 255))
        self.terrain_item.setRect(0, 0, m.width, m.height)
        rgba = self.colormap.map(mc.burn_probability, mode="byte")
        rgba[..., 3] = np.where(mc.burn_probability > 0, 215, 0)
        self.prob_item.setImage(rgba, levels=(0, 255))
        self.prob_item.setRect(0, 0, m.width, m.height)
        self.prob_plot.setRange(xRange=(0, m.width), yRange=(0, m.height), padding=0.02)

        sure = float(np.count_nonzero(mc.burn_probability >= 0.9)) * result.cell_area_ha
        any_burn = float(np.count_nonzero(mc.burn_probability > 0)) * result.cell_area_ha
        self.prob_note.setText(
            f"{mc.runs}회 중 한 번이라도 탄 면적 {any_burn:.0f} ha, 90% 이상 확률로 타는 면적 {sure:.0f} ha. "
            f"기상 오차: 풍속 ±{mc.summary['weather_error_sd']['wind_speed_ms']:g} m/s, "
            f"풍향 ±{mc.summary['weather_error_sd']['wind_dir_deg']:g}°, "
            f"습도 ±{mc.summary['weather_error_sd']['rh_pct']:g}% (표준편차)")

    def _update_summary(self, result: SimulationResult) -> None:
        r = result.summary["result"]
        parts = [f"기준 시뮬레이션: 피해 {r['burned_area_ha']:.1f} ha, 최대 확산 속도 "
                 f"{r['max_spread_rate_m_min']:.1f} m/분, 비화 {r['spot_fires']}회"]
        if result.montecarlo is not None:
            a = result.montecarlo.summary["area_ha"]
            parts.append(f"몬테카를로 {result.montecarlo.runs}회: 평균 {a['mean']:.1f} ha "
                         f"(표준편차 {a['sd']:.1f}), 80% 범위 {a['p10']:.1f} ~ {a['p90']:.1f} ha")
        self.summary_label.setText("  |  ".join(parts))
