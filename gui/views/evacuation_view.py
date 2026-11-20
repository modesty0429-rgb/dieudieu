"""
대피 안내 화면

등산객 팀마다 현재 시각의 경보 단계(색 배지), 상태, 남은 안전 시간, 추천 대피 경로를 표로 보여 준다.
재생 시각이 바뀔 때마다 update_time() 으로 갱신하고, 행을 고르면 지도에서 그 팀의 경로를 강조한다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

import theme
from services.result_loader import ALERT_KOREAN, EvacuationData, HikerEvacuation, MapData

COLUMNS = ["팀", "경보", "상태", "남은 시간", "최소 여유", "목적지"]


def status_text(hiker: HikerEvacuation, status: str, t: float) -> str:
    """시각 t 의 상태를 사람이 읽기 좋은 한국어로"""
    if not hiker.needs_evacuation:
        return "대피 불필요"
    if status == "HIKING":
        return f"출발 대기 ({hiker.depart_time:.0f}분)"
    if status == "EVACUATING":
        return "대피 중"
    if status == "SAFE":
        return f"완료 ({hiker.finish_time:.0f}분)"
    if status == "TRAPPED":
        return "고립·구조 요청"
    return status


def margin_text(hiker: HikerEvacuation) -> str:
    if not hiker.route_found:
        return "경로 없음"
    if hiker.min_margin is None:
        return "제한 없음"
    return f"{hiker.min_margin:+.0f}분"


class EvacuationView(QWidget):
    hiker_selected = Signal(int)     # 선택한 팀 id (-1 이면 선택 해제)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.evacuation: EvacuationData | None = None
        self.map: MapData | None = None

        self.summary_label = QLabel("대피 결과가 없습니다. 시뮬레이션을 실행하면 표시됩니다.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("statusText")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(170)

        legend = "  ".join(f'<span style="color:{theme.ALERT_COLORS[k]}">●</span> {v}'
                           for k, v in ALERT_KOREAN.items())
        legend_label = QLabel(f"경보 단계: {legend}<br>남은 시간: 주변 반경 안에 불이 오기까지 (- = 오지 않음)")
        legend_label.setObjectName("dim")

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addWidget(legend_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("선택한 팀의 추천 경로"))
        layout.addWidget(self.detail)

    # ------------------------------------------------------------------
    def set_data(self, evacuation: EvacuationData | None, map_data: MapData | None) -> None:
        self.evacuation = evacuation
        self.map = map_data
        self.table.setRowCount(0)
        self.detail.clear()
        if evacuation is None:
            self.summary_label.setText("이 결과에는 대피 계산이 없습니다. (run 모드 결과)")
            return

        s, cfg = evacuation.summary, evacuation.settings
        risk_color = theme.ERROR if s["at_risk_hikers"] else theme.SUCCESS
        self.summary_label.setText(
            f"{s['hikers']}팀 {s['people']}명 중 대피 {s['evacuated']}팀 · 완료 {s['safe']}팀 · "
            f"<span style='color:{risk_color}'>고립 {s['trapped']}팀 · 위험 {s['at_risk_hikers']}팀 "
            f"{s['at_risk_people']}명</span><br>"
            f"<span style='color:{theme.TEXT_DIM}'>기준: 주의 &lt; {cfg['caution_min']:.0f}분, "
            f"대피준비 &lt; {cfg['prepare_min']:.0f}분(출발), 즉시대피 &lt; {cfg['immediate_min']:.0f}분, "
            f"경보 가능 시각 {cfg['notify_delay_min']:.0f}분</span>")
        self.table.setRowCount(len(evacuation.hikers))
        for row, hiker in enumerate(evacuation.hikers):
            self._set_cell(row, 0, f"H{hiker.id} {hiker.name} ({hiker.group_size}명)")
            self._set_cell(row, 4, margin_text(hiker))
            self._set_cell(row, 5, hiker.exit_name if hiker.route_found else "-")
            if hiker.at_risk:
                self.table.item(row, 4).setForeground(QBrush(QColor(theme.ERROR)))

    def update_time(self, t: float) -> None:
        """재생 시각이 바뀌면 경보·상태·남은 시간 열을 갱신한다."""
        if self.evacuation is None:
            return
        levels, names = self.evacuation.alert_levels, self.evacuation.status_names
        for row, hiker in enumerate(self.evacuation.hikers):
            level = hiker.alert_at(t, levels)
            remaining = hiker.remaining_at(t)
            badge = self._set_cell(row, 1, f"● {ALERT_KOREAN.get(level, level)}")
            badge.setForeground(QBrush(QColor(theme.ALERT_COLORS.get(level, theme.TEXT))))
            self._set_cell(row, 2, status_text(hiker, hiker.status_at(t, names), t))
            if remaining < 0:
                remaining_text = "-"            # 불이 오지 않음
            elif remaining == 0:
                remaining_text = "0 (근접)"     # 이미 반경 안에 불이 있음
            else:
                remaining_text = f"{remaining:.0f}분"
            self._set_cell(row, 3, remaining_text)

    def selected_hiker_id(self) -> int:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or self.evacuation is None:
            return -1
        return self.evacuation.hikers[rows[0].row()].id

    # ------------------------------------------------------------------
    def _set_cell(self, row: int, column: int, text: str) -> QTableWidgetItem:
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, column, item)
        else:
            item.setText(text)
        return item

    def _on_selection(self) -> None:
        hiker_id = self.selected_hiker_id()
        self.hiker_selected.emit(hiker_id)
        self._show_detail(hiker_id)

    def _show_detail(self, hiker_id: int) -> None:
        if self.evacuation is None or hiker_id < 0:
            self.detail.clear()
            return
        hiker = next(h for h in self.evacuation.hikers if h.id == hiker_id)
        lines = [f"<b>H{hiker.id} {hiker.name}</b> ({hiker.group_size}명, 평지 {hiker.speed_kmh:.1f} km/h) "
                 f"— 시작: {hiker.start_name}"]
        if hiker.route_found and self.map is not None:
            names = [self.map.node_by_id(i).name for i in hiker.route_node_ids if self.map.node_by_id(i)]
            lines.append("경로: " + " → ".join(names))
            lines.append(f"소요 {hiker.travel_time:.0f}분, 최소 안전 여유 {margin_text(hiker)}")
        else:
            lines.append("<span style='color:%s'>안전한 대피 목적지로 가는 길이 없습니다. 구조 요청 대상.</span>"
                         % theme.ERROR)
        if hiker.needs_evacuation:
            lines.append(f"출발 {hiker.depart_time:.0f}분 → "
                         + (f"도착 {hiker.finish_time:.0f}분" if hiker.status == "SAFE"
                            else f"<span style='color:{theme.ERROR}'>{hiker.finish_time:.0f}분에 고립</span>"))
            if hiker.min_margin is not None and hiker.min_margin < 0:
                lines.append(f"<span style='color:{theme.ERROR}'>출발 시점에 이미 모든 경로가 위험합니다. "
                             f"대피 준비 기준을 앞당기면 결과가 달라질 수 있습니다.</span>")
        else:
            lines.append("시작 위치 주변에 불이 오지 않아 대피가 필요 없었습니다. (참고용 경로)")
        self.detail.setHtml("<br>".join(lines))
