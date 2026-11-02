from pathlib import Path

import cv2 as cv
from PyQt6.QtCore import (
    QElapsedTimer,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .backend import get_supported_video_formats

CROSS_SIZE = 20


def _zoom_all_icon():
    icon_image = QPixmap(24, 24)
    icon_image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon_image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Corner brackets suggest fitting the entire image into view.
    for color, width, offset in (
        (QColor("#071b1a"), 5, 1),
        (QColor("#35d5c4"), 2, 0),
    ):
        painter.setPen(
            QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
        )
        for x_sign, y_sign in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            x = 12 + x_sign * 8 + offset
            y = 12 + y_sign * 8 + offset
            painter.drawLine(x, y, x - x_sign * 5, y)
            painter.drawLine(x, y, x, y - y_sign * 5)
    painter.end()
    return QIcon(icon_image)


def _zoom_points_icon():
    icon_image = QPixmap(24, 24)
    icon_image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon_image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for center, color in (
        (QPointF(6, 7), QColor("#ed514e")),
        (QPointF(18, 7), QColor("#4ecb75")),
        (QPointF(12, 18), QColor("#4d8ee8")),
    ):
        painter.setPen(
            QPen(
                QColor("#071b1a"),
                4,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
            )
        )
        painter.drawLine(
            QPointF(center.x() - 3, center.y()),
            QPointF(center.x() + 3, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - 3),
            QPointF(center.x(), center.y() + 3),
        )
        painter.setPen(
            QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
        )
        painter.drawLine(
            QPointF(center.x() - 3, center.y()),
            QPointF(center.x() + 3, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - 3),
            QPointF(center.x(), center.y() + 3),
        )
    painter.end()
    return QIcon(icon_image)


def _zoom_frame_icon():
    icon_image = QPixmap(24, 24)
    icon_image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon_image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#071b1a"), 5))
    painter.drawRect(QRectF(4, 6, 16, 12))
    painter.setPen(QPen(QColor("#ff9f43"), 2))
    painter.drawRect(QRectF(4, 6, 16, 12))
    painter.end()
    return QIcon(icon_image)


def _points_fine_adjustment_icon():
    icon_image = QPixmap(24, 24)
    icon_image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon_image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for center, color, width, size in (
        (QPointF(15, 15), QColor(170, 205, 200, 105), 2, 7),
        (QPointF(10, 10), QColor("#071b1a"), 4, 8),
        (QPointF(10, 10), QColor("#f4ffff"), 2, 8),
    ):
        painter.setPen(
            QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
        )
        painter.drawLine(
            QPointF(center.x() - size / 2, center.y()),
            QPointF(center.x() + size / 2, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - size / 2),
            QPointF(center.x(), center.y() + size / 2),
        )
    painter.end()
    return QIcon(icon_image)


def load_oriented_image(image_object):
    if hasattr(image_object, "get_cv_image") and hasattr(
        image_object, "set_qt_image"
    ):
        qt_image = image_object.get_qt_image()
        if qt_image is not None:
            return qt_image
        cv_image = image_object.get_cv_image()
        if cv_image is None:
            return QImage()
        if cv_image.ndim == 2:
            height, width = cv_image.shape
            qt_image = QImage(
                cv_image.data,
                width,
                height,
                cv_image.strides[0],
                QImage.Format.Format_Grayscale8,
            ).copy()
        elif cv_image.shape[2] == 4:
            rgba_image = cv.cvtColor(cv_image, cv.COLOR_BGRA2RGBA)
            height, width = rgba_image.shape[:2]
            qt_image = QImage(
                rgba_image.data,
                width,
                height,
                rgba_image.strides[0],
                QImage.Format.Format_RGBA8888,
            ).copy()
        else:
            rgb_image = cv.cvtColor(cv_image, cv.COLOR_BGR2RGB)
            height, width = rgb_image.shape[:2]
            qt_image = QImage(
                rgb_image.data,
                width,
                height,
                rgb_image.strides[0],
                QImage.Format.Format_RGB888,
            ).copy()
        image_object.set_qt_image(qt_image)
        return qt_image
    reader = QImageReader(str(image_object))
    reader.setAutoTransform(True)
    return reader.read()


def _array_to_qimage(cv_image):
    if cv_image is None:
        return QImage()
    if cv_image.ndim == 2:
        height, width = cv_image.shape
        return QImage(
            cv_image.data,
            width,
            height,
            cv_image.strides[0],
            QImage.Format.Format_Grayscale8,
        ).copy()
    if cv_image.shape[2] == 4:
        rgba_image = cv.cvtColor(cv_image, cv.COLOR_BGRA2RGBA)
        height, width = rgba_image.shape[:2]
        return QImage(
            rgba_image.data,
            width,
            height,
            rgba_image.strides[0],
            QImage.Format.Format_RGBA8888,
        ).copy()
    rgb_image = cv.cvtColor(cv_image, cv.COLOR_BGR2RGB)
    height, width = rgb_image.shape[:2]
    return QImage(
        rgb_image.data,
        width,
        height,
        rgb_image.strides[0],
        QImage.Format.Format_RGB888,
    ).copy()


class ImageFilesOrganizer(QWidget):
    selected_image_changed = pyqtSignal(str)
    image_files_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("imageFilesOrganizer")
        layout = QVBoxLayout(self)
        self.add_files_button = QPushButton("Add files")
        self.image_list = _ImageFileListWidget(self)
        self.image_list.currentRowChanged.connect(self._selection_changed)
        layout.addWidget(self.add_files_button)
        layout.addWidget(self.image_list)
        self.add_files_button.clicked.connect(self.open_add_files_dialog)

    def open_add_files_dialog(self):
        filenames = QFileDialog.getOpenFileNames(
            self,
            "Add images",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff "
            "*.webp);;All files (*)",
        )[0]
        self.add_image_files(filenames)

    def add_image_files(self, filenames):
        added_items = []
        known_paths = {
            self.image_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.image_list.count())
        }
        for filename in filenames:
            path = Path(filename).expanduser().resolve()
            if not path.is_file() or not QImageReader(str(path)).canRead():
                continue
            path_text = str(path)
            if path_text in known_paths:
                continue
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, path_text)
            item.setToolTip(path_text)
            self.image_list.addItem(item)
            known_paths.add(path_text)
            added_items.append(item)
        if added_items:
            self.image_list.setCurrentItem(added_items[0])
            self._emit_image_files_changed()

    def set_image_files(self, filenames):
        self.image_list.clear()
        self.add_image_files(filenames)

    def _selection_changed(self, row):
        item = self.image_list.item(row) if row >= 0 else None
        self.selected_image_changed.emit(
            item.data(Qt.ItemDataRole.UserRole) if item else ""
        )

    def _emit_image_files_changed(self):
        self.image_files_changed.emit(
            [
                self.image_list.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(self.image_list.count())
            ]
        )

    def set_highlighted_paths(self, filenames):
        highlighted_paths = {
            str(Path(filename).resolve()) for filename in filenames
        }
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            font = item.font()
            font.setBold(
                item.data(Qt.ItemDataRole.UserRole) in highlighted_paths
            )
            item.setFont(font)


