"""
등산객 팀 설정 상자 (10단계)

  - 팀 수 1 ~ 10
  - 팀마다 이름, 인원, 걷는 속도(km/h), 위치
  - 위치: 등산로 노드(정상·갈림길 등)를 목록에서 고르거나,
          "📍 지도에서 위치 찍기"를 누른 뒤 지도의 등산로를 클릭

바뀔 때마다 teams_changed 를 보내 지도 미리보기가 바로 바뀐다.
실행할 때는 apply() 가 등산로·등산객 파일을 새로 써서 시나리오에 연결한다.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from services import app_config
from services import hiker_setup as hs
from services.result_loader import Hiker, TrailEdge, TrailNode
from services.scenario_writer import ScenarioOverrides

GUI_TRAIL_FILE = app_config.DATA_DIR / "trails" / "gui_trails.txt"
GUI_HIKER_FILE = app_config.DATA_DIR / "trails" / "gui_hikers.txt"
CUSTOM = -1          # 위치 목록에서 "지도에서 찍은 곳"


class HikerGroup(QGroupBox):
    teams_changed = Signal()           # 팀 설정이 바뀜 → 지도 미리보기 갱신
    pick_mode_changed = Signal(bool)   # 지도에서 위치 찍기 모드 켜짐/꺼짐

    COLUMNS = ("팀 이름", "인원", "km/h", "위치")

    def __init__(self, parent=None):
        super().__init__("등산객 팀", parent)
        self.nodes: list[TrailNode] = []
        self.edges: list[TrailEdge] = []
        self.default_teams: list[hs.TeamSpec] = []
        self.teams: list[hs.TeamSpec] = []
        self._filling = False

        self.count = QSpinBox()
        self.count.setRange(hs.MIN_TEAMS, hs.MAX_TEAMS)
        self.count.setSuffix(" 팀")
        self.count.valueChanged.connect(self._on_count_changed)
        self.reset_button = QPushButton("처음대로")
        self.reset_button.setToolTip("시나리오 파일의 등산객 팀으로 되돌립니다")
        self.reset_button.clicked.connect(self.reset)
        top = QHBoxLayout()
        top.addWidget(QLabel("팀 수"))
        top.addWidget(self.count, 1)
        top.addWidget(self.reset_button)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 78)
        self.table.itemChanged.connect(self._on_name_edited)
        self.table.setMinimumHeight(230)

        self.pick_button = QPushButton("📍 지도에서 위치 찍기")
        self.pick_button.setCheckable(True)
        self.pick_button.setToolTip("표에서 팀을 고른 뒤 누르고, 지도의 등산로를 클릭하세요.\n"
                                    "등산로 가운데를 찍으면 그 자리에서 출발합니다.")
        self.pick_button.toggled.connect(self._on_pick_toggled)
        self.hint = QLabel("팀을 고르고 '지도에서 위치 찍기'를 누른 뒤 등산로를 클릭하면 위치가 바뀝니다.")
        self.hint.setObjectName("dim")
        self.hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(self.pick_button)
        layout.addWidget(self.hint)

    # ------------------------------------------------------------------
    # 불러오기 / 되돌리기
    # ------------------------------------------------------------------
    def load(self, nodes: list[TrailNode], edges: list[TrailEdge], hikers: list[Hiker]) -> None:
        """시나리오 미리보기의 등산로·등산객으로 채운다. (신호는 보내지 않음)"""
        self.nodes, self.edges = list(nodes), list(edges)
        self.default_teams = hs.teams_from_hikers(hikers, nodes)
        self.teams = [hs.copy_team(t) for t in self.default_teams]
        self.pick_button.setChecked(False)
        self._refill()

    def reset(self) -> None:
        self.teams = [hs.copy_team(t) for t in self.default_teams]
        self._refill()
        self.teams_changed.emit()

    def is_default(self) -> bool:
        return self.teams == self.default_teams

    # ------------------------------------------------------------------
    # 결과
    # ------------------------------------------------------------------
    def layout_for_preview(self) -> tuple[list[TrailNode], list[TrailEdge], list[Hiker]]:
        """지금 설정으로 만든 등산로·등산객 (지도 미리보기용)"""
        return hs.build_layout(self.nodes, self.edges, self.teams)

    def apply(self, o: ScenarioOverrides, scenario_dir: Path) -> None:
        """
        시나리오 파일의 등산객 그대로면 아무것도 바꾸지 않는다.
        바꿨으면 등산로·등산객 파일을 새로 써서 시나리오가 그 파일을 쓰게 한다.
        """
        if not self.nodes or self.is_default():
            return
        nodes, edges, hikers = self.layout_for_preview()
        hs.write_trail_file(GUI_TRAIL_FILE, nodes, edges)
        hs.write_hiker_file(GUI_HIKER_FILE, hikers)
        for key, path in (("trail_file", GUI_TRAIL_FILE), ("hiker_file", GUI_HIKER_FILE)):
            o.set("trails", key, Path(_relative(path, scenario_dir)).as_posix())

    # ------------------------------------------------------------------
    # 지도에서 찍기
    # ------------------------------------------------------------------
    @property
    def picking(self) -> bool:
        return self.pick_button.isChecked()

    def selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return rows[0].row() if rows else -1

    def place_at(self, x: int, y: int) -> str:
        """지도 클릭 위치에 고른 팀을 둔다. 화면에 보여 줄 안내 문구를 돌려준다."""
        row = self.selected_row()
        if row < 0:
            row = 0
        snap = hs.snap_to_trail(self.nodes, self.edges, x, y)
        if snap is None:
            return "등산로에서 너무 멉니다. 하얀 점선(등산로) 위를 클릭하세요."
        team = self.teams[row]
        self.teams[row] = hs.copy_team(team, node_id=snap.node_id, x=snap.x, y=snap.y)
        self.pick_button.setChecked(False)
        self._refill(select=row)
        self.teams_changed.emit()
        return f"{team.name} 팀 위치: {self.teams[row].position_text(self.nodes)}"

    # ------------------------------------------------------------------
    # 표 채우기
    # ------------------------------------------------------------------
    def _refill(self, select: int = 0) -> None:
        self._filling = True
        self.count.blockSignals(True)
        self.count.setValue(max(hs.MIN_TEAMS, len(self.teams)))
        self.count.blockSignals(False)
        self.table.setRowCount(len(self.teams))
        for row, team in enumerate(self.teams):
            item = QTableWidgetItem(team.name)
            item.setToolTip("이름을 두 번 클릭해 바꿀 수 있습니다 (최대 10자, 띄어쓰기는 _ 로 바뀜)")
            self.table.setItem(row, 0, item)

            people = QSpinBox()
            people.setRange(1, 50)
            people.setValue(team.people)
            people.valueChanged.connect(lambda v, r=row: self._update(r, people=v))
            self.table.setCellWidget(row, 1, people)

            speed = QDoubleSpinBox()
            speed.setRange(1.0, 8.0)
            speed.setSingleStep(0.5)
            speed.setDecimals(1)
            speed.setValue(team.speed_kmh)
            speed.setToolTip("평지에서 걷는 속도 (일반 성인 3~4 km/h, 어린이·어르신 2~2.5, 트레일러너 6 이상)")
            speed.valueChanged.connect(lambda v, r=row: self._update(r, speed_kmh=v))
            self.table.setCellWidget(row, 2, speed)

            place = QComboBox()
            for node in hs.start_nodes(self.nodes):
                place.addItem(f"{_kind_icon(node.kind)} {node.name}", node.id)
            if team.node_id is None:
                place.addItem(team.position_text(self.nodes), CUSTOM)
            place.setToolTip("등산로 지점을 고르거나, 아래 '지도에서 위치 찍기'로 등산로 아무 곳이나 정할 수 있습니다")
            place.setCurrentIndex(place.findData(team.node_id if team.node_id is not None else CUSTOM))
            place.currentIndexChanged.connect(lambda _i, r=row, box=place: self._on_place_chosen(r, box))
            self.table.setCellWidget(row, 3, place)
        self._filling = False
        if self.teams:
            self.table.selectRow(min(select, len(self.teams) - 1))

    def _update(self, row: int, **changes) -> None:
        if self._filling or row >= len(self.teams):
            return
        self.teams[row] = hs.copy_team(self.teams[row], **changes)
        self.teams_changed.emit()

    def _on_name_edited(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 0:
            return
        row = item.row()
        name = hs.clean_name(item.text(), f"팀{row + 1}")
        if name != item.text():
            self._filling = True
            item.setText(name)
            self._filling = False
        self._update(row, name=name)

    def _on_place_chosen(self, row: int, box: QComboBox) -> None:
        node_id = box.currentData()
        if self._filling or node_id is None or node_id == CUSTOM:
            return
        node = next(n for n in self.nodes if n.id == node_id)
        self._update(row, node_id=node.id, x=node.x, y=node.y)

    def _on_count_changed(self, value: int) -> None:
        self.teams = hs.resize_teams(self.teams, value, self.nodes)
        self._refill(select=len(self.teams) - 1)
        self.teams_changed.emit()

    def _on_pick_toggled(self, on: bool) -> None:
        if on:
            row = max(self.selected_row(), 0)
            name = self.teams[row].name if self.teams else ""
            self.hint.setText(f"지도의 등산로를 클릭하면 '{name}' 팀이 그곳으로 옮겨집니다. (다시 누르면 취소)")
        else:
            self.hint.setText("팀을 고르고 '지도에서 위치 찍기'를 누른 뒤 등산로를 클릭하면 위치가 바뀝니다.")
        self.pick_mode_changed.emit(on)


def _kind_icon(kind: str) -> str:
    return {"SUMMIT": "⛰", "SHELTER": "🏠", "PARKING": "🅿", "JUNCTION": "↔", "POINT": "•"}.get(kind, "•")


def _relative(path: Path, base: Path) -> str:
    import os
    return os.path.relpath(path, base)
