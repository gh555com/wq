import sys
import uuid
import os
import signal
import time

from PySide2.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QScrollBar,
    QStyle, QStyleOptionSlider
)
from PySide2.QtCore import (
    Qt, QPoint, QPointF, QRect, QRectF, QSize, QTimer, QEvent, QUrl,
    QByteArray, QBuffer, QIODevice, QMimeData, qInstallMessageHandler, QSettings
)
from PySide2.QtGui import (
    QFont, QPainter, QPen, QColor, QTextCursor,
    QTextCharFormat, QPalette, QIntValidator,
    QTextDocument, QImage, QCursor
)

# ===== 配置 =====
_UNDO_CHAR_THRESHOLD = 444
_START_EMPTY_LINES = 222

# ===== 静音 OleSetClipboard 那条 Qt 警告（不影响实际拷贝）=====


def _qt_msg_handler(mode, context, message):
    try:
        s = str(message)
    except Exception:
        s = ""
    if "OleSetClipboard: Failed to set mime data" in s:
        return
    try:
        sys.__stderr__.write(s + "\n")
    except Exception:
        pass


try:
    qInstallMessageHandler(_qt_msg_handler)
except Exception:
    pass

# ===== 持久化设置（跨进程）=====
_SETTINGS = QSettings("dm", "wq_ggea")


def _s_get_str(k: str, default=""):
    try:
        v = _SETTINGS.value(k, default, type=str)
        return v if isinstance(v, str) else str(v)
    except Exception:
        try:
            v = _SETTINGS.value(k, default)
            return v if isinstance(v, str) else str(v)
        except Exception:
            return default


def _s_get_bool(k: str, default=False):
    try:
        return bool(_SETTINGS.value(k, default, type=bool))
    except Exception:
        v = _SETTINGS.value(k, default)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "y", "on")
        return bool(v)


def _s_set(k: str, v):
    try:
        _SETTINGS.setValue(k, v)
    except Exception:
        pass


q1 = "#ede4cf"
q2 = "#5a4630"
q4 = "#000000"
q5 = "rgba(220, 50, 47, 128)"
q83 = "rgba(0,0,0,20)"

SEL_BG = QColor(233, 211, 2)
MATCH_BG = QColor(233, 211, 2, 150)

# ✅ 滚动条标注：更深更暗金色，且 100% 不透明
MARK_COLOR = QColor("#3b2d05")

_WQ_PREFIX = "wq"
_WQ_DIRNAME = "wq_ggea_instances"


# ===== 懒加载：锁文件扫描相关 =====
def _wq_dir() -> str:
    import tempfile
    return os.path.join(tempfile.gettempdir(), _WQ_DIRNAME)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, 0, pid
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return True

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True


def _alloc_wq_id(prefix=_WQ_PREFIX):
    import glob

    wq_dir = _wq_dir()
    os.makedirs(wq_dir, exist_ok=True)

    for p in glob.glob(os.path.join(wq_dir, f"{prefix}_instance_*.lock")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                s = f.read().strip()
            pid = int(s) if s.isdigit() else -1
            if not _pid_exists(pid):
                try:
                    os.unlink(p)
                except Exception:
                    pass
        except Exception:
            pass

    for i in range(1, 100000):
        lock_path = os.path.join(wq_dir, f"{prefix}_instance_{i}.lock")
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return i, lock_path
        except FileExistsError:
            continue
        except Exception:
            continue

    return 1, None


def _free_wq_lock(lock_path: str):
    if not lock_path:
        return
    try:
        os.unlink(lock_path)
    except Exception:
        pass


def _qimage_to_png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _load_image_from_bytes(raw: bytes) -> QImage:
    img = QImage()
    img.loadFromData(QByteArray(raw))
    return img


def _decode_data_url_image(src: str) -> bytes:
    if not src.startswith("data:image"):
        return b""
    if "base64," not in src:
        return b""
    try:
        import base64
        b64 = src.split("base64,", 1)[1]
        return base64.b64decode(b64)
    except Exception:
        return b""


# ✅ 极致保真：只做不会影响外观的最小处理
def _normalize_text(s: str) -> str:
    if not s:
        return ""
    if "\r" in s:
        s = s.replace("\r\n", "\n").replace("\r", "\n")
    if "\ufeff" in s:
        s = s.replace("\ufeff", "")
    if "\u200b" in s:
        s = s.replace("\u200b", "")
    return s


# ✅ 懒加载：只在粘贴 HTML 时才用
_IMG_SRC_RE = None


def _extract_img_srcs(html: str):
    global _IMG_SRC_RE
    if not html:
        return []
    if _IMG_SRC_RE is None:
        import re
        _IMG_SRC_RE = re.compile(
            r"""<img[^>]+src\s*=\s*['"]([^'"]+)['"]""", re.I)
    try:
        return _IMG_SRC_RE.findall(html)
    except Exception:
        return []


class q6(QWidget):
    def __init__(q7, q8):
        super().__init__(q8)
        q7.setFixedSize(28, 28)
        q7.setCursor(Qt.SizeFDiagCursor)
        q7.q9 = False
        q7.q10 = QPoint()
        q7.q11 = QRect()

    def paintEvent(q7, q12):
        q13 = QPainter(q7)
        q13.setRenderHint(QPainter.Antialiasing)
        q14 = QPen(QColor("#8c7a3e"))
        q14.setWidth(2)
        q13.setPen(q14)
        q15 = q7.width()
        q16 = q7.height()
        q13.drawLine(q15 - 6, q16 - 20, q15 - 20, q16 - 6)
        q13.drawLine(q15 - 6, q16 - 12, q15 - 12, q16 - 6)

    def mousePressEvent(q7, q12):
        if q7.window().isMaximized():
            return
        if q12.button() == Qt.LeftButton:
            q7.q9 = True
            q7.q10 = q12.globalPos()
            q7.q11 = q7.window().geometry()

    def mouseMoveEvent(q7, q12):
        if q7.q9:
            q17 = q12.globalPos() - q7.q10
            q18 = QRect(q7.q11)
            q18.setWidth(max(200, q18.width() + q17.x()))
            q18.setHeight(max(200, q18.height() + q17.y()))
            q7.window().setGeometry(q18)

    def mouseReleaseEvent(q7, q12):
        q7.q9 = False


class q81(QWidget):
    def __init__(q85, q86):
        super().__init__(q86)
        q85.q86 = q86

    def sizeHint(q85):
        return QSize(q85.q86.q87(), 0)

    def paintEvent(q85, q12):
        q85.q86.q88(q12)


class qSB(QScrollBar):
    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self._markers = []
        self._jump_drag = False

    def set_markers(self, markers):
        self._markers = markers or []
        self.update()

    def _handle_rect(self) -> QRect:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        return self.style().subControlRect(QStyle.CC_ScrollBar, opt, QStyle.SC_ScrollBarSlider, self)

    def _value_from_y(self, y: int) -> int:
        mn = self.minimum()
        mx = self.maximum()
        rng = mx - mn
        if rng <= 0:
            return mn

        h = max(1, self.height())
        handle = self._handle_rect()
        hh = max(1, handle.height())

        track = max(1, h - hh)
        yy = int(y - hh * 0.5)
        yy = max(0, min(yy, track))

        ratio = yy / float(track)
        return int(mn + ratio * rng)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            handle = self._handle_rect()
            if not handle.contains(e.pos()):
                self._jump_drag = True
                self.setValue(self._value_from_y(e.pos().y()))
                e.accept()
                return

        self._jump_drag = False
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._jump_drag and (e.buttons() & Qt.LeftButton):
            self.setValue(self._value_from_y(e.pos().y()))
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._jump_drag = False
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)

        if not self._markers:
            return

        h = max(1, self.height())
        w = max(1, self.width())

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(Qt.NoPen)

        c = QColor(MARK_COLOR)
        c.setAlpha(255)
        p.setBrush(c)

        for kind, a, b in self._markers:
            y1 = int(a * h)
            y2 = int(b * h)
            if y2 <= y1:
                y2 = y1 + 2
            if (y2 - y1) < 2:
                y2 = y1 + 2

            y1 = max(0, y1)
            y2 = min(h, y2)

            if kind == "find":
                x = 1 if w >= 3 else 0
                ww = max(1, w - 2) if w >= 3 else w
            else:
                x = 0
                ww = w

            p.drawRect(x, y1, ww, max(1, y2 - y1))

        p.end()