class _ImageFileListWidget(QListWidget):
    def __init__(self, organizer):
        super().__init__(organizer)
        self.organizer = organizer
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            row = self.currentRow()
            if row >= 0:
                self.takeItem(row)
                if self.count():
                    self.setCurrentRow(min(row, self.count() - 1))
                else:
                    self.organizer._selection_changed(-1)
                self.organizer._emit_image_files_changed()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.source() is self:
            super().dragEnterEvent(event)
        elif self._has_image_urls(event.mimeData().urls()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self:
            super().dragMoveEvent(event)
        elif self._has_image_urls(event.mimeData().urls()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.source() is self:
            super().dropEvent(event)
            self.organizer._emit_image_files_changed()
            return
        if not self._has_image_urls(event.mimeData().urls()):
            event.ignore()
            return
        self.organizer.add_image_files(
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        )
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    @staticmethod
    def _has_image_urls(urls):
        return any(
            url.isLocalFile()
            and Path(url.toLocalFile()).is_file()
            and QImageReader(url.toLocalFile()).canRead()
            for url in urls
        )


class _FitImageLabel(QLabel):
    def __init__(self, empty_text, parent=None):
        super().__init__(empty_text, parent)
        self._source_pixmap = QPixmap()
        self._zoom = 1.0
        self._pan = QPointF()
        self._drag_position = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(160, 120)
        self.setStyleSheet("background-color: #202020; color: white;")
        self.setMouseTracking(True)

    def set_source_pixmap(self, pixmap, keep_view=False):
        self._source_pixmap = pixmap
        if not keep_view:
            self.zoom_all()
        if pixmap.isNull():
            self.setPixmap(QPixmap())
        else:
            self.setText("")
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.zoom_all()

    def zoom_all(self):
        self._zoom = 1.0
        self._pan = QPointF()
        self.update()

    def paintEvent(self, event):
        if self._source_pixmap.isNull():
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = self.contentsRect()
        base_scale = min(
            bounds.width() / self._source_pixmap.width(),
            bounds.height() / self._source_pixmap.height(),
        )
        scale = base_scale * self._zoom
        width = self._source_pixmap.width() * scale
        height = self._source_pixmap.height() * scale
        center = QPointF(bounds.center()) + self._pan
        target = QRectF(
            center.x() - width / 2, center.y() - height / 2, width, height
        )
        painter.drawPixmap(
            target, self._source_pixmap, QRectF(self._source_pixmap.rect())
        )

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._source_pixmap.isNull()
        ):
            self._drag_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            position = event.position()
            self._pan += position - self._drag_position
            self._drag_position = position
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_position is not None
        ):
            self._drag_position = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if self._source_pixmap.isNull():
            return super().wheelEvent(event)
        bounds = self.contentsRect()
        base_scale = min(
            bounds.width() / self._source_pixmap.width(),
            bounds.height() / self._source_pixmap.height(),
        )
        old_scale = base_scale * self._zoom
        center = QPointF(bounds.center())
        cursor_position = event.position()
        image_position = QPointF(
            (cursor_position.x() - center.x() - self._pan.x()) / old_scale
            + self._source_pixmap.width() / 2,
            (cursor_position.y() - center.y() - self._pan.y()) / old_scale
            + self._source_pixmap.height() / 2,
        )
        factor = 1.15 ** (event.angleDelta().y() / 120)
        self._zoom = max(0.1, min(20.0, self._zoom * factor))
        new_scale = base_scale * self._zoom
        self._pan = QPointF(
            cursor_position.x()
            - center.x()
            - (image_position.x() - self._source_pixmap.width() / 2)
            * new_scale,
            cursor_position.y()
            - center.y()
            - (image_position.y() - self._source_pixmap.height() / 2)
            * new_scale,
        )
        self.update()
        event.accept()


