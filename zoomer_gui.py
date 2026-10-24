import sys
import math
import random
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QSplitter

from widgets import (
	VideoSettingsDialog,
	imageFilesAndPreviewArea,
	imageFusionEditionArea,
)
from zoomer_backend import imageClass, loadConfig, saveConfig, createBlendedFrame


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
		saveConfig(self.project_filename, self.configData)

	def save_as(self, _checked=False):
		filename, _selected_filter = QFileDialog.getSaveFileName(
			self, "Save project as", self.project_filename,
			"JSON files (*.json);;All files (*)",
		)
		if filename:
			self.project_filename = filename
			saveConfig(self.project_filename, self.configData)

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

	def set_image_workspace(self, image_entries, base_directory):
		self.image_entries = self.configData["images_data"]
		self.base_directory = Path(base_directory)
		if self._normalize_boundary_points():
			self.save_autosave()
		self.image_files_and_preview_area = imageFilesAndPreviewArea(self)
		organizer = self.image_files_and_preview_area.image_files_organizer
		organizer.selectedImageChanged.connect(self._select_pair_from_path)
		organizer.imageFilesChanged.connect(self._organizer_files_changed)
		self.workspace_splitter = QSplitter(Qt.Orientation.Vertical, self)
		self.workspace_splitter.addWidget(self.image_files_and_preview_area)
		self.image_fusion_edition_area = imageFusionEditionArea(self)
		self.image_fusion_editor = self.image_fusion_edition_area.editor
		self.image_fusion_editor.pairRequested.connect(self._navigate_pair)
		self.image_fusion_editor.imageEdited.connect(self._image_edited)
		self.image_fusion_editor.fusionPreviewRequested.connect(self._update_fusion_preview)
		self.image_fusion_editor.alphaRangeEdited.connect(self._alpha_range_edited)
		self._fusion_preview_timer = QTimer(self)
		self._fusion_preview_timer.setSingleShot(True)
		self._fusion_preview_timer.setInterval(75)
		self._fusion_preview_timer.timeout.connect(
			self.image_fusion_editor.refresh_fusion_preview
		)
		self.workspace_splitter.addWidget(self.image_fusion_edition_area)
		self.setCentralWidget(self.workspace_splitter)
		paths = [self._path_for_entry(entry) for entry in image_entries]
		organizer.set_image_files(paths)
		self._show_pair(max(0, organizer.image_list.currentRow()))

	@staticmethod
	def _image_path(image_entry):
		image_object = image_entry["image"]
		if isinstance(image_object, imageClass):
			return Path(image_object.getImagePath())
		return Path(image_object)

	def _path_for_entry(self, image_entry):
		path = self._image_path(image_entry)
		return path if path.is_absolute() else self.base_directory / path

	def _organizer_files_changed(self, filenames):
		entries_by_path = {
			self._path_for_entry(entry).resolve(): entry
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
		self._normalize_boundary_points()
		self.save_autosave()
		current_row = self.image_files_and_preview_area.image_files_organizer.image_list.currentRow()
		self._show_pair(max(0, current_row))

	def _normalize_boundary_points(self):
		if not self.image_entries:
			return False
		changed = False
		if self.image_entries[0].get("prev_points") is not None:
			self.image_entries[0]["prev_points"] = None
			changed = True
		if self.image_entries[-1].get("next_points") is not None:
			self.image_entries[-1]["next_points"] = None
			changed = True
		return changed

	def _new_image_entry(self, image_path):
		image_object = imageClass(str(image_path))
		image = image_object.getCvImage()
		if image is None:
			raise ValueError(f"Unable to load image: {image_path}")
		video_width, video_height = self.video_settings.get("size", (960, 540))
		video_aspect = float(video_width) / float(video_height)
		image_height, image_width = image.shape[:2]
		image_width = float(image_width)
		image_height = float(image_height)
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
			"image": image_object,
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
		saveConfig(str(temporary_path), self.configData)
		temporary_path.replace(self.autosave_path)

	def _paths_for_entries(self):
		return [
			str(self._path_for_entry(entry).resolve())
			for entry in self.image_entries
		]

	def _select_pair_from_path(self, filename):
		if not filename:
			self.image_files_and_preview_area.preview_area.set_image("")
			self._show_pair(0)
			return
		organizer = self.image_files_and_preview_area.image_files_organizer
		self._show_pair(max(0, organizer.image_list.currentRow()))

	def _show_pair(self, pair_index):
		paths = self._paths_for_entries()
		organizer = self.image_files_and_preview_area.image_files_organizer
		pair_index = max(0, min(pair_index, max(0, len(paths) - 2)))
		if paths:
			selected_index = min(pair_index, len(paths) - 1)
			self.image_files_and_preview_area.preview_area.set_image(
				self.image_entries[selected_index]["image"]
			)
		else:
			selected_index = 0
			self.image_files_and_preview_area.preview_area.set_image("")
		organizer.set_highlighted_paths(paths[pair_index:pair_index + 2] if len(paths) > 1 else [])
		self.image_fusion_editor.set_pair(self.image_entries, paths, pair_index)

	def _navigate_pair(self, pair_index):
		organizer = self.image_files_and_preview_area.image_files_organizer
		if organizer.image_list.currentRow() == pair_index:
			self._show_pair(pair_index)
		else:
			organizer.image_list.setCurrentRow(pair_index)

	def _update_fusion_preview(self, pair_index, size_alpha, blend_alpha):
		if not 0 <= pair_index < len(self.image_entries) - 1:
			self.image_files_and_preview_area.preview_area.set_fusion_frame(None)
			return
		frame = createBlendedFrame(
			self.configData,
			pair_index,
			size_alpha,
			blend_alpha,
			interpolationMethod="linear",
		)
		self.image_files_and_preview_area.preview_area.set_fusion_frame(frame)

	def _alpha_range_edited(self, pair_index, alpha_range):
		if not 0 <= pair_index < len(self.image_entries):
			return
		self.image_entries[pair_index]["alpha_range"] = list(alpha_range)
		self.save_autosave()

	def _image_edited(self, image_index, field, value):
		if image_index >= len(self.image_entries):
			return
		if field == "prev_points" and image_index == 0:
			return
		if field == "next_points" and image_index == len(self.image_entries) - 1:
			return
		entry = self.image_entries[image_index]
		if field == "frame":
			upper_left = value["upper_left"]
			entry["frame"] = [
				[upper_left[0], upper_left[1]],
				[upper_left[0] + value["width"], upper_left[1] + value["height"]],
			]
		else:
			entry[field] = [[point[0], point[1]] for point in value]
		self.save_autosave()
		self._fusion_preview_timer.start()


def main() -> int:
	app = QApplication(sys.argv)
	config_path = Path(__file__).resolve().parent / "autosave.json"
	if config_path.exists():
		config_data = loadConfig(str(config_path))
	else:
		fallback_path = Path(__file__).resolve().parent / "prat.json"
		config_data = loadConfig(str(fallback_path))
	window = MainApp(config_data, config_path)
	window.set_image_workspace(config_data["images_data"], config_path.parent)
	window.resize(1000, 700)
	window.show()
	return app.exec()


if __name__ == "__main__":
	raise SystemExit(main())
