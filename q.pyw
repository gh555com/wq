import sys
import os
import signal
import time
import re
import tempfile

from PySide2.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QTextEdit, QLineEdit, QLabel, QScrollBar,
    QStyle, QStyleOptionSlider, QFileDialog
)
from PySide2.QtCore import (
    Qt, QPoint, QPointF, QRect, QRectF, QSize, QTimer, QEvent,
    QByteArray, QBuffer, QIODevice, QMimeData, qInstallMessageHandler, QSettings, QUrl
)
from PySide2.QtGui import (
    QFont, QPainter, QPen, QColor, QTextCursor,
    QTextCharFormat, QPalette, QIntValidator, QImage
)

# ===== 配置 =====
_UNDO_CHAR_THRESHOLD = 444
_START_EMPTY_LINES = 222

# ===== 静音警告 =====
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

# ===== 持久化设置 =====
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
q5 = "rgba(220, 50, 47, 128)"
q83 = "rgba(0,0,0,20)"

SEL_BG = QColor(233, 211, 2)
MATCH_BG = QColor(233, 211, 2, 150)
MARK_COLOR = QColor("#3b2d05")
IMG_BORDER_COLOR = QColor("#8c7a3e")
IMG_HOVER_BORDER = QColor("#FF6600")

_WQ_PREFIX = "wq"
_WQ_DIRNAME = "wq_ggea_instances"

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
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
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

_IMG_SRC_RE = None
def _extract_img_srcs(html: str):
    global _IMG_SRC_RE
    if not html:
        return []
    if _IMG_SRC_RE is None:
        _IMG_SRC_RE = re.compile(r"""<img[^>]+src\s*=\s*['"]([^'"]+)['"]""", re.I)
    try:
        return _IMG_SRC_RE.findall(html)
    except Exception:
        return []

def _detect_image_format(raw: bytes) -> tuple:
    """检测图片格式，返回 (mime_type, extension)"""
    if not raw:
        return ("image/png", "png")
    if raw.startswith(b'\x89PNG'):
        return ("image/png", "png")
    elif raw.startswith(b'GIF87a') or raw.startswith(b'GIF89a'):
        return ("image/gif", "gif")
    elif raw.startswith(b'\xFF\xD8\xFF'):
        return ("image/jpeg", "jpg")
    elif raw.startswith(b'BM'):
        return ("image/bmp", "bmp")
    elif len(raw) > 12 and raw[8:12] == b'WEBP':
        return ("image/webp", "webp")
    elif raw.startswith(b'RIFF') and len(raw) > 12 and raw[8:12] == b'WEBP':
        return ("image/webp", "webp")
    elif raw.startswith(b'\x00\x00\x01\x00'):
        return ("image/x-icon", "ico")
    return ("image/png", "png")

def _format_size(size_bytes: int) -> str:
    """格式化文件大小：b小写，K/M/G大写，只保留整数，无空格"""
    if size_bytes < 1024:
        return f"{int(size_bytes)}b"
    elif size_bytes < 1024 * 1024:
        return f"{int(size_bytes / 1024)}Kb"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{int(size_bytes / 1024 / 1024)}Mb"
    else:
        return f"{int(size_bytes / 1024 / 1024 / 1024)}Gb"


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
        mn, mx = self.minimum(), self.maximum()
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
            # 所有类型的标注都显示在左边
            x = 0
            ww = w
            p.drawRect(x, y1, ww, max(1, y2 - y1))
        p.end()


# 图片标记正则：[ 787x448, 5Mb  #1 ]
_IMG_TAG_RE = re.compile(r'\[\s*(\d+)x(\d+),\s*\d+[bKMG]b\s+#(\d+)\s*\]')


