import sys
import json
import math
import random
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QSplitter

from widgets import VideoSettingsDialog, imageFilesAndPreviewArea, imageMarkersEditor


class MainApp(QMainWindow):
	def __init__(self, config_data, autosave_path):
		super().__init__()
		self.configData = config_data
		self.video_settings = self.configData.setdefault("video_data", {})
		self.configData.setdefault("images_data", [])
		self.autosave_path = Path(autosave_path)
		self.project_filename = str(self.autosave_path)
		self.export_filename = ""
		self.image_entries = []
		self.setWindowTitle("Zoomer")
		self._create_menus()

	def _create_menus(self):
		file_menu = self.menuBar().addMenu("&File")
		save_action = file_menu.addAction("Save")
		save_action.triggered.connect(self.save_project)
		save_as_action = file_menu.addAction("Save as...")
		save_as_action.triggered.connect(self.save_as)
		new_action = file_menu.addAction("New...")
		new_action.triggered.connect(self.new_project)

		video_action = self.menuBar().addAction("&Video")
		video_action.triggered.connect(self.open_video_settings)

		export_action = self.menuBar().addAction("&Export")
		export_action.triggered.connect(self.select_export_filename)

	def save_project(self, _checked=False):
		pass

	def save_as(self, _checked=False):
		filename, _selected_filter = QFileDialog.getSaveFileName(
			self, "Save project as", self.project_filename,
			"JSON files (*.json);;All files (*)",
		)
		if filename:
			self.project_filename = filename

	def new_project(self, _checked=False):
		filename, _selected_filter = QFileDialog.getSaveFileName(
			self, "New project", "",
			"JSON files (*.json);;All files (*)",
		)
		if filename:
			self.project_filename = filename

	def open_video_settings(self, _checked=False):
		dialog = VideoSettingsDialog(self.video_settings, self)
		if dialog.exec():
			self.video_settings = dialog.settings()
			self.configData["video_data"] = self.video_settings
			self.save_autosave()

	def select_export_filename(self, _checked=False):
		filename, _selected_filter = QFileDialog.getSaveFileName(
			self, "Export video", "",
			"MP4 video (*.mp4);;All files (*)",
		)
		if filename:
			self.export_filename = filename

	def receive_points_changed(self, points):
		print(f'DEBUG - points changed: {points}')

	def receive_frame_changed(self, frame):
		print(f'DEBUG - frame changed: {frame}')

	def set_image_workspace(self, image_entries, base_directory):
		self.image_entries = self.configData["images_data"]
		self.base_directory = Path(base_directory)
		self.image_files_and_preview_area = imageFilesAndPreviewArea(self)
		organizer = self.image_files_and_preview_area.image_files_organizer
		organizer.selectedImageChanged.connect(self._select_image)
		self.workspace_splitter = QSplitter(Qt.Orientation.Vertical, self)
		self.workspace_splitter.addWidget(self.image_files_and_preview_area)
		self.image_fusion_editor = None
		self.setCentralWidget(self.workspace_splitter)
		paths = [self.base_directory / entry['filename'] for entry in image_entries]
		organizer.set_image_files(paths)
		organizer.imageFilesChanged.connect(self._organizer_files_changed)

	def _organizer_files_changed(self, filenames):
		entries_by_path = {
			(self.base_directory / entry["filename"]).resolve(): entry
			for entry in self.image_entries
		}
		updated_entries = []
		for filename in filenames:
			path = Path(filename).resolve()
			entry = entries_by_path.get(path)
			if entry is None:
				entry = self._new_image_entry(path)
			updated_entries.append(entry)
		self.image_entries = updated_entries
		self.configData["images_data"] = updated_entries
		self.save_autosave()
		selected_item = self.image_files_and_preview_area.image_files_organizer.image_list.currentItem()
		if selected_item is not None:
			self._select_image(selected_item.data(Qt.ItemDataRole.UserRole))
		elif self.image_fusion_editor is not None:
			index = self.workspace_splitter.indexOf(self.image_fusion_editor)
			self.workspace_splitter.widget(index).deleteLater()
			self.image_fusion_editor = None

	def _new_image_entry(self, image_path):
		from widgets import load_oriented_image

		image = load_oriented_image(image_path)
		if image.isNull():
			raise ValueError(f"Unable to load image: {image_path}")
		video_width, video_height = self.video_settings.get("size", (960, 540))
		video_aspect = float(video_width) / float(video_height)
		image_width = float(image.width())
		image_height = float(image.height())
		if image_width / image_height > video_aspect:
			frame_height = image_height
			frame_width = frame_height * video_aspect
		else:
			frame_width = image_width
			frame_height = frame_width / video_aspect
		frame_x = (image_width - frame_width) / 2
		frame_y = (image_height - frame_height) / 2
		frame = [
			[frame_x, frame_y],
			[frame_x + frame_width, frame_y + frame_height],
		]
		return {
			"filename": str(image_path),
			"frame": frame,
			"prev_points": self._random_equilateral_triangle(frame_x, frame_y, frame_width, frame_height),
			"next_points": self._random_equilateral_triangle(frame_x, frame_y, frame_width, frame_height),
		}

	@staticmethod
	def _random_equilateral_triangle(frame_x, frame_y, frame_width, frame_height):
		angle = random.uniform(0, 2 * math.pi)
		unit_vertices = [
			(math.cos(angle + index * 2 * math.pi / 3),
			 math.sin(angle + index * 2 * math.pi / 3))
			for index in range(3)
		]
		unit_xs = [vertex[0] for vertex in unit_vertices]
		unit_ys = [vertex[1] for vertex in unit_vertices]
		unit_width = max(unit_xs) - min(unit_xs)
		unit_height = max(unit_ys) - min(unit_ys)
		maximum_side = min(frame_width / unit_width, frame_height / unit_height)
		side = maximum_side * random.uniform(0.35, 0.8)
		vertices = [(x * side, y * side) for x, y in unit_vertices]
		vertex_xs = [vertex[0] for vertex in vertices]
		vertex_ys = [vertex[1] for vertex in vertices]
		minimum_x = frame_x - min(vertex_xs)
		maximum_x = frame_x + frame_width - max(vertex_xs)
		minimum_y = frame_y - min(vertex_ys)
		maximum_y = frame_y + frame_height - max(vertex_ys)
		center_x = random.uniform(minimum_x, maximum_x)
		center_y = random.uniform(minimum_y, maximum_y)
		return [[center_x + x, center_y + y] for x, y in vertices]

	def save_autosave(self):
		self.autosave_path.parent.mkdir(parents=True, exist_ok=True)
		temporary_path = self.autosave_path.with_name(self.autosave_path.name + ".tmp")
		temporary_path.write_text(
			json.dumps(self.configData, indent=2) + "\n", encoding="utf-8"
		)
		temporary_path.replace(self.autosave_path)

	def _select_image(self, filename):
		self.image_files_and_preview_area.preview_area.set_image(filename)
		if not filename:
			return
		selected_path = Path(filename).resolve()
		image_data = next((
			entry for entry in self.image_entries
			if (self.base_directory / entry['filename']).resolve() == selected_path
		), None)
		if image_data is None:
			return
		frame_upper_left, frame_lower_right = image_data['frame']
		frame_width = frame_lower_right[0] - frame_upper_left[0]
		frame_height = frame_lower_right[1] - frame_upper_left[1]
		points = image_data.get('next_points') or image_data.get('prev_points')
		if points is None:
			points = [[0, 0], [1, 0], [0, 1]]
		editor = imageMarkersEditor(
			str(selected_path), frame_upper_left, frame_width,
			frame_width / frame_height, points,
		)
		editor.setObjectName("imageFusionEditor")
		editor.pointsChanged.connect(self.receive_points_changed)
		editor.frameChanged.connect(self.receive_frame_changed)
		if self.image_fusion_editor is None:
			self.workspace_splitter.addWidget(editor)
		else:
			index = self.workspace_splitter.indexOf(self.image_fusion_editor)
			self.workspace_splitter.replaceWidget(index, editor)
			self.image_fusion_editor.deleteLater()
		self.image_fusion_editor = editor
		self.workspace_splitter.setStretchFactor(0, 1)
		self.workspace_splitter.setStretchFactor(1, 3)


def main() -> int:
	app = QApplication(sys.argv)
	config_path = Path(__file__).resolve().parent / "autosave.json"
	if config_path.exists():
		with config_path.open(encoding="utf-8") as config_file:
			config_data = json.load(config_file)
	else:
		fallback_path = Path(__file__).resolve().parent / "prat.json"
		with fallback_path.open(encoding="utf-8") as config_file:
			config_data = json.load(config_file)
	window = MainApp(config_data, config_path)
	window.set_image_workspace(config_data["images_data"], config_path.parent)
	window.resize(1000, 700)
	window.show()
	return app.exec()


if __name__ == "__main__":
	raise SystemExit(main())
