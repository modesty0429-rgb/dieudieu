"""
메인 지도

위에서 내려다본 산 지형 위에 여러 레이어를 겹쳐 그린다. (아래 → 위 순서)
    1) 바탕: 음영기복 + 연료 색          (ImageItem)
    2) 등고선 (100 m 간격)               (IsocurveItem)
    3) 불: 연소 중(노랑→빨강), 전소(검정) (ImageItem, 투명 배경)
    4) 불 도착 등시선 (60분 간격)          (IsocurveItem)
    5) 등산로, 노드, 노드 이름
    6) 대피 경로 (팀별, 선택한 팀은 굵게)
    7) 등산객(경보 단계 색, 시각에 따라 이동), 발화 지점

좌표: 격자 셀 (x, y) 는 화면에서 [x, x+1] × [y, y+1] 사각형이다. 점은 셀 중심(x+0.5, y+0.5)에 찍는다.
y 축을 뒤집어(invertY) y = 0(북쪽)이 위에 오게 한다.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import theme
from services import daylight_render, map_render
from services.result_loader import MapData, SimulationResult

pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)

CONTOUR_STEP_M = 100        # 등고선 간격
ISOCHRONE_STEP_MIN = 60     # 불 도착 등시선 간격


class MapView(QWidget):
    cell_clicked = Signal(int, int)     # 지도를 클릭한 셀 (x, y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.map: MapData | None = None
        self.result: SimulationResult | None = None
        self.time = 0.0
        self._contours: list[pg.IsocurveItem] = []
        self._isochrones: list[pg.IsocurveItem] = []
        self._node_labels: list[pg.TextItem] = []
        self._route_items: dict[int, pg.PlotDataItem] = {}   # 팀 id → 경로 선
        self._hiker_labels: list[pg.TextItem] = []
        self.selected_hiker = -1
        self.evacuation = None     # 지도에 그릴 대피 결과 (기본 예측 또는 보수적 예측)

        self._build_plot()
        self._build_controls()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.controls)
        layout.addWidget(self.plot, 1)
        layout.addWidget(self.info_label)
        layout.addWidget(self.legend_label)

    # ------------------------------------------------------------------
    # 화면 구성
    # ------------------------------------------------------------------
    def _build_plot(self) -> None:
        self.plot = pg.PlotWidget(background=theme.BACKGROUND)
        self.plot.setAspectLocked(True)
        self.plot.invertY(True)
        self.plot.hideButtons()
        self.plot.setMenuEnabled(False)
        for axis in ("left", "bottom"):
            self.plot.getAxis(axis).setTextPen(theme.TEXT_DIM)
            self.plot.getAxis(axis).setPen(theme.BORDER)

        self.terrain_item = pg.ImageItem()
        self.fire_item = pg.ImageItem()
        self.fire_item.setZValue(10)
        # (8단계) 낮/밤: 지도 전체를 덮는 어둠·노을 + 어두울 때 불 주변의 빛. 불은 그 위에 그려서 밤에 더 또렷하다
        self.night_item = pg.ImageItem()
        self.night_item.setZValue(8)
        self.glow_item = pg.ImageItem()
        self.glow_item.setZValue(9)
        self.plot.addItem(self.terrain_item)
        self.plot.addItem(self.night_item)
        self.plot.addItem(self.glow_item)
        self.plot.addItem(self.fire_item)

        self.trail_items: list[pg.PlotDataItem] = []
        self.node_item = pg.ScatterPlotItem(size=11, pen=pg.mkPen("k", width=1))
        self.node_item.setZValue(30)
        self.hiker_item = pg.ScatterPlotItem(size=13, symbol="d", pen=pg.mkPen("k", width=1.5),
                                             brush=pg.mkBrush(255, 255, 255))
        self.hiker_item.setZValue(40)
        self.ignition_item = pg.ScatterPlotItem(size=20, symbol="star", pen=pg.mkPen("w", width=1),
                                                brush=pg.mkBrush(*theme.IGNITION_COLOR))
        self.ignition_item.setZValue(50)
        for item in (self.node_item, self.hiker_item, self.ignition_item):
            self.plot.addItem(item)

        scene = self.plot.scene()
        scene.sigMouseMoved.connect(self._on_mouse_moved)
        scene.sigMouseClicked.connect(self._on_mouse_clicked)

        self.info_label = QLabel("지도 위에 마우스를 올리면 셀 정보가 보입니다. 클릭하면 발화 지점으로 지정됩니다.")
        self.info_label.setObjectName("infoBar")
        self.legend_label = QLabel(self._legend_html())
        self.legend_label.setObjectName("dim")

    def _build_controls(self) -> None:
        """레이어 켜기/끄기 체크박스"""
        self.controls = QHBoxLayout()
        self.controls.addWidget(QLabel("레이어:"))
        self.check_fuel = self._add_check("연료 색", True, self._redraw_terrain)
        self.check_contour = self._add_check("등고선", True, self._update_contour_visibility)
        self.check_fire = self._add_check("불", True, self._redraw_fire)
        self.check_isochrone = self._add_check("도착 등시선(60분)", False, self._update_isochrone_visibility)
        self.check_trails = self._add_check("등산로", True, self._update_trail_visibility)
        self.check_hikers = self._add_check("등산객", True, self._update_hiker_visibility)
        self.check_routes = self._add_check("대피 경로", True, self._update_route_visibility)
        self.check_night = self._add_check("낮/밤", True, self._redraw_night)
        self.controls.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusText")
        self.controls.addWidget(self.status_label)

    def _add_check(self, text: str, checked: bool, slot) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(checked)
        box.toggled.connect(lambda _checked: slot())
        self.controls.addWidget(box)
        return box

    @staticmethod
    def _legend_html() -> str:
        def chip(rgb, label):
            return f'<span style="color:rgb{tuple(rgb)}">■</span> {label}'
        fuels = [chip(theme.FUEL_COLORS[c], theme.FUEL_NAMES[c]) for c in (1, 2, 3, 4, 5, 7, 8, 9)]
        alerts = "".join(f'<span style="color:{color}">◆</span>' for color in theme.ALERT_COLORS.values())
        fire = [chip(theme.FIRE_NEW, "막 붙은 불"), chip(theme.FIRE_OLD, "연소 중"), chip((90, 90, 90), "전소"),
                chip(theme.IGNITION_COLOR, "★ 발화 지점"), f"{alerts} 등산객(정상→고립)",
                chip(theme.NODE_COLORS["PARKING"], "● 주차장"), chip(theme.NODE_COLORS["SHELTER"], "● 대피소")]
        return "  ".join(fuels) + "<br>" + "  ".join(fire)

    # ------------------------------------------------------------------
    # 데이터 설정
    # ------------------------------------------------------------------
    def set_map(self, map_data: MapData) -> None:
        """새 지도를 그린다. (결과는 지움)"""
        self.map = map_data
        self.result = None
        self.time = 0.0
        self._redraw_terrain()
        self._draw_contours()
        self._draw_trails()
        self._draw_hikers()
        self.set_ignitions(map_data.ignitions)
        self._clear_routes()
        self._clear_isochrones()
        self.fire_item.clear()
        self.night_item.clear()
        self.glow_item.clear()
        self.status_label.setText("")
        self.plot.setRange(xRange=(0, map_data.width), yRange=(0, map_data.height), padding=0.02)

    def set_result(self, result: SimulationResult) -> None:
        """시뮬레이션 결과를 붙인다. 지도가 다르면 지도부터 다시 그린다."""
        if self.map is None or self.map.elevation.shape != result.map.elevation.shape:
            self.set_map(result.map)
        else:
            self.map = result.map
            self._draw_trails()
            self._draw_hikers()
            self.set_ignitions(result.map.ignitions)
        self.result = result
        self.evacuation = result.evacuation
        self.selected_hiker = -1
        self._draw_isochrones()
        self._draw_routes()
        self.set_time(0.0)

    def set_time(self, t: float) -> None:
        """시각 t 의 불 모습을 그린다."""
        self.time = t
        self._redraw_fire()
        self._redraw_night()
        self._draw_hikers()
        if self.result is not None:
            text = f"피해 {self.result.burned_area_at(t):7.1f} ha  |  연소 중 {self.result.burning_cells_at(t):4d}칸"
            sun = self.result.sun_at(t)
            if sun is not None:
                _, name, icon = daylight_render.sun_phase(sun[0])
                text += f"  |  {icon} {name} (해 고도 {sun[0]:+.0f}°)"
            self.status_label.setText(text)

    def set_ignitions(self, ignitions: list[tuple[int, int, float]]) -> None:
        """발화 지점 표시 (클릭으로 새로 고를 때도 사용)"""
        xs = [x + 0.5 for x, _, _ in ignitions]
        ys = [y + 0.5 for _, y, _ in ignitions]
        self.ignition_item.setData(xs, ys)

    # ------------------------------------------------------------------
    # 레이어 그리기
    # ------------------------------------------------------------------
    def _redraw_terrain(self) -> None:
        if self.map is None:
            return
        image = map_render.terrain_image(self.map.elevation, self.map.fuel, self.map.cell_size,
                                         show_fuel=self.check_fuel.isChecked())
        self.terrain_item.setImage(image, levels=(0, 255))
        self.terrain_item.setRect(0, 0, self.map.width, self.map.height)

    def _draw_contours(self) -> None:
        for item in self._contours:
            self.plot.removeItem(item)
        self._contours.clear()
        if self.map is None:
            return
        elevation = self.map.elevation
        start = np.ceil(elevation.min() / CONTOUR_STEP_M) * CONTOUR_STEP_M
        for level in np.arange(start, elevation.max(), CONTOUR_STEP_M):
            major = int(level) % 500 == 0
            pen = pg.mkPen(255, 255, 255, 90 if major else 45, width=1.2 if major else 0.8)
            item = pg.IsocurveItem(data=elevation, level=float(level), pen=pen)
            item.setZValue(5)
            self.plot.addItem(item)
            self._contours.append(item)
        self._update_contour_visibility()

    def _clear_isochrones(self) -> None:
        for item in self._isochrones:
            self.plot.removeItem(item)
        self._isochrones.clear()

    def _draw_isochrones(self) -> None:
        """불 도착 시각 등시선: '이 선까지 불이 몇 분 만에 왔는지'"""
        self._clear_isochrones()
        if self.result is None:
            return
        # 도착하지 않은 셀은 아주 큰 값으로 바꿔 등시선이 바깥쪽에서 닫히게 한다
        arrival = np.where(self.result.arrival >= 0, self.result.arrival, 1e6)
        for level in map_render.arrival_contours(self.result.arrival, ISOCHRONE_STEP_MIN):
            item = pg.IsocurveItem(data=arrival, level=float(level),
                                   pen=pg.mkPen(255, 210, 120, 200, width=1.5, style=Qt.PenStyle.DashLine))
            item.setZValue(15)
            self.plot.addItem(item)
            self._isochrones.append(item)
        self._update_isochrone_visibility()

    def _redraw_fire(self) -> None:
        if self.result is None or not self.check_fire.isChecked():
            self.fire_item.clear()
            return
        overlay = map_render.fire_overlay(self.result.arrival, self.result.burnout, self.time)
        self.fire_item.setImage(overlay, levels=(0, 255))
        self.fire_item.setRect(0, 0, self.map.width, self.map.height)

    def _redraw_night(self) -> None:
        """(8단계) 시각 t 의 해 고도에 맞춰 지도를 어둡게(노을빛으로) 덮고, 밤에는 불빛을 더한다."""
        sun = self.result.sun_at(self.time) if self.result is not None else None
        if sun is None or not self.check_night.isChecked():
            self.night_item.clear()
            self.glow_item.clear()
            return
        elevation, level = sun
        tint = np.array([[daylight_render.night_tint(level, elevation)]], dtype=np.uint8)
        self.night_item.setImage(tint, levels=(0, 255))
        self.night_item.setRect(0, 0, self.map.width, self.map.height)
        if self.check_fire.isChecked():
            glow = daylight_render.fire_glow(self.result.arrival, self.result.burnout, self.time, 1.0 - level)
            self.glow_item.setImage(glow, levels=(0, 255))
            self.glow_item.setRect(0, 0, self.map.width, self.map.height)
        else:
            self.glow_item.clear()

    def _draw_trails(self) -> None:
        for item in self.trail_items + self._node_labels:
            self.plot.removeItem(item)
        self.trail_items.clear()
        self._node_labels.clear()
        if self.map is None:
            return

        pen = pg.mkPen(*theme.TRAIL_COLOR, 220, width=2, style=Qt.PenStyle.DashLine)
        for edge in self.map.edges:
            xs = [x + 0.5 for x, _ in edge.points]
            ys = [y + 0.5 for _, y in edge.points]
            item = pg.PlotDataItem(xs, ys, pen=pen)
            item.setZValue(20)
            self.plot.addItem(item)
            self.trail_items.append(item)

        spots = []
        font = QFont()
        font.setPointSize(8)
        for node in self.map.nodes:
            color = theme.NODE_COLORS.get(node.kind, (200, 200, 200))
            symbol = "s" if node.is_exit else ("t" if node.kind == "SUMMIT" else "o")
            spots.append({"pos": (node.x + 0.5, node.y + 0.5), "brush": pg.mkBrush(*color), "symbol": symbol})
            label = pg.TextItem(node.name, color=(235, 235, 235), anchor=(0, 1.2))
            label.setFont(font)
            label.setPos(node.x + 1.5, node.y + 0.5)
            label.setZValue(35)
            self.plot.addItem(label)
            self._node_labels.append(label)
        self.node_item.setData(spots)
        self._update_trail_visibility()

    def _draw_hikers(self) -> None:
        """
        등산객을 그린다.
          대피 결과가 있으면: 시각 t 의 위치에 경보 단계 색으로 (이동 애니메이션)
          없으면: 시작 노드에 흰색으로
        """
        for label in self._hiker_labels:
            self.plot.removeItem(label)
        self._hiker_labels.clear()
        if self.map is None:
            self.hiker_item.clear()
            return

        spots = []
        evacuation = self.evacuation if self.result is not None else None
        if evacuation is not None:
            for hiker in evacuation.hikers:
                x, y = hiker.position_at(self.time)
                color = theme.ALERT_COLORS.get(hiker.alert_at(self.time, evacuation.alert_levels), "#ffffff")
                size = 18 if hiker.id == self.selected_hiker else 13
                spots.append({"pos": (x + 0.5, y - 0.8), "brush": pg.mkBrush(color), "size": size})
                self._add_hiker_label(f"H{hiker.id}", x, y)
        else:
            for hiker in self.map.hikers:
                node = self.map.node_by_id(hiker.node_id)
                if node is not None:
                    spots.append({"pos": (node.x + 0.5, node.y - 0.8), "brush": pg.mkBrush("w"), "size": 13})
                    self._add_hiker_label(f"H{hiker.id}", node.x, node.y)
        self.hiker_item.setData(spots)
        self._update_hiker_visibility()

    def _add_hiker_label(self, text: str, x: float, y: float) -> None:
        label = pg.TextItem(text, color=(255, 255, 255), anchor=(1.1, 1.3))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        label.setFont(font)
        label.setPos(x + 0.5, y - 0.8)
        label.setZValue(41)
        label.setVisible(self.check_hikers.isChecked())
        self.plot.addItem(label)
        self._hiker_labels.append(label)

    # ------------------------------------------------------------------
    # 대피 경로
    # ------------------------------------------------------------------
    def _route_points(self, node_ids: list[int]) -> list[tuple[int, int]]:
        """노드 id 순서 → 등산로 간선 좌표를 이어 붙인 꺾은선"""
        points: list[tuple[int, int]] = []
        for a, b in zip(node_ids[:-1], node_ids[1:]):
            edge = next((e for e in self.map.edges if (e.start_id, e.end_id) in ((a, b), (b, a))), None)
            if edge is None:
                continue
            segment = edge.points if edge.start_id == a else list(reversed(edge.points))
            points.extend(segment if not points else segment[1:])
        return points

    def _clear_routes(self) -> None:
        for item in self._route_items.values():
            self.plot.removeItem(item)
        self._route_items.clear()

    def _draw_routes(self) -> None:
        """팀별 추천 대피 경로. 위험한 팀(고립·여유 부족)은 빨간색, 나머지는 초록색."""
        self._clear_routes()
        if self.result is None or self.evacuation is None:
            return
        for hiker in self.evacuation.hikers:
            if not hiker.route_found or len(hiker.route_node_ids) < 2:
                continue
            points = self._route_points(hiker.route_node_ids)
            item = pg.PlotDataItem([x + 0.5 for x, _ in points], [y + 0.5 for _, y in points])
            item.setZValue(25)
            self.plot.addItem(item)
            self._route_items[hiker.id] = item
        self._style_routes()

    def _style_routes(self) -> None:
        if self.result is None or self.evacuation is None:
            return
        risky = {h.id for h in self.evacuation.hikers if h.at_risk}
        for hiker_id, item in self._route_items.items():
            color = theme.ALERT_COLORS["IMMEDIATE"] if hiker_id in risky else theme.ALERT_COLORS["NONE"]
            selected = hiker_id == self.selected_hiker
            dimmed = self.selected_hiker >= 0 and not selected
            pen = pg.mkPen(color, width=5 if selected else 2.5)
            item.setPen(pen)
            item.setOpacity(0.25 if dimmed else 0.9)
            item.setZValue(27 if selected else 25)
        self._update_route_visibility()

    def set_evacuation(self, evacuation) -> None:
        """기본 예측 / 보수적 예측 중 지도에 보여 줄 대피 결과를 바꾼다."""
        self.evacuation = evacuation
        self._draw_routes()
        self._draw_hikers()

    def highlight_hiker(self, hiker_id: int) -> None:
        """대피 화면에서 고른 팀의 경로를 굵게, 나머지는 흐리게"""
        self.selected_hiker = hiker_id
        self._style_routes()
        self._draw_hikers()

    # ------------------------------------------------------------------
    # 레이어 켜기/끄기
    # ------------------------------------------------------------------
    def _update_contour_visibility(self) -> None:
        for item in self._contours:
            item.setVisible(self.check_contour.isChecked())

    def _update_isochrone_visibility(self) -> None:
        for item in self._isochrones:
            item.setVisible(self.check_isochrone.isChecked())

    def _update_trail_visibility(self) -> None:
        visible = self.check_trails.isChecked()
        for item in self.trail_items + self._node_labels:
            item.setVisible(visible)
        self.node_item.setVisible(visible)

    def _update_hiker_visibility(self) -> None:
        visible = self.check_hikers.isChecked()
        self.hiker_item.setVisible(visible)
        for label in self._hiker_labels:
            label.setVisible(visible)

    def _update_route_visibility(self) -> None:
        for item in self._route_items.values():
            item.setVisible(self.check_routes.isChecked())

    # ------------------------------------------------------------------
    # 마우스
    # ------------------------------------------------------------------
    def _cell_at(self, scene_pos) -> tuple[int, int] | None:
        """화면 좌표 → 격자 셀 (지도 밖이면 None)"""
        if self.map is None:
            return None
        point = self.plot.plotItem.vb.mapSceneToView(scene_pos)
        x, y = int(np.floor(point.x())), int(np.floor(point.y()))
        if 0 <= x < self.map.width and 0 <= y < self.map.height:
            return x, y
        return None

    def _on_mouse_moved(self, scene_pos) -> None:
        cell = self._cell_at(scene_pos)
        if cell is None:
            return
        x, y = cell
        m = self.map
        fuel = int(m.fuel[y, x])
        text = (f"({x:3d}, {y:3d})  고도 {m.elevation[y, x]:5.0f} m  |  "
                f"{theme.FUEL_NAMES.get(fuel, f'연료 {fuel}')}")
        if self.result is not None:
            arrival = self.result.arrival[y, x]
            text += f"  |  불 도착 {arrival:6.1f}분" if arrival >= 0 else "  |  불 도착 안 함"
        node = next((n for n in m.nodes if abs(n.x - x) <= 1 and abs(n.y - y) <= 1), None)
        if node is not None:
            text += f"  |  {node.name}"
        self.info_label.setText(text)

    def _on_mouse_clicked(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cell = self._cell_at(event.scenePos())
        if cell is not None:
            self.cell_clicked.emit(*cell)
