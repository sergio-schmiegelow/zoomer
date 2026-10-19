import sys
import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QSplitter

from widgets import VideoSettingsDialog, imageFilesAndPreviewArea, imageMarkersEditor


class MainApp(QMainWindow):
	def __init__(self, video_settings, project_filename):
		super().__init__()
		self.video_settings = dict(video_settings)
		self.project_filename = project_filename
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
		self.image_entries = image_entries
		self.base_directory = Path(base_directory)
		self.image_files_and_preview_area = imageFilesAndPreviewArea(self)
		self.image_files_and_preview_area.image_files_organizer.selectedImageChanged.connect(
			self._select_image
		)
		self.workspace_splitter = QSplitter(Qt.Orientation.Vertical, self)
		self.workspace_splitter.addWidget(self.image_files_and_preview_area)
		self.image_fusion_editor = None
		self.setCentralWidget(self.workspace_splitter)
		paths = [self.base_directory / entry['filename'] for entry in image_entries]
		self.image_files_and_preview_area.image_files_organizer.set_image_files(paths)

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
	config_path = Path(__file__).resolve().parent / "prat.json"
	with config_path.open(encoding="utf-8") as config_file:
		project_data = json.load(config_file)
	window = MainApp(project_data.get("video_data", {}), str(config_path))
	window.set_image_workspace(project_data["images_data"], config_path.parent)
	window.resize(1000, 700)
	window.show()
	return app.exec()


if __name__ == "__main__":
	raise SystemExit(main())
