import sys
import json
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow

from widgets import imageMarkersEditor


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
