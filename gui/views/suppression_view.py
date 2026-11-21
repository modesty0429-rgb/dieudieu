"""
진화 전략 비교 화면

    ┌──────────────────────── 전략 비교표 ─────────────────────────┐
    │ 전략 | 피해 면적 | 감소율 | 등산로 소실 | 위험 팀/인원 | 비화 | 살수 │
    ├──────────── 왼쪽 지도 ─────────┬──────── 오른쪽 지도 ─────────┤
    │ [대응 없음 ▼]                  │ [방화선 + 헬기 ▼]             │
    │  (같은 시각의 불 모습)          │  (방화선 = 흰 칸, 살수 = 하늘색) │
    └────────────────────────────────┴──────────────────────────────┘

두 지도는 확대·이동이 함께 움직이고(링크), 재생 시각도 지도 탭과 같다.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

import theme
from services import map_render
from services.result_loader import MapData, StrategyResult, SuppressionData

COLUMNS = ["전략", "피해 면적", "감소율", "등산로 소실", "위험 팀 / 인원", "고립", "비화", "헬기 살수"]
DROP_COLOR = (90, 210, 255)


class StrategyMap(QWidget):
    """전략 하나의 불 모습을 보여 주는 작은 지도"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.map: MapData | None = None
        self.strategy: StrategyResult | None = None
        self.firebreak: list[tuple[int, int]] = []
        self.time = 0.0

        self.combo = QComboBox()
        self.area_label = QLabel("")
        self.area_label.setObjectName("statusText")
        top = QHBoxLayout()
        top.addWidget(QLabel(title))
        top.addWidget(self.combo, 1)
        top.addWidget(self.area_label)

        self.plot = pg.PlotWidget(background=theme.BACKGROUND)
        self.plot.setAspectLocked(True)
        self.plot.invertY(True)
        self.plot.hideButtons()
        self.plot.setMenuEnabled(False)
        self.plot.getAxis("left").setTextPen(theme.TEXT_DIM)
        self.plot.getAxis("bottom").setTextPen(theme.TEXT_DIM)
        self.terrain_item = pg.ImageItem()
        self.fire_item = pg.ImageItem()
        self.fire_item.setZValue(10)
        self.firebreak_item = pg.ScatterPlotItem(size=5, symbol="s", pxMode=True, pen=None,
                                                 brush=pg.mkBrush(*theme.FIREBREAK))
        self.firebreak_item.setZValue(20)
        self.drop_item = pg.ScatterPlotItem(symbol="o", pen=pg.mkPen(*DROP_COLOR, width=2), brush=None)
        self.drop_item.setZValue(30)
        for item in (self.terrain_item, self.fire_item, self.firebreak_item, self.drop_item):
            self.plot.addItem(item)
        self.trail_items: list[pg.PlotDataItem] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self.plot, 1)

    def set_map(self, map_data: MapData) -> None:
        self.map = map_data
        image = map_render.terrain_image(map_data.elevation, map_data.fuel, map_data.cell_size)
        # 불이 잘 보이도록 바탕을 조금 어둡게
        self.terrain_item.setImage((image * 0.75).astype(np.uint8), levels=(0, 255))
        self.terrain_item.setRect(0, 0, map_data.width, map_data.height)
        for item in self.trail_items:
            self.plot.removeItem(item)
        self.trail_items.clear()
        pen = pg.mkPen(*theme.TRAIL_COLOR, 160, width=1.2, style=Qt.PenStyle.DashLine)
        for edge in map_data.edges:
            item = pg.PlotDataItem([x + 0.5 for x, _ in edge.points], [y + 0.5 for _, y in edge.points], pen=pen)
            item.setZValue(15)
            self.plot.addItem(item)
            self.trail_items.append(item)
        self.plot.setRange(xRange=(0, map_data.width), yRange=(0, map_data.height), padding=0.02)

    def set_strategy(self, strategy: StrategyResult | None) -> None:
        """전략을 바꾼다. 방화선은 전략마다 다를 수 있으므로 그 전략의 방화선을 그린다."""
        self.strategy = strategy
        self.firebreak = strategy.firebreak_cells if strategy is not None and strategy.use_firebreak else []
        xs = [x + 0.5 for x, _ in self.firebreak]
        ys = [y + 0.5 for _, y in self.firebreak]
        self.firebreak_item.setData(xs, ys)
        self.set_time(self.time)

    def set_time(self, t: float) -> None:
        self.time = t
        if self.strategy is None or self.map is None:
            self.fire_item.clear()
            self.drop_item.clear()
            self.area_label.setText("")
            return
        s = self.strategy
        overlay = map_render.fire_overlay(s.arrival, s.burnout, t)
        self.fire_item.setImage(overlay, levels=(0, 255))
        self.fire_item.setRect(0, 0, self.map.width, self.map.height)

        # 지금까지 뿌린 물: 최근 것일수록 크고 진하게
        drops = s.drops[s.drops[:, 0] <= t] if len(s.drops) else s.drops
        spots = []
        radius_px = 14
        for time_min, x, y in drops:
            age = t - time_min
            alpha = 230 if age < 45 else 90
            spots.append({"pos": (x + 0.5, y + 0.5), "size": radius_px,
                          "pen": pg.mkPen(*DROP_COLOR, alpha, width=2)})
        self.drop_item.setData(spots)

        cell_area = self.map.cell_size ** 2 / 10000.0
        area = float(np.count_nonzero((s.arrival >= 0) & (s.arrival <= t))) * cell_area
        self.area_label.setText(f"피해 {area:6.1f} ha")