class q19(QPlainTextEdit):
    """纯文本编辑器，图片自己绘制，支持逐字Undo/Redo"""

    def __init__(q20):
        super().__init__()
        q20._zen = False

        q20._pending_single = False
        q20._mouse_trigger = False

        # Undo/Redo 系统
        q20._undo = []
        q20._redo = []
        q20._in_replay = False
        q20._last_text = ""

        # 双击快捷键计时
        q20._shift_rel_t = 0.0
        q20._shift_rel_n = 0
        q20._alt_rel_t = 0.0
        q20._alt_rel_n = 0

        q20._debounce_ms = 118
        q20._debounce_timer = QTimer(q20)
        q20._debounce_timer.setSingleShot(True)
        q20._debounce_timer.timeout.connect(q20._flush_debounced_refresh)

        q20.setFont(QFont("Consolas", 11))
        q20.setUndoRedoEnabled(False)
        q20.setContextMenuPolicy(Qt.NoContextMenu)
        q20.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        q20.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        q20.setMouseTracking(True)
        q20.viewport().setMouseTracking(True)

        q20._sb = qSB()
        q20.setVerticalScrollBar(q20._sb)

        q20.setStyleSheet(f'''
        QPlainTextEdit {{
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
        ''')

        pal = q20.palette()
        pal.setColor(QPalette.Highlight, SEL_BG)
        pal.setColor(QPalette.HighlightedText, QColor(q2))
        q20.setPalette(pal)

        # 图片系统
        q20._img_counter = 0
        q20._img_data = {}   # {id: raw_bytes}
        q20._img_info = {}   # {id: (width, height, size_bytes)}
        q20._img_cache = {}  # {(id, max_w): QImage}

        q20._hover_img_id = 0
        q20._hover_img_rect = QRect()

        q20._kope_id = 0
        q20._kope_raw = b""

        # ✅ 任务一：为 GIF kope 准备临时文件（最稳：像复制文件一样粘贴）
        q20._kope_tmp_by_id = {}   # {img_id: path}
        q20._kope_tmp_files = []   # [path,...]

        q20._last_needle = ""

        # 图片 hover bar
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

        # 行号区
        q20.q89 = q81(q20)

        q20.blockCountChanged.connect(q20.q90)
        q20.verticalScrollBar().valueChanged.connect(lambda _: q20.q89.update())
        q20.verticalScrollBar().valueChanged.connect(lambda _: q20._update_hover())

        # Undo/Redo：监听文档变化
        q20.document().contentsChange.connect(q20._on_contents_change)

        q20.selectionChanged.connect(q20._on_selection_changed)
        q20.cursorPositionChanged.connect(lambda: q20.viewport().update())

        init_text = "\n" * _START_EMPTY_LINES
        q20.setPlainText(init_text)
        q20._last_text = init_text
        q20.q90(0)

    def doc_size_bytes(q20) -> int:
        try:
            plain = q20.toPlainText() or ""
        except Exception:
            plain = ""
        plain = _IMG_TAG_RE.sub('', plain)
        try:
            return int(len(plain.encode("utf-8", errors="ignore")))
        except Exception:
            return 0

    # ==================== 任务一：临时文件（GIF） ====================

    def _ensure_kope_temp_file(q20, img_id: int, raw: bytes, ext: str) -> str:
        try:
            base_dir = os.path.join(tempfile.gettempdir(), "wq_ggea_kope")
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"wq_kope_{os.getpid()}_{img_id}.{ext}")
            try:
                with open(path, "wb") as f:
                    f.write(raw)
            except Exception:
                return ""
            q20._kope_tmp_by_id[img_id] = path
            if path not in q20._kope_tmp_files:
                q20._kope_tmp_files.append(path)
            return path
        except Exception:
            return ""

    def cleanup_temp_files(q20):
        # 尽力清理：有些程序粘贴后会占用文件，删不掉就算了
        try:
            for p in reversed(list(q20._kope_tmp_files)):
                try:
                    os.unlink(p)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            q20._kope_tmp_files.clear()
            q20._kope_tmp_by_id.clear()
        except Exception:
            pass

    # ==================== Undo/Redo 系统 ====================

    def _on_contents_change(q20, pos, removed, added):
        if q20._in_replay:
            return

        old_text = q20._last_text
        new_text = q20.toPlainText()

        deleted_text = old_text[pos:pos + removed] if removed > 0 else ""
        inserted_text = new_text[pos:pos + added] if added > 0 else ""

        q20._last_text = new_text

        if not deleted_text and not inserted_text:
            return

        # ✅ 任务二：任何编辑行为都清空匹配高亮（绝不跟着编辑光标走）
        if q20._last_needle:
            try:
                q20.setExtraSelections([])
            except Exception:
                pass
            q20._last_needle = ""

        q20._redo.clear()

        entry = {
            'pos': pos,
            'deleted': deleted_text,
            'inserted': inserted_text,
        }

        change_size = max(len(deleted_text), len(inserted_text))

        if change_size >= _UNDO_CHAR_THRESHOLD:
            q20._undo.append(('big', entry))
        else:
            q20._undo.append(('small', entry))

        # ✅ 让行号/滚动标记/hover 跟随内容刷新（debounce）
        q20._schedule_debounced_refresh()

    def _undo_one(q20):
        if not q20._undo:
            return

        # ✅ 任务二：undo 也是编辑，必须清空高亮
        q20._clear_match_highlight()

        kind, entry = q20._undo.pop()

        redo_entry = {
            'pos': entry['pos'],
            'deleted': entry['inserted'],
            'inserted': entry['deleted'],
        }
        q20._redo.append((kind, redo_entry))

        q20._in_replay = True
        try:
            tc = q20.textCursor()

            if entry['inserted']:
                tc.setPosition(entry['pos'])
                tc.setPosition(entry['pos'] + len(entry['inserted']), QTextCursor.KeepAnchor)
                tc.removeSelectedText()

            if entry['deleted']:
                tc.setPosition(entry['pos'])
                tc.insertText(entry['deleted'])
                tc.setPosition(entry['pos'] + len(entry['deleted']))

            q20.setTextCursor(tc)
            q20._last_text = q20.toPlainText()
        finally:
            q20._in_replay = False

        q20._schedule_debounced_refresh()

    def _redo_one(q20):
        if not q20._redo:
            return

        # ✅ 任务二：redo 也是编辑，必须清空高亮
        q20._clear_match_highlight()

        kind, entry = q20._redo.pop()

        undo_entry = {
            'pos': entry['pos'],
            'deleted': entry['inserted'],
            'inserted': entry['deleted'],
        }
        q20._undo.append((kind, undo_entry))

        q20._in_replay = True
        try:
            tc = q20.textCursor()

            if entry['inserted']:
                tc.setPosition(entry['pos'])
                tc.setPosition(entry['pos'] + len(entry['inserted']), QTextCursor.KeepAnchor)
                tc.removeSelectedText()

            if entry['deleted']:
                tc.setPosition(entry['pos'])
                tc.insertText(entry['deleted'])
                tc.setPosition(entry['pos'] + len(entry['deleted']))

            q20.setTextCursor(tc)
            q20._last_text = q20.toPlainText()
        finally:
            q20._in_replay = False

        q20._schedule_debounced_refresh()

    # ==================== 图片系统 ====================

    def _next_img_id(q20):
        q20._img_counter += 1
        return q20._img_counter

    def _get_cached_image(q20, img_id: int, max_w: int) -> QImage:
        if img_id not in q20._img_data:
            return QImage()

        cache_key = (img_id, max_w)
        if cache_key in q20._img_cache:
            return q20._img_cache[cache_key]

        raw = q20._img_data[img_id]
        img = _load_image_from_bytes(raw)
        if img.isNull():
            return img

        if img.width() > max_w:
            img = img.scaledToWidth(max_w, Qt.SmoothTransformation)

        q20._img_cache[cache_key] = img
        return img

    def _find_visible_images(q20):
        """返回 [(img_id, top_y, block_rect), ...]"""
        results = []
        vp = q20.viewport().rect()

        block = q20.firstVisibleBlock()
        while block.isValid():
            br = q20.blockBoundingGeometry(block).translated(q20.contentOffset())
            if br.top() > vp.bottom():
                break

            text = block.text()
            m = _IMG_TAG_RE.match(text)
            if m:
                img_id = int(m.group(3))
                if img_id in q20._img_data:
                    results.append((img_id, int(br.top()), br))

            block = block.next()

        return results

    def _insert_image(q20, raw: bytes, img: QImage = None):
        if img is None:
            img = _load_image_from_bytes(raw)
        if img.isNull():
            return

        img_id = q20._next_img_id()
        q20._img_data[img_id] = raw

        w = img.width()
        h = img.height()
        size_bytes = len(raw)
        q20._img_info[img_id] = (w, h, size_bytes)

        size_str = _format_size(size_bytes)
        tag_line = f"[ {w}x{h}, {size_str}  #{img_id} ]"

        max_w = max(50, q20.viewport().width() - 20)
        show_img = img
        if img.width() > max_w:
            show_img = img.scaledToWidth(max_w, Qt.SmoothTransformation)

        ih = show_img.height()
        fm = q20.fontMetrics()
        line_h = fm.height()
        lines_needed = max(1, (ih + line_h - 1) // line_h) + 2

        placeholder = "\n" * lines_needed
        insert_text = f"\n{tag_line}{placeholder}"

        tc = q20.textCursor()
        tc.insertText(insert_text)
        q20.setTextCursor(tc)

    def _image_rect_at(q20, img_id: int) -> QRect:
        vp = q20.viewport().rect()
        max_w = max(50, vp.width() - 20)

        for iid, top_y, block_rect in q20._find_visible_images():
            if iid == img_id:
                img = q20._get_cached_image(img_id, max_w)
                if img.isNull():
                    return QRect()
                iw = img.width()
                ih = img.height()
                line_h = int(block_rect.height())
                img_y = top_y + line_h + 2
                img_x = 10
                return QRect(img_x, img_y, iw, ih)

        return QRect()

    def _image_at_point(q20, pt: QPoint):
        vp = q20.viewport().rect()
        max_w = max(50, vp.width() - 20)

        for img_id, top_y, block_rect in q20._find_visible_images():
            img = q20._get_cached_image(img_id, max_w)
            if img.isNull():
                continue
            iw = img.width()
            ih = img.height()
            line_h = int(block_rect.height())
            img_y = top_y + line_h + 2
            img_x = 10
            img_rect = QRect(img_x, img_y, iw, ih)

            if img_rect.contains(pt):
                return img_id, img_rect

        return 0, QRect()

    def _update_hover(q20):
        if not q20._hover_img_id:
            q20._img_bar.hide()
            return

        rect = q20._image_rect_at(q20._hover_img_id)
        if rect.isNull():
            q20._img_bar.hide()
            q20._hover_img_id = 0
            q20._hover_img_rect = QRect()
            return

        q20._hover_img_rect = rect
        q20._place_bar_inside_image(rect)
        q20.viewport().update()

    def _place_bar_inside_image(q20, img_rect: QRect):
        if img_rect.isNull():
            q20._img_bar.hide()
            return

        vp = q20.viewport().rect()
        vis = img_rect.intersected(vp)
        if vis.isNull():
            q20._img_bar.hide()
            return

        q20._img_bar.adjustSize()
        bw = q20._img_bar.width()
        bh = q20._img_bar.height()

        pad = 4
        x = vis.left() + pad
        y = vis.top() + (vis.height() - bh) // 2  # 垂直居中

        x = max(vis.left() + pad, min(x, vis.right() - bw - pad))
        y = max(vis.top() + pad, min(y, vis.bottom() - bh - pad))

        q20._img_bar.move(int(x), int(y))
        q20._img_bar.show()
        q20._img_bar.raise_()

    def _save_hover_image(q20):
        img_id = q20._hover_img_id
        if not img_id:
            return
        raw = q20._img_data.get(img_id, b"")
        if not raw:
            return

        q20._img_bar.hide()

        # 检测原始格式
        mime_type, ext = _detect_image_format(raw)

        # 构建过滤器，把原始格式放第一个
        filter_map = {
            "png": "PNG Image (*.png)",
            "gif": "GIF Image (*.gif)",
            "jpg": "JPEG Image (*.jpg *.jpeg)",
            "bmp": "BMP Image (*.bmp)",
            "webp": "WebP Image (*.webp)",
            "ico": "Icon (*.ico)",
        }

        primary_filter = filter_map.get(ext, "PNG Image (*.png)")
        all_filters = [primary_filter]
        for k, v in filter_map.items():
            if v != primary_filter:
                all_filters.append(v)
        all_filters.append("All Files (*.*)")
        filter_str = ";;".join(all_filters)

        last_dir = _s_get_str("last_save_dir", "")
        if last_dir and os.path.isdir(last_dir):
            start_path = os.path.join(last_dir, f"image.{ext}")
        else:
            start_path = f"image.{ext}"

        path, _ = QFileDialog.getSaveFileName(
            q20, "另存为图片", start_path, filter_str
        )
        if not path:
            q20._update_hover()
            return

        try:
            with open(path, "wb") as f:
                f.write(raw)
            _s_set("last_save_dir", os.path.dirname(path))
        except Exception:
            pass

        q20._update_hover()

    def _kope_hover_image(q20):
        img_id = q20._hover_img_id
        if not img_id:
            return
        raw = q20._img_data.get(img_id, b"")
        if not raw:
            return

        q20._kope_id = img_id
        q20._kope_raw = raw

        # 检测原始格式
        mime_type, ext = _detect_image_format(raw)

        try:
            md = QMimeData()

            # ✅ 任务一：原始格式数据（GIF 就是 5MB 原封不动）
            md.setData(mime_type, QByteArray(raw))

            # ✅ 兼容：同时放一个 PNG（很多程序只吃 image/png / imageData）
            img = _load_image_from_bytes(raw)
            if not img.isNull():
                md.setImageData(img)
                try:
                    png_raw = _qimage_to_png_bytes(img)
                    md.setData("image/png", QByteArray(png_raw))
                except Exception:
                    pass

            # ✅ 最稳方案：GIF 额外放入一个临时文件 URL（像复制文件一样粘贴，保动图）
            if ext.lower() == "gif":
                tmp_path = q20._ensure_kope_temp_file(img_id, raw, ext)
                if tmp_path:
                    md.setUrls([QUrl.fromLocalFile(tmp_path)])

            QApplication.clipboard().setMimeData(md)
        except Exception:
            try:
                img = _load_image_from_bytes(raw)
                if not img.isNull():
                    QApplication.clipboard().setImage(img)
            except Exception:
                pass

        old = q20._btn_kope.text()
        q20._btn_kope.setText("ok")
        QTimer.singleShot(260, lambda: q20._btn_kope.setText(old))

    # ==================== 选中高亮 ====================

    def _clear_match_highlight(q20):
        if q20._last_needle:
            try:
                q20.setExtraSelections([])
            except Exception:
                pass
            q20._last_needle = ""
            q20._update_scroll_marks()

    def _needle(q20):
        tc = q20.textCursor()
        if tc.hasSelection():
            t = tc.selectedText().replace("\u2029", "\n").strip("\n")
            if t and not t.isspace():
                return t
        tmp = QTextCursor(tc)
        tmp.select(QTextCursor.WordUnderCursor)
        t = tmp.selectedText().strip()
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
        doc = q20.document()
        while True:
            idx = plain.find(needle, start)
            if idx == -1:
                break
            if has_sel and idx == sel_start and (idx + L) == sel_end:
                start = idx + L
                continue

            c = QTextCursor(doc)
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
                        # 对于 QPlainTextEdit，使用 blockBoundingGeometry 获取相对于文档的位置
                        br = q20.blockBoundingGeometry(b)
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
                br1 = q20.blockBoundingGeometry(b1)
                br2 = q20.blockBoundingGeometry(b2)
                a = max(0.0, float(br1.top()) / doc_h)
                bb = min(1.0, float(br2.bottom()) / doc_h)
                markers.append(("sel", a, bb))

        q20.verticalScrollBar().set_markers(markers)

    # ==================== 事件处理 ====================

    def _schedule_debounced_refresh(q20):
        q20._debounce_timer.start(q20._debounce_ms)

    def _flush_debounced_refresh(q20):
        if not q20._zen:
            q20.q89.update()
        q20._update_hover()
        q20._update_scroll_marks()

    def paintEvent(q20, e):
        super().paintEvent(e)

        p = QPainter(q20.viewport())
        vp = q20.viewport().rect()
        max_w = max(50, vp.width() - 20)

        for img_id, top_y, block_rect in q20._find_visible_images():
            img = q20._get_cached_image(img_id, max_w)
            if img.isNull():
                continue

            iw = img.width()
            ih = img.height()

            line_h = int(block_rect.height())
            img_y = top_y + line_h + 2
            img_x = 10

            img_rect = QRect(img_x, img_y, iw, ih)

            if img_rect.bottom() >= 0 and img_rect.top() <= vp.bottom():
                p.drawImage(img_rect.topLeft(), img)

                is_hover = (img_id == q20._hover_img_id)
                border_color = IMG_HOVER_BORDER if is_hover else IMG_BORDER_COLOR
                pen = QPen(border_color)
                pen.setWidth(2 if is_hover else 1)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(img_rect.adjusted(0, 0, -1, -1))

        if q20.hasFocus():
            r = q20.cursorRect(q20.textCursor())
            if vp.intersects(r.adjusted(-2, -10, 2, 2)):
                cx = float(int(r.left()))
                top = float(int(r.top()))
                dot_d = 11.0
                radius = dot_d * 0.5
                cy = top - radius - 3.0

                p.setRenderHint(QPainter.Antialiasing, False)
                line_pen = QPen(QColor("#000000"))
                line_pen.setWidth(1)
                p.setPen(line_pen)
                p.drawLine(QPointF(cx, top), QPointF(cx, cy + radius))

                p.setRenderHint(QPainter.Antialiasing, True)
                red = QColor("#d60000")
                red.setAlphaF(0.4)
                p.setPen(QPen(red))
                p.setBrush(red)
                p.drawEllipse(QRectF(cx - radius, cy - radius, dot_d, dot_d))

        p.end()

    def mouseMoveEvent(q20, e):
        super().mouseMoveEvent(e)

        if q20._img_bar.isVisible() and q20._img_bar.geometry().contains(e.pos()):
            return

        img_id, rect = q20._image_at_point(e.pos())

        old_id = q20._hover_img_id

        if img_id:
            q20._hover_img_id = img_id
            q20._hover_img_rect = rect
            q20._place_bar_inside_image(rect)
            if img_id != old_id:
                q20.viewport().update()
        else:
            if q20._hover_img_id and q20._hover_img_rect.contains(e.pos()):
                return
            q20._img_bar.hide()
            q20._hover_img_id = 0
            q20._hover_img_rect = QRect()
            if old_id:
                q20.viewport().update()

    def leaveEvent(q20, e):
        old = q20._hover_img_id
        q20._img_bar.hide()
        q20._hover_img_id = 0
        q20._hover_img_rect = QRect()
        if old:
            q20.viewport().update()
        super().leaveEvent(e)

    def insertFromMimeData(q20, md):
        try:
            text = _normalize_text(md.text() or "")
        except Exception:
            text = ""

        try:
            has_img = bool(md.hasImage())
        except Exception:
            has_img = False

        try:
            has_urls = bool(md.hasUrls())
        except Exception:
            has_urls = False

        try:
            has_html = bool(md.hasHtml())
        except Exception:
            has_html = False

        if text:
            tc = q20.textCursor()
            tc.insertText(text)
            q20.setTextCursor(tc)

        if has_img:
            try:
                img = md.imageData()
                if isinstance(img, QImage) and not img.isNull():
                    raw = _qimage_to_png_bytes(img)
                    q20._insert_image(raw, img)
            except Exception:
                pass

        if has_urls:
            try:
                for u in md.urls():
                    if u.isLocalFile():
                        path = u.toLocalFile()
                        with open(path, "rb") as f:
                            raw = f.read()
                        q20._insert_image(raw)
            except Exception:
                pass

        if has_html:
            try:
                html = md.html()
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
                            pass
                    elif os.path.exists(s):
                        try:
                            with open(s, "rb") as f:
                                raw = f.read()
                        except Exception:
                            pass
                    if raw:
                        q20._insert_image(raw)
            except Exception:
                pass

        q20._schedule_debounced_refresh()

    def keyPressEvent(q20, e):
        mods = e.modifiers()

        # ✅ 任务三：Ctrl+C：无选区复制整行；有选区复制选区
        if (mods & Qt.ControlModifier) and e.key() == Qt.Key_C:
            tc = q20.textCursor()
            if not tc.hasSelection():
                tmp = QTextCursor(tc)
                tmp.select(QTextCursor.LineUnderCursor)
                t = tmp.selectedText().replace("\u2029", "\n")
                if not t.endswith("\n"):
                    t += "\n"
                QApplication.clipboard().setText(t)
                e.accept()
                return
            else:
                t = tc.selectedText().replace("\u2029", "\n")
                QApplication.clipboard().setText(t)
                e.accept()
                return

        # Ctrl+Z: Undo
        if (mods & Qt.ControlModifier) and e.key() == Qt.Key_Z and not (mods & Qt.ShiftModifier):
            q20._undo_one()
            e.accept()
            return

        # Ctrl+Y 或 Ctrl+Shift+Z: Redo
        if ((mods & Qt.ControlModifier) and e.key() == Qt.Key_Y) or \
           ((mods & Qt.ControlModifier) and (mods & Qt.ShiftModifier) and e.key() == Qt.Key_Z):
            q20._redo_one()
            e.accept()
            return

        # Ctrl+V: 粘贴
        if (mods & Qt.ControlModifier) and e.key() == Qt.Key_V and not (mods & Qt.ShiftModifier):
            q20._clear_match_highlight()
            cb = QApplication.clipboard()
            md = cb.mimeData()
            if md:
                q20.insertFromMimeData(md)
            e.accept()
            return

        # Ctrl+Shift+V: 粘贴 kope 的图片
        if (mods & Qt.ControlModifier) and (mods & Qt.ShiftModifier) and e.key() == Qt.Key_V:
            if q20._kope_raw:
                q20._insert_image(q20._kope_raw)
                e.accept()
                return

        super().keyPressEvent(e)

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
                tc = q20.textCursor()
                tc.movePosition(QTextCursor.Start)
                q20.setTextCursor(tc)
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
                tc = q20.textCursor()
                tc.movePosition(QTextCursor.End)
                q20.setTextCursor(tc)
                e.accept()
                return

        super().keyReleaseEvent(e)

    def _on_selection_changed(q20):
        q20._pending_single = False
        if q20._mouse_trigger:
            q20.q96()
        else:
            q20._schedule_debounced_refresh()

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
        # 移除鼠标按钮检查，直接调用 q96
        q20.q96()
        q20._mouse_trigger = False

    def resizeEvent(q20, e):
        super().resizeEvent(e)
        q20._img_cache.clear()

        if q20._zen:
            return
        cr = q20.contentsRect()
        q20.q89.setGeometry(cr.left(), cr.top(), q20.q87(), cr.height())

    def q87(q20):
        blocks = max(1, q20.blockCount())
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
        q20._update_hover()
        q20._update_scroll_marks()

    def q88(q20, event):
        if q20._zen:
            return

        painter = QPainter(q20.q89)
        rect = event.rect()
        painter.fillRect(rect, QColor(q1))

        block = q20.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(q20.blockBoundingGeometry(block).translated(q20.contentOffset()).top())
        bottom = top + int(q20.blockBoundingRect(block).height())

        while block.isValid() and top <= rect.bottom():
            if block.isVisible() and bottom >= rect.top():
                num = str(block_num + 1)
                col = QColor(q2)
                col.setAlpha(40)
                painter.setPen(col)
                painter.drawText(0, top, q20.q89.width() - 1,
                               q20.fontMetrics().height(),
                               Qt.AlignLeft | Qt.AlignVCenter, num)

            block = block.next()
            top = bottom
            bottom = top + int(q20.blockBoundingRect(block).height())
            block_num += 1

    def set_zen(q20, on: bool):
        q20._zen = on
        q20.q89.setVisible(not on)
        if on:
            q20.setViewportMargins(0, 0, 0, 0)
        else:
            q20.q90(0)
        QTimer.singleShot(0, q20._update_hover)
        QTimer.singleShot(0, q20._update_scroll_marks)


class q64(QWidget):
    def __init__(q65):
        super().__init__()
        q65.setWindowFlags(Qt.FramelessWindowHint)
        q65.setContextMenuPolicy(Qt.NoContextMenu)
        q65.setStyleSheet(f"background:{q1}; border:none;")

        q65._wq_id = 0
        q65._wq_lock = None

        q65.q70 = False
        q65.q71 = QRect()
        q65._zen = False

        q65._drag_title = False
        q65._drag_off = QPoint()

        q65._logo_show_docsize = False
        q65._logo_docsize_txt = ""

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

    def _pos_resize_grip(q65):
        if not hasattr(q65, "q80") or q65.q80 is None:
            return
        try:
            w = int(q65.width())
            h = int(q65.height())
            gw = int(q65.q80.width())
            gh = int(q65.q80.height())
            q65.q80.move(max(0, w - gw), max(0, h - gh))
            q65.q80.raise_()
        except Exception:
            pass

    def _doc_size_bytes(q65) -> int:
        try:
            ed = q65.q79
        except Exception:
            return 0
        try:
            if hasattr(ed, "doc_size_bytes"):
                return int(ed.doc_size_bytes())
        except Exception:
            pass
        return 0

    def _update_logo_docsize(q65):
        n = q65._doc_size_bytes()
        q65._logo_docsize_txt = f"{n:,}"
        q65._logo_show_docsize = True
        q65._sync_logo()

    def _late_init_after_show(q65):
        q65._swap_in_real_editor()
        QTimer.singleShot(0, q65._late_alloc_wq_id)
        if _s_get_bool("win_max", False):
            QTimer.singleShot(0, q65._restore_maximized)
        QTimer.singleShot(0, q65._pos_resize_grip)

    def _swap_in_real_editor(q65):
        old = q65.q79 if hasattr(q65, "q79") else None
        old_text = ""
        if isinstance(old, QPlainTextEdit):
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
        q65.q79._last_text = q65.q79.toPlainText()

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
        QTimer.singleShot(0, q65._pos_resize_grip)

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
        QTimer.singleShot(0, q65._pos_resize_grip)

    def _sync_logo(q65):
        if not hasattr(q65, "q_logo"):
            return
        left = f"{_WQ_PREFIX}{q65._wq_id}" if q65._wq_id else "wq?"
        suffix = q65._logo_docsize_txt if q65._logo_show_docsize else "的梦gaea"
        q65.q_logo.setText(f"{left} : {suffix}")

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
        q65.q_logo.setStyleSheet(f"color:{q2}; font-weight:normal; margin-top:1px;")

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

        ph = QPlainTextEdit()
        ph.setUndoRedoEnabled(False)
        ph.setReadOnly(True)
        ph.setFocusPolicy(Qt.NoFocus)
        ph.setFont(QFont("Consolas", 11))
        ph.setStyleSheet(f"QPlainTextEdit{{background:{q1}; color:{q2}; border:none;}}")
        ph.setPlainText("\n" * _START_EMPTY_LINES)
        q65.q79 = ph
        q65.q72.addWidget(q65.q79)

        q65.q80 = q6(q65)
        QTimer.singleShot(0, q65._pos_resize_grip)

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
        q65.q80.setVisible(not on)
        if hasattr(q65, "q79") and hasattr(q65.q79, "set_zen"):
            q65.q79.set_zen(on)
        QTimer.singleShot(0, q65._pos_resize_grip)

    def eventFilter(q65, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            try:
                if event.button() == Qt.RightButton:
                    q65.toggle_zen()
                    return True
            except Exception:
                pass

        if (not q65._zen) and (obj in (q65.q73, q65.q_logo)):
            if event.type() == QEvent.MouseButtonPress:
                try:
                    if event.button() == Qt.LeftButton:
                        q65._update_logo_docsize()
                        if not q65.isMaximized():
                            q65._drag_title = True
                            q65._drag_off = event.globalPos() - q65.pos()
                        return True
                except Exception:
                    pass

            if event.type() == QEvent.MouseMove:
                try:
                    if q65._drag_title and (event.buttons() & Qt.LeftButton) and (not q65.isMaximized()):
                        q65.move(event.globalPos() - q65._drag_off)
                        return True
                except Exception:
                    pass

            if event.type() == QEvent.MouseButtonRelease:
                try:
                    q65._drag_title = False
                    return True
                except Exception:
                    pass

            if event.type() == QEvent.MouseButtonDblClick:
                try:
                    if obj == q65.q73 and event.button() == Qt.LeftButton:
                        q65.q92()
                        return True
                except Exception:
                    pass

        return False

    def changeEvent(q65, e):
        super().changeEvent(e)
        q65._sync_max_button()

    def resizeEvent(q65, e):
        super().resizeEvent(e)
        q65._pos_resize_grip()

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
        QTimer.singleShot(0, q65._pos_resize_grip)

    def closeEvent(q65, e):
        try:
            maxed = bool(q65.isMaximized() or q65.q70)
            _s_set("win_max", bool(maxed))
            base = q65.q71 if (maxed and q65.q71.isValid()) else q65.geometry()
            _s_set("win_rect", f"{base.x()},{base.y()},{base.width()},{base.height()}")
        except Exception:
            pass

        # ✅ 任务一：退出时清理 kope 生成的临时 GIF 文件
        try:
            if hasattr(q65, "q79") and hasattr(q65.q79, "cleanup_temp_files"):
                q65.q79.cleanup_temp_files()
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