class VideoPreviewWidget(QWidget):
    export_interrupted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_provider = None
        self._total_frames = 0
        self._needs_render = False
        self._exporting = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_playback)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setObjectName("videoPositionSlider")
        self.position_label = QLabel("No video")
        self.position_label.setMinimumWidth(110)
        self.position_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        slider_row = QHBoxLayout()
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(self.position_label)
        layout.addLayout(slider_row)

        style = self.style()
        self.start_button = self._make_button(
            "videoStartButton",
            "Go to start",
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward),
        )
        self.previous_button = self._make_button(
            "videoPreviousFrameButton",
            "Return one frame",
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward),
        )
        self.play_button = self._make_button(
            "videoPlayButton",
            "Play",
            style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self.pause_button = self._make_button(
            "videoPauseButton",
            "Pause",
            style.standardIcon(QStyle.StandardPixmap.SP_MediaPause),
        )
        self.next_button = self._make_button(
            "videoNextFrameButton",
            "Advance one frame",
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward),
        )
        self.end_button = self._make_button(
            "videoEndButton",
            "Go to end",
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward),
        )
        self.export_banner = QFrame(self)
        self.export_banner.setObjectName("videoExportBanner")
        self.export_banner.setStyleSheet(
            "QFrame#videoExportBanner { background-color: #3a3320;"
            " border: 1px solid #c9a227; border-radius: 4px; }"
            "QFrame#videoExportBanner QLabel { color: #ffe9a6; }"
        )
        export_layout = QHBoxLayout(self.export_banner)
        export_layout.setContentsMargins(8, 4, 8, 4)
        self.export_banner_label = QLabel("Exporting video file")
        self.export_interrupt_button = QPushButton("Interrupt")
        export_layout.addWidget(self.export_banner_label, 1)
        export_layout.addWidget(self.export_interrupt_button)
        self.export_banner.hide()
        layout.addWidget(self.export_banner)
        self.export_interrupt_button.clicked.connect(
            lambda _checked=False: self.export_interrupted.emit()
        )
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        for button in (
            self.start_button,
            self.previous_button,
            self.play_button,
            self.pause_button,
            self.next_button,
            self.end_button,
        ):
            buttons_row.addWidget(button)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        self.canvas = _FitImageLabel("Video preview unavailable")
        layout.addWidget(self.canvas, 1)

        self.slider.valueChanged.connect(self._position_changed)
        self.start_button.clicked.connect(
            lambda _checked=False: self.slider.setValue(0)
        )
        self.end_button.clicked.connect(
            lambda _checked=False: self.slider.setValue(self.slider.maximum())
        )
        self.previous_button.clicked.connect(
            lambda _checked=False: self.slider.setValue(
                self.slider.value() - 1
            )
        )
        self.next_button.clicked.connect(
            lambda _checked=False: self.slider.setValue(
                self.slider.value() + 1
            )
        )
        self.play_button.clicked.connect(lambda _checked=False: self.play())
        self.pause_button.clicked.connect(lambda _checked=False: self.pause())
        self._fps = 30.0
        self._update_controls()

    @staticmethod
    def _make_button(object_name, tooltip, icon):
        button = QToolButton()
        button.setObjectName(object_name)
        button.setIcon(icon)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        return button

    def is_playing(self):
        return self._timer.isActive()

    def set_video(self, total_frames, fps, frame_provider):
        self._frame_provider = frame_provider
        self._total_frames = max(0, int(total_frames))
        self._fps = max(1.0, float(fps))
        if self.is_playing():
            self._timer.setInterval(self._playback_interval())
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, self._total_frames - 1))
        self.slider.blockSignals(False)
        self._update_controls()
        self._render_current_frame()

    def set_error(self, message):
        self.pause()
        self._frame_provider = None
        self._total_frames = 0
        self._needs_render = False
        self.slider.blockSignals(True)
        self.slider.setRange(0, 0)
        self.slider.blockSignals(False)
        self.canvas.set_source_pixmap(QPixmap())
        self.canvas.setText(message)
        self._update_controls()

    def set_exporting(self, exporting):
        self._exporting = bool(exporting)
        self.export_banner.setVisible(exporting)
        self.export_interrupt_button.setEnabled(exporting)
        if exporting:
            self.pause()
        self._update_controls()

    def set_export_progress(self, frame, position, total_frames):
        self.slider.blockSignals(True)
        self.slider.setValue(position)
        self.slider.blockSignals(False)
        self.export_banner_label.setText(
            f"Exporting video file ({position + 1} / {total_frames})"
        )
        self.position_label.setText(
            f"Exporting frame {position + 1} / {total_frames}"
        )
        if frame is None or not hasattr(frame, "shape"):
            return
        pixmap = QPixmap.fromImage(_array_to_qimage(frame))
        self.canvas.set_source_pixmap(pixmap, keep_view=True)

    def set_export_stopping(self):
        self.export_banner_label.setText(
            "Stopping export after current frame..."
        )
        self.export_interrupt_button.setEnabled(False)

    def finish_export(self):
        self._exporting = False
        self.export_banner.hide()
        self._update_controls()

    def play(self):
        if self._total_frames < 2:
            return
        if self.slider.value() >= self.slider.maximum():
            self.slider.setValue(0)
        # The timer interval caps playback at the project FPS;
        # slow renders only lower it.
        self._timer.start(self._playback_interval())
        self._update_controls()

    def pause(self):
        self._timer.stop()
        self._update_controls()

    def _playback_interval(self):
        return max(1, round(1000 / self._fps))

    def _advance_playback(self):
        if self.slider.value() >= self.slider.maximum():
            self.pause()
            return
        self.slider.setValue(self.slider.value() + 1)

    def _update_controls(self):
        if not self.export_banner.isVisible():
            self._exporting = False
        has_video = self._frame_provider is not None and self._total_frames > 0
        playing = self.is_playing()
        self.slider.setEnabled(has_video and not self._exporting)
        for button in (
            self.start_button,
            self.previous_button,
            self.next_button,
            self.end_button,
        ):
            button.setEnabled(
                has_video and not playing and not self._exporting
            )
        self.play_button.setEnabled(
            has_video
            and self._total_frames > 1
            and not playing
            and not self._exporting
        )
        self.pause_button.setEnabled(playing and not self._exporting)
        if has_video:
            self.position_label.setText(
                f"Frame {self.slider.value() + 1} / {self._total_frames}"
            )
        else:
            self.position_label.setText("No video")

    def _position_changed(self, _value):
        self._update_controls()
        self._render_current_frame()

    def _render_current_frame(self):
        if self._frame_provider is None or self._total_frames <= 0:
            return
        if not self.isVisible():
            self._needs_render = True
            return
        self._needs_render = False
        try:
            frame = self._frame_provider(self.slider.value())
        except Exception as error:
            print(error)
            self.pause()
            self.canvas.set_source_pixmap(QPixmap())
            self.canvas.setText("Unable to generate video frame")
            return
        if frame is None or not hasattr(frame, "shape"):
            self.canvas.set_source_pixmap(QPixmap())
            self.canvas.setText("Unable to generate video frame")
            return
        pixmap = QPixmap.fromImage(_array_to_qimage(frame))
        same_size = pixmap.size() == self.canvas._source_pixmap.size()
        self.canvas.set_source_pixmap(pixmap, keep_view=same_size)

    def showEvent(self, event):
        super().showEvent(event)
        if self._needs_render:
            self._render_current_frame()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.pause()


class PreviewArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewArea")
        self.tabs = QTabWidget(self)
        self.input_image_label = _FitImageLabel("Select an image to preview")
        self.fusion_image_label = _FitImageLabel("Fusion preview unavailable")
        self.tabs.addTab(self.input_image_label, "Input image")
        self.tabs.addTab(self.fusion_image_label, "Fusion preview")
        self.video_preview = VideoPreviewWidget()
        self.tabs.addTab(self.video_preview, "Video preview")
        self.tabs.setCurrentWidget(self.fusion_image_label)
        self.tabs.currentChanged.connect(self._update_previews)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.zoom_all_button = QToolButton(self)
        self.zoom_all_button.setIcon(_zoom_all_icon())
        self.zoom_all_button.setIconSize(QSize(20, 20))
        self.zoom_all_button.setToolTip("Zoom all")
        self.zoom_all_button.clicked.connect(self.zoom_all)
        toolbar.addWidget(self.zoom_all_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        layout.addWidget(self.tabs)
        self._input_pixmap = QPixmap()
        self._fusion_pixmap = QPixmap()

    def set_image(self, image_object):
        has_image = image_object is not None and not (
            isinstance(image_object, str) and not image_object
        )
        image = load_oriented_image(image_object) if has_image else QImage()
        if image.isNull():
            self._input_pixmap = QPixmap()
            self.input_image_label.setText(
                "Select an image to preview"
                if not has_image
                else "Unable to load image"
            )
        else:
            self._input_pixmap = QPixmap.fromImage(image)
        self.input_image_label.set_source_pixmap(self._input_pixmap)
        self._update_previews()

    def set_fusion_frame(self, image):
        if image is None or not hasattr(image, "shape"):
            self._fusion_pixmap = QPixmap()
            self.fusion_image_label.setText("Fusion preview unavailable")
        else:
            qt_image = _array_to_qimage(image)
            self._fusion_pixmap = QPixmap.fromImage(qt_image)
        self.fusion_image_label.set_source_pixmap(self._fusion_pixmap)
        self._update_previews()

    def set_fusion_error(self, message):
        self._fusion_pixmap = QPixmap()
        self.fusion_image_label._source_pixmap = QPixmap()
        self.fusion_image_label.setPixmap(QPixmap())
        self.fusion_image_label.setText(message)

    def set_video(self, total_frames, fps, frame_provider):
        self.video_preview.set_video(total_frames, fps, frame_provider)

    def set_video_error(self, message):
        self.video_preview.set_error(message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_previews)

    def _fit_previews(self):
        self.input_image_label.zoom_all()
        self.fusion_image_label.zoom_all()
        self.video_preview.canvas.zoom_all()
        self._update_previews()

    def zoom_all(self):
        current_label = self.tabs.currentWidget()
        current_label = getattr(current_label, "canvas", current_label)
        if isinstance(current_label, _FitImageLabel):
            current_label.zoom_all()

    def _update_previews(self, _index=None):
        _ = _index
        current_label = self.tabs.currentWidget()
        if current_label is None:
            return
        self.input_image_label.update()
        self.fusion_image_label.update()


class FusionStepSlider(QWidget):
    value_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 50
        self._minimum = 0
        self._maximum = 100
        self.setMinimumHeight(30)
        self.setMouseTracking(True)

    def minimum(self):
        return self._minimum

    def maximum(self):
        return self._maximum

    def value(self):
        return self._value

    def set_range(self, minimum, maximum):
        self._minimum, self._maximum = minimum, maximum
        self.set_value(self._value)

    def set_value(self, value):
        value = max(self._minimum, min(self._maximum, int(value)))
        if value != self._value:
            self._value = value
            self.value_changed.emit(value)
        self.update()

    def _position_for_value(self, value):
        left, right = 7, max(8, self.width() - 8)
        return left + (right - left) * (value - self._minimum) / (
            self._maximum - self._minimum
        )

    def _value_for_position(self, x):
        left, right = 7, max(8, self.width() - 8)
        fraction = (x - left) / (right - left)
        return max(
            self._minimum,
            min(
                self._maximum,
                round(
                    self._minimum + fraction * (self._maximum - self._minimum)
                ),
            ),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center_y = self.height() / 2
        left = self._position_for_value(self._minimum)
        right = self._position_for_value(self._maximum)
        handle_x = self._position_for_value(self._value)
        painter.setPen(QPen(QColor("#707070"), 4))
        painter.drawLine(QPointF(left, center_y), QPointF(right, center_y))
        painter.setPen(QPen(QColor("#168a82"), 4))
        painter.drawLine(QPointF(left, center_y), QPointF(handle_x, center_y))
        painter.setPen(QPen(QColor("#202020"), 1))
        painter.setBrush(QColor("#f2f2ed"))
        painter.drawEllipse(QPointF(handle_x, center_y), 7, 7)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_value(self._value_for_position(event.position().x()))

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.set_value(self._value_for_position(event.position().x()))


class AlphaRangeSlider(QWidget):
    range_changed = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lower = 0
        self._upper = 100
        self._active_handle = "lower"
        self.setMinimumHeight(30)
        self.setMouseTracking(True)

    @property
    def values(self):
        return self._lower, self._upper

    def set_values(self, lower, upper):
        lower = max(0, min(100, int(lower)))
        upper = max(0, min(100, int(upper)))
        self._lower, self._upper = sorted((lower, upper))
        self.update()

    def _position_for_value(self, value):
        left, right = 7, max(8, self.width() - 8)
        return left + (right - left) * value / 100

    def _value_for_position(self, x):
        left, right = 7, max(8, self.width() - 8)
        return max(0, min(100, round((x - left) * 100 / (right - left))))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center_y = self.height() / 2
        left = self._position_for_value(0)
        right = self._position_for_value(100)
        lower_x = self._position_for_value(self._lower)
        upper_x = self._position_for_value(self._upper)
        painter.setPen(QPen(QColor("#707070"), 4))
        painter.drawLine(QPointF(left, center_y), QPointF(right, center_y))
        painter.setPen(QPen(QColor("#168a82"), 4))
        painter.drawLine(
            QPointF(lower_x, center_y), QPointF(upper_x, center_y)
        )
        for x in (lower_x, upper_x):
            painter.setPen(QPen(QColor("#202020"), 1))
            painter.setBrush(QColor("#f2f2ed"))
            painter.drawEllipse(QPointF(x, center_y), 7, 7)
        event.accept()

    def mousePressEvent(self, event):
        value = self._value_for_position(event.position().x())
        lower_distance = abs(value - self._lower)
        upper_distance = abs(value - self._upper)
        self._active_handle = (
            "lower" if lower_distance <= upper_distance else "upper"
        )
        self._set_active_value(value)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_active_value(
                self._value_for_position(event.position().x())
            )

    def _set_active_value(self, value):
        if self._active_handle == "lower":
            self._lower = min(value, self._upper)
        else:
            self._upper = max(value, self._lower)
        self.update()
        self.range_changed.emit(self._lower, self._upper)


class ImageFilesAndPreviewArea(QSplitter):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName("imageFilesAndPreviewArea")
        self.image_files_organizer = ImageFilesOrganizer(self)
        self.preview_area = PreviewArea(self)
        self.addWidget(self.image_files_organizer)
        self.addWidget(self.preview_area)
        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 3)


class _BusySpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(22, 22)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _advance(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        for spoke in range(12):
            color = QColor("#ffe9a6")
            color.setAlphaF((spoke + 1) / 12)
            painter.setPen(
                QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(QPointF(0, -6), QPointF(0, -10))
            painter.rotate(30)


class ImageFusionEditor(QWidget):
    image_edited = pyqtSignal(int, str, object)
    pair_requested = pyqtSignal(int)
    fusion_preview_requested = pyqtSignal(int, float, float)
    alpha_range_edited = pyqtSignal(int, object)
    alignment_points_requested = pyqtSignal(int)
    alignment_interrupted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("imageFusionEditor")
        self.pair_index = 0
        self.proj_image_entries = []
        self.image_paths = []
        self.cfg_frame_crosshair_enabled = True
        self.layout = QVBoxLayout(self)
        self.navigation = QHBoxLayout()
        self.previous_button = QPushButton("Previous pair")
        self.pair_label = QLabel()
        self.next_button = QPushButton("Next pair")
        self.find_alignment_button = QPushButton(
            _points_fine_adjustment_icon(), "Find alignment points"
        )
        self.find_alignment_button.setObjectName("findAlignmentPoints")
        self.find_alignment_button.setEnabled(False)
        self.navigation.addWidget(self.previous_button)
        self.navigation.addStretch(1)
        self.navigation.addWidget(self.pair_label)
        self.navigation.addWidget(self.find_alignment_button)
        self.navigation.addStretch(1)
        self.navigation.addWidget(self.next_button)
        self.layout.addLayout(self.navigation)
        self.alignment_banner = QFrame(self)
        self.alignment_banner.setObjectName("alignmentBanner")
        self.alignment_banner.setStyleSheet(
            "QFrame#alignmentBanner { background-color: #3a3320;"
            " border: 1px solid #c9a227;"
            "border-radius: 4px; }"
            " QFrame#alignmentBanner QLabel { color: #ffe9a6; }"
        )
        banner_layout = QHBoxLayout(self.alignment_banner)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        self.alignment_spinner = _BusySpinner(self.alignment_banner)
        self.alignment_banner_label = QLabel(
            "Trying to find alignment points. It can take a while..."
        )
        self.alignment_interrupt_button = QPushButton("Interrupt")
        banner_layout.addWidget(self.alignment_spinner)
        banner_layout.addWidget(self.alignment_banner_label, 1)
        banner_layout.addWidget(self.alignment_interrupt_button)
        self.alignment_banner.hide()
        self.layout.addWidget(self.alignment_banner)
        self.alignment_interrupt_button.clicked.connect(
            lambda _checked=False: self.alignment_interrupted.emit()
        )
        self.pair_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.layout.addWidget(self.pair_splitter, 1)
        self.fusion_controls = QWidget(self)
        controls_layout = QGridLayout(self.fusion_controls)
        controls_layout.setColumnMinimumWidth(0, 110)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.setColumnMinimumWidth(2, 76)
        fusion_step_label = QLabel("Fusion step")
        fusion_step_label.setFixedWidth(110)
        self.fusion_step_slider = FusionStepSlider(self.fusion_controls)
        self.fusion_step_slider.set_range(0, 100)
        self.fusion_step_slider.set_value(50)
        self.fusion_step_value = QLabel("50%")
        self.fusion_step_value.setFixedWidth(76)
        self.fusion_step_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        controls_layout.addWidget(fusion_step_label, 0, 0)
        controls_layout.addWidget(self.fusion_step_slider, 0, 1)
        controls_layout.addWidget(self.fusion_step_value, 0, 2)
        alpha_range_label = QLabel("Alpha range")
        alpha_range_label.setFixedWidth(110)
        self.alpha_range_slider = AlphaRangeSlider(self.fusion_controls)
        self.alpha_range_slider.set_values(0, 100)
        self.alpha_range_value = QLabel("0% - 100%")
        self.alpha_range_value.setFixedWidth(76)
        self.alpha_range_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        controls_layout.addWidget(alpha_range_label, 1, 0)
        controls_layout.addWidget(self.alpha_range_slider, 1, 1)
        controls_layout.addWidget(self.alpha_range_value, 1, 2)
        self.layout.addWidget(self.fusion_controls)
        self.previous_button.clicked.connect(self._previous_pair)
        self.next_button.clicked.connect(self._next_pair)
        self.find_alignment_button.clicked.connect(
            lambda _checked=False: self.alignment_points_requested.emit(
                self.pair_index
            )
        )
        self.fusion_step_slider.value_changed.connect(
            self._fusion_step_changed
        )
        self.alpha_range_slider.range_changed.connect(
            self._alpha_range_changed
        )
        self.set_pair([], [], 0)

    def _fusion_step_changed(self, value):
        self.fusion_step_value.setText(f"{value}%")
        self._emit_fusion_preview_request()

    def _alpha_range_changed(self, lower, upper):
        self.alpha_range_value.setText(f"{lower}% - {upper}%")
        self.alpha_range_edited.emit(
            self.pair_index, [lower / 100, upper / 100]
        )
        self._emit_fusion_preview_request()

    def _emit_fusion_preview_request(self):
        if len(self.proj_image_entries) < 2:
            return
        fusion_step = self.fusion_step_slider.value() / 100
        minimum_alpha, maximum_alpha = (
            value / 100 for value in self.alpha_range_slider.values
        )
        if fusion_step < minimum_alpha:
            blend_alpha = 0.0
        elif fusion_step > maximum_alpha:
            blend_alpha = 1.0
        elif maximum_alpha == minimum_alpha:
            blend_alpha = 0.0
        else:
            blend_alpha = (fusion_step - minimum_alpha) / (
                maximum_alpha - minimum_alpha
            )
        self.fusion_preview_requested.emit(
            self.pair_index, fusion_step, blend_alpha
        )

    def refresh_fusion_preview(self):
        self._emit_fusion_preview_request()

    def set_alignment_running(self, running):
        self.alignment_banner.setVisible(running)
        if running:
            self.alignment_spinner.start()
        else:
            self.alignment_spinner.stop()
        self.find_alignment_button.setEnabled(
            not running and len(self.proj_image_entries) > 1
        )
        self.previous_button.setEnabled(not running and self.pair_index > 0)
        self.next_button.setEnabled(
            not running and self.pair_index < len(self.proj_image_entries) - 2
        )

    def set_pair(self, proj_image_entries, image_paths, pair_index):
        self.proj_image_entries = proj_image_entries
        self.image_paths = image_paths
        self.pair_index = pair_index
        while self.pair_splitter.count():
            widget = self.pair_splitter.widget(0)
            self.pair_splitter.widget(0).setParent(None)
            widget.deleteLater()

        pair_count = max(0, len(proj_image_entries) - 1)
        if pair_count == 0:
            self.pair_label.setText("Add at least two images to edit a pair")
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.find_alignment_button.setEnabled(False)
            self.fusion_step_slider.setEnabled(False)
            self.alpha_range_slider.setEnabled(False)
            return

        self.pair_index = max(0, min(pair_index, pair_count - 1))
        alpha_range = proj_image_entries[self.pair_index].get(
            "alpha_range", [0.0, 1.0]
        )
        self.alpha_range_slider.set_values(
            round(float(alpha_range[0]) * 100),
            round(float(alpha_range[1]) * 100),
        )
        low, high = self.alpha_range_slider.values
        self.alpha_range_value.setText(f"{low}% - {high}%")
        self.fusion_step_slider.setEnabled(True)
        self.alpha_range_slider.setEnabled(True)
        self.pair_label.setText(f"Pair {self.pair_index + 1} / {pair_count}")
        self.previous_button.setEnabled(self.pair_index > 0)
        self.next_button.setEnabled(self.pair_index < pair_count - 1)
        self.find_alignment_button.setEnabled(True)
        for offset, points_field in ((0, "next_points"), (1, "prev_points")):
            entry_index = self.pair_index + offset
            entry = proj_image_entries[entry_index]
            path = image_paths[entry_index]
            column = QWidget(self.pair_splitter)
            column_layout = QVBoxLayout(column)
            filename_label = QLabel(Path(path).name)
            filename_label.setObjectName("fusionFilename")
            filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = filename_label.font()
            font.setBold(True)
            filename_label.setFont(font)
            column_layout.addWidget(filename_label)
            frame_top_left, frame_bottom_right = entry["frame"]
            frame_width = frame_bottom_right[0] - frame_top_left[0]
            frame_height = frame_bottom_right[1] - frame_top_left[1]
            points = entry.get(points_field)
            if points is None:
                points = [[0, 0], [1, 0], [0, 1]]
            canvas_row = QHBoxLayout()
            zoom_toolbar = QVBoxLayout()
            zoom_toolbar.setSpacing(4)
            zoom_all_button = QToolButton(column)
            zoom_all_button.setObjectName("zoomAllButton")
            zoom_all_button.setIcon(_zoom_all_icon())
            zoom_all_button.setIconSize(QSize(24, 24))
            zoom_all_button.setFixedSize(40, 40)
            zoom_all_button.setToolTip("Zoom all")
            zoom_all_button.setAccessibleName("Zoom all")
            zoom_all_button.setAutoRaise(False)
            zoom_all_button.setStyleSheet(
                "QToolButton#zoomAllButton {"
                "background-color: #454b4b; border: 1px solid #101414;"
                "border-top-color: #929b99; border-left-color: #7d8785;"
                "border-radius: 4px; padding: 2px; }"
                "QToolButton#zoomAllButton:hover { background-color: #586260;"
                "border-top-color: #c3cfcc; border-left-color: #aab5b2; }"
                "QToolButton#zoomAllButton:pressed {"
                " background-color: #252a29;"
                "border-top-color: #101414; border-left-color: #101414;"
                "border-bottom-color: #929b99; border-right-color: #7d8785; }"
            )
            zoom_points_button = self._make_zoom_button(
                column,
                "zoomPointsButton",
                _zoom_points_icon(),
                "Zoom to points",
            )
            zoom_frame_button = self._make_zoom_button(
                column, "zoomFrameButton", _zoom_frame_icon(), "Zoom to frame"
            )
            zoom_toolbar.addWidget(zoom_all_button)
            zoom_toolbar.addWidget(zoom_points_button)
            zoom_toolbar.addWidget(zoom_frame_button)
            zoom_toolbar.addStretch(1)
            canvas_row.addLayout(zoom_toolbar, 0)
            editor = ImageMarkersEditor(
                entry["image"],
                frame_top_left,
                frame_width,
                frame_width / frame_height,
                points,
                column,
            )
            editor._fitted = True
            QTimer.singleShot(0, editor.zoom_to_frame)
            zoom_all_button.clicked.connect(editor.zoom_all)
            zoom_points_button.clicked.connect(editor.zoom_to_points)
            zoom_frame_button.clicked.connect(editor.zoom_to_frame)
            editor.setObjectName("imageMarkersEditor")
            editor.cfg_frame_crosshair_enabled = (
                self.cfg_frame_crosshair_enabled
            )
            editor.frame_changed.connect(
                lambda value, index=entry_index: self.image_edited.emit(
                    index, "frame", value
                )
            )
            editor.points_changed.connect(
                lambda value, index=entry_index, field=points_field: (
                    self.image_edited.emit(index, field, value)
                )
            )
            canvas_row.addWidget(editor, 1)
            column_layout.addLayout(canvas_row, 1)
            column.filename_label = filename_label
            column.editor = editor
            self.pair_splitter.addWidget(column)
        self.pair_splitter.setStretchFactor(0, 1)
        self.pair_splitter.setStretchFactor(1, 1)
        self._emit_fusion_preview_request()

    @staticmethod
    def _make_zoom_button(parent, object_name, icon, tooltip):
        button = QToolButton(parent)
        button.setObjectName(object_name)
        button.setIcon(icon)
        button.setIconSize(QSize(24, 24))
        button.setFixedSize(40, 40)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRaise(False)
        button.setStyleSheet(
            "QToolButton {"
            "background-color: #454b4b; border: 1px solid #101414;"
            "border-top-color: #929b99; border-left-color: #7d8785;"
            "border-radius: 4px; padding: 2px; }"
            "QToolButton:hover { background-color: #586260;"
            "border-top-color: #c3cfcc; border-left-color: #aab5b2; }"
            "QToolButton:pressed { background-color: #252a29;"
            "border-top-color: #101414; border-left-color: #101414;"
            "border-bottom-color: #929b99; border-right-color: #7d8785; }"
        )
        return button

    def set_frame_crosshair_enabled(self, enabled):
        self.cfg_frame_crosshair_enabled = bool(enabled)
        for index in range(self.pair_splitter.count()):
            column = self.pair_splitter.widget(index)
            column.editor.cfg_frame_crosshair_enabled = (
                self.cfg_frame_crosshair_enabled
            )
            column.editor.update()

    def set_editor_points(self, image_index, points_field, points):
        column_index = image_index - self.pair_index
        if not 0 <= column_index < self.pair_splitter.count():
            return False
        expected_field = "next_points" if column_index == 0 else "prev_points"
        if points_field != expected_field:
            return False
        self.pair_splitter.widget(column_index).editor.set_points(points)
        return True

    def _previous_pair(self):
        if self.pair_index > 0:
            self.pair_requested.emit(self.pair_index - 1)

    def _next_pair(self):
        if self.pair_index < len(self.proj_image_entries) - 2:
            self.pair_requested.emit(self.pair_index + 1)


class ImageFusionEditionArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("imageFusionEditionArea")
        self.layout = QVBoxLayout(self)
        self.editor = ImageFusionEditor(self)
        self.layout.addWidget(self.editor)


class VideoSettingsWidget(QWidget):
    VIDEO_SIZES = {
        "SD 480p (640 x 480)": (640, 480),
        "HD 720p (1280 x 720)": (1280, 720),
        "Full HD 1080p (1920 x 1080)": (1920, 1080),
        "QHD 1440p (2560 x 1440)": (2560, 1440),
        "4K UHD (3840 x 2160)": (3840, 2160),
    }
    FRAME_RATES = (23.976, 24, 25, 29.97, 30, 50, 59.94, 60, 120)

    def __init__(self, video_data, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        self.video_format_combo = QComboBox()
        supported_formats = get_supported_video_formats()
        for extension, label, _fourcc in supported_formats:
            self.video_format_combo.addItem(label, extension)
        if not supported_formats:
            self.video_format_combo.addItem(
                "No supported video formats detected", None
            )
            self.video_format_combo.setEnabled(False)
        layout.addRow("Output format", self.video_format_combo)

        self.video_size_combo = QComboBox()
        for label, dimensions in self.VIDEO_SIZES.items():
            self.video_size_combo.addItem(label, dimensions)
        self.video_size_combo.addItem("Custom", None)
        size_row = QHBoxLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 16384)
        self.width_spin.setSuffix(" px")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 16384)
        self.height_spin.setSuffix(" px")
        size_row.addWidget(self.width_spin)
        size_row.addWidget(self.height_spin)
        layout.addRow("Video size", self.video_size_combo)
        layout.addRow("Custom dimensions", size_row)

        self.frame_rate_combo = QComboBox()
        for frame_rate in self.FRAME_RATES:
            label = f"{frame_rate:g} fps"
            self.frame_rate_combo.addItem(label, frame_rate)
        self.frame_rate_combo.addItem("Custom", None)
        self.custom_frame_rate = QDoubleSpinBox()
        self.custom_frame_rate.setRange(1, 240)
        self.custom_frame_rate.setDecimals(3)
        self.custom_frame_rate.setSuffix(" fps")
        layout.addRow("Framerate", self.frame_rate_combo)
        layout.addRow("Custom framerate", self.custom_frame_rate)

        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.01, 86400)
        self.duration_spin.setDecimals(2)
        self.duration_spin.setSuffix(" s")
        layout.addRow("Duration", self.duration_spin)

        self.interpolation_method_combo = QComboBox()
        self.interpolation_method_combo.addItem("Logarithmic", "log")
        self.interpolation_method_combo.addItem("Linear", "linear")
        layout.addRow("Interpolation", self.interpolation_method_combo)

        self.video_size_combo.currentIndexChanged.connect(
            self._select_video_size
        )
        self.frame_rate_combo.currentIndexChanged.connect(
            self._select_frame_rate
        )
        self._initialize_values(video_data)
        self._select_video_size(self.video_size_combo.currentIndex())
        self._select_frame_rate(self.frame_rate_combo.currentIndex())

    def _initialize_values(self, video_data):
        selected_format = video_data.get("format", "avi")
        format_index = self.video_format_combo.findData(selected_format)
        if format_index < 0 and self.video_format_combo.count():
            format_index = 0
        if format_index >= 0:
            self.video_format_combo.setCurrentIndex(format_index)

        width, height = video_data.get("size", (1920, 1080))
        matching_size = next(
            (
                index
                for index, dimensions in enumerate(self.VIDEO_SIZES.values())
                if dimensions == (width, height)
            ),
            -1,
        )
        if matching_size >= 0:
            self.video_size_combo.setCurrentIndex(matching_size)
        else:
            self.video_size_combo.setCurrentIndex(
                self.video_size_combo.count() - 1
            )
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)

        frame_rate = video_data.get("FPS", 30)
        matching_rate = next(
            (
                index
                for index, rate in enumerate(self.FRAME_RATES)
                if rate == frame_rate
            ),
            -1,
        )
        if matching_rate >= 0:
            self.frame_rate_combo.setCurrentIndex(matching_rate)
        else:
            self.frame_rate_combo.setCurrentIndex(
                self.frame_rate_combo.count() - 1
            )
        self.custom_frame_rate.setValue(frame_rate)
        self.duration_spin.setValue(video_data.get("duration", 10))
        interpolation_method = video_data.get("interpolation_method", "log")
        method_index = self.interpolation_method_combo.findData(
            interpolation_method
        )
        self.interpolation_method_combo.setCurrentIndex(
            method_index if method_index >= 0 else 0
        )

    def _select_video_size(self, index):
        custom = self.video_size_combo.itemData(index) is None
        self.width_spin.setEnabled(custom)
        self.height_spin.setEnabled(custom)
        if not custom:
            width, height = self.video_size_combo.itemData(index)
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)

    def _select_frame_rate(self, index):
        frame_rate = self.frame_rate_combo.itemData(index)
        custom = frame_rate is None
        self.custom_frame_rate.setEnabled(custom)
        if not custom:
            self.custom_frame_rate.setValue(frame_rate)

    def settings(self):
        selected_size = self.video_size_combo.currentData()
        frame_rate = self.frame_rate_combo.currentData()
        return {
            "format": self.video_format_combo.currentData(),
            "size": selected_size
            or (self.width_spin.value(), self.height_spin.value()),
            "FPS": frame_rate
            if frame_rate is not None
            else self.custom_frame_rate.value(),
            "duration": self.duration_spin.value(),
            "interpolation_method": (
                self.interpolation_method_combo.currentData()
            ),
        }