class q19(QTextEdit):
    def __init__(q20):
        super().__init__()
        q20._zen = False

        q20._pending_single = False
        q20._mouse_trigger = False

        # ✅ 自定义 undo / redo 栈（核心）
        q20._undo = []  # act 或 ("grp",[act,...])
        q20._redo = []
        q20._in_replay = False  # undo/redo 回放期间不记录

        # ✅ 500ms 双抬起：Shift 顶部 / Alt 底部
        q20._shift_rel_t = 0.0
        q20._shift_rel_n = 0
        q20._alt_rel_t = 0.0
        q20._alt_rel_n = 0

        # ✅ debounce：减少大粘贴时 textChanged 风暴
        q20._debounce_ms = 118
        q20._debounce_timer = QTimer(q20)
        q20._debounce_timer.setSingleShot(True)
        q20._debounce_timer.timeout.connect(q20._flush_debounced_refresh)

        q20.setAcceptRichText(False)
        q20.setFont(QFont("Consolas", 11))

        # ✅ 必须关掉 Qt 自带 undo（否则必然整块回退）
        q20.setUndoRedoEnabled(False)

        q20.setContextMenuPolicy(Qt.NoContextMenu)

        q20.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        q20.setLineWrapMode(QTextEdit.WidgetWidth)

        q20.setMouseTracking(True)
        q20.viewport().setMouseTracking(True)

        q20._sb = qSB()
        q20.setVerticalScrollBar(q20._sb)

        q20.setStyleSheet(f'''
        QTextEdit {{
            background:{q1};
            color:{q2};
            border:none;
            selection-background-color: rgb(233,211,2);
            selection-color: {q2};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {q5};
            min-height: 40px;
            border-radius: 0px;
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QScrollBar:horizontal {{
            height: 0px;
            background: transparent;
        }}
        QScrollBar::handle:horizontal {{
            background: transparent;
        }}
        ''')

        pal = q20.palette()
        pal.setColor(QPalette.Highlight, SEL_BG)
        pal.setColor(QPalette.HighlightedText, QColor(q2))
        q20.setPalette(pal)

        q20._img_raw = {}
        q20._hover_img_name = ""
        q20._hover_img_pos = -1
        q20._hover_img_size = QSize(0, 0)

        q20._kope_name = ""
        q20._kope_raw = b""

        q20._last_needle = ""

        # ✅ hover bar：固定左下角 + 稳定显示（防闪）
        q20._img_bar = QWidget(q20.viewport())
        q20._img_bar.setObjectName("img_bar")
        q20._img_bar.setMouseTracking(True)
        q20._img_bar.setStyleSheet("""
        QWidget#img_bar{background:transparent;}
        QPushButton{border:1px solid rgba(0,0,0,60); border-radius:8px; background:rgba(255,255,255,185); padding-left:10px; padding-right:10px;}
        QPushButton:hover{background:rgba(255,255,255,235);}
        """)
        bar_lay = QHBoxLayout(q20._img_bar)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        bar_lay.setSpacing(6)

        q20._btn_save = QPushButton("另存")
        q20._btn_kope = QPushButton("kope")
        q20._btn_save.setFixedHeight(18)
        q20._btn_kope.setFixedHeight(18)
        q20._btn_save.clicked.connect(q20._save_hover_image)
        q20._btn_kope.clicked.connect(q20._kope_hover_image)

        bar_lay.addWidget(q20._btn_save)
        bar_lay.addWidget(q20._btn_kope)
        q20._img_bar.adjustSize()
        q20._img_bar.hide()

        # ✅ hover bar 防闪：离开图片后延迟隐藏（光标快速来回不闪）
        q20._img_hide_delay_ms = 120
        q20._img_hide_timer = QTimer(q20)
        q20._img_hide_timer.setSingleShot(True)
        q20._img_hide_timer.timeout.connect(q20._maybe_hide_img_bar)

        q20.q89 = q81(q20)

        q20.document().blockCountChanged.connect(q20.q90)
        q20.verticalScrollBar().valueChanged.connect(lambda _: q20.q89.update())
        q20.verticalScrollBar().valueChanged.connect(
            lambda _: q20._update_img_bar_pos())

        q20.textChanged.connect(q20._schedule_debounced_refresh)
        q20.selectionChanged.connect(q20._on_selection_changed)
        q20.cursorPositionChanged.connect(lambda: q20.viewport().update())

        # ✅ 启动就要 222 空行
        q20.setPlainText("\n" * _START_EMPTY_LINES)
        q20.q90(0)

    # ====== 只允许“光标点击”触发匹配高亮：编辑时清空 ======

    def _clear_match_highlight(q20):
        if q20._last_needle:
            q20.setExtraSelections([])
            q20._last_needle = ""
            q20._update_scroll_marks()

    # ====== clipboard mimeData 快照（修复 md 已被 C++ 删除）=====

    def _snapshot_clipboard_mimedata(q20) -> QMimeData:
        cb = QApplication.clipboard()

        md0 = None
        try:
            md0 = cb.mimeData()
        except Exception:
            md0 = None

        md = QMimeData()

        # text（最稳）
        try:
            md.setText(_normalize_text(cb.text() or ""))
        except Exception:
            pass

        # html
        try:
            if md0 is not None and md0.hasHtml():
                md.setHtml(md0.html() or "")
        except Exception:
            pass

        # urls
        try:
            if md0 is not None and md0.hasUrls():
                md.setUrls(md0.urls())
        except Exception:
            pass

        # image（用 cb.image 更稳）
        try:
            img = cb.image()
            if isinstance(img, QImage) and (not img.isNull()):
                md.setImageData(img)
                raw = _qimage_to_png_bytes(img)
                md.setData("image/png", QByteArray(raw))
        except Exception:
            pass

        # formats（尽量保真）
        try:
            if md0 is not None:
                for fmt in md0.formats():
                    try:
                        md.setData(fmt, QByteArray(md0.data(fmt)))
                    except Exception:
                        pass
        except Exception:
            pass

        return md

    # ====== undo/redo 记录结构 ======
    # 插入文本(1): ("ins_txt1", pos, ch)
    # 插入文本(N): ("ins_txtN", pos, text)
    # 插入图:     ("ins_img", pos, name)
    # 删除区间:   ("del_rng", pos, units)  units=[("txt",ch) or ("img",name), ...]
    # 分组:       ("grp", [act,...])  （acts 按“前进执行顺序”保存）

    def _new_edit(q20):
        # 任何新编辑都会清空 redo
        if q20._in_replay:
            return
        if q20._redo:
            q20._redo.clear()

    def _push_undo(q20, act):
        if q20._in_replay:
            return
        q20._undo.append(act)

    def _push_undo_group(q20, acts):
        if q20._in_replay:
            return
        if acts:
            q20._undo.append(("grp", acts))

    def _delete_range(q20, pos: int, ln: int):
        if ln <= 0:
            return
        doc = q20.document()
        maxp = doc.characterCount() - 1
        a = max(0, min(pos, maxp))
        b = max(0, min(pos + ln, maxp))
        if b <= a:
            return
        c = QTextCursor(doc)
        c.setPosition(a)
        c.setPosition(b, QTextCursor.KeepAnchor)
        c.removeSelectedText()
        q20.setTextCursor(c)

    def _unit_at_pos(q20, pos: int):
        doc = q20.document()
        maxp = doc.characterCount() - 1
        if pos < 0 or pos >= maxp:
            return None
        c = QTextCursor(doc)
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.KeepAnchor)
        fmt = c.charFormat()
        if fmt.isImageFormat():
            return ("img", fmt.toImageFormat().name())
        s = c.selectedText()
        if s == "\u2029":
            s = "\n"
        return ("txt", s)

    def _capture_units(q20, start: int, end: int):
        units = []
        for p in range(start, end):
            u = q20._unit_at_pos(p)
            if u is None:
                continue
            units.append(u)
        return units

    def _ensure_image_resource(q20, name: str):
        raw = q20._img_raw.get(name, b"")
        if not raw:
            return
        img = _load_image_from_bytes(raw)
        if img.isNull():
            return
        max_w = max(50, q20.viewport().width() - 20)
        show_img = img
        if img.width() > max_w:
            show_img = img.scaledToWidth(max_w, Qt.SmoothTransformation)
        q20.document().addResource(QTextDocument.ImageResource, QUrl(name), show_img)

    def _insert_image_tc(q20, tc: QTextCursor, img: QImage, raw: bytes, force_name: str = "") -> str:
        if not raw:
            raw = _qimage_to_png_bytes(img)

        name = force_name or f"img_{uuid.uuid4().hex}.png"
        q20._img_raw[name] = raw

        max_w = max(50, q20.viewport().width() - 20)
        show_img = img
        if img.width() > max_w:
            show_img = img.scaledToWidth(max_w, Qt.SmoothTransformation)

        q20.document().addResource(QTextDocument.ImageResource, QUrl(name), show_img)
        tc.insertImage(name)
        return name

    def _apply_forward(q20, act):
        tag = act[0]
        doc = q20.document()

        if tag == "ins_txt1":
            _, pos, ch = act
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.insertText(ch)
            q20.setTextCursor(c)
            return

        if tag == "ins_txtN":
            _, pos, text = act
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.insertText(text)
            q20.setTextCursor(c)
            return

        if tag == "ins_img":
            _, pos, name = act
            q20._ensure_image_resource(name)
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.insertImage(name)
            q20.setTextCursor(c)
            return

        if tag == "del_rng":
            _, pos, units = act
            ln = len(units)
            q20._delete_range(pos, ln)
            return

    def _apply_inverse(q20, act):
        tag = act[0]
        doc = q20.document()

        if tag == "ins_txt1":
            _, pos, ch = act
            q20._delete_range(pos, 1)
            return

        if tag == "ins_txtN":
            _, pos, text = act
            q20._delete_range(pos, len(text))
            return

        if tag == "ins_img":
            _, pos, name = act
            q20._delete_range(pos, 1)
            return

        if tag == "del_rng":
            _, pos, units = act
            c = QTextCursor(doc)
            c.setPosition(pos)
            for kind, payload in units:
                if kind == "txt":
                    c.insertText(payload)
                else:
                    q20._ensure_image_resource(payload)
                    c.insertImage(payload)
            q20.setTextCursor(c)
            return

    def _undo_one(q20):
        if not q20._undo:
            return
        q20._in_replay = True
        try:
            act = q20._undo.pop()
            if act[0] == "grp":
                acts = act[1]
                for sub in reversed(acts):
                    q20._apply_inverse(sub)
            else:
                q20._apply_inverse(act)
            q20._redo.append(act)
        finally:
            q20._in_replay = False

        q20._clear_match_highlight()
        q20._schedule_debounced_refresh()

    def _redo_one(q20):
        if not q20._redo:
            return
        q20._in_replay = True
        try:
            act = q20._redo.pop()
            if act[0] == "grp":
                acts = act[1]
                for sub in acts:
                    q20._apply_forward(sub)
            else:
                q20._apply_forward(act)
            q20._undo.append(act)
        finally:
            q20._in_replay = False

        q20._clear_match_highlight()
        q20._schedule_debounced_refresh()

    # ====== 刷新/绘制/行号 ======

    def _schedule_debounced_refresh(q20):
        q20._debounce_timer.start(q20._debounce_ms)

    def _flush_debounced_refresh(q20):
        if not q20._zen:
            q20.q89.update()
        q20._update_img_bar_pos()
        q20._update_scroll_marks()

    # ✅ 光标棒棒糖（红点 + 连线）
    def paintEvent(self, e):
        super().paintEvent(e)

        if not self.hasFocus():
            return

        r = self.cursorRect(self.textCursor())
        vp = self.viewport().rect()
        if not vp.intersects(r.adjusted(-2, -10, 2, 2)):
            return

        p = QPainter(self.viewport())

        cx = float(int(r.left()))
        top = float(int(r.top()))

        dot_d = 11.0
        radius = dot_d * 0.5
        cy = top - radius - 3.0

        p.setRenderHint(QPainter.Antialiasing, False)
        line_pen = QPen(QColor("#000000"))
        line_pen.setWidth(1)
        line_pen.setCosmetic(True)
        line_pen.setCapStyle(Qt.SquareCap)
        p.setPen(line_pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(cx, top), QPointF(cx, cy + radius))

        p.setRenderHint(QPainter.Antialiasing, True)
        red = QColor("#d60000")
        red.setAlphaF(0.4)
        dot_pen = QPen(red)
        dot_pen.setWidth(1)
        dot_pen.setCosmetic(True)
        p.setPen(dot_pen)
        p.setBrush(red)
        p.drawEllipse(QRectF(cx - radius, cy - radius, dot_d, dot_d))

        p.end()

    def keyReleaseEvent(q20, e):
        if e.isAutoRepeat():
            super().keyReleaseEvent(e)
            return

        now = time.monotonic()

        if e.key() == Qt.Key_Shift:
            if (now - q20._shift_rel_t) <= 0.5:
                q20._shift_rel_n += 1
            else:
                q20._shift_rel_n = 1
            q20._shift_rel_t = now
            if q20._shift_rel_n >= 2:
                q20._shift_rel_n = 0
                sb = q20.verticalScrollBar()
                sb.setValue(sb.minimum())
                e.accept()
                return

        elif e.key() == Qt.Key_Alt:
            if (now - q20._alt_rel_t) <= 0.5:
                q20._alt_rel_n += 1
            else:
                q20._alt_rel_n = 1
            q20._alt_rel_t = now
            if q20._alt_rel_n >= 2:
                q20._alt_rel_n = 0
                sb = q20.verticalScrollBar()
                sb.setValue(sb.maximum())
                e.accept()
                return

        super().keyReleaseEvent(e)

    def _on_selection_changed(q20):
        q20._pending_single = False
        if q20._mouse_trigger:
            q20.q96()
        else:
            q20._schedule_debounced_refresh()

    def scrollContentsBy(q20, dx, dy):
        super().scrollContentsBy(dx, dy)
        q20._update_img_bar_pos()

    def resizeEvent(q20, e):
        super().resizeEvent(e)
        q20.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        q20.setLineWrapMode(QTextEdit.WidgetWidth)
        q20._update_img_bar_pos()

        if q20._zen:
            return
        cr = q20.contentsRect()
        q20.q89.setGeometry(cr.left(), cr.top(), q20.q87(), cr.height())

    def q87(q20):
        blocks = max(1, q20.document().blockCount())
        digits = len(str(blocks))
        fm = q20.fontMetrics()
        try:
            w = fm.horizontalAdvance("9" * digits)
        except Exception:
            w = fm.width("9" * digits)
        return w + 1

    def q90(q20, _=0):
        if q20._zen:
            q20.setViewportMargins(0, 0, 0, 0)
        else:
            q20.setViewportMargins(q20.q87(), 0, 0, 0)
        q20.q89.update()
        q20._update_img_bar_pos()
        q20._update_scroll_marks()

    def q88(q20, event):
        if q20._zen:
            return

        painter = QPainter(q20.q89)
        rect = event.rect()
        painter.fillRect(rect, QColor(q1))

        doc = q20.document()
        layout = doc.documentLayout()
        y_offset = float(q20.verticalScrollBar().value())

        try:
            pos = layout.hitTest(
                QPointF(0.0, y_offset + float(rect.top())), Qt.FuzzyHit)
        except Exception:
            pos = -1

        block = doc.findBlock(pos) if (
            pos is not None and pos >= 0) else doc.firstBlock()
        if not block.isValid():
            block = doc.firstBlock()

        for _ in range(3):
            pb = block.previous()
            if pb.isValid():
                block = pb
            else:
                break

        while block.isValid():
            br = layout.blockBoundingRect(block)
            top = int(br.top() - y_offset)
            height = int(br.height())

            if top + height >= rect.top() and top <= rect.bottom():
                num = str(block.blockNumber() + 1)
                col = QColor(q2)
                col.setAlpha(40)
                painter.setPen(col)
                painter.drawText(0, top, q20.q89.width() - 1, height,
                                 Qt.AlignLeft | Qt.AlignVCenter, num)

            if top > rect.bottom():
                break

            block = block.next()

    def q28(q20, t):
        return t.replace("\u2029", "\n")

    def _selected_single_image_name(q20):
        tc = q20.textCursor()
        if not tc.hasSelection():
            return ""
        if (tc.selectionEnd() - tc.selectionStart()) != 1:
            return ""
        c = QTextCursor(q20.document())
        c.setPosition(tc.selectionStart())
        c.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 1)
        fmt = c.charFormat()
        if fmt.isImageFormat():
            return fmt.toImageFormat().name()
        return ""

    # ====== 核心：键盘编辑/粘贴/undo/redo ======

    def keyPressEvent(q20, e):
        # Ctrl+Z undo
        if (e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_Z:
            q20._undo_one()
            e.accept()
            return

        # Ctrl+Y redo
        if (e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_Y:
            q20._redo_one()
            e.accept()
            return

        # Ctrl+Shift+V：粘贴 kope 内存图（并入 undo/redo）
        if (e.modifiers() & Qt.ControlModifier) and (e.modifiers() & Qt.ShiftModifier) and e.key() == Qt.Key_V:
            if q20._kope_raw:
                img = _load_image_from_bytes(q20._kope_raw)
                if not img.isNull():
                    q20._new_edit()
                    q20._clear_match_highlight()

                    tc = q20.textCursor()
                    acts_group = []

                    if tc.hasSelection():
                        s = tc.selectionStart()
                        en = tc.selectionEnd()
                        units = q20._capture_units(s, en)
                        if units:
                            acts_group.append(("del_rng", s, units))
                        tc.removeSelectedText()
                        tc.setPosition(s)

                    pos = tc.position()
                    name = f"img_{uuid.uuid4().hex}.png"
                    q20._img_raw[name] = q20._kope_raw
                    q20._ensure_image_resource(name)
                    tc.insertImage(name)
                    acts_group.append(("ins_img", pos, name))

                    q20.setTextCursor(tc)

                    q20._push_undo_group(acts_group)
                    q20._schedule_debounced_refresh()
                    e.accept()
                    return

        # Ctrl+C（保留你原逻辑：单图不处理）
        if (e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_C:
            img_name = q20._selected_single_image_name()
            if img_name:
                e.accept()
                return

            tc = q20.textCursor()
            if not tc.hasSelection():
                tmp = QTextCursor(tc)
                tmp.select(QTextCursor.LineUnderCursor)
                t = q20.q28(tmp.selectedText())
                if not t.endswith("\n"):
                    t += "\n"
                QApplication.clipboard().setText(t)
                e.accept()
                return

            QApplication.clipboard().setText(q20.q28(tc.selectedText()))
            e.accept()
            return

        # Ctrl+V：用“快照 mimeData”避免 md 被 C++ 释放
        if (e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_V:
            q20._new_edit()
            q20._clear_match_highlight()
            md = q20._snapshot_clipboard_mimedata()
            q20.insertFromMimeData(md)
            e.accept()
            return

        # ✅ 修复：Ctrl+A 全选（不再插入 \x01）
        if (e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_A:
            q20.selectAll()
            e.accept()
            return

        # ✅ 关键修复：凡是带 Ctrl/Alt/Meta 的组合键（除上面自定义的），交给 Qt 默认处理
        # 否则 e.text() 可能是控制字符（例如 \x01），被当作“普通输入”插进文档
        if (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
            super().keyPressEvent(e)
            return

        tc = q20.textCursor()

        # Backspace
        if e.key() == Qt.Key_Backspace:
            if tc.hasSelection():
                q20._new_edit()
                q20._clear_match_highlight()

                s = tc.selectionStart()
                en = tc.selectionEnd()
                units = q20._capture_units(s, en)
                if units:
                    q20._push_undo(("del_rng", s, units))
                tc.removeSelectedText()
                tc.setPosition(s)
                q20.setTextCursor(tc)
                q20._schedule_debounced_refresh()
                e.accept()
                return
            else:
                pos = tc.position()
                if pos > 0:
                    q20._new_edit()
                    q20._clear_match_highlight()

                    u = q20._unit_at_pos(pos - 1)
                    if u is not None:
                        q20._push_undo(("del_rng", pos - 1, [u]))
                    tc.deletePreviousChar()
                    q20.setTextCursor(tc)
                    q20._schedule_debounced_refresh()
                    e.accept()
                    return

        # Delete
        if e.key() == Qt.Key_Delete:
            if tc.hasSelection():
                q20._new_edit()
                q20._clear_match_highlight()

                s = tc.selectionStart()
                en = tc.selectionEnd()
                units = q20._capture_units(s, en)
                if units:
                    q20._push_undo(("del_rng", s, units))
                tc.removeSelectedText()
                tc.setPosition(s)
                q20.setTextCursor(tc)
                q20._schedule_debounced_refresh()
                e.accept()
                return
            else:
                pos = tc.position()
                u = q20._unit_at_pos(pos)
                if u is not None:
                    q20._new_edit()
                    q20._clear_match_highlight()

                    q20._push_undo(("del_rng", pos, [u]))
                    tc.deleteChar()
                    q20.setTextCursor(tc)
                    q20._schedule_debounced_refresh()
                    e.accept()
                    return

        # 普通输入（包括 IME 一次提交多字符）
        t = e.text() or ""
        if t:
            if t == "\r":
                t = "\n"
            t = _normalize_text(t)
            if not t:
                e.accept()
                return

            q20._new_edit()
            q20._clear_match_highlight()

            # 有选区：先记录 del_rng（作为一个 undo step），再插入
            if tc.hasSelection():
                s = tc.selectionStart()
                en = tc.selectionEnd()
                units = q20._capture_units(s, en)
                if units:
                    q20._push_undo(("del_rng", s, units))
                tc.removeSelectedText()
                tc.setPosition(s)

            big = (len(t) >= _UNDO_CHAR_THRESHOLD)
            if big:
                pos0 = tc.position()
                tc.insertText(t)
                q20._push_undo(("ins_txtN", pos0, t))
            else:
                for ch in t:
                    pos0 = tc.position()
                    tc.insertText(ch)
                    q20._push_undo(("ins_txt1", pos0, ch))

            q20.setTextCursor(tc)
            q20._schedule_debounced_refresh()
            e.accept()
            return

        # 其它键：交给 Qt（方向键/翻页/选择等）
        super().keyPressEvent(e)

    # ====== 粘贴：按阈值决定逐字/整块 undo/redo ======

    def insertFromMimeData(q20, md):
        if q20._in_replay:
            return

        # 防御：极端情况下 md 也可能失效
        try:
            text = _normalize_text(md.text() or "")
        except RuntimeError:
            text = ""
        except Exception:
            text = ""

        try:
            has_html = bool(md.hasHtml())
        except Exception:
            has_html = False

        try:
            html = md.html() if has_html else ""
        except Exception:
            html = ""

        try:
            has_img = bool(md.hasImage())
        except Exception:
            has_img = False

        try:
            has_urls = bool(md.hasUrls())
        except Exception:
            has_urls = False

        big = (len(text) >= _UNDO_CHAR_THRESHOLD)

        tc = q20.textCursor()

        # 记录是否替换选区
        sel_del_act = None
        if tc.hasSelection():
            s = tc.selectionStart()
            en = tc.selectionEnd()
            units = q20._capture_units(s, en)
            sel_del_act = ("del_rng", s, units) if units else None
            tc.removeSelectedText()
            tc.setPosition(s)

        # 大块：整块一个 undo step（group）
        if big:
            acts = []
            if sel_del_act is not None:
                acts.append(sel_del_act)

            # 插入整块文本
            if text:
                pos0 = tc.position()
                tc.insertText(text)
                acts.append(("ins_txtN", pos0, text))

            # 直接图片
            if has_img:
                try:
                    img = md.imageData()
                except Exception:
                    img = None
                if isinstance(img, QImage) and not img.isNull():
                    raw = _qimage_to_png_bytes(img)
                    pos0 = tc.position()
                    name = f"img_{uuid.uuid4().hex}.png"
                    q20._img_raw[name] = raw
                    q20._ensure_image_resource(name)
                    tc.insertImage(name)
                    acts.append(("ins_img", pos0, name))

            # urls 本地图
            if has_urls:
                try:
                    urls = md.urls()
                except Exception:
                    urls = []
                for u in urls:
                    try:
                        if u.isLocalFile():
                            path = u.toLocalFile()
                            with open(path, "rb") as f:
                                raw = f.read()
                            img = _load_image_from_bytes(raw)
                            if not img.isNull():
                                pos0 = tc.position()
                                name = f"img_{uuid.uuid4().hex}.png"
                                q20._img_raw[name] = raw
                                q20._ensure_image_resource(name)
                                tc.insertImage(name)
                                acts.append(("ins_img", pos0, name))
                    except Exception:
                        pass

            # html 抽 img
            if html:
                for src in _extract_img_srcs(html):
                    raw = b""
                    s = (src or "").strip()
                    if s.startswith("data:image"):
                        raw = _decode_data_url_image(s)
                    elif s.startswith("file:"):
                        try:
                            lp = QUrl(s).toLocalFile()
                            if lp:
                                with open(lp, "rb") as f:
                                    raw = f.read()
                        except Exception:
                            raw = b""
                    else:
                        if os.path.exists(s):
                            try:
                                with open(s, "rb") as f:
                                    raw = f.read()
                            except Exception:
                                raw = b""

                    if raw:
                        img = _load_image_from_bytes(raw)
                        if not img.isNull():
                            pos0 = tc.position()
                            name = f"img_{uuid.uuid4().hex}.png"
                            q20._img_raw[name] = raw
                            q20._ensure_image_resource(name)
                            tc.insertImage(name)
                            acts.append(("ins_img", pos0, name))

            q20.setTextCursor(tc)
            q20._push_undo_group(acts)
            q20._schedule_debounced_refresh()
            return

        # 小块：逐字（每个字符一个 undo step）
        else:
            # 先把“替换选区的删除”作为一个 undo step（稳定支持 redo）
            if sel_del_act is not None:
                q20._push_undo(sel_del_act)

            # 逐字插入
            for ch in text:
                pos0 = tc.position()
                tc.insertText(ch)
                q20._push_undo(("ins_txt1", pos0, ch))

            # 直接图片（小块情况下：图作为 1 step）
            if has_img:
                try:
                    img = md.imageData()
                except Exception:
                    img = None
                if isinstance(img, QImage) and not img.isNull():
                    raw = _qimage_to_png_bytes(img)
                    pos0 = tc.position()
                    name = f"img_{uuid.uuid4().hex}.png"
                    q20._img_raw[name] = raw
                    q20._ensure_image_resource(name)
                    tc.insertImage(name)
                    q20._push_undo(("ins_img", pos0, name))

            # urls 本地图（每张图 1 step）
            if has_urls:
                try:
                    urls = md.urls()
                except Exception:
                    urls = []
                for u in urls:
                    try:
                        if u.isLocalFile():
                            path = u.toLocalFile()
                            with open(path, "rb") as f:
                                raw = f.read()
                            img = _load_image_from_bytes(raw)
                            if not img.isNull():
                                pos0 = tc.position()
                                name = f"img_{uuid.uuid4().hex}.png"
                                q20._img_raw[name] = raw
                                q20._ensure_image_resource(name)
                                tc.insertImage(name)
                                q20._push_undo(("ins_img", pos0, name))
                    except Exception:
                        pass

            # html 抽 img
            if html:
                for src in _extract_img_srcs(html):
                    raw = b""
                    s = (src or "").strip()
                    if s.startswith("data:image"):
                        raw = _decode_data_url_image(s)
                    elif s.startswith("file:"):
                        try:
                            lp = QUrl(s).toLocalFile()
                            if lp:
                                with open(lp, "rb") as f:
                                    raw = f.read()
                        except Exception:
                            raw = b""
                    else:
                        if os.path.exists(s):
                            try:
                                with open(s, "rb") as f:
                                    raw = f.read()
                            except Exception:
                                raw = b""

                    if raw:
                        img = _load_image_from_bytes(raw)
                        if not img.isNull():
                            pos0 = tc.position()
                            name = f"img_{uuid.uuid4().hex}.png"
                            q20._img_raw[name] = raw
                            q20._ensure_image_resource(name)
                            tc.insertImage(name)
                            q20._push_undo(("ins_img", pos0, name))

            q20.setTextCursor(tc)
            q20._schedule_debounced_refresh()
            return

    # ====== 光标点击：只在点击时触发 q96（匹配高亮） ======

    def mousePressEvent(q20, e):
        if e.button() == Qt.RightButton:
            w = q20.window()
            if hasattr(w, "toggle_zen"):
                w.toggle_zen()
            e.accept()
            return

        if e.button() == Qt.LeftButton:
            q20._mouse_trigger = True
            q20._pending_single = True
            interval = QApplication.instance().doubleClickInterval()
            QTimer.singleShot(interval, q20._run_single_click_highlight)

        super().mousePressEvent(e)

    def mouseReleaseEvent(q20, e):
        super().mouseReleaseEvent(e)
        q20._mouse_trigger = False

    def mouseDoubleClickEvent(q20, e):
        q20._pending_single = False
        q20._mouse_trigger = True
        super().mouseDoubleClickEvent(e)
        q20.q96()
        q20._mouse_trigger = False

    def _run_single_click_highlight(q20):
        if not q20._pending_single:
            return
        q20._pending_single = False
        if QApplication.mouseButtons() != Qt.NoButton:
            return
        q20.q96()
        q20._mouse_trigger = False

    # ====== 图片 hover bar（固定左下角 + 稳定） ======

    def leaveEvent(q20, e):
        try:
            q20._img_hide_timer.stop()
        except Exception:
            pass
        q20._img_bar.hide()
        q20._hover_img_name = ""
        q20._hover_img_pos = -1
        q20._hover_img_size = QSize(0, 0)
        super().leaveEvent(e)

    def _image_at_cursor(q20, c: QTextCursor):
        def _check_pos(p: int):
            if p < 0:
                return ("", -1)
            cur = QTextCursor(q20.document())
            cur.setPosition(p)
            fmt = cur.charFormat()
            if fmt.isImageFormat():
                name = fmt.toImageFormat().name()
                return (name, p)
            return ("", -1)

        name, pos = _check_pos(c.position())
        if name:
            return name, pos

        name, pos = _check_pos(c.position() - 1)
        if name:
            return name, pos

        return "", -1

    def _maybe_hide_img_bar(q20):
        # 超稳：如果光标还在 bar 上或图片上，就不隐藏
        try:
            pos = q20.viewport().mapFromGlobal(QCursor.pos())
        except Exception:
            pos = QPoint(-9999, -9999)

        try:
            if q20._img_bar.isVisible() and q20._img_bar.geometry().contains(pos):
                return
        except Exception:
            pass

        try:
            c = q20.cursorForPosition(pos)
            name, p = q20._image_at_cursor(c)
            if name:
                # 仍在图片上：继续显示
                q20._hover_img_name = name
                q20._hover_img_pos = p
                q20._update_img_bar_pos()
                return
        except Exception:
            pass

        q20._img_bar.hide()
        q20._hover_img_name = ""
        q20._hover_img_pos = -1
        q20._hover_img_size = QSize(0, 0)

    def mouseMoveEvent(q20, e):
        super().mouseMoveEvent(e)

        # 光标在 bar 上：保持显示（不做 hover 判定，避免闪）
        if q20._img_bar.isVisible() and q20._img_bar.geometry().contains(e.pos()):
            try:
                q20._img_hide_timer.stop()
            except Exception:
                pass
            q20._update_img_bar_pos()
            return

        c = q20.cursorForPosition(e.pos())
        name, pos = q20._image_at_cursor(c)

        if name and pos >= 0:
            q20._hover_img_name = name
            q20._hover_img_pos = pos

            img = q20.document().resource(QTextDocument.ImageResource, QUrl(name))
            if isinstance(img, QImage) and not img.isNull():
                q20._hover_img_size = img.size()
            else:
                q20._hover_img_size = QSize(0, 0)

            try:
                q20._img_hide_timer.stop()
            except Exception:
                pass
            q20._update_img_bar_pos()
            return

        # 不在图片上：延迟隐藏（防止快速抖动导致忽隐忽现）
        if q20._hover_img_name:
            q20._img_hide_timer.start(q20._img_hide_delay_ms)

    def _update_img_bar_pos(q20):
        # ✅ 要求：按钮只允许固定左下角，位置永远不动（相对 viewport）
        if not q20._hover_img_name or q20._hover_img_pos < 0:
            q20._img_bar.hide()
            return

        q20._img_bar.adjustSize()
        bar_h = q20._img_bar.height()
        bar_w = q20._img_bar.width()

        vp = q20.viewport().rect()
        if vp.width() <= 0 or vp.height() <= 0:
            q20._img_bar.hide()
            return

        margin = 8
        x = margin
        y = vp.height() - bar_h - margin

        # clamp
        x = max(0, min(x, max(0, vp.width() - bar_w)))
        y = max(0, min(y, max(0, vp.height() - bar_h)))

        q20._img_bar.move(x, y)
        if not q20._img_bar.isVisible():
            q20._img_bar.show()
        try:
            q20._img_bar.raise_()
        except Exception:
            pass

    def _save_hover_image(q20):
        from PySide2.QtWidgets import QFileDialog

        name = q20._hover_img_name
        if not name:
            return
        raw = q20._img_raw.get(name, b"")
        if not raw:
            return

        q20._img_bar.hide()

        last_dir = _s_get_str("last_save_dir", "")
        if last_dir and os.path.isdir(last_dir):
            start_path = os.path.join(last_dir, "image.png")
        else:
            start_path = "image.png"

        path, _ = QFileDialog.getSaveFileName(
            q20, "另存为图片", start_path,
            "PNG Image (*.png);;All Files (*.*)"
        )
        if not path:
            q20._update_img_bar_pos()
            return

        try:
            with open(path, "wb") as f:
                f.write(raw)
            _s_set("last_save_dir", os.path.dirname(path))
        except Exception:
            pass

        q20._update_img_bar_pos()

    def _kope_hover_image(q20):
        name = q20._hover_img_name
        if not name:
            return
        raw = q20._img_raw.get(name, b"")
        if not raw:
            return

        q20._kope_name = name
        q20._kope_raw = raw

        img = _load_image_from_bytes(raw)
        if not img.isNull():
            try:
                md = QMimeData()
                md.setImageData(img)
                md.setData("image/png", QByteArray(raw))
                QApplication.clipboard().setMimeData(md)
            except Exception:
                try:
                    QApplication.clipboard().setImage(img)
                except Exception:
                    pass

        old = q20._btn_kope.text()
        q20._btn_kope.setText("ok")
        QTimer.singleShot(260, lambda: q20._btn_kope.setText(old))

        q20._update_img_bar_pos()

    # ====== zen 模式 ======

    def set_zen(q20, on: bool):
        q20._zen = on
        q20.q89.setVisible(not on)

        if on:
            q20.setViewportMargins(0, 0, 0, 0)
        else:
            q20.q90(0)

        q20.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        q20.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        q20.setLineWrapMode(QTextEdit.WidgetWidth)

        QTimer.singleShot(0, q20._update_img_bar_pos)
        QTimer.singleShot(0, q20._update_scroll_marks)

    # ====== 匹配高亮（只允许光标触发 q96） ======

    def _needle(q20):
        tc = q20.textCursor()
        if tc.hasSelection():
            t = q20.q28(tc.selectedText()).strip("\n")
            if t and not t.isspace():
                return t

        tmp = QTextCursor(tc)
        tmp.select(QTextCursor.WordUnderCursor)
        t = q20.q28(tmp.selectedText()).strip()
        if t and not t.isspace():
            return t

        return ""

    def _apply_match_highlight(q20, needle):
        extras = []
        if not needle:
            q20.setExtraSelections(extras)
            q20._last_needle = ""
            q20._update_scroll_marks()
            return

        tc = q20.textCursor()
        sel_start = tc.selectionStart()
        sel_end = tc.selectionEnd()
        has_sel = tc.hasSelection()

        fmt = QTextCharFormat()
        fmt.setBackground(MATCH_BG)
        fmt.setForeground(QColor(q2))

        plain = q20.toPlainText()
        L = len(needle)
        if L <= 0:
            q20.setExtraSelections([])
            q20._last_needle = ""
            q20._update_scroll_marks()
            return

        start = 0
        while True:
            idx = plain.find(needle, start)
            if idx == -1:
                break

            if has_sel and idx == sel_start and (idx + L) == sel_end:
                start = idx + L
                continue

            c = QTextCursor(q20.document())
            c.setPosition(idx)
            c.setPosition(idx + L, QTextCursor.KeepAnchor)

            es = QTextEdit.ExtraSelection()
            es.cursor = c
            es.format = fmt
            extras.append(es)

            start = idx + L

        q20.setExtraSelections(extras)
        q20._last_needle = needle
        q20._update_scroll_marks()

    def q96(q20):
        QTimer.singleShot(0, lambda: q20._apply_match_highlight(q20._needle()))

    def _update_scroll_marks(q20):
        doc = q20.document()
        layout = doc.documentLayout()
        doc_h = float(layout.documentSize().height())
        if doc_h <= 1:
            q20.verticalScrollBar().set_markers([])
            return

        markers = []

        needle = q20._last_needle
        if needle:
            plain = q20.toPlainText()
            L = len(needle)
            if L > 0 and plain:
                if len(plain) <= 2_000_000:
                    start = 0
                    blocks = set()

                    tc = q20.textCursor()
                    sel_start = tc.selectionStart()
                    sel_end = tc.selectionEnd()
                    has_sel = tc.hasSelection()

                    while True:
                        idx = plain.find(needle, start)
                        if idx == -1:
                            break
                        if has_sel and idx == sel_start and (idx + L) == sel_end:
                            start = idx + L
                            continue
                        b = doc.findBlock(idx)
                        if b.isValid():
                            blocks.add(b.blockNumber())
                        start = idx + L

                    for bn in sorted(blocks):
                        b = doc.findBlockByNumber(bn)
                        if not b.isValid():
                            continue
                        br = layout.blockBoundingRect(b)
                        a = max(0.0, float(br.top()) / doc_h)
                        bb = min(1.0, float(br.bottom()) / doc_h)
                        markers.append(("find", a, bb))

        cur = q20.textCursor()
        if cur.hasSelection():
            s = cur.selectionStart()
            e = max(s + 1, cur.selectionEnd())
            b1 = doc.findBlock(s)
            b2 = doc.findBlock(e - 1)
            if b1.isValid() and b2.isValid():
                br1 = layout.blockBoundingRect(b1)
                br2 = layout.blockBoundingRect(b2)
                a = max(0.0, float(br1.top()) / doc_h)
                bb = min(1.0, float(br2.bottom()) / doc_h)
                markers.append(("sel", a, bb))

        q20.verticalScrollBar().set_markers(markers)


class q64(QWidget):
    def __init__(q65):
        super().__init__()
        q65.setWindowFlags(Qt.FramelessWindowHint)
        q65.setContextMenuPolicy(Qt.NoContextMenu)
        q65.setStyleSheet(f"background:{q1}; border:none;")

        # ✅ 启动极快：先不扫锁文件（延迟到 show 后）
        q65._wq_id = 0
        q65._wq_lock = None

        q65.q66 = False
        q65.q67 = QPoint()
        q65.q70 = False
        q65.q71 = QRect()
        q65._zen = False

        q65.q68()

        rect_s = _s_get_str("win_rect", "")
        if rect_s:
            try:
                x, y, w, h = [int(i) for i in rect_s.split(",")[:4]]
                if w >= 200 and h >= 200:
                    q65.setGeometry(x, y, w, h)
                else:
                    q65.setGeometry(1935, 780, 860, 1275)
            except Exception:
                q65.setGeometry(1935, 780, 860, 1275)
        else:
            q65.setGeometry(1935, 780, 860, 1275)

        q65._sync_logo()
        q65._sync_max_button()

        q65.set_zen(True)

        QTimer.singleShot(0, q65._late_init_after_show)

    def _late_init_after_show(q65):
        q65._swap_in_real_editor()

        # ✅ 修复：Zen 模式不显示右下角倒三角拉杆
        try:
            if not q65._zen:
                q65.q80.show()
                q65.q80.raise_()
                q65.q80.move(q65.width() - 28, q65.height() - 28)
            else:
                q65.q80.hide()
        except Exception:
            pass

        QTimer.singleShot(0, q65._late_alloc_wq_id)

        if _s_get_bool("win_max", False):
            QTimer.singleShot(0, q65._restore_maximized)

    def _swap_in_real_editor(q65):
        old = q65.q79 if hasattr(q65, "q79") else None
        old_text = ""
        if isinstance(old, QTextEdit):
            try:
                old_text = old.toPlainText()
            except Exception:
                old_text = ""

        try:
            q65.q72.removeWidget(old)
        except Exception:
            pass
        try:
            if old is not None:
                old.deleteLater()
        except Exception:
            pass

        q65.q79 = q19()
        if old_text:
            q65.q79.setPlainText(old_text)
        else:
            q65.q79.setPlainText("\n" * _START_EMPTY_LINES)

        q65.q72.insertWidget(1, q65.q79)

        for w in [q65, q65.q73, q65.q79, q65.q79.viewport(),
                  q65.q_font_box, q65.q75, q65.q76, q65.q77, q65.q_logo]:
            try:
                w.installEventFilter(q65)
            except Exception:
                pass

        QTimer.singleShot(0, q65.apply_font_size)
        q65.set_zen(q65._zen)
        QTimer.singleShot(0, q65.q79.setFocus)

    def _late_alloc_wq_id(q65):
        try:
            q65._wq_id, q65._wq_lock = _alloc_wq_id()
        except Exception:
            q65._wq_id, q65._wq_lock = 1, None
        q65._sync_logo()

    def _restore_maximized(q65):
        try:
            q65.q71 = q65.geometry()
        except Exception:
            pass
        q65.showMaximized()
        q65.q70 = True
        q65._sync_max_button()

    def _sync_logo(q65):
        if hasattr(q65, "q_logo"):
            if q65._wq_id:
                q65.q_logo.setText(f"{_WQ_PREFIX}{q65._wq_id} : 的梦gaea")
            else:
                q65.q_logo.setText("wq? : 的梦gaea")

    def _sync_max_button(q65):
        if not hasattr(q65, "q76"):
            return
        q65.q76.setText("❐" if q65.isMaximized() else "□")

    def q68(q65):
        q65.q72 = QVBoxLayout(q65)
        q65.q72.setContentsMargins(0, 0, 0, 0)
        q65.q72.setSpacing(0)

        q65.q73 = QWidget()
        q65.q73.setFixedHeight(32)
        q65.q73.setStyleSheet(f"background:{q1}; border:none;")
        q74 = QHBoxLayout(q65.q73)
        q74.setContentsMargins(8, 0, 8, 0)
        q74.setSpacing(8)

        q65.q_logo = QLabel("wq? : 的梦gaea")
        q65.q_logo.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        f = QFont("Tahoma", 9)
        f.setBold(False)
        q65.q_logo.setFont(f)
        q65.q_logo.setStyleSheet(
            f"color:{q2}; font-weight:normal; margin-top:1px;")

        q65.q_font_box = QLineEdit()
        q65.q_font_box.setFixedWidth(70)
        saved_pt = _s_get_str("font_pt", "11").strip() or "11"
        q65.q_font_box.setText(saved_pt)

        q65.q_font_box.setAlignment(Qt.AlignCenter)
        q65.q_font_box.setValidator(QIntValidator(1, 200, q65.q_font_box))
        q65.q_font_box.setStyleSheet(
            "QLineEdit{border:1px solid rgba(0,0,0,40); border-radius:6px; padding:2px; background:rgba(255,255,255,80);}"
            "QLineEdit:focus{border:1px solid rgba(0,0,0,90);}"
        )
        q65.q_font_box.editingFinished.connect(q65.apply_font_size)

        q65.q75 = QPushButton("─")
        q65.q76 = QPushButton("□")
        q65.q77 = QPushButton("✕")

        btn_w = 68
        for b in (q65.q75, q65.q76, q65.q77):
            b.setFixedSize(btn_w, 28)
            b.setStyleSheet(
                "QPushButton{border:none; background:transparent; padding-left:10px; padding-right:10px; font-size:13px;}"
                "QPushButton:hover{background:%s;}" % q83
            )
            b.setContextMenuPolicy(Qt.NoContextMenu)

        q65.q75.clicked.connect(q65.showMinimized)
        q65.q76.clicked.connect(q65.q92)
        q65.q77.clicked.connect(q65.close)

        q74.addWidget(q65.q_logo)
        q74.addStretch()
        q74.addWidget(q65.q_font_box)
        q74.addWidget(q65.q75)
        q74.addWidget(q65.q76)
        q74.addWidget(q65.q77)

        q65.q72.addWidget(q65.q73)

        # ✅ placeholder：窗口一出现就必须是 222 空行
        # ✅ 防止 swap 前输入导致状态错乱：placeholder 只读且不抢焦点
        ph = QTextEdit()
        ph.setAcceptRichText(False)
        ph.setUndoRedoEnabled(False)
        ph.setReadOnly(True)
        ph.setFocusPolicy(Qt.NoFocus)
        ph.setFont(QFont("Consolas", 11))
        ph.setStyleSheet(
            f"QTextEdit{{background:{q1}; color:{q2}; border:none;}}")
        ph.setPlainText("\n" * _START_EMPTY_LINES)
        q65.q79 = ph
        q65.q72.addWidget(q65.q79)

        q65.q80 = q6(q65)

    def apply_font_size(q65):
        t = q65.q_font_box.text().strip()
        if not t:
            return
        try:
            size = int(t)
        except Exception:
            return
        size = max(1, min(200, size))

        _s_set("font_pt", str(size))

        try:
            f = q65.q79.font()
            f.setPointSize(size)
            q65.q79.setFont(f)
            if hasattr(q65.q79, "q90"):
                q65.q79.q90(0)
            q65.q79.viewport().update()
        except Exception:
            pass

    def toggle_zen(q65):
        q65.set_zen(not q65._zen)

    def set_zen(q65, on: bool):
        q65._zen = on
        q65.q73.setVisible(not on)

        # ✅ 修复 1：zen 模式不要显示右下角拉杆
        q65.q80.setVisible(not on)
        try:
            if not on:
                q65.q80.show()
                q65.q80.raise_()
            else:
                q65.q80.hide()
        except Exception:
            pass

        if hasattr(q65, "q79") and hasattr(q65.q79, "set_zen"):
            q65.q79.set_zen(on)

    # ✅ 点击顶栏一次，更新“编辑窗口文本总字节数（b）”
    def _update_logo_bytes(q65):
        try:
            wid = q65._wq_id if q65._wq_id else "?"
            txt = ""
            if hasattr(q65, "q79") and hasattr(q65.q79, "toPlainText"):
                txt = q65.q79.toPlainText() or ""
            n = len(txt.encode("utf-8"))
            q65.q_logo.setText(f"{_WQ_PREFIX}{wid} : {n:,}")
        except Exception:
            pass

    def eventFilter(q65, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            try:
                if (not q65._zen) and event.button() == Qt.LeftButton:
                    if obj in (q65.q73, q65.q_logo, q65.q_font_box, q65.q75, q65.q76, q65.q77):
                        q65._update_logo_bytes()
            except Exception:
                pass

            try:
                if event.button() == Qt.RightButton:
                    q65.toggle_zen()
                    return True
            except Exception:
                pass

        if event.type() == QEvent.MouseButtonDblClick:
            try:
                if obj == q65.q73 and event.button() == Qt.LeftButton and not q65._zen:
                    q65.q92()
                    return True
            except Exception:
                pass

        return False

    def changeEvent(q65, e):
        super().changeEvent(e)
        q65._sync_max_button()

    def resizeEvent(q65, e):
        # ✅ 拉杆仅非 zen 才显示 + 跟随位置
        if not q65._zen:
            q65.q80.move(q65.width() - 28, q65.height() - 28)
            try:
                q65.q80.show()
                q65.q80.raise_()
            except Exception:
                pass
        else:
            try:
                q65.q80.hide()
            except Exception:
                pass

    def mousePressEvent(q65, e):
        if e.button() == Qt.LeftButton and e.pos().y() < 32 and not q65.isMaximized() and not q65._zen:
            q65.q66 = True
            q65.q67 = e.globalPos() - q65.pos()

    def mouseMoveEvent(q65, e):
        if q65.q66:
            q65.move(e.globalPos() - q65.q67)

    def mouseReleaseEvent(q65, e):
        q65.q66 = False

    def q92(q65):
        if not q65.q70:
            q65.q71 = q65.geometry()
            q65.showMaximized()
            q65.q70 = True
        else:
            q65.showNormal()
            if q65.q71.isValid():
                q65.setGeometry(q65.q71)
            q65.q70 = False
        q65._sync_max_button()

    def closeEvent(q65, e):
        try:
            maxed = bool(q65.isMaximized() or q65.q70)
            _s_set("win_max", bool(maxed))
            base = q65.q71 if (maxed and q65.q71.isValid()) else q65.geometry()
            _s_set(
                "win_rect", f"{base.x()},{base.y()},{base.width()},{base.height()}")
        except Exception:
            pass

        _free_wq_lock(q65._wq_lock)
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    def _sigint_handler(*_):
        try:
            app.quit()
        except Exception:
            pass

    try:
        signal.signal(signal.SIGINT, _sigint_handler)
        _t = QTimer()
        _t.start(50)
        _t.timeout.connect(lambda: None)
    except Exception:
        pass

    win = q64()
    win.show()
    sys.exit(app.exec_())
