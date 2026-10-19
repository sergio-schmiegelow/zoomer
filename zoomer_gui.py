import sys
import json
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow

from widgets import VideoSettingsDialog, imageMarkersEditor


class MainApp(QMainWindow):
	def __init__(self, video_settings, project_filename):
		super().__init__()
		self.video_settings = dict(video_settings)
		self.project_filename = project_filename
		self.export_filename = ""
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


def main() -> int:
	app = QApplication(sys.argv)
	config_path = Path(__file__).resolve().parent / "prat.json"
	with config_path.open(encoding="utf-8") as config_file:
		project_data = json.load(config_file)
	image_data = project_data["images_data"][0]
	window = MainApp(project_data.get("video_data", {}), str(config_path))
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
