from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
	QAbstractItemView,
	QComboBox,
	QDialog,
	QDialogButtonBox,
	QDoubleSpinBox,
	QFileDialog,
	QFormLayout,
	QHBoxLayout,
	QLabel,
	QListWidget,
	QListWidgetItem,
	QPushButton,
	QSplitter,
	QSpinBox,
	QVBoxLayout,
	QWidget,
)


CROSS_SIZE = 20


def load_oriented_image(filename):
	reader = QImageReader(str(filename))
	reader.setAutoTransform(True)
	return reader.read()


class imageFilesOrganizer(QWidget):
	selectedImageChanged = pyqtSignal(str)
	imageFilesChanged = pyqtSignal(list)

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
			self, "Add images", "",
			"Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp);;All files (*)",
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
		self.selectedImageChanged.emit(item.data(Qt.ItemDataRole.UserRole) if item else "")

	def _emit_image_files_changed(self):
		self.imageFilesChanged.emit([
			self.image_list.item(index).data(Qt.ItemDataRole.UserRole)
			for index in range(self.image_list.count())
		])

	def set_highlighted_paths(self, filenames):
		highlighted_paths = {str(Path(filename).resolve()) for filename in filenames}
		for index in range(self.image_list.count()):
			item = self.image_list.item(index)
			font = item.font()
			font.setBold(item.data(Qt.ItemDataRole.UserRole) in highlighted_paths)
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
			url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
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


class previewArea(QLabel):
	def __init__(self, parent=None):
		super().__init__("Select an image to preview", parent)
		self.setObjectName("previewArea")
		self.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self.setMinimumSize(160, 120)
		self.setStyleSheet("background-color: #202020; color: white;")
		self._pixmap = QPixmap()

	def set_image(self, filename):
		image = load_oriented_image(filename) if filename else QImage()
		if image.isNull():
			self._pixmap = QPixmap()
			self.setText("Select an image to preview" if not filename else "Unable to load image")
		else:
			self._pixmap = QPixmap.fromImage(image)
			self.setText("")
		self._update_preview()

	def resizeEvent(self, event):
		super().resizeEvent(event)
		self._update_preview()

	def _update_preview(self):
		if not self._pixmap.isNull():
			self.setPixmap(self._pixmap.scaled(
				self.contentsRect().size(),
				Qt.AspectRatioMode.KeepAspectRatio,
				Qt.TransformationMode.SmoothTransformation,
			))


class imageFilesAndPreviewArea(QSplitter):
	def __init__(self, parent=None):
		super().__init__(Qt.Orientation.Horizontal, parent)
		self.setObjectName("imageFilesAndPreviewArea")
		self.image_files_organizer = imageFilesOrganizer(self)
		self.preview_area = previewArea(self)
		self.addWidget(self.image_files_organizer)
		self.addWidget(self.preview_area)
		self.setStretchFactor(0, 1)
		self.setStretchFactor(1, 3)


class imageFusionEditor(QWidget):
	imageEdited = pyqtSignal(int, str, object)
	pairRequested = pyqtSignal(int)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setObjectName("imageFusionEditor")
		self.pair_index = 0
		self.image_entries = []
		self.image_paths = []
		self.layout = QVBoxLayout(self)
		self.navigation = QHBoxLayout()
		self.previous_button = QPushButton("Previous pair")
		self.pair_label = QLabel()
		self.next_button = QPushButton("Next pair")
		self.navigation.addWidget(self.previous_button)
		self.navigation.addStretch(1)
		self.navigation.addWidget(self.pair_label)
		self.navigation.addStretch(1)
		self.navigation.addWidget(self.next_button)
		self.layout.addLayout(self.navigation)
		self.pair_splitter = QSplitter(Qt.Orientation.Horizontal, self)
		self.layout.addWidget(self.pair_splitter, 1)
		self.previous_button.clicked.connect(self._previous_pair)
		self.next_button.clicked.connect(self._next_pair)
		self.set_pair([], [], 0)

	def set_pair(self, image_entries, image_paths, pair_index):
		self.image_entries = image_entries
		self.image_paths = image_paths
		self.pair_index = pair_index
		while self.pair_splitter.count():
			widget = self.pair_splitter.widget(0)
			self.pair_splitter.widget(0).setParent(None)
			widget.deleteLater()

		pair_count = max(0, len(image_entries) - 1)
		if pair_count == 0:
			self.pair_label.setText("Add at least two images to edit a pair")
			self.previous_button.setEnabled(False)
			self.next_button.setEnabled(False)
			return

		self.pair_index = max(0, min(pair_index, pair_count - 1))
		self.pair_label.setText(f"Pair {self.pair_index + 1} / {pair_count}")
		self.previous_button.setEnabled(self.pair_index > 0)
		self.next_button.setEnabled(self.pair_index < pair_count - 1)
		for offset, points_field in ((0, "next_points"), (1, "prev_points")):
			entry_index = self.pair_index + offset
			entry = image_entries[entry_index]
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
			editor = imageMarkersEditor(
				path, frame_top_left, frame_width, frame_width / frame_height, points, column
			)
			editor.setObjectName("imageMarkersEditor")
			editor.frameChanged.connect(
				lambda value, index=entry_index: self.imageEdited.emit(index, "frame", value)
			)
			editor.pointsChanged.connect(
				lambda value, index=entry_index, field=points_field:
					self.imageEdited.emit(index, field, value)
			)
			column_layout.addWidget(editor, 1)
			column.filename_label = filename_label
			column.editor = editor
			self.pair_splitter.addWidget(column)
		self.pair_splitter.setStretchFactor(0, 1)
		self.pair_splitter.setStretchFactor(1, 1)

	def _previous_pair(self):
		if self.pair_index > 0:
			self.pairRequested.emit(self.pair_index - 1)

	def _next_pair(self):
		if self.pair_index < len(self.image_entries) - 2:
			self.pairRequested.emit(self.pair_index + 1)