class VideoSettingsDialog(QDialog):
    def __init__(self, video_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Settings")
        self.setModal(True)
        layout = QVBoxLayout(self)
        self.video_settings = VideoSettingsWidget(video_data, self)
        layout.addWidget(self.video_settings)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self):
        return self.video_settings.settings()


class NewProjectDialog(QDialog):
    def __init__(self, video_data=None, parent=None, project_name=""):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setModal(True)
        layout = QVBoxLayout(self)
        self.project_name_input = QLineEdit(project_name)
        self.project_name_input.setPlaceholderText("Project name")
        layout.addWidget(self.project_name_input)
        self.video_settings = VideoSettingsWidget(video_data or {}, self)
        layout.addWidget(self.video_settings)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def project_name(self):
        return self.project_name_input.text().strip()

    def settings(self):
        return self.video_settings.settings()


class ImageMarkersEditor(QWidget):
    points_changed = pyqtSignal(list)
    frame_changed = pyqtSignal(object)

    def __init__(
        self,
        image_filename,
        frame_upper_left,
        frame_width,
        frame_aspect_ratio,
        points,
        parent=None,
    ):
        super().__init__(parent)
        filename = (
            image_filename.get_image_path()
            if hasattr(image_filename, "get_image_path")
            else image_filename
        )
        image_path = Path(filename)
        self.image = load_oriented_image(image_filename)
        if self.image.isNull():
            raise ValueError(f"Unable to load image: {image_path}")

        self.frame_x = float(frame_upper_left[0])
        self.frame_y = float(frame_upper_left[1])
        self.frame_width = float(frame_width)
        self.frame_aspect_ratio = float(frame_aspect_ratio)
        if self.frame_width <= 0 or self.frame_aspect_ratio <= 0:
            raise ValueError("Frame width and aspect ratio must be positive")
        if len(points) != 3:
            raise ValueError("Exactly three points are required")
        self.points = [
            QPointF(float(point[0]), float(point[1])) for point in points
        ]

        self.scale = 1.0
        self.pan = QPointF(0, 0)
        self._fitted = False
        self._drag_mode = None
        self._drag_point = None
        self._last_mouse_position = QPointF()
        self.cfg_frame_crosshair_enabled = True
        self._marker_animation_clock = QElapsedTimer()
        self._marker_animation_clock.start()
        self._marker_animation_timer = QTimer(self)
        self._marker_animation_timer.setInterval(16)
        self._marker_animation_timer.timeout.connect(self.update)
        self._marker_animation_timer.start()
        self.setMinimumSize(480, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @property
    def frame_height(self):
        return self.frame_width / self.frame_aspect_ratio

    def set_points(self, points):
        if len(points) != 3:
            raise ValueError("Exactly three points are required")
        self.points = [
            QPointF(float(point[0]), float(point[1])) for point in points
        ]
        self.update()

    def image_to_widget(self, point):
        return QPointF(
            point.x() * self.scale + self.pan.x(),
            point.y() * self.scale + self.pan.y(),
        )

    def widget_to_image(self, point):
        return QPointF(
            (point.x() - self.pan.x()) / self.scale,
            (point.y() - self.pan.y()) / self.scale,
        )

    def resizeEvent(self, _event):
        super().resizeEvent(_event)
        if not self._fitted:
            self.zoom_all()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self.zoom_all()

    def zoom_all(self):
        if self.width() <= 0 or self.height() <= 0:
            return
        frame_right = self.frame_x + self.frame_width
        frame_bottom = self.frame_y + self.frame_height
        all_x = [0.0, float(self.image.width()), self.frame_x, frame_right]
        all_y = [0.0, float(self.image.height()), self.frame_y, frame_bottom]
        all_x.extend(point.x() for point in self.points)
        all_y.extend(point.y() for point in self.points)
        bounds = QRectF(
            min(all_x),
            min(all_y),
            max(all_x) - min(all_x),
            max(all_y) - min(all_y),
        )
        self._zoom_to_bounds(bounds)

    def zoom_to_points(self):
        if not self.points:
            return
        all_x = [point.x() for point in self.points]
        all_y = [point.y() for point in self.points]
        self._zoom_to_bounds(
            QRectF(
                min(all_x),
                min(all_y),
                max(all_x) - min(all_x),
                max(all_y) - min(all_y),
            )
        )

    def zoom_to_frame(self):
        self._zoom_to_bounds(
            QRectF(
                self.frame_x,
                self.frame_y,
                self.frame_width,
                self.frame_height,
            )
        )

    def _zoom_to_bounds(self, bounds):
        if self.width() <= 0 or self.height() <= 0:
            return
        if bounds.width() <= 0:
            bounds.setWidth(1.0)
        if bounds.height() <= 0:
            bounds.setHeight(1.0)
        padding = CROSS_SIZE + 8
        view = QRectF(self.rect())
        available_width = max(1, view.width() - 2 * padding)
        available_height = max(1, view.height() - 2 * padding)
        self.scale = min(
            available_width / bounds.width(),
            available_height / bounds.height(),
        )
        self.pan = QPointF(
            view.center().x() - bounds.center().x() * self.scale,
            view.center().y() - bounds.center().y() * self.scale,
        )
        self._fitted = True
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#202020"))
        image_top_left = self.image_to_widget(QPointF(0, 0))
        painter.drawImage(
            QRectF(
                image_top_left.x(),
                image_top_left.y(),
                self.image.width() * self.scale,
                self.image.height() * self.scale,
            ),
            self.image,
            QRectF(self.image.rect()),
        )

        frame_top_left = self.image_to_widget(
            QPointF(self.frame_x, self.frame_y)
        )
        frame_bottom_right = self.image_to_widget(
            QPointF(
                self.frame_x + self.frame_width,
                self.frame_y + self.frame_height,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        frame_rect = QRectF(
            frame_top_left.x(),
            frame_top_left.y(),
            frame_bottom_right.x() - frame_top_left.x(),
            frame_bottom_right.y() - frame_top_left.y(),
        )
        for frame_color, frame_width in (
            (QColor("black"), 7),
            (QColor("white"), 4),
            (QColor("#ff8c00"), 2),
        ):
            painter.setPen(QPen(frame_color, frame_width))
            painter.drawRect(frame_rect)
        if self.cfg_frame_crosshair_enabled:
            center = self.image_to_widget(
                QPointF(
                    self.frame_x + self.frame_width / 2,
                    self.frame_y + self.frame_height / 2,
                )
            )
            painter.setPen(QPen(QColor("black"), 7))
            painter.drawLine(
                QPointF(center.x() - CROSS_SIZE, center.y()),
                QPointF(center.x() + CROSS_SIZE, center.y()),
            )
            painter.drawLine(
                QPointF(center.x(), center.y() - CROSS_SIZE),
                QPointF(center.x(), center.y() + CROSS_SIZE),
            )
            painter.setPen(QPen(QColor("white"), 3))
            painter.drawLine(
                QPointF(center.x() - CROSS_SIZE, center.y()),
                QPointF(center.x() + CROSS_SIZE, center.y()),
            )
            painter.drawLine(
                QPointF(center.x(), center.y() - CROSS_SIZE),
                QPointF(center.x(), center.y() + CROSS_SIZE),
            )

        point_colors = (
            QColor("#ff7777"),
            QColor("#75e695"),
            QColor("#78aaff"),
        )
        for point, color in zip(self.points, point_colors):
            position = self.image_to_widget(point)
            phase = self._marker_animation_clock.elapsed() % 1000
            brightness = phase / 500 if phase < 500 else (1000 - phase) / 500
            outline_color = QColor.fromRgbF(brightness, brightness, brightness)
            for line_color, line_width, line_size in (
                (outline_color, 3, CROSS_SIZE),
                (color, 2, CROSS_SIZE - 2),
            ):
                painter.setPen(QPen(line_color, line_width))
                half_size = line_size / 2
                painter.drawLine(
                    QPointF(position.x() - half_size, position.y()),
                    QPointF(position.x() + half_size, position.y()),
                )
                painter.drawLine(
                    QPointF(position.x(), position.y() - half_size),
                    QPointF(position.x(), position.y() + half_size),
                )
        _event.accept()

    def _frame_handle_at(self, position):
        top_left = self.image_to_widget(QPointF(self.frame_x, self.frame_y))
        bottom_right = self.image_to_widget(
            QPointF(
                self.frame_x + self.frame_width,
                self.frame_y + self.frame_height,
            )
        )
        tolerance = 9
        if self.cfg_frame_crosshair_enabled:
            center = self.image_to_widget(
                QPointF(
                    self.frame_x + self.frame_width / 2,
                    self.frame_y + self.frame_height / 2,
                )
            )
            if (position - center).manhattanLength() <= CROSS_SIZE:
                return "center"
        near_left = abs(position.x() - top_left.x()) <= tolerance
        near_right = abs(position.x() - bottom_right.x()) <= tolerance
        near_top = abs(position.y() - top_left.y()) <= tolerance
        near_bottom = abs(position.y() - bottom_right.y()) <= tolerance
        within_x = (
            top_left.x() - tolerance
            <= position.x()
            <= bottom_right.x() + tolerance
        )
        within_y = (
            top_left.y() - tolerance
            <= position.y()
            <= bottom_right.y() + tolerance
        )
        if near_top and near_left:
            return "top-left"
        if near_top and near_right:
            return "top-right"
        if near_bottom and near_left:
            return "bottom-left"
        if near_bottom and near_right:
            return "bottom-right"
        if near_left and within_y:
            return "left"
        if near_right and within_y:
            return "right"
        if near_top and within_x:
            return "top"
        if near_bottom and within_x:
            return "bottom"
        return None

    def _set_hover_cursor(self, position):
        handle = self._frame_handle_at(position)
        if handle == "center":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if handle in ("top-left", "bottom-right"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            return
        if handle in ("top-right", "bottom-left"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            return
        if any(
            (self.image_to_widget(point) - position).manhattanLength()
            <= CROSS_SIZE
            for point in self.points
        ):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        if handle:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _set_frame_width(self, width, edge):
        minimum_width = 1.0
        width = max(minimum_width, width)
        old_right = self.frame_x + self.frame_width
        old_bottom = self.frame_y + self.frame_height
        if "left" in edge:
            self.frame_x = old_right - width
        if "top" in edge:
            self.frame_y = old_bottom - width / self.frame_aspect_ratio
        self.frame_width = width

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        position = event.position()
        self._last_mouse_position = position
        handle = self._frame_handle_at(position)
        if handle == "center":
            self._drag_mode = "frame-move"
        elif handle in (
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
        ):
            self._drag_mode = "frame-resize"
            self._drag_corner = handle
        else:
            nearest_point = min(
                range(len(self.points)),
                key=lambda index: (
                    self.image_to_widget(self.points[index]) - position
                ).manhattanLength(),
            )
            if (
                self.image_to_widget(self.points[nearest_point]) - position
            ).manhattanLength() <= CROSS_SIZE:
                self._drag_mode = "point"
                self._drag_point = nearest_point
            elif handle:
                self._drag_mode = "frame-move"
            else:
                self._drag_mode = "pan"
        if self._drag_mode == "frame-resize":
            self._set_hover_cursor(position)
        else:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        position = event.position()
        if self._drag_mode == "point":
            self.points[self._drag_point] = self.widget_to_image(position)
            self.points_changed.emit(
                [(point.x(), point.y()) for point in self.points]
            )
        elif self._drag_mode == "frame-resize":
            delta = position - self._last_mouse_position
            if "-" in self._drag_corner:
                x_direction = -1 if "left" in self._drag_corner else 1
                y_direction = -1 if "top" in self._drag_corner else 1
                x_width_delta = delta.x() * x_direction
                y_width_delta = (
                    delta.y() * y_direction * self.frame_aspect_ratio
                )
                if abs(delta.x()) < 1e-6:
                    width_delta = y_width_delta / self.scale
                elif abs(delta.y()) < 1e-6:
                    width_delta = x_width_delta / self.scale
                else:
                    width_delta = (x_width_delta + y_width_delta) / (
                        2 * self.scale
                    )
            self._set_frame_width(
                self.frame_width + width_delta, self._drag_corner
            )
            self.frame_changed.emit(self._frame_data())
        elif self._drag_mode == "frame-move":
            self.frame_x += (
                position.x() - self._last_mouse_position.x()
            ) / self.scale
            self.frame_y += (
                position.y() - self._last_mouse_position.y()
            ) / self.scale
            self.frame_changed.emit(self._frame_data())
        elif self._drag_mode == "pan":
            self.pan += position - self._last_mouse_position
        self._last_mouse_position = position
        self.update()
        if self._drag_mode is None:
            self._set_hover_cursor(position)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = None
            self._drag_point = None
            self.unsetCursor()
            self.update()

    def wheelEvent(self, event):
        position = event.position()
        image_position = self.widget_to_image(position)
        factor = 1.15 ** (event.angleDelta().y() / 120)
        self.scale = min(40.0, max(0.05, self.scale * factor))
        self.pan = QPointF(
            position.x() - image_position.x() * self.scale,
            position.y() - image_position.y() * self.scale,
        )
        self.update()
        event.accept()

    def _frame_data(self):
        return {
            "upper_left": (self.frame_x, self.frame_y),
            "width": self.frame_width,
            "height": self.frame_height,
            "aspect_ratio": self.frame_aspect_ratio,
        }
