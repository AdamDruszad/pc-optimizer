"""Újrahasznosított Fluent elemek: felületkártya, oldalváz, hős panel, metrikakártya, listasor, megerősítés."""
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    DotInfoBadge,
    FluentIconBase,
    HorizontalSeparator,
    HyperlinkButton,
    IconWidget,
    InfoBadge,
    LargeTitleLabel,
    MessageBoxBase,
    PrimaryPushButton,
    SimpleCardWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    SwitchButton,
    TitleLabel,
    isDarkTheme,
    setCustomStyleSheet,
    themeColor,
)
from qfluentwidgets import FluentIcon as FIF

from .theme import DARK, LIGHT, pair, tok


def text(cls, s: str = "", tone: str = "text", wrap: bool = False):
    """Fluent címke a paletta szövegszínével (világos és sötét témára külön)."""
    label = cls(s)
    label.setTextColor(*pair(tone))
    label.setWordWrap(wrap)
    return label


def clear(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


def badge(value: str, kind: str = "success") -> InfoBadge:
    """Állapotjelvény a paletta színeivel; a betűszín a téma szerint kontrasztos."""
    b = InfoBadge.custom(value, *pair(kind))
    setCustomStyleSheet(b, f"InfoBadge{{color:{LIGHT['on_status']}}}", f"InfoBadge{{color:{DARK['on_status']}}}")
    return b


def danger_button(text_: str) -> PrimaryPushButton:
    """Visszafordíthatatlan műveletekhez: piros, a többi elsődleges gombtól elkülönülő."""
    button = PrimaryPushButton(text_)
    setCustomStyleSheet(
        button,
        "PrimaryPushButton{background:#DC2626;border:1px solid #B91C1C;color:#FFFFFF}"
        "PrimaryPushButton:hover{background:#B91C1C}PrimaryPushButton:pressed{background:#991B1B}",
        "PrimaryPushButton{background:#F87171;border:1px solid #EF4444;color:#1F0A0A}"
        "PrimaryPushButton:hover{background:#FB8A8A}PrimaryPushButton:pressed{background:#EF4444}")
    return button


class Surface(SimpleCardWidget):
    """Kártya a paletta felület- és szegélyszínével (a könyvtári kártya áttetsző színeit felülírja)."""

    hero = False

    def __init__(self, parent=None, padding: int = 20, spacing: int = 12):
        super().__init__(parent)
        self.setBorderRadius(12)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(padding, padding, padding, padding)
        self.box.setSpacing(spacing)

    def _normalBackgroundColor(self):
        return tok("hero" if self.hero else "surface")

    def _hoverBackgroundColor(self):
        return self._normalBackgroundColor()

    def _pressedBackgroundColor(self):
        return self._normalBackgroundColor()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._normalBackgroundColor())
        painter.setPen(QPen(tok("hero") if self.hero else tok("border"), 1))
        r = self.borderRadius
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), r, r)


class Page(SmoothScrollArea):
    """Görgethető oldalváz: cím, alcím, majd az oldal tartalma (self.body)."""

    def __init__(self, win, key: str, title: str, subtitle: str):
        super().__init__(win)
        self.win = win
        self.setObjectName(key)
        self.content = QWidget()
        self.content.setObjectName(f"{key}Content")
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(36, 28, 36, 28)
        self.body.setSpacing(16)
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(text(TitleLabel, title))
        head.addWidget(text(BodyLabel, subtitle, "muted"))
        self.body.addLayout(head)
        self.body.addSpacing(8)
        self.build()
        self.body.addStretch(1)
        self.setWidget(self.content)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()

    def build(self) -> None: ...

    def on_show(self) -> None: ...

    def on_tick(self) -> None: ...


def section(title: str, right: QWidget | None = None) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(text(SubtitleLabel, title))
    row.addStretch(1)
    if right is not None:
        row.addWidget(right)
    return row