class imageFusionEditionArea(QWidget):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setObjectName("imageFusionEditionArea")
		self.layout = QVBoxLayout(self)
		self.editor = imageFusionEditor(self)
		self.layout.addWidget(self.editor)


class VideoSettingsDialog(QDialog):
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
		self.setWindowTitle("Video Settings")
		self.setModal(True)
		layout = QFormLayout(self)

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

		buttons = QDialogButtonBox(
			QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
		)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addRow(buttons)

		self.video_size_combo.currentIndexChanged.connect(self._select_video_size)
		self.frame_rate_combo.currentIndexChanged.connect(self._select_frame_rate)
		self._initialize_values(video_data)
		self._select_video_size(self.video_size_combo.currentIndex())
		self._select_frame_rate(self.frame_rate_combo.currentIndex())

	def _initialize_values(self, video_data):
		width, height = video_data.get("size", (1920, 1080))
		matching_size = next(
			(index for index, dimensions in enumerate(self.VIDEO_SIZES.values())
			 if dimensions == (width, height)),
			-1,
		)
		if matching_size >= 0:
			self.video_size_combo.setCurrentIndex(matching_size)
		else:
			self.video_size_combo.setCurrentIndex(self.video_size_combo.count() - 1)
		self.width_spin.setValue(width)
		self.height_spin.setValue(height)

		frame_rate = video_data.get("FPS", 30)
		matching_rate = next(
			(index for index, rate in enumerate(self.FRAME_RATES) if rate == frame_rate),
			-1,
		)
		if matching_rate >= 0:
			self.frame_rate_combo.setCurrentIndex(matching_rate)
		else:
			self.frame_rate_combo.setCurrentIndex(self.frame_rate_combo.count() - 1)
		self.custom_frame_rate.setValue(frame_rate)
		self.duration_spin.setValue(video_data.get("duration", 10))

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
			"size": selected_size or (self.width_spin.value(), self.height_spin.value()),
			"FPS": frame_rate if frame_rate is not None else self.custom_frame_rate.value(),
			"duration": self.duration_spin.value(),
		}


