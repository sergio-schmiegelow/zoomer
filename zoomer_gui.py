import copy
import json
import sys
import math
import random
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QSplitter

from widgets import (
	VideoSettingsDialog,
	imageFilesAndPreviewArea,
	imageFusionEditionArea
)
from zoomer_backend import (
    imageClass, 
    loadConfig, 
    saveConfig, 
    createBlendedFrame,
    autoAlignImages,
    videoGeneratorClass
)

HISTORY_LIMIT = 10


class _AlignmentJob(QThread):
	def __init__(self, proj_data, parent=None):
		super().__init__(parent)
		self.proj_data = proj_data
		self.aligned = False
		self.error = None
		self.cancelled = False

	def run(self):
		try:
			self.aligned = bool(autoAlignImages(self.proj_data, 0))
		except Exception as error:
			self.error = error
CFG_DEFAULTS = {
	"frame_crosshair": True,
	"auto_open_last_project": False,
	"last_project": "",
}


class MainApp(QMainWindow):
	def __init__(self, proj_data=None, autosave_path=None, cfg_data=None, cfg_path=None):
		super().__init__()
		self.projData = proj_data if proj_data is not None else {
			"video_data": {}, "images_data": []
		}
		self.proj_video_settings = self.projData.setdefault("video_data", {})
		self.projData.setdefault("images_data", [])
		self.proj_filename = (
			str(autosave_path) if autosave_path and Path(autosave_path).suffix.lower() == ".zmr" else None
		)
		self.cfg_path = Path(cfg_path or Path(__file__).resolve().parent / "zoomer.cfg")
		self.cfgData = {**CFG_DEFAULTS, **(cfg_data or {})}
		self.export_filename = ""
		self.proj_image_entries = []
		self._alignment_job = None
		self._alignment_jobs = set()
		self._video_generator = None
		self._video_preview_timer = QTimer(self)
		self._video_preview_timer.setSingleShot(True)
		self._video_preview_timer.setInterval(200)
		self._video_preview_timer.timeout.connect(self._refresh_video_preview)
		self._undo_stack = deque(maxlen=HISTORY_LIMIT)
		self._redo_stack = deque(maxlen=HISTORY_LIMIT)
		# Drags emit many edits; one burst becomes a single history entry.
		self._edit_burst_timer = QTimer(self)
		self._edit_burst_timer.setSingleShot(True)
		self._edit_burst_timer.setInterval(600)
		self.setWindowTitle("Zoomer")
		self._create_menus()
		self._update_window_title()
		self._save_cfg()

	def _create_menus(self):
		file_menu = self.menuBar().addMenu("&File")
		open_action = file_menu.addAction("Open project")
		open_action.setShortcut(QKeySequence.StandardKey.Open)
		open_action.triggered.connect(self.open_project)
		save_action = file_menu.addAction("Save project")
		save_action.triggered.connect(self.save_project)
		save_as_action = file_menu.addAction("Save project as")
		save_as_action.triggered.connect(self.save_as)
		new_action = file_menu.addAction("New project")
		new_action.triggered.connect(self.new_project)

		edit_menu = self.menuBar().addMenu("&Edit")
		undo_action = edit_menu.addAction("Undo")
		undo_action.setShortcut(QKeySequence("Ctrl+Z"))
		undo_action.triggered.connect(self.undo)
		redo_action = edit_menu.addAction("Redo")
		redo_action.setShortcut(QKeySequence("Ctrl+Y"))
		redo_action.triggered.connect(self.redo)

		video_action = self.menuBar().addAction("&Video")
		video_action.triggered.connect(self.open_video_settings)

		export_action = self.menuBar().addAction("&Export")
		export_action.triggered.connect(self.select_export_filename)

		options_menu = self.menuBar().addMenu("&Options")
		self.cfg_frame_crosshair_action = options_menu.addAction("Frame crosshair")
		self.cfg_frame_crosshair_action.setCheckable(True)
		self.cfg_frame_crosshair_action.setChecked(bool(self.cfgData["frame_crosshair"]))
		self.cfg_frame_crosshair_action.toggled.connect(self._set_frame_crosshair_enabled)
		self.cfg_auto_open_last_project_action = options_menu.addAction("Auto open last project")
		self.cfg_auto_open_last_project_action.setCheckable(True)
		self.cfg_auto_open_last_project_action.setChecked(
			bool(self.cfgData["auto_open_last_project"])
		)
		self.cfg_auto_open_last_project_action.toggled.connect(self._set_auto_open_last_project)

	def _save_cfg(self):
		self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
		temporary_path = self.cfg_path.with_name(self.cfg_path.name + ".tmp")
		with temporary_path.open("w", encoding="utf-8") as config_file:
			json.dump(self.cfgData, config_file, indent=2)
		temporary_path.replace(self.cfg_path)

	def _set_auto_open_last_project(self, enabled):
		self.cfgData["auto_open_last_project"] = bool(enabled)
		self._save_cfg()

	def _remember_project(self, filename):
		self.cfgData["last_project"] = str(Path(filename).resolve())
		self._save_cfg()
		self._update_window_title()

	def _update_window_title(self):
		project_name = self.projData.get("project_name", "")
		if not project_name and self.proj_filename:
			project_name = Path(self.proj_filename).stem
		self.setWindowTitle(f"Zoomer - {project_name}" if project_name else "Zoomer - No project")

	def open_project(self, _checked=False):
		filename, _selected_filter = QFileDialog.getOpenFileName(
			self, "Open project", self.proj_filename or str(Path.home()),
			"Zoomer projects (*.zmr);;All files (*)",
		)
		if not filename:
			return
		try:
			proj_loaded = loadConfig(filename)
		except Exception as error:
			print(error)
			QMessageBox.warning(self, "Open project", f"Unable to open {filename}:\n{error}")
			return
		self._undo_stack.clear()
		self._redo_stack.clear()
		self._edit_burst_timer.stop()
		self.proj_filename = filename
		self.proj_directory = Path(filename).resolve().parent
		proj_loaded.setdefault("images_data", [])
		proj_loaded.setdefault("video_data", {})
		self._apply_restored_config(proj_loaded)
		self._remember_project(filename)
		if self._normalize_boundary_points():
			self.save_autosave()

	def save_project(self, _checked=False):
		if not self.proj_filename:
			self.new_project()
			return
		saveConfig(self.proj_filename, self.projData)
		self._remember_project(self.proj_filename)

	def save_as(self, _checked=False):
		filename, _selected_filter = QFileDialog.getSaveFileName(
			self, "Save project as", self.proj_filename or str(Path.home()),
			"Zoomer projects (*.zmr)",
		)
		if filename:
			self.proj_filename = str(Path(filename).with_suffix(".zmr"))
			self.projData["project_name"] = Path(self.proj_filename).stem
			saveConfig(self.proj_filename, self.projData)
			self._remember_project(self.proj_filename)

	def new_project(self, _checked=False):
		dialog = VideoSettingsDialog({}, self, project_mode=True)
		if not dialog.exec():
			return
		project_name = dialog.project_name()
		if not project_name or Path(project_name).name != project_name or "\\" in project_name:
			QMessageBox.warning(self, "New project", "Enter a project name without path separators.")
			return
		suggested_path = str(Path.home() / f"{project_name}.zmr")
		filename, _selected_filter = QFileDialog.getSaveFileName(
			self, "Create project", suggested_path, "Zoomer projects (*.zmr)",
		)
		if not filename:
			return
		self._undo_stack.clear()
		self._redo_stack.clear()
		self._edit_burst_timer.stop()
		self.proj_filename = str(Path(filename).with_suffix(".zmr"))
		self.proj_directory = Path(self.proj_filename).resolve().parent
		self.projData.clear()
		self.projData.update({
			"project_name": project_name,
			"video_data": dialog.settings(),
			"images_data": [],
		})
		self.proj_video_settings = self.projData["video_data"]
		self.proj_image_entries = self.projData["images_data"]
		self._apply_restored_config(dict(self.projData))
		saveConfig(self.proj_filename, self.projData)
		self._remember_project(self.proj_filename)

	def open_video_settings(self, _checked=False):
		dialog = VideoSettingsDialog(self.proj_video_settings, self)
		if dialog.exec():
			self._record_history()
			self.proj_video_settings = dialog.settings()
			self.projData["video_data"] = self.proj_video_settings
			self.save_autosave()

	def select_export_filename(self, _checked=False):
		filename, _selected_filter = QFileDialog.getSaveFileName(
			self, "Export video", "output.avi",
			"AVI video (*.avi);;All files (*)",
		)
		if filename:
			export_path = Path(filename)
			if export_path.suffix.lower() != ".avi":
				export_path = export_path.with_suffix(".avi")
			self.export_filename = str(export_path)

	def set_image_workspace(self, proj_image_entries, proj_directory):
		self.proj_image_entries = self.projData["images_data"]
		self.proj_directory = Path(proj_directory)
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
		self.image_fusion_editor.set_frame_crosshair_enabled(
			self.cfg_frame_crosshair_action.isChecked()
		)
		self.image_fusion_editor.pairRequested.connect(self._navigate_pair)
		self.image_fusion_editor.imageEdited.connect(self._image_edited)
		self.image_fusion_editor.fusionPreviewRequested.connect(self._update_fusion_preview)
		self.image_fusion_editor.alphaRangeEdited.connect(self._alpha_range_edited)
		self.image_fusion_editor.alignmentPointsRequested.connect(
			self._run_auto_alignment
		)
		self.image_fusion_editor.alignmentInterrupted.connect(self._interrupt_alignment)
		self._fusion_preview_timer = QTimer(self)
		self._fusion_preview_timer.setSingleShot(True)
		self._fusion_preview_timer.setInterval(75)
		self._fusion_preview_timer.timeout.connect(
			self.image_fusion_editor.refresh_fusion_preview
		)
		self.workspace_splitter.addWidget(self.image_fusion_edition_area)
		self.setCentralWidget(self.workspace_splitter)
		paths = [self._path_for_entry(entry) for entry in proj_image_entries]
		organizer.set_image_files(paths)
		self._show_pair(max(0, organizer.image_list.currentRow()))
		self._schedule_video_preview()

	def _schedule_video_preview(self):
		self._video_preview_timer.start()

	def _refresh_video_preview(self):
		if not hasattr(self, "image_files_and_preview_area"):
			return
		preview_area = self.image_files_and_preview_area.preview_area
		if len(self.proj_image_entries) < 2:
			preview_area.set_video_error("Add at least two images to preview the video")
			return
		try:
			if self._video_generator is None or self._video_generator.projData is not self.projData:
				self._video_generator = videoGeneratorClass(self.projData, "")
			success, error = self._video_generator.performVideoCalculations()
		except Exception as exception:
			print(exception)
			success, error = False, str(exception)
		if not success:
			preview_area.set_video_error(error or "Unable to calculate the video")
			return
		preview_area.set_video(
			self._video_generator.getTotalFrames(),
			self.proj_video_settings.get("FPS", 30),
			self._video_generator.generateVideoFrameOnPosition,
		)

	def _set_frame_crosshair_enabled(self, enabled):
		self.cfgData["frame_crosshair"] = bool(enabled)
		self._save_cfg()
		if hasattr(self, "image_fusion_editor"):
			self.image_fusion_editor.set_frame_crosshair_enabled(enabled)

	def _run_auto_alignment(self, index):
		if self._alignment_job is not None or not 0 <= index < len(self.proj_image_entries) - 1:
			return
		entries = (self.proj_image_entries[index], self.proj_image_entries[index + 1])
		# The worker edits private copies so the live project changes only on success.
		job = _AlignmentJob({
			"video_data": self.proj_video_settings,
			"images_data": [dict(entry) for entry in entries],
		}, self)
		job.index = index
		job.entries = entries
		job.finished.connect(lambda: self._alignment_finished(job))
		self._alignment_job = job
		self._alignment_jobs.add(job)
		self.image_fusion_editor.set_alignment_running(True)
		job.start()

	def _interrupt_alignment(self):
		# SIFT cannot be stopped mid-call; the thread finishes in the background and its result is dropped.
		if self._alignment_job is not None:
			self._alignment_job.cancelled = True
			self._alignment_job = None
		self.image_fusion_editor.set_alignment_running(False)

	def _alignment_finished(self, job):
		self._alignment_jobs.discard(job)
		if job.cancelled:
			job.deleteLater()
			return
		self._alignment_job = None
		self.image_fusion_editor.set_alignment_running(False)
		index = job.index
		current = self.proj_image_entries[index:index + 2]
		still_valid = len(current) == 2 and all(a is b for a, b in zip(current, job.entries))
		if job.error is not None:
			print(job.error)
		if not job.aligned:
			QMessageBox.warning(self, "Find alignment points", "Unable to find alignment points.")
		elif still_valid:
			self._edit_burst_timer.stop()
			self._record_history()
			results = job.proj_data["images_data"]
			for offset, field in ((0, "next_points"), (1, "prev_points")):
				points = results[offset][field]
				self.proj_image_entries[index + offset][field] = [[float(x), float(y)] for x, y in points]
			self._normalize_boundary_points()
			self.save_autosave()
			self._show_pair(index)
		job.deleteLater()

	@staticmethod
	def _image_path(image_entry):
		image_object = image_entry["image"]
		if isinstance(image_object, imageClass):
			return Path(image_object.getImagePath())
		return Path(image_object)

	def _path_for_entry(self, image_entry):
		path = self._image_path(image_entry)
		return path if path.is_absolute() else self.proj_directory / path

	def _organizer_files_changed(self, filenames):
		entries_by_path = {
			self._path_for_entry(entry).resolve(): entry
			for entry in self.proj_image_entries
		}
		updated_entries = []
		for filename in filenames:
			path = Path(filename).resolve()
			entry = entries_by_path.get(path)
			if entry is None:
				entry = self._new_image_entry(path)
			updated_entries.append(entry)
		unchanged = len(updated_entries) == len(self.proj_image_entries) and all(
			new is old for new, old in zip(updated_entries, self.proj_image_entries)
		)
		if not unchanged:
			self._record_history()
		self.proj_image_entries = updated_entries
		self.projData["images_data"] = updated_entries
		self._normalize_boundary_points()
		self.save_autosave()
		current_row = self.image_files_and_preview_area.image_files_organizer.image_list.currentRow()
		self._show_pair(max(0, current_row))

	def _snapshot(self):
		snapshot = {
			key: copy.deepcopy(value)
			for key, value in self.projData.items() if key != "images_data"
		}
		snapshot["images_data"] = []
		for entry in self.proj_image_entries:
			saved = {key: copy.deepcopy(value) for key, value in entry.items() if key != "image"}
			saved["image"] = str(self._image_path(entry))
			snapshot["images_data"].append(saved)
		return snapshot

	def _record_history(self, coalesce=False):
		if coalesce:
			burst_active = self._edit_burst_timer.isActive()
			self._edit_burst_timer.start()
			if burst_active:
				return
		self._undo_stack.append(self._snapshot())
		self._redo_stack.clear()

	def undo(self, _checked=False):
		self._travel_history(self._undo_stack, self._redo_stack)

	def redo(self, _checked=False):
		self._travel_history(self._redo_stack, self._undo_stack)

	def _travel_history(self, source, target):
		if not source:
			return
		current_images = {str(self._image_path(entry)): entry["image"] for entry in self.proj_image_entries}
		try:
			proj_restored = self._restore_snapshot(source[-1], current_images)
		except ValueError as error:
			print(error)
			return
		target.append(self._snapshot())
		source.pop()
		self._edit_burst_timer.stop()
		self._apply_restored_config(proj_restored)

	@staticmethod
	def _restore_snapshot(snapshot, current_images):
		proj_restored = {
			key: copy.deepcopy(value) for key, value in snapshot.items() if key != "images_data"
		}
		proj_restored["images_data"] = []
		for saved in snapshot["images_data"]:
			entry = copy.deepcopy(saved)
			path = entry["image"]
			image = current_images.get(path)
			entry["image"] = image if image is not None else imageClass(path)
			proj_restored["images_data"].append(entry)
		return proj_restored

	def _apply_restored_config(self, proj_restored):
		organizer = self.image_files_and_preview_area.image_files_organizer
		row = organizer.image_list.currentRow()
		self.projData.clear()
		self.projData.update(proj_restored)
		self.proj_video_settings = self.projData.setdefault("video_data", {})
		self.proj_image_entries = self.projData["images_data"]
		organizer.blockSignals(True)
		organizer.set_image_files([self._path_for_entry(entry) for entry in self.proj_image_entries])
		organizer.image_list.setCurrentRow(min(max(row, 0), organizer.image_list.count() - 1))
		organizer.blockSignals(False)
		self.save_autosave()
		self._show_pair(max(0, organizer.image_list.currentRow()))

	def _normalize_boundary_points(self):
		if not self.proj_image_entries:
			return False
		changed = False
		if self.proj_image_entries[0].get("prev_points") is not None:
			self.proj_image_entries[0]["prev_points"] = None
			changed = True
		if self.proj_image_entries[-1].get("next_points") is not None:
			self.proj_image_entries[-1]["next_points"] = None
			changed = True
		return changed

	def _new_image_entry(self, image_path):
		image_object = imageClass(str(image_path))
		image = image_object.getCvImage()
		if image is None:
			raise ValueError(f"Unable to load image: {image_path}")
		video_width, video_height = self.proj_video_settings.get("size", (960, 540))
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
		self._schedule_video_preview()
		if self.proj_filename:
			saveConfig(self.proj_filename, self.projData)

	def _paths_for_entries(self):
		return [
			str(self._path_for_entry(entry).resolve())
			for entry in self.proj_image_entries
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
				self.proj_image_entries[selected_index]["image"]
			)
		else:
			selected_index = 0
			self.image_files_and_preview_area.preview_area.set_image("")
		organizer.set_highlighted_paths(paths[pair_index:pair_index + 2] if len(paths) > 1 else [])
		self.image_fusion_editor.set_pair(self.proj_image_entries, paths, pair_index)

	def _navigate_pair(self, pair_index):
		organizer = self.image_files_and_preview_area.image_files_organizer
		if organizer.image_list.currentRow() == pair_index:
			self._show_pair(pair_index)
		else:
			organizer.image_list.setCurrentRow(pair_index)

	def _update_fusion_preview(self, pair_index, size_alpha, blend_alpha):
		if not 0 <= pair_index < len(self.proj_image_entries) - 1:
			self.image_files_and_preview_area.preview_area.set_fusion_frame(None)
			return
		try:
			frame = createBlendedFrame(
				self.projData,
				pair_index,
				size_alpha,
				blend_alpha,
				interpolationMethod=self.proj_video_settings.get("interpolation_method", "log"),
			)
		except Exception as error:
			print(error)
			self.image_files_and_preview_area.preview_area.set_fusion_error(
				"Invalid fusion parameters"
			)
			return
		self.image_files_and_preview_area.preview_area.set_fusion_frame(frame)

	def _alpha_range_edited(self, pair_index, alpha_range):
		if not 0 <= pair_index < len(self.proj_image_entries):
			return
		self._record_history(coalesce=True)
		self.proj_image_entries[pair_index]["alpha_range"] = list(alpha_range)
		self.save_autosave()

	def _image_edited(self, image_index, field, value):
		if image_index >= len(self.proj_image_entries):
			return
		if field == "prev_points" and image_index == 0:
			return
		if field == "next_points" and image_index == len(self.proj_image_entries) - 1:
			return
		self._record_history(coalesce=True)
		entry = self.proj_image_entries[image_index]
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
	app_directory = Path(__file__).resolve().parent
	cfg_path = app_directory / "zoomer.cfg"
	try:
		with cfg_path.open("r", encoding="utf-8") as cfg_file:
			cfgData = {**CFG_DEFAULTS, **json.load(cfg_file)}
	except (OSError, json.JSONDecodeError):
		cfgData = dict(CFG_DEFAULTS)
	window = MainApp(cfg_data=cfgData, cfg_path=cfg_path)
	window.set_image_workspace([], app_directory)
	cfg_last_project = cfgData.get("last_project", "")
	if cfgData.get("auto_open_last_project") and cfg_last_project and Path(cfg_last_project).is_file():
		window.proj_filename = cfg_last_project
		try:
			proj_loaded = loadConfig(cfg_last_project)
			proj_loaded.setdefault("project_name", Path(cfg_last_project).stem)
			window.proj_directory = Path(cfg_last_project).resolve().parent
			window._apply_restored_config(proj_loaded)
			if window._normalize_boundary_points():
				window.save_autosave()
			window._remember_project(cfg_last_project)
		except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
			QMessageBox.warning(window, "Open project", f"Unable to open {cfg_last_project}:\n{error}")
			QTimer.singleShot(0, window.new_project)
	else:
		QTimer.singleShot(0, window.new_project)
	window.resize(1000, 700)
	window.show()
	return app.exec()


if __name__ == "__main__":
	raise SystemExit(main())
