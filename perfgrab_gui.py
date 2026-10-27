#!/usr/bin/env python3
"""perfgrab - Android game QA toolkit over adb: performance runs and interruption checklists."""
import os
import sys
import threading
import time
from types import SimpleNamespace

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QIcon, QImage, QKeySequence,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
                               QCompleter, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSizePolicy, QSpinBox, QScrollArea, QSplitter, QStackedWidget, QStatusBar,
                               QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import interrupts as ix  # noqa: E402
import perfgrab as core  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
MOD = "Cmd" if sys.platform == "darwin" else "Ctrl"

# ============================================================================ theme
C = {
    "bg": "#0F1115", "panel": "#15181E", "panel2": "#1B1F27", "raised": "#20252F", "border": "#262B35",
    "text": "#E6E8EC", "muted": "#8A91A0", "dim": "#5D6472", "accent": "#7C5CFF", "accent2": "#6A4BF0",
    "fps": "#3DDC97", "cpu": "#4EA8FF", "gpu": "#FFB547", "ram": "#C084FC", "temp": "#FF6B6B",
    "danger": "#E5484D", "ok": "#3DDC97", "warn": "#FFB547", "info": "#4EA8FF",
}
STATUS_COLOR = {"Passed": C["ok"], "Failed": C["danger"], "Blocked": "#F28C38", "Skipped": C["muted"],
                "N/A": C["dim"]}
MODE_COLOR = {ix.AUTO: C["ok"], ix.ASSISTED: C["info"], ix.MANUAL: C["warn"]}

QSS = f"""
* {{ color: {C['text']}; font-size: 13px; }}
QMainWindow, #page {{ background: {C['bg']}; }}
QToolBar {{ background: {C['panel']}; border: none; border-bottom: 1px solid {C['border']}; padding: 6px 10px; spacing: 8px; }}
#rail {{ background: {C['panel']}; border-right: 1px solid {C['border']}; }}
#rail QToolButton {{ border: none; border-radius: 8px; padding: 8px 2px; color: {C['muted']}; font-size: 11px; font-weight: 600; }}
#rail QToolButton:hover {{ background: {C['panel2']}; }}
#rail QToolButton:checked {{ background: {C['raised']}; color: {C['text']}; }}
#side {{ background: {C['panel']}; border-right: 1px solid {C['border']}; }}
#bar {{ background: {C['panel']}; border-bottom: 1px solid {C['border']}; }}
#card {{ background: {C['panel']}; border: 1px solid {C['border']}; border-radius: 10px; }}
#detail {{ background: {C['panel']}; border: none; border-left: 1px solid {C['border']}; }}
#detailInner {{ background: {C['panel']}; }}
#section {{ color: {C['muted']}; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; }}
#muted {{ color: {C['muted']}; }}
#mono {{ font-family: Menlo, Consolas, monospace; color: {C['muted']}; }}
#h1 {{ font-size: 18px; font-weight: 700; }}
#h2 {{ font-size: 15px; font-weight: 700; }}
#pill {{ border: 1px solid {C['border']}; border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: 700; }}
#prompt {{ background: #1E1A33; border: 1px solid {C['accent']}; border-radius: 10px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit#input {{
    background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {C['accent']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit#input:focus {{ border-color: {C['accent']}; }}
QComboBox QAbstractItemView {{ background: {C['panel2']}; border: 1px solid {C['border']}; selection-background-color: {C['accent']}; }}
QListWidget {{ background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 2px; }}
QListWidget::item {{ padding: 5px 4px; border-radius: 4px; }}
QListWidget::item:hover {{ background: {C['raised']}; }}
QListWidget::item:selected {{ background: #2A2450; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator, QListWidget::indicator {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid #3A4050; background: {C['panel2']}; }}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']}; }}
QPushButton, QToolButton#btn {{ background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover, QToolButton#btn:hover {{ border-color: #3A4152; background: {C['raised']}; }}
QPushButton:disabled {{ color: {C['dim']}; }}
QToolButton#btn::menu-indicator {{ image: none; width: 0; }}
QToolButton#run {{ background: {C['accent']}; border: 1px solid {C['accent']}; border-radius: 6px;
    padding: 6px 30px 6px 14px; font-weight: 700; }}
QToolButton#run:hover {{ background: {C['accent2']}; }}
QToolButton#run::menu-button {{ border-left: 1px solid {C['accent2']}; width: 22px; }}
QToolButton#run::menu-arrow {{ width: 8px; height: 8px; }}
QPushButton#primary {{ background: {C['accent']}; border: 1px solid {C['accent']}; font-weight: 700; }}
QPushButton#primary:hover {{ background: {C['accent2']}; }}
QPushButton#primary:disabled {{ background: #352F5E; border-color: #352F5E; color: #8E87B8; }}
QPushButton#danger {{ background: {C['danger']}; border: 1px solid {C['danger']}; font-weight: 700; }}
QPushButton#result {{ padding: 7px 0; font-weight: 700; }}
QPushButton#result:checked {{ color: #0F1115; }}
QProgressBar {{ background: {C['panel2']}; border: none; border-radius: 2px; }}
QProgressBar::chunk {{ background: {C['accent']}; border-radius: 2px; }}
QTabWidget::pane {{ border: 1px solid {C['border']}; border-radius: 10px; background: {C['panel']}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {C['muted']}; padding: 7px 12px; font-weight: 600; }}
QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; }}
QTableWidget, QTreeWidget {{ background: {C['bg']}; border: none; gridline-color: {C['border']};
    selection-background-color: #2A2450; alternate-background-color: #12151A; }}
QTreeWidget::item {{ padding: 4px 0; }}
QTreeWidget::item:selected, QTableWidget::item:selected {{ background: #2A2450; }}
QHeaderView::section {{ background: {C['panel']}; color: {C['muted']}; border: none;
    border-bottom: 1px solid {C['border']}; border-right: 1px solid {C['border']}; padding: 5px 6px; font-weight: 600; }}
QPlainTextEdit#log {{ background: {C['bg']}; border: none; font-family: Menlo, Consolas, monospace; font-size: 11px; color: {C['muted']}; }}
QSplitter::handle {{ background: {C['border']}; }}
QStatusBar {{ background: {C['panel']}; border-top: 1px solid {C['border']}; color: {C['muted']}; font-size: 11px; }}
QStatusBar::item {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; }}
QScrollBar::handle:vertical {{ background: #333A48; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; }}
QScrollBar::handle:horizontal {{ background: #333A48; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{ background: {C['panel2']}; border: 1px solid {C['border']}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['accent']}; }}
QToolTip {{ background: {C['panel2']}; color: {C['text']}; border: 1px solid {C['border']}; }}
QDialog {{ background: {C['panel']}; }}
"""


def label(text="", obj=None, wrap=False):
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(wrap)
    return lab


def pill(text, color):
    p = label(text, "pill")
    p.setStyleSheet(f"color:{color}; border-color:{color};")
    return p


def set_pill(p, text, color):
    p.setText(text)
    p.setStyleSheet(f"color:{color}; border-color:{color};")


def hline():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{C['border']};")
    return f


def make_icon(kind, color=C["muted"], size=22):
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2, 2)
    pen = QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    s = size
    if kind == "perf":
        path = QPainterPath(QPointF(3, s - 6))
        for x, y in ((7, s - 11), (11, s - 8), (15, 6), (19, 10)):
            path.lineTo(QPointF(x, y))
        p.drawPath(path)
        p.drawLine(QPointF(3, s - 3), QPointF(s - 3, s - 3))
    elif kind == "check":
        for i, y in enumerate((5, 11, 17)):
            p.drawLine(QPointF(10, y), QPointF(s - 3, y))
            p.drawPolyline([QPointF(3, y), QPointF(4.8, y + 1.8), QPointF(7.5, y - 1.8)])
    p.end()
    return QIcon(pm)


def cell_text(v):
    if v is None or v == "":
        return ""
    return f"{v:g}" if isinstance(v, float) else str(v)


def qt_similarity(a, b):
    ia, ib = QImage.fromData(a), QImage.fromData(b)
    if ia.isNull() or ib.isNull():
        return None
    fa = ia.scaled(64, 64, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_Grayscale8)
    fb = ib.scaled(64, 64, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_Grayscale8)
    total = 0
    for y in range(64):
        for x in range(0, 64, 2):
            total += abs(fa.pixelColor(x, y).value() - fb.pixelColor(x, y).value())
    mad = total / (64 * 32)
    return max(0.0, 1 - mad / 64)