class SuppressionView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: SuppressionData | None = None

        self.info_label = QLabel("진화 전략 결과가 없습니다. 왼쪽에서 '진화 전략 비교 포함'을 켜고 실행하세요.")
        self.info_label.setWordWrap(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(170)

        self.left = StrategyMap("왼쪽:")
        self.right = StrategyMap("오른쪽:")
        self.right.plot.setXLink(self.left.plot)     # 확대·이동을 함께
        self.right.plot.setYLink(self.left.plot)
        self.left.combo.currentIndexChanged.connect(lambda: self._on_combo(self.left))
        self.right.combo.currentIndexChanged.connect(lambda: self._on_combo(self.right))

        maps = QHBoxLayout()
        maps.addWidget(self.left, 1)
        maps.addWidget(self.right, 1)

        legend = QLabel(f'<span style="color:rgb{theme.FIREBREAK}">■</span> 방화선   '
                        f'<span style="color:rgb{DROP_COLOR}">○</span> 헬기 살수 (최근 45분은 진하게)   '
                        f'<span style="color:rgb{theme.FIRE_OLD}">■</span> 연소 중   '
                        f'<span style="color:rgb(90,90,90)">■</span> 전소')
        legend.setObjectName("dim")

        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.table)
        layout.addLayout(maps, 1)
        layout.addWidget(legend)

    # ------------------------------------------------------------------
    def set_data(self, data: SuppressionData | None, map_data: MapData | None) -> None:
        self.data = data
        self.table.setRowCount(0)
        for view in (self.left, self.right):
            view.combo.blockSignals(True)
            view.combo.clear()
            view.combo.blockSignals(False)
            view.set_strategy(None)
        if data is None or map_data is None:
            self.info_label.setText("진화 전략 결과가 없습니다. 왼쪽에서 '진화 전략 비교 포함'을 켜고 실행하세요.")
            return

        cfg = data.settings
        self.info_label.setText(
            f"방화선 {len(data.firebreak_cells)}칸 ({len(data.firebreak_steps)}개 조각, "
            f"{cfg['firebreak_ready_min']:.0f}분 완성, 탐욕법)  ·  {data.combined_plan_text()}<br>"
            f"헬기 {cfg['helicopters']}대 (반경 {cfg['heli_radius_cells']}칸, {cfg['heli_interval_min']:.0f}분 간격, "
            f"첫 살수 {cfg['first_drop_min']:.0f}분, 효과 {cfg['heli_effect_min']:.0f}분)")
        self._fill_table(data)
        for view in (self.left, self.right):
            view.set_map(map_data)
            view.combo.blockSignals(True)
            for s in data.strategies:
                view.combo.addItem(s.name, s.key)
            view.combo.blockSignals(False)
        self.left.combo.setCurrentIndex(0)                          # 대응 없음
        self.right.combo.setCurrentIndex(len(data.strategies) - 1)  # 방화선 + 헬기
        self._on_combo(self.left)
        self._on_combo(self.right)

    def update_time(self, t: float) -> None:
        self.left.set_time(t)
        self.right.set_time(t)

    # ------------------------------------------------------------------
    def _fill_table(self, data: SuppressionData) -> None:
        best_area = min(s.burned_area_ha for s in data.strategies)
        best_risk = min(s.at_risk_people for s in data.strategies)
        self.table.setRowCount(len(data.strategies))
        for row, s in enumerate(data.strategies):
            values = [s.name, f"{s.burned_area_ha:.1f} ha", f"{s.reduction_pct:.1f}% 감소" if row else "기준",
                      f"{s.trail_burned_km:.2f} km", f"{s.at_risk_hikers}팀 / {s.at_risk_people}명",
                      f"{s.trapped_hikers}팀", f"{s.spot_fires}회", f"{len(s.drops)}회"]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
            if s.burned_area_ha == best_area:
                self.table.item(row, 1).setForeground(QBrush(QColor(theme.SUCCESS)))
            if s.at_risk_people == best_risk:
                self.table.item(row, 4).setForeground(QBrush(QColor(theme.SUCCESS)))
            elif s.at_risk_people > 0:
                self.table.item(row, 4).setForeground(QBrush(QColor(theme.ERROR)))

    def _on_combo(self, view: StrategyMap) -> None:
        if self.data is None:
            return
        view.set_strategy(self.data.by_key(view.combo.currentData()))