class imageMarkersEditor(QWidget):
	pointsChanged = pyqtSignal(list)
	frameChanged = pyqtSignal(object)

	def __init__(self, image_filename, frame_upper_left, frame_width, frame_aspect_ratio, points, parent=None):
		super().__init__(parent)
		image_path = Path(image_filename)
		if not image_path.is_absolute():
			image_path = Path(__file__).resolve().parent / image_path
		self.image = load_oriented_image(image_path)
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
		self.points = [QPointF(float(point[0]), float(point[1])) for point in points]

		self.scale = 1.0
		self.pan = QPointF(0, 0)
		self._fitted = False
		self._drag_mode = None
		self._drag_point = None
		self._last_mouse_position = QPointF()
		self.zoom_all_button = QPushButton("Zoom all", self)
		self.zoom_all_button.setFixedSize(96, 34)
		self.zoom_all_button.clicked.connect(self.zoom_all)
		self.setMinimumSize(480, 360)
		self.setMouseTracking(True)
		self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

	@property
	def frame_height(self):
		return self.frame_width / self.frame_aspect_ratio

	def image_to_widget(self, point):
		return QPointF(point.x() * self.scale + self.pan.x(), point.y() * self.scale + self.pan.y())

	def widget_to_image(self, point):
		return QPointF((point.x() - self.pan.x()) / self.scale, (point.y() - self.pan.y()) / self.scale)

	def resizeEvent(self, _event):
		super().resizeEvent(_event)
		self.zoom_all_button.move(self.width() - self.zoom_all_button.width() - 12, 10)
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
			min(all_x), min(all_y), max(all_x) - min(all_x), max(all_y) - min(all_y)
		)
		padding = CROSS_SIZE + 8
		view = QRectF(0, 48, self.width(), self.height() - 48)
		available_width = max(1, view.width() - 2 * padding)
		available_height = max(1, view.height() - 2 * padding)
		self.scale = min(available_width / bounds.width(), available_height / bounds.height())
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
			QRectF(image_top_left.x(), image_top_left.y(),
				self.image.width() * self.scale, self.image.height() * self.scale),
			self.image,
			QRectF(self.image.rect()),
		)

		frame_top_left = self.image_to_widget(QPointF(self.frame_x, self.frame_y))
		frame_bottom_right = self.image_to_widget(
			QPointF(self.frame_x + self.frame_width, self.frame_y + self.frame_height)
		)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		frame_rect = QRectF(
			frame_top_left.x(), frame_top_left.y(),
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

		point_colors = (QColor("red"), QColor("green"), QColor("blue"))
		for point, color in zip(self.points, point_colors):
			position = self.image_to_widget(point)
			for line_color, line_width, line_size in (
				(QColor("black"), 7, CROSS_SIZE),
				(QColor("white"), 4, CROSS_SIZE - 4),
				(color, 2, CROSS_SIZE - 8),
			):
				painter.setPen(QPen(line_color, line_width))
				half_size = line_size / 2
				painter.drawLine(QPointF(position.x() - half_size, position.y()),
					QPointF(position.x() + half_size, position.y()))
				painter.drawLine(QPointF(position.x(), position.y() - half_size),
					QPointF(position.x(), position.y() + half_size))
		_event.accept()

	def _frame_handle_at(self, position):
		top_left = self.image_to_widget(QPointF(self.frame_x, self.frame_y))
		bottom_right = self.image_to_widget(
			QPointF(self.frame_x + self.frame_width, self.frame_y + self.frame_height)
		)
		tolerance = 9
		near_left = abs(position.x() - top_left.x()) <= tolerance
		near_right = abs(position.x() - bottom_right.x()) <= tolerance
		near_top = abs(position.y() - top_left.y()) <= tolerance
		near_bottom = abs(position.y() - bottom_right.y()) <= tolerance
		within_x = top_left.x() - tolerance <= position.x() <= bottom_right.x() + tolerance
		within_y = top_left.y() - tolerance <= position.y() <= bottom_right.y() + tolerance
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
		if handle in ("top-left", "bottom-right"):
			self.setCursor(Qt.CursorShape.SizeFDiagCursor)
			return
		if handle in ("top-right", "bottom-left"):
			self.setCursor(Qt.CursorShape.SizeBDiagCursor)
			return
		if any((self.image_to_widget(point) - position).manhattanLength() <= CROSS_SIZE
			for point in self.points):
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
		if handle in ("top-left", "top-right", "bottom-left", "bottom-right"):
			self._drag_mode = "frame-resize"
			self._drag_corner = handle
		else:
			nearest_point = min(
				range(len(self.points)),
				key=lambda index: (self.image_to_widget(self.points[index]) - position).manhattanLength(),
			)
			if (self.image_to_widget(self.points[nearest_point]) - position).manhattanLength() <= CROSS_SIZE:
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
			self.pointsChanged.emit([(point.x(), point.y()) for point in self.points])
		elif self._drag_mode == "frame-resize":
			delta = position - self._last_mouse_position
			if "-" in self._drag_corner:
				x_direction = -1 if "left" in self._drag_corner else 1
				y_direction = -1 if "top" in self._drag_corner else 1
				x_width_delta = delta.x() * x_direction
				y_width_delta = delta.y() * y_direction * self.frame_aspect_ratio
				if abs(delta.x()) < 1e-6:
					width_delta = y_width_delta / self.scale
				elif abs(delta.y()) < 1e-6:
					width_delta = x_width_delta / self.scale
				else:
					width_delta = (x_width_delta + y_width_delta) / (2 * self.scale)
			self._set_frame_width(self.frame_width + width_delta, self._drag_corner)
			self.frameChanged.emit(self._frame_data())
		elif self._drag_mode == "frame-move":
			self.frame_x += (position.x() - self._last_mouse_position.x()) / self.scale
			self.frame_y += (position.y() - self._last_mouse_position.y()) / self.scale
			self.frameChanged.emit(self._frame_data())
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
		self.pan = QPointF(position.x() - image_position.x() * self.scale,
			position.y() - image_position.y() * self.scale)
		self.update()
		event.accept()

	def _frame_data(self):
		return {
			"upper_left": (self.frame_x, self.frame_y),
			"width": self.frame_width,
			"height": self.frame_height,
			"aspect_ratio": self.frame_aspect_ratio,
		}