# ============================================================================ widgets
class MetricCard(QFrame):
    copied = Signal(str, str)

    def __init__(self, title, color, unit=""):
        super().__init__()
        self.setObjectName("card")
        self.title, self.unit = title, unit
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(1)
        lay.addWidget(label(title.upper(), "section"))
        self.value = QLabel("-")
        self.value.setStyleSheet(f"font-size:24px; font-weight:800; color:{color};")
        lay.addWidget(self.value)
        self.sub = label(" ", "muted")
        self.sub.setStyleSheet("font-size:11px;")
        lay.addWidget(self.sub)
        self.setMinimumWidth(120)

    def mousePressEvent(self, e):
        if self.value.text() not in ("", "-"):
            self.copied.emit(self.value.text(), self.title)
        super().mousePressEvent(e)

    def set(self, value, sub=None):
        self.value.setText("-" if value is None else f"{value}{self.unit}")
        if sub is not None:
            self.sub.setText(sub)


class LineChart(QWidget):
    def __init__(self, title, series, y_max=None, suffix="", nice_steps=None):
        super().__init__()
        self.title, self.series, self.fixed_max, self.suffix = title, series, y_max, suffix
        self.nice_steps = nice_steps
        self.clear()
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def clear(self):
        self.data = {k: [] for k, _, _ in self.series}
        self.t = []
        self.update()

    def add(self, t, values):
        self.t.append(t)
        for k in self.data:
            self.data[k].append(values.get(k))
        self.update()

    def _ymax(self):
        if self.fixed_max:
            return self.fixed_max
        vals = [v for arr in self.data.values() for v in arr if v is not None]
        m = max(vals) if vals else 60
        for s in self.nice_steps or []:
            if s >= m * 1.05:
                return s
        return max(10, m * 1.15)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(QRectF(14, 8, w / 2, 18), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        f.setBold(False)
        f.setPixelSize(11)
        p.setFont(f)
        x = w - 14
        for _, name, color in reversed(self.series):
            tw = p.fontMetrics().horizontalAdvance(name)
            x -= tw
            p.setPen(QColor(C["muted"]))
            p.drawText(QRectF(x, 8, tw + 2, 18), Qt.AlignVCenter, name)
            x -= 12
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x + 4, 17), 3.5, 3.5)
            x -= 14
        left, right, top, bottom = 42, 14, 34, 22
        plot = QRectF(left, top, w - left - right, h - top - bottom)
        ymax = self._ymax()
        for i in range(5):
            y = plot.bottom() - plot.height() * i / 4
            p.setPen(QPen(QColor(C["border"]), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(C["dim"]))
            p.drawText(QRectF(0, y - 8, left - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{ymax * i / 4:.0f}{self.suffix}")
        if len(self.t) < 2:
            p.setPen(QColor(C["dim"]))
            p.drawText(plot, Qt.AlignCenter, "No data")
            return
        t0, span = self.t[0], max(self.t[-1] - self.t[0], 1e-6)
        p.setPen(QColor(C["dim"]))
        for i in range(5):
            xx = plot.left() + plot.width() * i / 4
            p.drawText(QRectF(xx - 30, plot.bottom() + 3, 60, 16), Qt.AlignCenter, core.fmt_clock(t0 + span * i / 4))

        def pt(i, v):
            return QPointF(plot.left() + plot.width() * (self.t[i] - t0) / span,
                           plot.bottom() - plot.height() * min(v, ymax) / ymax)

        for si, (k, _, color) in enumerate(self.series):
            arr = self.data[k]
            idx = [i for i, v in enumerate(arr) if v is not None]
            if len(idx) < 2:
                continue
            path = QPainterPath(pt(idx[0], arr[idx[0]]))
            for i in idx[1:]:
                path.lineTo(pt(i, arr[i]))
            if si == 0:
                area = QPainterPath(path)
                area.lineTo(QPointF(pt(idx[-1], 0).x(), plot.bottom()))
                area.lineTo(QPointF(pt(idx[0], 0).x(), plot.bottom()))
                area.closeSubpath()
                g = QLinearGradient(0, plot.top(), 0, plot.bottom())
                c1, c2 = QColor(color), QColor(color)
                c1.setAlpha(80)
                c2.setAlpha(0)
                g.setColorAt(0, c1)
                g.setColorAt(1, c2)
                p.fillPath(area, QBrush(g))
            p.setPen(QPen(QColor(color), 1.8))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        arr = [v for v in self.data[self.series[0][0]] if v is not None]
        if arr:
            avg = sum(arr) / len(arr)
            y = plot.bottom() - plot.height() * min(avg, ymax) / ymax
            p.setPen(QPen(QColor(C["muted"]), 1, Qt.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.drawText(QRectF(plot.right() - 110, y - 17, 110, 15), Qt.AlignRight, f"avg {avg:.1f}{self.suffix}")


class Thumb(QLabel):
    def __init__(self, caption):
        super().__init__()
        self.caption, self.path = caption, None
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(150)
        self.setStyleSheet(f"background:{C['bg']}; border:1px solid {C['border']}; border-radius:6px; color:{C['dim']};")
        self.setText(caption)
        self.setCursor(Qt.PointingHandCursor)

    def show_file(self, path):
        self.path = path
        pm = QPixmap(path) if path and os.path.exists(path) else QPixmap()
        if pm.isNull():
            self.setPixmap(QPixmap())
            self.setText(self.caption)
        else:
            self.setPixmap(pm.scaledToHeight(144, Qt.SmoothTransformation))

    def mousePressEvent(self, e):
        if self.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))


# ============================================================================ workers
class DeviceWorker(QThread):
    done = Signal(object)

    def __init__(self, adb_path, serial=None, full=True):
        super().__init__()
        self.adb_path, self.serial, self.full = adb_path, serial, full

    def run(self):
        res = {"error": None, "devices": [], "info": None, "packages": [], "adb": None, "serial": None}
        try:
            res["adb"] = core.find_adb(self.adb_path)
        except SystemExit as e:
            res["error"] = str(e).splitlines()[0]
            self.done.emit(res)
            return
        res["devices"] = core.list_devices(res["adb"])
        if self.full and res["devices"]:
            serial = self.serial if self.serial in res["devices"] else res["devices"][0]
            res["serial"] = serial
            adb = core.Adb(res["adb"], serial)
            res["info"] = core.device_info(adb)
            out = adb.sh("pm list packages -3")
            res["packages"] = sorted(x.split(":", 1)[1].strip() for x in out.splitlines() if x.startswith("package:"))
        self.done.emit(res)


class PerfWorker(QThread):
    log = Signal(str)
    phase = Signal(str, object)
    sample = Signal(dict)
    game_started = Signal(str, int, int)
    game_done = Signal(dict, list)
    ask_ready = Signal(str)
    all_done = Signal(str, list)

    def __init__(self, adb_path, serial, dev, packages, args, confirm):
        super().__init__()
        self.adb_path, self.serial, self.dev = adb_path, serial, dev
        self.packages, self.args, self.confirm = packages, args, confirm
        self.stop_event, self.ready_event = threading.Event(), threading.Event()

    def stop(self):
        self.stop_event.set()
        self.ready_event.set()

    def run(self):
        adb = core.Adb(self.adb_path, self.serial)
        session = os.path.join(self.args.out, time.strftime("session_%Y%m%d_%H%M%S"))
        os.makedirs(session, exist_ok=True)
        lines = []
        for i, pkg in enumerate(self.packages):
            if self.stop_event.is_set():
                break
            if i and self.confirm:
                self.ready_event.clear()
                self.ask_ready.emit(pkg)
                self.ready_event.wait()
                if self.stop_event.is_set():
                    break
            self.game_started.emit(pkg, i + 1, len(self.packages))
            try:
                res = core.run_test(adb, pkg, self.dev, self.args, session, log=self.log.emit,
                                    on_sample=self.sample.emit,
                                    on_phase=lambda n, v=None: self.phase.emit(n, v), stop_event=self.stop_event)
            except Exception as e:
                self.log.emit(f"error: {e!r}")
                res = None
            if res:
                lines.append(res[0]["_tsv_line"])
                self.game_done.emit(*res)
            adb.sh(f"am force-stop {pkg}")
        if lines:
            with open(os.path.join(session, "all_rows.tsv"), "w", encoding="utf-8") as f:
                f.write("\t".join(core.TABLE_COLUMNS) + "\n" + "\n".join(lines) + "\n")
        self.all_done.emit(session, lines)


class DiagWorker(QThread):
    done = Signal(str, str)

    def __init__(self, adb_path, serial, pkg):
        super().__init__()
        self.adb_path, self.serial, self.pkg = adb_path, serial, pkg

    def run(self):
        try:
            text = core.fps_diagnostics(core.Adb(self.adb_path, self.serial), self.pkg)
        except Exception as e:
            text = f"diagnostics failed: {e!r}"
        self.done.emit(self.pkg, text)


class InterruptWorker(QThread):
    event = Signal(str, dict)

    def __init__(self, adb_path, serial, pkg, queue, opts, evidence_dir):
        super().__init__()
        self.queue = queue
        self.runner = ix.Runner(core.Adb(adb_path, serial), pkg, opts,
                                lambda ev, **d: self.event.emit(ev, d),
                                similarity_fn=qt_similarity, evidence_dir=evidence_dir)

    def run(self):
        self.runner.run(self.queue)


# ============================================================================ performance page
COURSE_COLS = [(i, chr(65 + i), n) for i, n in enumerate(core.TABLE_COLUMNS) if n]
PHASES = {"launch1": ("1st launch", C["cpu"]), "launch2": ("2nd launch", C["cpu"]),
          "play": ("Recording", C["fps"]), "saving": ("Saving", C["gpu"])}


class PerformancePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.worker = None
        self.results = []
        self.live = {}
        self.play_start, self.play_duration = None, 0
        st = win.settings
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---- side
        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(290)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(label("GAMES", "section"))
        top.addStretch()
        self.sel_count = label("0 selected", "muted")
        self.sel_count.setStyleSheet("font-size:11px;")
        top.addWidget(self.sel_count)
        v.addLayout(top)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter packages")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        v.addWidget(self.search)
        self.games = QListWidget()
        self.games.itemChanged.connect(self._count)
        v.addWidget(self.games, 1)
        v.addSpacing(6)
        v.addWidget(label("RUN SETTINGS", "section"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(7)
        self.tester = QLineEdit(st.value("tester", ""))
        self.graphics = QComboBox()
        self.graphics.setEditable(True)
        self.graphics.addItems(["Low", "Normal", "High", "Ultra"])
        self.graphics.setCurrentText(st.value("graphics", "High"))
        self.duration = QSpinBox()
        self.duration.setRange(1, 180)
        self.duration.setSuffix(" min")
        self.duration.setValue(int(st.value("duration", 30)))
        self.interval = QDoubleSpinBox()
        self.interval.setRange(1, 10)
        self.interval.setSingleStep(0.5)
        self.interval.setSuffix(" s")
        self.interval.setValue(float(st.value("interval", 2)))
        self.between = QSpinBox()
        self.between.setRange(3, 120)
        self.between.setSuffix(" s")
        self.between.setValue(int(st.value("between", 10)))
        for name, w in (("Tester", self.tester), ("Graphics", self.graphics), ("Duration", self.duration),
                        ("Sample rate", self.interval), ("Launch gap", self.between)):
            form.addRow(label(name, "muted"), w)
        v.addLayout(form)
        self.attach = QCheckBox("Attach to running game")
        self.confirm = QCheckBox("Confirm before each game")
        self.confirm.setChecked(st.value("pause", "true") == "true")
        self.comma = QCheckBox("Decimal comma")
        self.comma.setChecked(st.value("comma", "false") == "true")
        for cb in (self.attach, self.confirm, self.comma):
            v.addWidget(cb)
        v.addSpacing(4)
        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.clicked.connect(self.start_or_stop)
        v.addWidget(self.btn_start)
        h.addWidget(side)

        # ---- main
        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(18, 14, 18, 14)
        mv.setSpacing(12)
        head = QHBoxLayout()
        self.title = label("No run", "h1")
        self.subtitle = label("", "muted")
        tv = QVBoxLayout()
        tv.setSpacing(0)
        tv.addWidget(self.title)
        tv.addWidget(self.subtitle)
        head.addLayout(tv, 1)
        self.phase = pill("Idle", C["muted"])
        head.addWidget(self.phase, 0, Qt.AlignTop)
        mv.addLayout(head)
        prog = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setRange(0, 1000)
        self.timer = label("00:00 / 00:00", "mono")
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.timer)
        mv.addLayout(prog)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.c_fps = MetricCard("FPS", C["fps"])
        self.c_cpu = MetricCard("CPU (game)", C["cpu"], "%")
        self.c_gpu = MetricCard("GPU", C["gpu"], "%")
        self.c_ram = MetricCard("RAM (game)", C["ram"], " MB")
        self.c_temp = MetricCard("Battery", C["temp"], "°C")
        self.c_launch = MetricCard("Launch 1 / 2", C["text"])
        for c in (self.c_fps, self.c_cpu, self.c_gpu, self.c_ram, self.c_temp, self.c_launch):
            cards.addWidget(c)
            c.copied.connect(lambda txt, t: self.win.copy(txt, f"{t}: {txt}"))
        mv.addLayout(cards)

        charts = QFrame()
        charts.setObjectName("card")
        cv = QVBoxLayout(charts)
        cv.setContentsMargins(2, 2, 2, 2)
        self.fps_chart = LineChart("FPS", [("fps", "FPS", C["fps"])], nice_steps=[40, 60, 80, 120, 160, 240])
        self.load_chart = LineChart("Load", [("cpu", "CPU", C["cpu"]), ("gpu", "GPU", C["gpu"])], y_max=100, suffix="%")
        cv.addWidget(self.fps_chart, 3)
        cv.addWidget(hline())
        cv.addWidget(self.load_chart, 2)
        mv.addWidget(charts, 3)

        self.tabs = QTabWidget()
        rt = QWidget()
        rl = QVBoxLayout(rt)
        rl.setContentsMargins(8, 8, 8, 8)
        self.table = QTableWidget(0, 1 + len(COURSE_COLS))
        self.table.setHorizontalHeaderLabels(["Package"] + [f"{l}\n{n}" for _, l, n in COURSE_COLS])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setDefaultAlignment(Qt.AlignCenter)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        QShortcut(QKeySequence.Copy, self.table, activated=self.copy_selection)
        rl.addWidget(self.table, 1)
        b = QHBoxLayout()
        for text, fn in (("Copy row", lambda: self.copy_rows(False)), ("Copy with headers", lambda: self.copy_rows(True))):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        b.addStretch()
        self.btn_diag = QPushButton("FPS diagnostics")
        self.btn_diag.clicked.connect(self.run_diag)
        for text, fn in (("Chart", self.open_chart), ("Show in folder", self.open_folder)):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn) if text != "Chart" else (b.addWidget(self.btn_diag), b.addWidget(btn))
        rl.addLayout(b)
        self.tabs.addTab(rt, "Results")
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.tabs.addTab(self.log_view, "Log")
        self.tabs.setMinimumHeight(180)
        mv.addWidget(self.tabs, 2)
        h.addWidget(main, 1)

        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(500)

    # ---- device hooks
    def set_packages(self, packages):
        checked = set(self.checked()) or set((self.win.settings.value("selected", "") or "").split(","))
        self.games.blockSignals(True)
        self.games.clear()
        for pkg in packages:
            it = QListWidgetItem(pkg)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if pkg in checked else Qt.Unchecked)
            self.games.addItem(it)
        self.games.blockSignals(False)
        self._filter(self.search.text())
        self._count()

    def _filter(self, t):
        t = t.lower().strip()
        for i in range(self.games.count()):
            self.games.item(i).setHidden(bool(t) and t not in self.games.item(i).text().lower())

    def checked(self):
        return [self.games.item(i).text() for i in range(self.games.count())
                if self.games.item(i).checkState() == Qt.Checked]

    def _count(self, *_):
        self.sel_count.setText(f"{len(self.checked())} selected")

    def busy(self):
        return bool(self.worker and self.worker.isRunning())

    # ---- run
    def start_or_stop(self):
        if self.busy():
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Stopping…")
            self.worker.stop()
            return
        w = self.win
        if not w.dev:
            w.status("No device")
            return
        pkgs = self.checked()
        if not pkgs:
            w.status("Select at least one game")
            return
        self.save_settings()
        args = SimpleNamespace(duration=self.duration.value(), interval=self.interval.value(),
                               tester=self.tester.text().strip(), graphics=self.graphics.currentText().strip(),
                               between=self.between.value(), attach=self.attach.isChecked(),
                               decimal_comma=self.comma.isChecked(), out=os.path.join(APP_DIR, "perf_results"))
        self.worker = PerfWorker(w.adb_path, w.serial, w.dev, pkgs, args, self.confirm.isChecked())
        k = self.worker
        k.log.connect(self.log)
        k.phase.connect(self._phase)
        k.sample.connect(self._sample)
        k.game_started.connect(self._started)
        k.game_done.connect(self._done)
        k.ask_ready.connect(self._ask)
        k.all_done.connect(self._all_done)
        k.finished.connect(lambda: self._running(False))
        self._running(True)
        k.start()

    def _running(self, on):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("Stop" if on else "Start")
        self.btn_start.setObjectName("danger" if on else "primary")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        for x in (self.games, self.search, self.tester, self.graphics, self.duration, self.interval,
                  self.between, self.attach, self.confirm, self.comma):
            x.setEnabled(not on)
        self.win.lock_device(on)
        if not on:
            self.play_start = None

    def _started(self, pkg, i, n):
        self.current_pkg = pkg
        self.title.setText(pkg)
        self.subtitle.setText(f"{i}/{n} · {self.win.dev['device']} · {self.graphics.currentText()}")
        self.fps_chart.clear()
        self.load_chart.clear()
        self.live = {"fps": [], "launch": [None, None]}
        for c in (self.c_fps, self.c_cpu, self.c_gpu, self.c_ram, self.c_temp, self.c_launch):
            c.set(None, " ")
        self.progress.setValue(0)
        self.timer.setText("00:00 / 00:00")

    def _phase(self, name, value):
        if name in PHASES:
            set_pill(self.phase, *PHASES[name])
        if name in ("launch1_done", "launch2_done"):
            self.live["launch"][0 if name == "launch1_done" else 1] = value
            a, b = self.live["launch"]
            self.c_launch.value.setText(f"{'-' if a is None else a} / {'-' if b is None else b}")
            self.c_launch.sub.setText("seconds")
        if name == "play":
            self.play_start, self.play_duration = time.time(), value
        if name == "saving":
            self.play_start = None

    def _sample(self, s):
        fps, t = s.get("fps"), s["t_sec"]
        if fps is not None:
            self.live["fps"].append(fps)
        arr = self.live["fps"]
        if fps is None:
            self.c_fps.set(None, "detecting source…" if t < 15 else "no frame data")
        else:
            self.c_fps.set(f"{fps:.0f}", f"min {min(arr):.0f} · max {max(arr):.0f} · avg {sum(arr) / len(arr):.1f}")
            if s.get("fps_method"):
                self.c_fps.setToolTip(core.FPS_METHOD_NAMES.get(s["fps_method"], ""))
        cpu, gpu = s.get("cpu_game"), s.get("gpu")
        self.c_cpu.set(None if cpu is None else f"{cpu * 100:.0f}",
                       "" if s.get("cpu_total") is None else f"system {s['cpu_total'] * 100:.0f}%")
        self.c_gpu.set(None if gpu is None else f"{gpu * 100:.0f}", "not exposed" if gpu is None else " ")
        self.c_ram.set(s.get("game_pss_mb"), f"free {s.get('mem_available_mb') or '-'} MB")
        dt = s.get("device_temp_c")
        self.c_temp.set(s.get("battery_temp_c"), f"skin {dt}°C" if dt is not None else " ")
        if t > 0.5:
            self.fps_chart.add(t, {"fps": fps})
            self.load_chart.add(t, {"cpu": None if cpu is None else cpu * 100, "gpu": None if gpu is None else gpu * 100})

    def _tick(self):
        if self.play_start:
            el = time.time() - self.play_start
            self.timer.setText(f"{core.fmt_clock(el)} / {core.fmt_clock(self.play_duration)}")
            self.progress.setValue(int(1000 * min(1, el / max(1, self.play_duration))))

    def _done(self, summary, row):
        self.results.append((summary, row))
        r = self.table.rowCount()
        self.table.insertRow(r)
        it = QTableWidgetItem(summary["package"])
        it.setToolTip(summary["results_folder"])
        self.table.setItem(r, 0, it)
        for c, (idx, _, col) in enumerate(COURSE_COLS, start=1):
            cell = QTableWidgetItem(cell_text(row[idx]) or "-")
            cell.setData(Qt.UserRole, cell_text(row[idx]))
            cell.setTextAlignment(Qt.AlignCenter)
            if col == "Average FPS":
                cell.setForeground(QColor(C["fps"]))
                if summary.get("fps_method"):
                    cell.setToolTip(core.FPS_METHOD_NAMES.get(summary["fps_method"], ""))
            self.table.setItem(r, c, cell)
        self.table.clearSelection()
        self.table.selectRow(r)
        self.tabs.setTabText(0, f"Results ({len(self.results)})")
        set_pill(self.phase, "Done", C["ok"])
        self.progress.setValue(1000)

    def _ask(self, pkg):
        r = QMessageBox.question(self, "Next game", f"Next: {pkg}\nUnlock the device and continue.",
                                 QMessageBox.Ok | QMessageBox.Cancel)
        if r != QMessageBox.Ok:
            self.worker.stop_event.set()
        self.worker.ready_event.set()

    def _all_done(self, session, lines):
        self.last_session = session
        if lines:
            QApplication.clipboard().setText("\n".join(lines))
            self.win.status(f"Run finished · {len(lines)} row(s) copied")
            core.notify_done("perfgrab", f"Performance run finished: {len(lines)} game(s)")
        else:
            set_pill(self.phase, "Stopped", C["muted"])

    # ---- copy
    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.results[r] for r in rows] if rows else list(self.results)

    def copy_rows(self, headers):
        sel = self._selected()
        if not sel:
            return
        lines = ["\t".join(core.tsv_value(v, self.comma.isChecked()) for v in row) for _, row in sel]
        if headers:
            lines.insert(0, "\t".join(core.TABLE_COLUMNS))
        self.win.copy("\n".join(lines), f"{len(sel)} row(s) copied")

    def copy_selection(self):
        idx = self.table.selectedIndexes()
        if not idx:
            return
        rows, cols = sorted({i.row() for i in idx}), sorted({i.column() for i in idx})
        chosen = {(i.row(), i.column()) for i in idx}
        out = []
        for r in rows:
            vals = []
            for c in cols:
                it = self.table.item(r, c)
                v = it.data(Qt.UserRole) if it and (r, c) in chosen else ""
                vals.append(it.text() if it and v is None else (v or ""))
            out.append("\t".join(vals))
        self.win.copy("\n".join(out), f"{len(chosen)} cell(s) copied")

    def _menu(self, pos):
        it = self.table.itemAt(pos)
        if it and not it.isSelected():
            self.table.clearSelection()
            it.setSelected(True)
        m = QMenu(self)
        m.addAction(f"Copy\t{MOD}+C", self.copy_selection)
        m.addAction("Copy row (A-Z)", lambda: self.copy_rows(False))
        m.addAction("Copy row with headers", lambda: self.copy_rows(True))
        m.addSeparator()
        m.addAction("Open chart", self.open_chart)
        m.addAction("Show in folder", self.open_folder)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def open_folder(self):
        sel = self._selected()
        path = sel[-1][0]["results_folder"] if sel else os.path.join(APP_DIR, "perf_results")
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_chart(self):
        sel = self._selected()
        if sel:
            png = os.path.join(sel[-1][0]["results_folder"], "chart.png")
            if os.path.exists(png):
                QDesktopServices.openUrl(QUrl.fromLocalFile(png))
            else:
                self.win.status("No chart (matplotlib not installed)")

    def run_diag(self):
        pkg = getattr(self, "current_pkg", None) if self.busy() else None
        pkg = pkg or (self.checked() or [None])[0]
        if not pkg or not self.win.dev:
            self.win.status("Select a game")
            return
        self.btn_diag.setEnabled(False)
        self.log(f"FPS diagnostics: {pkg}")
        self.diag = DiagWorker(self.win.adb_path, self.win.serial, pkg)
        self.diag.done.connect(self._diag_done)
        self.diag.start()

    def _diag_done(self, pkg, text):
        self.btn_diag.setEnabled(True)
        out = os.path.join(APP_DIR, "perf_results")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, f"fps_diag_{pkg}_{time.strftime('%H%M%S')}.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        self.log_view.appendPlainText(text)
        self.tabs.setCurrentIndex(1)
        self.win.copy(text, "Diagnostics copied")

    def log(self, msg):
        self.log_view.appendPlainText(f"{time.strftime('%H:%M:%S')}  {msg.strip()}")

    def save_settings(self):
        s = self.win.settings
        for k, v in (("tester", self.tester.text()), ("graphics", self.graphics.currentText()),
                     ("duration", self.duration.value()), ("interval", self.interval.value()),
                     ("between", self.between.value()), ("pause", str(self.confirm.isChecked()).lower()),
                     ("comma", str(self.comma.isChecked()).lower()), ("selected", ",".join(self.checked()))):
            s.setValue(k, v)


# ============================================================================ interruptions page
class InterruptionsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.cl = None
        self.items = []
        self.tree_items = []
        self.worker = None
        self.cur = None            # index of item shown in the detail panel
        self.running_idx = None
        self.run_dir = None
        self.run_started = None
        self.awaiting_verdict = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- bar
        bar = QWidget()
        bar.setObjectName("bar")
        b = QHBoxLayout(bar)
        b.setContentsMargins(12, 8, 12, 8)
        b.setSpacing(8)
        self.btn_open = QPushButton("Open checklist…")
        self.btn_open.clicked.connect(self.open_dialog)
        self.btn_open.setMinimumWidth(150)
        self.btn_open.setMaximumWidth(230)
        b.addWidget(self.btn_open)
        b.addSpacing(6)
        b.addWidget(label("Sheet", "muted"))
        self.sheet = QComboBox()
        self.sheet.setMinimumWidth(130)
        self.sheet.activated.connect(lambda _: self.load(self.cl.path, self.sheet.currentText()) if self.cl else None)
        b.addWidget(self.sheet)
        b.addWidget(label("Column", "muted"))
        self.status_col = QComboBox()
        self.status_col.setMinimumWidth(130)
        self.status_col.activated.connect(self._status_col_changed)
        b.addWidget(self.status_col)
        b.addWidget(label("Game", "muted"))
        self.game = QComboBox()
        self.game.setEditable(True)
        self.game.setMinimumWidth(220)
        self.game.lineEdit().setPlaceholderText("Game package")
        self.game.setInsertPolicy(QComboBox.NoInsert)
        self.game.completer().setFilterMode(Qt.MatchContains)
        self.game.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.game.setCurrentText(win.settings.value("ix_game", ""))
        b.addWidget(self.game)
        self.opts_btn = QToolButton()
        self.opts_btn.setObjectName("btn")
        self.opts_btn.setText("Options ▾")
        self.opts_btn.setMinimumWidth(96)
        self.opts_btn.setPopupMode(QToolButton.InstantPopup)
        om = QMenu(self)
        self.long_bg = int(win.settings.value("long_bg", 120))
        grp = []
        for sec, name in ((60, "1 min"), (120, "2 min"), (300, "5 min"), (600, "10 min")):
            a = QAction(f"Long background: {name}", self, checkable=True)
            a.setChecked(sec == self.long_bg)
            a.triggered.connect(lambda _=False, s=sec: self._set_long_bg(s))
            om.addAction(a)
            grp.append(a)
        self._bg_actions = grp
        self.opts_btn.setMenu(om)
        b.addWidget(self.opts_btn)
        b.addStretch()
        self.prog_lbl = label("", "mono")
        self.prog_lbl.setMinimumWidth(48)
        self.prog_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        b.addWidget(self.prog_lbl)
        self.prog = QProgressBar()
        self.prog.setFixedSize(70, 4)
        self.prog.setTextVisible(False)
        b.addWidget(self.prog)
        self.btn_run = QToolButton()
        self.btn_run.setObjectName("run")
        self.btn_run.setText("Run all")
        self.btn_run.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_run.clicked.connect(lambda: self.start(selected=False))
        rm = QMenu(self)
        rm.addAction("Run all", lambda: self.start(selected=False))
        rm.addAction("Run selected", lambda: self.start(selected=True))
        self.btn_run.setMenu(rm)
        self.btn_sel = self.btn_run
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.hide()
        self.btn_report = QPushButton("Report")
        self.btn_report.clicked.connect(self.show_report)
        self.btn_report.setEnabled(False)
        for x in (self.btn_run, self.btn_stop, self.btn_report):
            x.setMinimumWidth(x.sizeHint().width() + 16)
            b.addWidget(x)
        for lab_ in bar.findChildren(QLabel):
            lab_.setMinimumWidth(lab_.sizeHint().width())
        root.addWidget(bar)

        # ---- body
        self.stack = QStackedWidget()
        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.addStretch()
        e_btn = QPushButton("Open checklist…")
        e_btn.setObjectName("primary")
        e_btn.setFixedWidth(200)
        e_btn.clicked.connect(self.open_dialog)
        ev.addWidget(label("No checklist loaded", "h2"), 0, Qt.AlignHCenter)
        hint = label(".xlsx with Summary / Check and Status columns", "muted")
        ev.addWidget(hint, 0, Qt.AlignHCenter)
        ev.addSpacing(8)
        ev.addWidget(e_btn, 0, Qt.AlignHCenter)
        ev.addStretch()
        self.stack.addWidget(empty)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        left = QSplitter(Qt.Vertical)
        left.setHandleWidth(1)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["ID", "Summary", "Priority", "Trigger", "Result", "Comment"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        hh = self.tree.header()
        hh.setStretchLastSection(False)
        for i, w in enumerate((110, 400, 74, 86, 76, 200)):
            self.tree.setColumnWidth(i, w)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.currentItemChanged.connect(self._tree_current)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        left.addWidget(self.tree)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        left.addWidget(self.log_view)
        left.setSizes([600, 120])
        split.addWidget(left)
        split.addWidget(self._build_detail())
        split.setSizes([860, 460])
        split.setStretchFactor(0, 1)
        self.stack.addWidget(split)
        root.addWidget(self.stack, 1)

        # shortcuts
        for i, st in enumerate(ix.STATUSES, start=1):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, activated=lambda s=st: self._pick(s))
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.save_next)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=lambda: self.btn_go.isVisible() and self.btn_go.click())
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self.btn_retry.isEnabled() and self.retry())

        last = win.settings.value("ix_last", "")
        if last and os.path.exists(last):
            QTimer.singleShot(0, lambda: self.load(last))

    # ---------------------------------------------------------------- detail panel
    def _build_detail(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setObjectName("detail")
        outer.setMinimumWidth(430)
        outer.setMaximumWidth(560)
        outer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        d = QWidget()
        d.setObjectName("detailInner")
        outer.setWidget(d)
        v = QVBoxLayout(d)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        top = QHBoxLayout()
        self.d_id = label("", "mono")
        self.d_prio = pill("", C["muted"])
        self.d_phase = pill("", C["muted"])
        top.addWidget(self.d_id)
        top.addWidget(self.d_prio)
        top.addStretch()
        top.addWidget(self.d_phase)
        v.addLayout(top)
        self.d_summary = label("", "h2", wrap=True)
        v.addWidget(self.d_summary)
        trig = QHBoxLayout()
        self.d_mode = pill("", C["muted"])
        trig.addWidget(self.d_mode)
        self.d_action = QComboBox()
        self.d_action.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.d_action.setMinimumContentsLength(12)
        self.d_action.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        for key, (mode, desc) in ix.ACTIONS.items():
            self.d_action.addItem(desc, key)
        self.d_action.activated.connect(self._action_changed)
        trig.addWidget(self.d_action, 1)
        v.addLayout(trig)

        self.prompt = QFrame()
        self.prompt.setObjectName("prompt")
        pl = QHBoxLayout(self.prompt)
        pl.setContentsMargins(12, 10, 10, 10)
        self.prompt_text = label("", wrap=True)
        pl.addWidget(self.prompt_text, 1)
        self.btn_go = QPushButton("Trigger")
        self.btn_go.setObjectName("primary")
        self.btn_go.setMinimumWidth(90)
        self.prompt_text.setMinimumWidth(120)
        self.prompt_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.btn_go.setToolTip(f"{MOD}+T")
        self.btn_go.clicked.connect(self._go)
        pl.addWidget(self.btn_go)
        self.prompt.hide()
        v.addWidget(self.prompt)

        v.addWidget(hline())
        v.addWidget(label("CHECKS", "section"))
        self.checks = QListWidget()
        self.checks.setFixedHeight(140)
        self.checks.setWordWrap(True)
        self.checks.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.checks.setSelectionMode(QAbstractItemView.NoSelection)
        self.checks.setStyleSheet(f"QListWidget {{ background:{C['bg']}; }}")
        v.addWidget(self.checks)
        shots = QHBoxLayout()
        self.th_before, self.th_after = Thumb("Before"), Thumb("After")
        shots.addWidget(self.th_before)
        shots.addWidget(self.th_after)
        v.addLayout(shots)

        v.addWidget(hline())
        v.addWidget(label("RESULT", "section"))
        res = QHBoxLayout()
        res.setSpacing(4)
        self.res_group = QButtonGroup(self)
        self.res_group.setExclusive(True)
        self.res_btns = {}
        for i, st in enumerate(ix.STATUSES, start=1):
            btn = QPushButton(st)
            btn.setObjectName("result")
            btn.setCheckable(True)
            btn.setToolTip(f"{MOD}+{i}")
            col = STATUS_COLOR[st]
            btn.setStyleSheet(f"QPushButton#result:checked {{ background:{col}; border-color:{col}; }}")
            btn.setMinimumWidth(60)
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            self.res_group.addButton(btn)
            self.res_btns[st] = btn
            res.addWidget(btn)
        v.addLayout(res)
        self.d_link = QLineEdit()
        self.d_link.setPlaceholderText("Issue link")
        v.addWidget(self.d_link)
        self.d_comment = QPlainTextEdit()
        self.d_comment.setObjectName("input")
        self.d_comment.setPlaceholderText("Comment")
        self.d_comment.setFixedHeight(64)
        v.addWidget(self.d_comment)
        foot = QHBoxLayout()
        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setToolTip(f"{MOD}+R")
        self.btn_retry.clicked.connect(self.retry)
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("primary")
        self.btn_save.setToolTip(f"{MOD}+Enter")
        self.btn_save.clicked.connect(self.save_next)
        foot.addWidget(self.btn_retry)
        foot.addStretch()
        foot.addWidget(self.btn_save)
        v.addLayout(foot)
        v.addStretch()
        self._detail_enabled(False)
        return outer

    def _detail_enabled(self, on):
        for w in list(self.res_btns.values()) + [self.d_link, self.d_comment, self.btn_save]:
            w.setEnabled(on)
        self.btn_retry.setEnabled(False)

    # ---------------------------------------------------------------- loading
    def open_dialog(self):
        start = os.path.dirname(self.cl.path) if self.cl else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Open checklist", start, "Excel (*.xlsx *.xlsm)")
        if path:
            self.load(path)

    def load(self, path, sheet=None):
        try:
            cl = ix.load_checklist(path, sheet)
        except Exception as e:
            QMessageBox.warning(self, "Open checklist", f"{os.path.basename(path)}\n\n{e}")
            return
        self.cl, self.items = cl, cl.items
        self.win.settings.setValue("ix_last", path)
        fm = self.btn_open.fontMetrics()
        self.btn_open.setText(fm.elidedText(os.path.basename(path), Qt.ElideMiddle, 190))
        self.btn_open.setToolTip(f"{path}\nClick to open another checklist")
        self.sheet.clear()
        self.sheet.addItems(cl.sheets)
        self.sheet.setCurrentText(cl.sheet)
        self.status_col.clear()
        for col, name in cl.status_cols:
            self.status_col.addItem(name, col)
        pref = next((i for i, (_, n) in enumerate(cl.status_cols) if "android" in n.lower()), 0)
        self.status_col.setCurrentIndex(pref)
        if pref:
            ix.read_status(cl, cl.status_cols[pref][0])
        self.run_dir = None
        self.btn_report.setEnabled(False)
        self._fill_tree()
        self.stack.setCurrentIndex(1)
        self._progress()
        self.win.status(f"Loaded {len(self.items)} checks from {os.path.basename(path)} / {cl.sheet}")

    def _status_col_changed(self, _):
        if self.cl:
            ix.read_status(self.cl, self.status_col.currentData())
            for it in self.items:
                it.result = ""
            self._fill_tree()

    def _fill_tree(self):
        self.tree.clear()
        self.tree_items = []
        groups = {}
        bold = QFont(self.tree.font())
        bold.setBold(True)
        for i, it in enumerate(self.items):
            g = groups.get(it.category)
            if g is None:
                g = QTreeWidgetItem([it.category])
                g.setFont(0, bold)
                g.setData(0, Qt.UserRole, -1)
                self.tree.addTopLevelItem(g)
                g.setFirstColumnSpanned(True)
                g.setExpanded(True)
                groups[it.category] = g
            row = QTreeWidgetItem(g)
            row.setData(0, Qt.UserRole, i)
            self.tree_items.append(row)
            self._paint_row(i)
        if self.tree_items:
            self.tree.setCurrentItem(self.tree_items[0])

    def _paint_row(self, i):
        it, row = self.items[i], self.tree_items[i]
        row.setText(0, it.id)
        row.setText(1, it.summary)
        row.setToolTip(1, it.summary)
        row.setText(2, it.priority)
        row.setText(3, it.mode.capitalize())
        row.setForeground(3, QColor(MODE_COLOR[it.mode]))
        row.setToolTip(3, ix.describe(it))
        st = it.final_status
        shown = st if st and st.lower() not in ix.NOT_RUN else "Not run"
        row.setText(4, shown)
        row.setForeground(4, QColor(STATUS_COLOR.get(shown, C["dim"])))
        comment = it.new_comment if it.result else it.comment
        row.setText(5, comment)
        row.setToolTip(5, comment)
        if self.running_idx == i:
            for c in range(6):
                row.setBackground(c, QColor("#1E1A33"))
        else:
            for c in range(6):
                row.setBackground(c, QBrush())

    def _progress(self):
        done = sum(1 for it in self.items if it.result)
        self.prog_lbl.setText(f"{done}/{len(self.items)}")
        self.prog.setRange(0, max(1, len(self.items)))
        self.prog.setValue(done)

    # ---------------------------------------------------------------- detail
    def _tree_current(self, cur, _prev):
        if cur is None:
            return
        i = cur.data(0, Qt.UserRole)
        if i is None or i < 0:
            return
        if self.running_idx is not None and self.awaiting_verdict is False and i != self.running_idx:
            pass
        if self.running_idx is not None:
            return          # during a run the panel follows the running item
        self.show_item(i)

    def show_item(self, i, checks=None, suggested=None):
        self.cur = i
        it = self.items[i]
        self.d_id.setText(it.id)
        self.d_prio.setVisible(bool(it.priority))
        set_pill(self.d_prio, it.priority or "", {"high": C["danger"], "medium": C["warn"]}.get(it.priority.lower(), C["muted"]))
        self.d_summary.setText(it.summary)
        set_pill(self.d_mode, it.mode.upper(), MODE_COLOR[it.mode])
        self.d_action.setCurrentIndex(max(0, self.d_action.findData(it.action)))
        self.d_action.setEnabled(self.running_idx is None)
        self.checks.clear()
        for ch in (checks if checks is not None else it.checks):
            self._add_check(ch)
        ev = {os.path.basename(p).rsplit("_", 1)[-1].split(".")[0]: p for p in it.evidence}
        self.th_before.show_file(ev.get("before"))
        self.th_after.show_file(ev.get("after"))
        status = suggested or it.final_status
        self.res_group.setExclusive(False)
        for st, btn in self.res_btns.items():
            btn.setChecked(st == status)
        self.res_group.setExclusive(True)
        self.d_link.setText(it.new_link or it.link)
        self.d_comment.setPlainText(it.new_comment if it.result else it.comment)
        self._detail_enabled(self.running_idx is None or self.awaiting_verdict)
        self.btn_retry.setEnabled(self.awaiting_verdict)
        self.btn_save.setText("Save && Next" if self.running_idx is not None else "Save")
        if self.running_idx is None:
            set_pill(self.d_phase, "", C["muted"])
            self.d_phase.hide()

    def _add_check(self, ch):
        icon = {"ok": "✓", "fail": "✕", "warn": "!", "na": "–"}[ch["state"]]
        color = {"ok": C["ok"], "fail": C["danger"], "warn": C["warn"], "na": C["dim"]}[ch["state"]]
        item = QListWidgetItem(f"{icon}  {ch['name']}" + (f"  ·  {ch['detail']}" if ch.get("detail") else ""))
        item.setForeground(QColor(color))
        item.setToolTip(ch.get("detail", ""))
        self.checks.addItem(item)

    def _action_changed(self, _):
        if self.cur is None:
            return
        it = self.items[self.cur]
        it.action = self.d_action.currentData()
        it.mode = ix.ACTIONS[it.action][0] if it.mode != ix.ASSISTED or it.action in (
            "call", "music", "headphones_wired", "generic", "loading_interrupt", "net_loading") else ix.ASSISTED
        set_pill(self.d_mode, it.mode.upper(), MODE_COLOR[it.mode])
        self._paint_row(self.cur)

    def _pick(self, status):
        if self.res_btns[status].isEnabled():
            self.res_btns[status].setChecked(True)

    def _current_status(self):
        b = self.res_group.checkedButton()
        return b.text() if b else ""

    # ---------------------------------------------------------------- run
    def start(self, selected):
        w = self.win
        if not self.cl:
            self.open_dialog()
            return
        if not w.dev:
            w.status("No device")
            return
        pkg = self.game.currentText().strip()
        if pkg not in w.packages:
            w.status("Select the game package")
            self.game.setFocus()
            return
        if selected:
            idxs = set()
            for t in self.tree.selectedItems():
                i = t.data(0, Qt.UserRole)
                if i == -1:
                    idxs |= {t.child(k).data(0, Qt.UserRole) for k in range(t.childCount())}
                elif i is not None:
                    idxs.add(i)
            queue = sorted(idxs)
        else:
            queue = list(range(len(self.items)))
        if not queue:
            w.status("Nothing selected")
            return
        w.settings.setValue("ix_game", pkg)
        if not self.run_dir:
            base = os.path.splitext(os.path.basename(self.cl.path))[0]
            self.run_dir = os.path.join(APP_DIR, "runs", f"{base}_{time.strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(self.run_dir, exist_ok=True)
            self.run_started = time.time()
            self.meta = None
        self.pkg = pkg
        self.worker = InterruptWorker(w.adb_path, w.serial, pkg, [(i, self.items[i]) for i in queue],
                                      {"long_bg_sec": self.long_bg}, os.path.join(self.run_dir, "evidence"))
        self.worker.event.connect(self._event)
        self.worker.finished.connect(self._finished)
        self._running(True)
        self.log(f"Run started: {len(queue)} check(s) · {pkg}")
        self.worker.start()
        threading.Thread(target=self._collect_meta, args=(pkg,), daemon=True).start()

    def _collect_meta(self, pkg):
        adb = core.Adb(self.win.adb_path, self.win.serial)
        self._build = ix.game_version(adb, pkg)

    def _running(self, on):
        self.btn_run.setVisible(not on)
        self.btn_stop.setVisible(on)
        for x in (self.btn_open, self.sheet, self.status_col, self.game, self.opts_btn):
            x.setEnabled(not on)
        self.win.lock_device(on)
        if not on:
            self.running_idx = None
            self.awaiting_verdict = False
            self.prompt.hide()
            self.d_phase.hide()
            self.d_action.setEnabled(True)
            self._detail_enabled(self.cur is not None)

    def stop(self):
        if self.worker:
            self.worker.runner.stop()
            self.btn_stop.setEnabled(False)
            self.log("Stopping, restoring device settings…")

    def _event(self, ev, d):
        if ev == "log":
            self.log(d["text"])
        elif ev == "item_started":
            prev = self.running_idx
            self.running_idx = d["idx"]
            self.awaiting_verdict = False
            if prev is not None:
                self._paint_row(prev)
            self._paint_row(d["idx"])
            self.tree.scrollToItem(self.tree_items[d["idx"]])
            self.tree.setCurrentItem(self.tree_items[d["idx"]])
            self.show_item(d["idx"], checks=[], suggested="")
            self.d_comment.clear()
            self.prompt.hide()
            self._detail_enabled(False)
            self.d_phase.show()
            it = self.items[d["idx"]]
            self.log(f"{it.id}: {ix.describe(it)}")
        elif ev == "phase":
            set_pill(self.d_phase, d["text"], C["info"])
            self.d_phase.show()
            if d["text"] != "Waiting":
                self.prompt.hide()
        elif ev == "wait_user":
            self.prompt_text.setText(d["prompt"])
            self.btn_go.setText(d["button"])
            self.btn_go.setEnabled(True)
            self.prompt.show()
            set_pill(self.d_phase, "Waiting", C["warn"])
            core.notify_done("perfgrab", d["prompt"]) if not self.window().isActiveWindow() else None
            self.btn_go.setFocus()
        elif ev == "checked":
            i = d["idx"]
            it = self.items[i]
            it.checks, it.evidence = d["checks"], d["evidence"]
            self.awaiting_verdict = True
            self.prompt.hide()
            self.show_item(i, suggested=d["status"])
            self.d_comment.setPlainText(d["comment"])
            set_pill(self.d_phase, "Review", C["accent"])
            self.btn_save.setFocus()
        elif ev == "item_done":
            pass

    def _go(self):
        if self.worker:
            self.btn_go.setEnabled(False)
            self.worker.runner.go()

    def retry(self):
        if self.worker and self.awaiting_verdict:
            self.awaiting_verdict = False
            self._detail_enabled(False)
            self.worker.runner.submit({"retry": True})

    def save_next(self):
        if self.cur is None or not self.btn_save.isEnabled():
            return
        status = self._current_status()
        if not status:
            self.win.status("Pick a result")
            return
        it = self.items[self.cur]
        it.result = status
        it.new_comment = self.d_comment.toPlainText().strip()
        it.new_link = self.d_link.text().strip()
        self._paint_row(self.cur)
        self._progress()
        self._autosave()
        if self.worker and self.awaiting_verdict and self.running_idx == self.cur:
            self.awaiting_verdict = False
            self._detail_enabled(False)
            self.worker.runner.submit({"status": status})
        else:
            nxt = self.cur + 1
            if nxt < len(self.tree_items):
                self.tree.setCurrentItem(self.tree_items[nxt])

    def _finished(self):
        prev = self.running_idx
        self._running(False)
        self.btn_stop.setEnabled(True)
        if prev is not None:
            self._paint_row(prev)
        self._autosave()
        done = sum(1 for it in self.items if it.result)
        self.log(f"Run finished · {done}/{len(self.items)} with result")
        core.notify_done("perfgrab", "Interruptions run finished")
        self.show_report()

    # ---------------------------------------------------------------- output
    def _meta(self):
        d = self.win.dev or {}
        return {
            "game": self.game.currentText().strip(), "build": getattr(self, "_build", ""),
            "device": d.get("device", ""), "os": d.get("os", ""),
            "tester": self.win.perf.tester.text().strip(),
            "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.run_started or time.time())),
            "duration_min": round((time.time() - self.run_started) / 60, 1) if self.run_started else None,
            "status_col": self.status_col.currentText(),
        }

    def _paths(self):
        if not self.run_dir:
            base = os.path.splitext(os.path.basename(self.cl.path))[0]
            self.run_dir = os.path.join(APP_DIR, "runs", f"{base}_{time.strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(self.run_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(self.cl.path))[0]
        return (os.path.join(self.run_dir, f"{base}_filled.xlsx"), os.path.join(self.run_dir, "report.md"),
                os.path.join(self.run_dir, "run.json"))

    def _autosave(self):
        if not self.cl or not any(it.result for it in self.items):
            return
        xlsx, md, js = self._paths()
        meta = self._meta()
        try:
            info = {"game": meta["game"],
                    "device": meta["device"], "os": meta["os"], "build": meta["build"],
                    "tester": meta["tester"], "date": meta["date"][:10]}
            ix.save_checklist(self.cl, xlsx, self.status_col.currentData(), info)
            with open(md, "w", encoding="utf-8") as f:
                f.write(ix.build_report(self.cl, self.items, meta))
            ix.save_run_json(js, self.cl, self.items, meta)
            self.btn_report.setEnabled(True)
        except Exception as e:
            self.log(f"save failed: {e!r}")

    def show_report(self):
        if not self.cl or not any(it.result for it in self.items):
            return
        self._autosave()
        xlsx, md, _ = self._paths()
        with open(md, encoding="utf-8") as f:
            text = f.read()
        dlg = QDialog(self)
        dlg.setWindowTitle("Run report")
        dlg.resize(640, 520)
        v = QVBoxLayout(dlg)
        counts = {s: sum(1 for it in self.items if it.result == s) for s in ix.STATUSES}
        row = QHBoxLayout()
        for s in ix.STATUSES:
            if counts[s]:
                row.addWidget(pill(f"{s} {counts[s]}", STATUS_COLOR[s]))
        row.addStretch()
        v.addLayout(row)
        view = QPlainTextEdit(text)
        view.setObjectName("log")
        view.setReadOnly(True)
        v.addWidget(view, 1)
        btns = QHBoxLayout()
        for text_, fn in (("Copy report", lambda: self.win.copy(text, "Report copied")),
                          ("Open checklist", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(xlsx))),
                          ("Show in folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.run_dir)))):
            b = QPushButton(text_)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch()
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(dlg.accept)
        btns.addWidget(close)
        v.addLayout(btns)
        self._report_dlg = dlg
        dlg.show()

    # ---------------------------------------------------------------- misc
    def _tree_menu(self, pos):
        m = QMenu(self)
        m.addAction("Run selected", lambda: self.start(True))
        m.addSeparator()
        for st in ix.STATUSES:
            m.addAction(f"Mark {st}", lambda s=st: self._mark_selected(s))
        m.addAction("Clear result", lambda: self._mark_selected(""))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _mark_selected(self, status):
        if self.running_idx is not None:
            return
        for t in self.tree.selectedItems():
            i = t.data(0, Qt.UserRole)
            if i is not None and i >= 0:
                self.items[i].result = status
                self._paint_row(i)
        self._progress()
        self._autosave()

    def _set_long_bg(self, sec):
        self.long_bg = sec
        self.win.settings.setValue("long_bg", sec)
        for a in self._bg_actions:
            a.setChecked(a.text().endswith(f"{sec // 60} min"))

    def set_packages(self, packages):
        cur = self.game.currentText()
        self.game.clear()
        self.game.addItems(packages)
        self.game.setCurrentText(cur)

    def busy(self):
        return bool(self.worker and self.worker.isRunning())

    def log(self, msg):
        self.log_view.appendPlainText(f"{time.strftime('%H:%M:%S')}  {msg}")


# ============================================================================ main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("perfgrab")
        self.resize(1400, 880)
        self.setMinimumSize(1180, 720)
        self.settings = QSettings("perfgrab", "perfgrab")
        self.adb_path = self.settings.value("adb", "adb")
        self.serial, self.dev, self.devices, self.packages = None, None, [], []
        self.dev_worker = None

        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)
        brand = label("perfgrab")
        brand.setStyleSheet("font-weight:800; font-size:14px; padding-right:10px;")
        tb.addWidget(brand)
        self.dot = QLabel("●")
        tb.addWidget(self.dot)
        self.dev_combo = QComboBox()
        self.dev_combo.setMinimumWidth(260)
        self.dev_combo.activated.connect(self._serial_picked)
        tb.addWidget(self.dev_combo)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        tb.addWidget(self.btn_refresh)
        self.btn_devcopy = QPushButton("Copy specs")
        self.btn_devcopy.setToolTip("Device model, CPU, GPU, RAM, OS (columns C-G)")
        self.btn_devcopy.clicked.connect(self.copy_device)
        tb.addWidget(self.btn_devcopy)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.dev_specs = label("", "muted")
        tb.addWidget(self.dev_specs)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        rail = QWidget()
        rail.setObjectName("rail")
        rail.setFixedWidth(104)
        rv = QVBoxLayout(rail)
        rv.setContentsMargins(6, 10, 6, 10)
        rv.setSpacing(4)
        self.nav = QButtonGroup(self)
        self.pages = QStackedWidget()
        self.perf = PerformancePage(self)
        self.inter = InterruptionsPage(self)
        for i, (name, icon, page) in enumerate((("Performance", "perf", self.perf),
                                                 ("Interruptions", "check", self.inter))):
            b = QToolButton()
            b.setText(name)
            b.setIcon(make_icon(icon))
            b.setIconSize(QSize(22, 22))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.nav.addButton(b, i)
            rv.addWidget(b)
            self.pages.addWidget(page)
        rv.addStretch()
        self.nav.idClicked.connect(self._nav)
        h.addWidget(rail)
        h.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        start = int(self.settings.value("page", 0))
        self.nav.button(start).setChecked(True)
        self.pages.setCurrentIndex(start)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.adb_lbl = label("", "muted")
        sb.addPermanentWidget(self.adb_lbl)

        self._set_dot(None)
        self.poll = QTimer(self)
        self.poll.timeout.connect(self._poll)
        self.poll.start(4000)
        self.refresh()

    def _nav(self, i):
        self.pages.setCurrentIndex(i)
        self.settings.setValue("page", i)

    # ---- device
    def _set_dot(self, ok):
        color = C["dim"] if ok is None else (C["ok"] if ok else C["danger"])
        self.dot.setStyleSheet(f"color:{color}; font-size:11px;")

    def busy(self):
        return self.perf.busy() or self.inter.busy()

    def lock_device(self, on):
        self.dev_combo.setEnabled(not on)
        self.btn_refresh.setEnabled(not on)

    def refresh(self):
        if (self.dev_worker and self.dev_worker.isRunning()) or self.busy():
            return
        self.dev_worker = DeviceWorker(self.adb_path, self.serial, True)
        self.dev_worker.done.connect(self._loaded)
        self.dev_worker.start()

    def _poll(self):
        if (self.dev_worker and self.dev_worker.isRunning()) or self.busy():
            return
        self.dev_worker = DeviceWorker(self.adb_path, full=False)
        self.dev_worker.done.connect(lambda r: self.refresh() if r["devices"] != self.devices else None)
        self.dev_worker.start()

    def _loaded(self, res):
        if res["error"]:
            self._set_dot(False)
            self.dev_combo.clear()
            self.dev_combo.addItem("adb not found")
            self.status(res["error"])
            return
        self.adb_path = res["adb"]
        self.settings.setValue("adb", self.adb_path)
        self.adb_lbl.setText(f"adb: {self.adb_path}")
        self.devices = res["devices"]
        self.dev_combo.clear()
        if not self.devices:
            self.dev, self.packages = None, []
            self._set_dot(False)
            self.dev_combo.addItem("No device")
            self.dev_specs.setText("")
        else:
            self.serial, self.dev, self.packages = res["serial"], res["info"], res["packages"]
            for s in self.devices:
                name = self.dev["device"] if s == self.serial else s
                self.dev_combo.addItem(f"{name}  ·  {s}", s)
            self.dev_combo.setCurrentIndex(self.devices.index(self.serial))
            self._set_dot(True)
            d = self.dev
            self.dev_specs.setText(f"{d['os']}  ·  {d['cpu']}  ·  {d['gpu']}  ·  {d['ram_gb']} GB")
            self.status(f"Connected: {d['device']} ({self.serial}) · {len(self.packages)} packages")
        self.perf.set_packages(self.packages)
        self.inter.set_packages(self.packages)

    def _serial_picked(self, i):
        s = self.dev_combo.itemData(i)
        if s and s != self.serial:
            self.serial = s
            self.refresh()

    def copy_device(self):
        if self.dev:
            d = self.dev
            self.copy("\t".join(cell_text(v) for v in (d["device"], d["cpu"], d["gpu"], d["ram_gb"], d["os"])),
                      "Device specs copied")

    # ---- helpers
    def copy(self, text, msg="Copied"):
        QApplication.clipboard().setText(text)
        self.status(msg)

    def status(self, msg):
        self.statusBar().showMessage(msg, 6000)

    def shutdown(self):
        self.poll.stop()
        for t in (self.dev_worker, self.perf.worker, self.inter.worker):
            if t and t.isRunning():
                if t is self.inter.worker:
                    t.runner.stop()
                elif t is self.perf.worker:
                    t.stop()
                t.wait(15000)

    def closeEvent(self, e):
        if self.busy():
            if QMessageBox.question(self, "perfgrab", "A run is in progress. Stop it and quit?") != QMessageBox.Yes:
                e.ignore()
                return
            if self.perf.worker:
                self.perf.worker.stop()
                self.perf.worker.wait(8000)
            if self.inter.worker:
                self.inter.worker.runner.stop()
                self.inter.worker.wait(15000)
        self.perf.save_settings()
        e.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("perfgrab")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    core.keep_awake()
    w = MainWindow()
    app.aboutToQuit.connect(w.shutdown)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
