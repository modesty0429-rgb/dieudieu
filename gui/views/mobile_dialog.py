"""
"휴대폰으로 발화 정보 보내기" 창 (11단계, 관제 역할)

지금 설정 패널의 발화 지점·날씨로 링크를 만들어 QR 코드와 함께 보여 준다.
등산객 휴대폰은 QR 을 찍거나 문자로 받은 링크를 누르면, 휴대폰 안의 C 엔진(WebAssembly)이
인터넷 없이 확산·대피 경로·경보를 계산한다.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
                               QVBoxLayout)

from services import mobile_link


def qr_pixmap(text: str, size: int = 260) -> QPixmap | None:
    """
    링크 → QR 코드 그림. qrcode 패키지로 칸(검정/흰색) 배열만 만들고, 그림은 Qt 로 직접 그린다.
    (pillow·pypng 같은 그림 도구가 없어도 동작. qrcode 가 없으면 None: 링크만 보여 줌)
    """
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(text)
        qr.make(fit=True)
        matrix = qr.get_matrix()
    except Exception:                       # noqa: BLE001 — QR 을 못 그려도 링크는 보여 준다
        return None
    n = len(matrix)
    scale = max(1, size // n)
    image = QImage(n * scale, n * scale, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                painter.fillRect(x * scale, y * scale, scale, scale, QColor("black"))
    painter.end()
    return QPixmap.fromImage(image)


class MobileDialog(QDialog):
    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel
        self.setWindowTitle("📱 휴대폰으로 발화 정보 보내기")
        self.setMinimumWidth(560)

        self.now_check = QCheckBox("발화 시각 = 지금 (끄면 설정 패널의 시작 날짜·시각)")
        self.now_check.setChecked(True)
        self.now_check.toggled.connect(self.refresh)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.link = QLineEdit()
        self.link.setReadOnly(True)
        self.sms = QTextEdit()
        self.sms.setReadOnly(True)
        self.sms.setFixedHeight(72)
        copy_link = QPushButton("링크 복사")
        copy_link.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.link.text()))
        copy_sms = QPushButton("문자 내용 복사")
        copy_sms.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.sms.toPlainText()))
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        note = QLabel("휴대폰 카메라로 QR 을 찍거나, 문자·카카오톡으로 링크를 보내세요. 링크에는 발화 지점·시각·날씨 "
                      "숫자만 들어 있고(기상청 인증키 없음), 계산은 휴대폰이 인터넷 없이 합니다.")
        note.setObjectName("dim")
        note.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(copy_link)
        buttons.addWidget(copy_sms)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.now_check)
        layout.addWidget(self.info)
        layout.addWidget(self.qr)
        layout.addWidget(QLabel("링크"))
        layout.addWidget(self.link)
        layout.addWidget(QLabel("문자로 보낼 내용"))
        layout.addWidget(self.sms)
        layout.addWidget(note)
        layout.addLayout(buttons)
        self.refresh()

    def _fire_time(self) -> datetime:
        if self.now_check.isChecked():
            return datetime.now().replace(second=0, microsecond=0)
        group = self.panel.daylight_group
        return datetime.strptime(f"{group.date()} {group.start_time.time().toString('HH:mm')}", "%Y-%m-%d %H:%M")

    def _weather(self, when: datetime):
        p = self.panel
        if p.weather_fixed_radio.isChecked():
            return (p.wind_speed.value(), round(p.wind_dir.value()), round(p.humidity.value()), p.temperature.value())
        if p.weather_override is not None and p.weather_file_radio.isChecked():
            return mobile_link.weather_at(p.weather_override[0], when)     # 기상청에서 받은 실제 날씨
        return None                                                         # 휴대폰이 계절 평년 날씨로 추정

    def refresh(self) -> None:
        p = self.panel
        when = self._fire_time()
        try:
            message = mobile_link.build_message(p.current_scenario(), p.ignition_x.value(), p.ignition_y.value(),
                                                when, self._weather(when))
        except Exception as error:           # noqa: BLE001 — 어떤 오류든 창 안에 보여 준다
            self.info.setText(f"⚠ {error}")
            self.link.setText("")
            self.sms.setPlainText("")
            self.qr.clear()
            return
        w = message.weather
        weather_text = (f"바람 {w[0]:g} m/s ({w[1]:g}°), 습도 {w[2]:g}%, 기온 {w[3]:g}℃" if w
                        else "날씨 없음 → 휴대폰이 그 계절 평년 날씨로 추정")
        self.info.setText(f"<b>{message.mountain}</b> · 발화 지점 칸 ({p.ignition_x.value()}, {p.ignition_y.value()}) = "
                          f"{message.lat:.5f}, {message.lon:.5f} · {message.time:%Y-%m-%d %H:%M}<br>{weather_text}")
        self.link.setText(message.link())
        self.sms.setPlainText(message.sms_text())
        pixmap = qr_pixmap(message.link())
        if pixmap is None:
            self.qr.setText("(QR 코드를 그리려면: python -m pip install qrcode)")
        else:
            self.qr.setPixmap(pixmap)