def footnote(icon, s: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    i = IconWidget(icon)
    i.setFixedSize(16, 16)
    row.addWidget(i)
    row.addWidget(text(CaptionLabel, s, "muted", wrap=True), 1)
    return row


class Initials(QWidget):
    """Kezdőbetűs csempe a listákhoz (játékok, alkalmazások)."""

    def __init__(self, s: str, parent=None):
        super().__init__(parent)
        self.s = s[:2]
        self.setFixedSize(36, 36)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(themeColor())
        fill.setAlpha(60 if isDarkTheme() else 36)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setPen(tok("text"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.s)


def list_row(title: str, subtitle: str = "", leading: QWidget | None = None,
             trailing: tuple = ()) -> QWidget:
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 8, 0, 8)
    h.setSpacing(12)
    if leading is not None:
        h.addWidget(leading, 0, Qt.AlignmentFlag.AlignVCenter)
    v = QVBoxLayout()
    v.setSpacing(2)
    v.addWidget(text(StrongBodyLabel, title))
    if subtitle:
        v.addWidget(text(CaptionLabel, subtitle, "muted", wrap=True))
    h.addLayout(v, 1)
    for w in trailing:
        h.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


def add_rows(layout: QVBoxLayout, rows: list[QWidget]) -> None:
    for i, row in enumerate(rows):
        if i:
            layout.addWidget(HorizontalSeparator())
        layout.addWidget(row)


class ActionBar(Surface):
    def __init__(self, title: str, caption: str, button: QWidget, parent=None):
        super().__init__(parent, padding=16)
        row = QHBoxLayout()
        v = QVBoxLayout()
        v.setSpacing(2)
        self.title = text(StrongBodyLabel, title)
        self.caption = text(CaptionLabel, caption, "muted")
        v.addWidget(self.title)
        v.addWidget(self.caption)
        row.addLayout(v, 1)
        row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.box.addLayout(row)


class Sparkline(QWidget):
    """Kitöltött, színátmenetes vonaldiagram az előzményekből. top=None: automatikus skála."""

    def __init__(self, height: int = 44, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.values: list[float] = []
        self.top: float | None = None

    def set_values(self, values, top: float | None = None) -> None:
        self.values = [v for v in values if v is not None]
        self.top = top
        self.update()

    def paintEvent(self, e):
        if len(self.values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        top = self.top or max(max(self.values), 1e-6) * 1.15
        step = w / (len(self.values) - 1)
        points = [QPointF(i * step, h - 2 - (min(v, top) / top) * (h - 4)) for i, v in enumerate(self.values)]
        line = QPainterPath(points[0])
        for p in points[1:]:
            line.lineTo(p)
        area = QPainterPath(line)
        area.lineTo(w, h)
        area.lineTo(0, h)
        area.closeSubpath()
        color = QColor(tok("accent_hi") if isDarkTheme() else tok("accent"))
        grad = QLinearGradient(0, 0, 0, h)
        start, end = QColor(color), QColor(color)
        start.setAlpha(110)
        end.setAlpha(0)
        grad.setColorAt(0, start)
        grad.setColorAt(1, end)
        painter.fillPath(area, grad)
        painter.setPen(QPen(color, 2))
        painter.drawPath(line)


class MetricCard(Surface):
    def __init__(self, name: str, icon, chart_height: int = 44, parent=None):
        super().__init__(parent, padding=16, spacing=4)
        top = QHBoxLayout()
        top.addWidget(text(StrongBodyLabel, name, "muted"))
        top.addStretch(1)
        i = IconWidget(icon)
        i.setFixedSize(18, 18)
        top.addWidget(i)
        self.box.addLayout(top)
        self.value = text(TitleLabel, "—")
        self.box.addWidget(self.value)
        self.meta = text(CaptionLabel, "", "muted")
        self.box.addWidget(self.meta)
        self.chart = Sparkline(chart_height)
        self.box.addSpacing(6)
        self.box.addWidget(self.chart)

    def show_value(self, value: str, meta: str, history=(), top: float | None = None) -> None:
        self.value.setText(value)
        self.meta.setText(meta)
        self.chart.set_values(history, top)


class PowerToggle(QAbstractButton):
    """Nagy főkapcsoló a hős panelen. A könyvtár SwitchButtonje nem méretezhető, a PillToolButton pedig
    a téma áttetsző színeivel rajzol, ami a fordított (világos/sötét) hős felületen eltűnne."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(104, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        on = self.isChecked()
        painter.setPen(QPen(tok("hero_text"), 2) if self.hasFocus() else Qt.PenStyle.NoPen)
        painter.setBrush(QColor(themeColor()) if on else tok("hero_track"))
        painter.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 8
        knob = QRectF(r.right() - d - 4 if on else r.left() + 4, r.top() + 4, d, d)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(knob)
        inset = d * 0.27
        icon_color = QColor(themeColor()) if on else QColor("#3F6B5A")
        FIF.POWER_BUTTON.render(painter, knob.adjusted(inset, inset, -inset, -inset), fill=icon_color.name())


class SwitchRow(Surface):
    """Kapcsolósor: ikon, cím, tördelődő leírás, alatta jelvények, jobbra Be/Ki kapcsoló.
    A SwitchSettingCard helyett: az fix 70 px magas (két soros leírás rácsúszik a címre) és angol On/Off feliratú."""

    def __init__(self, icon, title: str, desc: str, tags: tuple = (), parent=None):
        super().__init__(parent, padding=16)
        row = QHBoxLayout()
        row.setSpacing(16)
        glyph = IconWidget(icon)
        glyph.setFixedSize(16, 16)
        row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(text(BodyLabel, title, wrap=True))
        col.addWidget(text(CaptionLabel, desc, "muted", wrap=True))
        if tags:
            line = QHBoxLayout()
            line.setContentsMargins(0, 6, 0, 0)
            line.setSpacing(8)
            for tag in tags:
                line.addWidget(tag)
            line.addStretch(1)
            col.addLayout(line)
        row.addLayout(col, 1)
        self.switch = SwitchButton()
        self.switch.setOnText("Be")
        self.switch.setOffText("Ki")
        self.switch.setAccessibleName(title)
        row.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)
        self.box.addLayout(row)


class _HeroLink(HyperlinkButton):
    """A könyvtár az ikont a témaszínnel festené; a fordított hős panelen a link színe olvasható."""

    def _drawIcon(self, icon, painter, rect, state=QIcon.State.Off):
        if isinstance(icon, FluentIconBase):
            icon = icon.icon(color=tok("hero_link"))
        super()._drawIcon(icon, painter, rect, state)


class HeroCard(Surface):
    """A fő művelet panele (terv: világos panel sötét felületen). Fordított színekkel, nagy címmel."""

    hero = True
    toggled = Signal()

    def __init__(self, link_text: str = "", on_link: Callable | None = None, with_toggle: bool = False,
                 action: QWidget | None = None, parent=None):
        super().__init__(parent, padding=32, spacing=10)
        row = QHBoxLayout()
        row.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(10)
        self.title = text(LargeTitleLabel, "", "hero_text", wrap=True)
        left.addWidget(self.title)
        status = QHBoxLayout()
        status.setSpacing(8)
        self.dot = DotInfoBadge.success()
        status.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status = text(CaptionLabel, "", "hero_muted")
        status.addWidget(self.status)
        status.addStretch(1)
        left.addLayout(status)
        self.desc = text(BodyLabel, "", "hero_muted", wrap=True)
        left.addWidget(self.desc)
        if link_text:
            link = _HeroLink("", link_text)
            link.setIcon(FIF.LINK)
            setCustomStyleSheet(link, f"HyperlinkButton{{color:{LIGHT['hero_link']}}}",
                                f"HyperlinkButton{{color:{DARK['hero_link']}}}")
            if on_link:
                link.clicked.connect(on_link)
            left.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)
        row.addLayout(left, 1)
        self.toggle = None
        if with_toggle:
            right = QVBoxLayout()
            right.setSpacing(8)
            right.addStretch(1)
            self.toggle = PowerToggle()
            self.toggle.setAccessibleName("Játék mód")
            self.toggle.clicked.connect(self.toggled.emit)
            right.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignHCenter)
            self.toggle_label = text(CaptionLabel, "", "hero_muted")
            right.addWidget(self.toggle_label, 0, Qt.AlignmentFlag.AlignHCenter)
            right.addStretch(1)
            row.addLayout(right)
        if action is not None:
            row.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        self.box.addLayout(row)

    def set_state(self, title: str, status: str, desc: str, active: bool = False, toggle_label: str = "") -> None:
        self.title.setText(title)
        self.status.setText(status)
        self.desc.setText(desc)
        self.dot.setVisible(active)
        if self.toggle is not None:
            self.toggle.setChecked(active)
            self.toggle_label.setText(toggle_label)


class ConfirmDialog(MessageBoxBase):
    def __init__(self, parent, title: str, lines: list[str], note: str, ok_text: str, danger: bool):
        super().__init__(parent)
        self.viewLayout.setSpacing(8)
        self.viewLayout.addWidget(text(SubtitleLabel, title))
        self.viewLayout.addWidget(text(BodyLabel, "Ez fog történni:", "muted"))
        for line in lines[:12]:
            self.viewLayout.addWidget(text(BodyLabel, f"•  {line}", wrap=True))
        if len(lines) > 12:
            self.viewLayout.addWidget(text(BodyLabel, f"… és még {len(lines) - 12} változás", "muted"))
        if note:
            self.viewLayout.addSpacing(4)
            self.viewLayout.addWidget(text(CaptionLabel, note, "muted", wrap=True))
        self.yesButton.setText(ok_text)
        self.cancelButton.setText("Mégse")
        if danger:
            setCustomStyleSheet(self.yesButton, "PrimaryPushButton{background:#DC2626;color:#FFFFFF}",
                                "PrimaryPushButton{background:#F87171;color:#1F0A0A}")
        self.widget.setMinimumWidth(500)


def confirm(parent, title: str, lines: list[str], note: str = "", ok_text: str = "Alkalmazás",
            danger: bool = False) -> bool:
    return bool(ConfirmDialog(parent, title, lines, note, ok_text, danger).exec())
