import sys
import json
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QWidget


CROSS_SIZE = 20


class imageMarkersEditor(QWidget):
	pointsChanged = pyqtSignal(list)
	frameChanged = pyqtSignal(object)

	def __init__(self, image_filename, frame_upper_left, frame_width, frame_aspect_ratio, points, parent=None):
		super().__init__(parent)
		image_path = Path(image_filename)
		if not image_path.is_absolute():
			image_path = Path(__file__).resolve().parent / image_path
		self.image = QImage(str(image_path))
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


class MainApp(QMainWindow):
	def receive_points_changed(self, points):
		print(f'DEBUG - points changed: {points}')

	def receive_frame_changed(self, frame):
		print(f'DEBUG - frame changed: {frame}')


def main() -> int:
	app = QApplication(sys.argv)
	window = MainApp()
	config_path = Path(__file__).resolve().parent / "prat.json"
	with config_path.open(encoding="utf-8") as config_file:
		image_data = json.load(config_file)["images_data"][0]
	imageFilename = image_data["filename"]
	frameUL = image_data["frame"][0]
	frameLR = image_data["frame"][1]
	frame_width = frameLR[0] - frameUL[0]
	frame_height = frameLR[1] - frameUL[1]
	frame_aspect_ratio = frame_width / frame_height
	imageEditor = imageMarkersEditor(
		image_data["filename"], frameUL, frame_width,
		frame_aspect_ratio, image_data["next_points"],
	)
	imageEditor.pointsChanged.connect(window.receive_points_changed)
	imageEditor.frameChanged.connect(window.receive_frame_changed)
	window.setCentralWidget(imageEditor)
	window.resize(1000, 700)
	window.show()
	return app.exec()


if __name__ == "__main__":
	raise SystemExit(main())
