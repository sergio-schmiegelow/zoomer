import argparse
import copy
import json
import sys
from collections import deque
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QEvent, Qt, QThread, QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import __version__
from .backend import (
    ImageClass,
    VideoGenerator,
    auto_align_images,
    calculate_pair_correlation,
    create_blended_frame,
    get_pair_blend_alpha_range,
    get_supported_video_formats,
    load_project,
    save_project,
)
from .widgets import (
    ImageFilesAndPreviewArea,
    ImageFusionEditionArea,
    NewProjectDialog,
    VideoSettingsDialog,
    _BusySpinner,
)

HISTORY_LIMIT = 10
CFG_FILENAME = "zoomer.cfg"
AUTOSAVE_FILENAME = "autosave.zmr"
PREVIEW_INTERACTION_EVENTS = frozenset(
    (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.KeyPress,
        QEvent.Type.Wheel,
        QEvent.Type.TabletPress,
        QEvent.Type.TouchBegin,
        QEvent.Type.DragEnter,
        QEvent.Type.Drop,
    )
)


class _ProjectLoadJob(QThread):
    def __init__(self, filename, parent=None):
        super().__init__(parent)
        self.filename = filename
        self.project = None
        self.error = None

    def run(self):
        try:
            self.project = load_project(self.filename)
        except Exception as error:
            self.error = error


class _ProjectLoadingDialog(QDialog):
    def __init__(self, parent):
        super().__init__(
            parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        layout = QVBoxLayout(self)
        banner = QFrame(self)
        banner.setObjectName("loadingBanner")
        banner.setStyleSheet(
            "QFrame#loadingBanner { background-color: #3a3320;"
            " border: 1px solid #c9a227; border-radius: 4px; }"
            " QFrame#loadingBanner QLabel { color: #ffe9a6; }"
        )
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        self.spinner = _BusySpinner(banner)
        banner_layout.addWidget(self.spinner)
        banner_layout.addWidget(QLabel("Loading project"))
        layout.addWidget(banner)

    def reject(self):
        pass

    def closeEvent(self, event):
        event.ignore()


class _AlignmentJob(QThread):
    def __init__(self, proj_data, parent=None):
        super().__init__(parent)
        self.proj_data = proj_data
        self.aligned = False
        self.correlation = None
        self.error = None
        self.cancelled = False

    def run(self):
        try:
            self.aligned = bool(auto_align_images(self.proj_data, 0))
            if self.aligned:
                self.correlation = calculate_pair_correlation(
                    self.proj_data, 0
                )
        except Exception as error:
            self.error = error


class _VideoExportJob(QThread):
    def __init__(self, video_generator, total_frames, parent=None):
        super().__init__(parent)
        self.video_generator = video_generator
        self.total_frames = total_frames
        self._cancel_event = Event()
        self.pending_frames = deque()
        self.error_message = ""
        self.cancelled = False
        self.generated_frames = 0

    def interrupt(self):
        self._cancel_event.set()

    def run(self):
        try:
            if not self.video_generator.open_video_writer():
                raise RuntimeError("Failed to open video writer")
            for position in range(self.total_frames):
                if self._cancel_event.is_set():
                    self.cancelled = True
                    break
                frame = self.video_generator.generate_video_frame_on_position(
                    position
                )
                if frame is None:
                    raise RuntimeError(
                        f"Unable to generate video frame {position + 1}"
                    )
                self.video_generator.save_video_frame(frame)
                self.generated_frames += 1
                self.pending_frames.append((frame, position))
        except Exception as error:
            self.error_message = str(error)
        finally:
            self.video_generator.close_video_writer()


CFG_DEFAULTS = {
    "frame_crosshair": True,
    "marker_thickness": 2,
    "auto_alpha_range": True,
    "correlation_threshold": 0.2,
    "auto_open_last_project": False,
    "last_project": "",
}


class MainApp(QMainWindow):
    def __init__(
        self,
        proj_data=None,
        autosave_path=None,
        cfg_data=None,
        cfg_path=None,
        recovery_path=None,
    ):
        super().__init__()
        self.proj_data = (
            proj_data
            if proj_data is not None
            else {"video_data": {}, "images_data": []}
        )
        self.proj_video_settings = self.proj_data.setdefault("video_data", {})
        self.proj_data.setdefault("images_data", [])
        self.proj_filename = (
            str(autosave_path)
            if autosave_path and Path(autosave_path).suffix.lower() == ".zmr"
            else None
        )
        self.cfg_path = Path(cfg_path or Path.cwd() / CFG_FILENAME)
        self.recovery_path = Path(
            recovery_path or self.cfg_path.parent / AUTOSAVE_FILENAME
        )
        self.cfg_data = {**CFG_DEFAULTS, **(cfg_data or {})}
        self.cfg_data["marker_thickness"] = max(
            1, min(10, int(self.cfg_data.get("marker_thickness", 2)))
        )
        self._project_modified = False
        self.export_filename = ""
        self.proj_image_entries = []
        self._alignment_job = None
        self._alignment_jobs = set()
        self._video_export_job = None
        self._video_generator = None
        self._fusion_view_pair_index = None
        self._video_preview_timer = QTimer(self)
        self._video_preview_timer.setSingleShot(True)
        self._video_preview_timer.setInterval(200)
        self._video_preview_timer.timeout.connect(self._refresh_video_preview)
        self._video_export_timer = QTimer(self)
        self._video_export_timer.timeout.connect(self._drain_export_frames)
        self._undo_stack = deque(maxlen=HISTORY_LIMIT)
        self._redo_stack = deque(maxlen=HISTORY_LIMIT)
        # Drags emit many edits; one burst becomes a single history entry.
        self._edit_burst_timer = QTimer(self)
        self._edit_burst_timer.setSingleShot(True)
        self._edit_burst_timer.setInterval(600)
        self.setWindowTitle(f"Zoomer {__version__}")
        self._create_menus()
        self._update_window_title()
        self._save_cfg()
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (
            event.type() in PREVIEW_INTERACTION_EVENTS
            and isinstance(watched, QWidget)
            and self._video_export_job is None
            and hasattr(self, "image_files_and_preview_area")
        ):
            area = self.image_files_and_preview_area
            organizer = area.image_files_organizer
            editor = getattr(self, "image_fusion_editor", None)
            if watched is organizer or organizer.isAncestorOf(watched):
                area.preview_area.tabs.setCurrentWidget(
                    area.preview_area.input_image_label
                )
            elif editor is not None and (
                watched is editor or editor.isAncestorOf(watched)
            ):
                area.preview_area.tabs.setCurrentWidget(
                    area.preview_area.fusion_image_label
                )
        return super().eventFilter(watched, event)

    def _create_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        self.file_menu_action = file_menu.menuAction()
        open_action = file_menu.addAction("Open project")
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_project)
        save_action = file_menu.addAction("Save project")
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_project)
        save_as_action = file_menu.addAction("Save project as")
        save_as_action.triggered.connect(self.save_as)
        new_action = file_menu.addAction("New project")
        new_action.triggered.connect(self.new_project)

        edit_menu = self.menuBar().addMenu("&Edit")
        self.edit_menu_action = edit_menu.menuAction()
        undo_action = edit_menu.addAction("Undo")
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.triggered.connect(self.undo)
        redo_action = edit_menu.addAction("Redo")
        redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        redo_action.triggered.connect(self.redo)

        video_action = self.menuBar().addAction("&Video")
        video_action.triggered.connect(self.open_video_settings)
        self.video_menu_action = video_action

        export_action = self.menuBar().addAction("&Export")
        export_action.triggered.connect(self.select_export_filename)
        self.export_menu_action = export_action

        options_menu = self.menuBar().addMenu("&Options")
        self.cfg_frame_crosshair_action = options_menu.addAction(
            "Frame crosshair"
        )
        self.cfg_frame_crosshair_action.setCheckable(True)
        self.cfg_frame_crosshair_action.setChecked(
            bool(self.cfg_data["frame_crosshair"])
        )
        self.cfg_frame_crosshair_action.toggled.connect(
            self._set_frame_crosshair_enabled
        )
        marker_thickness_action = QWidgetAction(self)
        self.cfg_marker_thickness_spin = QSpinBox(options_menu)
        self.cfg_marker_thickness_spin.setRange(1, 10)
        self.cfg_marker_thickness_spin.setPrefix("Marker thickness: ")
        self.cfg_marker_thickness_spin.setToolTip(
            "Pixel thickness of the colored alignment cross and its outline"
        )
        self.cfg_marker_thickness_spin.setValue(
            int(self.cfg_data.get("marker_thickness", 2))
        )
        marker_thickness_action.setDefaultWidget(
            self.cfg_marker_thickness_spin
        )
        options_menu.addAction(marker_thickness_action)
        correlation_threshold_action = QWidgetAction(self)
        self.cfg_correlation_threshold_spin = QDoubleSpinBox(options_menu)
        self.cfg_correlation_threshold_spin.setRange(0.0, 1.0)
        self.cfg_correlation_threshold_spin.setSingleStep(0.05)
        self.cfg_correlation_threshold_spin.setDecimals(2)
        self.cfg_correlation_threshold_spin.setPrefix(
            "Correlation threshold: "
        )
        self.cfg_correlation_threshold_spin.setToolTip(
            "Correlation threshold for the auto alignment"
        )
        self.cfg_correlation_threshold_spin.setValue(
            max(0.0, min(1.0, float(self.cfg_data["correlation_threshold"])))
        )
        correlation_threshold_action.setDefaultWidget(
            self.cfg_correlation_threshold_spin
        )
        options_menu.addAction(correlation_threshold_action)
        self.cfg_correlation_threshold_spin.valueChanged.connect(
            self._set_correlation_threshold
        )
        self.cfg_marker_thickness_spin.valueChanged.connect(
            self._set_marker_thickness
        )
        self.cfg_auto_alpha_range_action = options_menu.addAction(
            "Auto alpha range"
        )
        self.cfg_auto_alpha_range_action.setCheckable(True)
        self.cfg_auto_alpha_range_action.setChecked(
            bool(self.cfg_data["auto_alpha_range"])
        )
        self.cfg_auto_alpha_range_action.toggled.connect(
            self._set_auto_alpha_range
        )
        self.cfg_auto_open_last_project_action = options_menu.addAction(
            "Auto open last project"
        )
        self.cfg_auto_open_last_project_action.setCheckable(True)
        self.cfg_auto_open_last_project_action.setChecked(
            bool(self.cfg_data["auto_open_last_project"])
        )
        self.cfg_auto_open_last_project_action.toggled.connect(
            self._set_auto_open_last_project
        )
        options_menu.setToolTipsVisible(True)
        self.cfg_frame_crosshair_action.setToolTip(
            "Show a crosshair at the center of the frame in the image "
            "editor. Drag it to move the frame."
        )
        self.cfg_auto_alpha_range_action.setToolTip(
            "Automatically set each pair's alpha range to the largest "
            "contiguous range where both images fill the video frame "
            "(full range if there is none)."
        )
        self.cfg_auto_open_last_project_action.setToolTip(
            "Reopen the last project automatically when the application "
            "starts."
        )

    def _save_cfg(self):
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cfg_path.with_name(self.cfg_path.name + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as config_file:
            json.dump(self.cfg_data, config_file, indent=2)
        temporary_path.replace(self.cfg_path)

    def _set_auto_open_last_project(self, enabled):
        self.cfg_data["auto_open_last_project"] = bool(enabled)
        self._save_cfg()

    def _remember_project(self, filename):
        self.cfg_data["last_project"] = str(Path(filename).resolve())
        self._save_cfg()
        self._update_window_title()

    def _update_window_title(self):
        project_name = self.proj_data.get("project_name", "")
        if not project_name and self.proj_filename:
            project_name = Path(self.proj_filename).stem
        if self._project_modified:
            project_name = f"{project_name or 'No project'} *"
        self.setWindowTitle(
            f"Zoomer {__version__} - {project_name}"
            if project_name
            else f"Zoomer {__version__} - No project"
        )

    def _set_project_modified(self, modified):
        modified = bool(modified)
        if modified == self._project_modified:
            return
        self._project_modified = modified
        self._update_window_title()

    def open_project(self, _checked=False):
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open project",
            self.proj_filename or str(Path.home()),
            "Zoomer projects (*.zmr);;All files (*)",
        )
        if not filename:
            return
        if self._is_recovery_path(filename):
            QMessageBox.warning(
                self,
                "Open project",
                "autosave.zmr is a recovery file, not a named project. "
                "Choose Recover autosave at startup to restore it.",
            )
            return
        try:
            proj_loaded = self._load_project_with_progress(filename)
        except Exception as error:
            print(error)
            QMessageBox.warning(
                self, "Open project", f"Unable to open {filename}:\n{error}"
            )
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
        self._set_project_modified(False)
        if self._normalize_boundary_points():
            self.save_autosave(mark_modified=False)

    def _load_project_with_progress(self, filename):
        dialog = _ProjectLoadingDialog(self)
        job = _ProjectLoadJob(filename, dialog)
        job.finished.connect(dialog.accept)
        dialog.spinner.start()
        job.start()
        try:
            dialog.exec()
        finally:
            job.wait()
            dialog.spinner.stop()
        if job.error is not None:
            raise job.error
        return job.project

    def save_project(self, _checked=False):
        if not self.proj_filename:
            return self.save_as()
        save_project(self.proj_filename, self.proj_data)
        self.save_autosave(mark_modified=False)
        self._remember_project(self.proj_filename)
        self._set_project_modified(False)
        return True

    def _is_recovery_path(self, filename):
        return Path(filename).resolve() == self.recovery_path.resolve()

    def save_as(self, _checked=False):
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save project as",
            self.proj_filename or str(Path.home()),
            "Zoomer projects (*.zmr)",
        )
        if not filename:
            return False
        named_path = Path(filename).with_suffix(".zmr")
        if self._is_recovery_path(named_path):
            QMessageBox.warning(
                self,
                "Save project as",
                "The autosave file is reserved for crash recovery.",
            )
            return False
        self.proj_filename = str(named_path)
        self.proj_data["project_name"] = Path(self.proj_filename).stem
        save_project(self.proj_filename, self.proj_data)
        self._remember_project(self.proj_filename)
        self.save_autosave(mark_modified=False)
        self._set_project_modified(False)
        return True

    def new_project(self, _checked=False):
        dialog = NewProjectDialog({}, self)
        if not dialog.exec():
            return
        project_name = dialog.project_name()
        if (
            not project_name
            or Path(project_name).name != project_name
            or "\\" in project_name
        ):
            QMessageBox.warning(
                self,
                "New project",
                "Enter a project name without path separators.",
            )
            return
        suggested_path = str(Path.home() / f"{project_name}.zmr")
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Create project",
            suggested_path,
            "Zoomer projects (*.zmr)",
        )
        if not filename:
            return
        named_path = Path(filename).with_suffix(".zmr")
        if self._is_recovery_path(named_path):
            QMessageBox.warning(
                self,
                "New project",
                "The autosave file is reserved for crash recovery.",
            )
            return
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._edit_burst_timer.stop()
        self.proj_filename = str(named_path)
        self.proj_directory = Path(self.proj_filename).resolve().parent
        self.proj_data.clear()
        self.proj_data.update(
            {
                "project_name": project_name,
                "video_data": dialog.settings(),
                "images_data": [],
            }
        )
        self.proj_video_settings = self.proj_data["video_data"]
        self.proj_image_entries = self.proj_data["images_data"]
        self._apply_restored_config(dict(self.proj_data))
        save_project(self.proj_filename, self.proj_data)
        self._remember_project(self.proj_filename)
        self.save_autosave(mark_modified=False)
        self._set_project_modified(False)

    def open_video_settings(self, _checked=False):
        dialog = VideoSettingsDialog(self.proj_video_settings, self)
        if dialog.exec():
            self._record_history()
            self.proj_video_settings = dialog.settings()
            self.proj_data["video_data"] = self.proj_video_settings
            self.save_autosave()

    def select_export_filename(self, _checked=False):
        if self._video_export_job is not None:
            return
        selected_format = self.proj_video_settings.get("format", "avi")
        format_info = next(
            (
                supported_format
                for supported_format in get_supported_video_formats()
                if supported_format[0] == selected_format
            ),
            None,
        )
        if format_info is None:
            QMessageBox.warning(
                self,
                "Export video",
                "Selected video format is unsupported by this OpenCV build.",
            )
            return
        extension, format_label, _fourcc = format_info
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export video",
            f"output.{extension}",
            f"{format_label};;All files (*)",
        )
        if filename:
            export_path = Path(filename)
            if export_path.suffix.lower() != f".{extension}":
                export_path = export_path.with_suffix(f".{extension}")
            self.export_filename = str(export_path)
            self._start_video_export()

    def _start_video_export(self):
        if len(self.proj_image_entries) < 2:
            QMessageBox.warning(
                self,
                "Export video",
                "Add at least two images before exporting.",
            )
            return
        if self._video_generator is None:
            self._refresh_video_preview()
        generator = self._video_generator
        if generator is None:
            QMessageBox.warning(
                self, "Export video", "The video preview is not ready."
            )
            return

        generator.set_video_filename(self.export_filename)
        success, error_message = generator.perform_video_calculations()
        if not success:
            QMessageBox.warning(
                self,
                "Export video",
                error_message or "Unable to calculate video frames.",
            )
            return

        total_frames = generator.get_total_frames()
        self._video_preview_timer.stop()
        preview_area = self.image_files_and_preview_area.preview_area
        preview_area.tabs.setCurrentWidget(preview_area.video_preview)
        preview_area.video_preview.set_exporting(True)
        self._set_export_locked(True)

        job = _VideoExportJob(generator, total_frames, self)
        job.finished.connect(self._video_export_finished)
        self._video_export_job = job
        self._video_export_timer.start(16)
        job.start()

    def _drain_export_frames(self):
        job = self._video_export_job
        if job is None:
            self._video_export_timer.stop()
            return
        preview = self.image_files_and_preview_area.preview_area.video_preview
        while job.pending_frames:
            frame, position = job.pending_frames.popleft()
            preview.set_export_progress(frame, position, job.total_frames)

    def _interrupt_video_export(self):
        if self._video_export_job is None:
            return
        self._video_export_job.interrupt()
        self.image_files_and_preview_area.preview_area.video_preview.set_export_stopping()

    def _video_export_finished(self):
        job = self._video_export_job
        if job is None:
            return
        self._drain_export_frames()
        self._video_export_timer.stop()
        self._video_export_job = None
        preview = self.image_files_and_preview_area.preview_area.video_preview
        preview.set_exporting(False)
        preview.finish_export()
        self._set_export_locked(False)
        if job is not None:
            job.deleteLater()

        if job.error_message:
            print(job.error_message)
            QMessageBox.warning(self, "Export video", job.error_message)
        elif job.cancelled:
            preview.position_label.setText(
                f"Export interrupted at frame {job.generated_frames}"
            )
        else:
            QMessageBox.information(
                self,
                "Export video",
                f"Video exported to {self.export_filename}",
            )

    def _set_export_locked(self, locked):
        for action in (
            self.file_menu_action,
            self.edit_menu_action,
            self.video_menu_action,
            self.export_menu_action,
        ):
            action.setEnabled(not locked)
        self.image_files_and_preview_area.image_files_organizer.setEnabled(
            not locked
        )
        self.image_fusion_edition_area.setEnabled(not locked)

    def closeEvent(self, event):
        if self._video_export_job is not None:
            self._video_export_job.interrupt()
            self._video_export_job.wait()
        if self._project_modified:
            choice = QMessageBox.question(
                self,
                "Unsaved project changes",
                "Save changes to the named project before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if choice == QMessageBox.StandardButton.Save:
                if not self.save_project():
                    event.ignore()
                    return
            elif choice == QMessageBox.StandardButton.Discard:
                self.recovery_path.unlink(missing_ok=True)
                self._set_project_modified(False)
        super().closeEvent(event)

    def set_image_workspace(self, proj_image_entries, proj_directory):
        self.proj_image_entries = self.proj_data["images_data"]
        self.proj_directory = Path(proj_directory)
        if self._normalize_boundary_points():
            self.save_autosave()
        self.image_files_and_preview_area = ImageFilesAndPreviewArea(self)
        organizer = self.image_files_and_preview_area.image_files_organizer
        organizer.selected_image_changed.connect(self._select_pair_from_path)
        organizer.image_files_changed.connect(self._organizer_files_changed)
        self.workspace_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.workspace_splitter.addWidget(self.image_files_and_preview_area)
        self.image_fusion_edition_area = ImageFusionEditionArea(self)
        self.image_fusion_editor = self.image_fusion_edition_area.editor
        self.image_fusion_editor.set_frame_crosshair_enabled(
            self.cfg_frame_crosshair_action.isChecked()
        )
        self.image_fusion_editor.set_marker_thickness(
            self.cfg_marker_thickness_spin.value()
        )
        self.image_fusion_editor.set_auto_alpha_range(
            self.cfg_auto_alpha_range_action.isChecked()
        )
        self.image_fusion_editor.auto_alpha_range_toggled.connect(
            self.cfg_auto_alpha_range_action.setChecked
        )
        self.image_fusion_editor.pair_requested.connect(self._navigate_pair)
        self.image_fusion_editor.image_edited.connect(self._image_edited)
        self.image_fusion_editor.fusion_preview_requested.connect(
            self._update_fusion_preview
        )
        self.image_fusion_editor.alpha_range_edited.connect(
            self._alpha_range_edited
        )
        self.image_fusion_editor.alpha_range_auto_set.connect(
            self._alpha_range_auto_set
        )
        self.image_fusion_editor.alignment_points_requested.connect(
            self._run_auto_alignment
        )
        self.image_fusion_editor.alignment_interrupted.connect(
            self._interrupt_alignment
        )
        self.image_files_and_preview_area.preview_area.video_preview.export_interrupted.connect(
            self._interrupt_video_export
        )
        self._fusion_preview_timer = QTimer(self)
        self._fusion_preview_timer.setSingleShot(True)
        self._fusion_preview_timer.setInterval(75)
        self._fusion_preview_timer.timeout.connect(self._refresh_fusion_editor)
        self.workspace_splitter.addWidget(self.image_fusion_edition_area)
        self.setCentralWidget(self.workspace_splitter)
        paths = [self._path_for_entry(entry) for entry in proj_image_entries]
        organizer.set_image_files(paths)
        self._show_pair(max(0, organizer.image_list.currentRow()))
        self._schedule_video_preview()
        self._set_project_modified(False)

    def _schedule_video_preview(self):
        self._video_preview_timer.start()

    def _refresh_video_preview(self):
        if not hasattr(self, "image_files_and_preview_area"):
            return
        preview_area = self.image_files_and_preview_area.preview_area
        if len(self.proj_image_entries) < 2:
            preview_area.set_video_error(
                "Add at least two images to preview the video"
            )
            return
        try:
            if (
                self._video_generator is None
                or self._video_generator.proj_data is not self.proj_data
            ):
                self._video_generator = VideoGenerator(self.proj_data, "")
            success, error = self._video_generator.perform_video_calculations()
        except Exception as exception:
            print(exception)
            success, error = False, str(exception)
        if not success:
            preview_area.set_video_error(
                error or "Unable to calculate the video"
            )
            return
        preview_area.set_video(
            self._video_generator.get_total_frames(),
            self.proj_video_settings.get("FPS", 30),
            self._video_generator.generate_video_frame_on_position,
            self._video_generator.get_zoom_on_position,
        )

    def _set_frame_crosshair_enabled(self, enabled):
        self.cfg_data["frame_crosshair"] = bool(enabled)
        self._save_cfg()
        if hasattr(self, "image_fusion_editor"):
            self.image_fusion_editor.set_frame_crosshair_enabled(enabled)

    def _set_auto_alpha_range(self, enabled):
        self.cfg_data["auto_alpha_range"] = bool(enabled)
        self._save_cfg()
        if hasattr(self, "image_fusion_editor"):
            self.image_fusion_editor.set_auto_alpha_range(enabled)
            self._update_recommended_alpha_range()

    def _set_correlation_threshold(self, threshold):
        self.cfg_data["correlation_threshold"] = float(threshold)
        self._save_cfg()

    def _set_marker_thickness(self, thickness):
        thickness = max(1, min(10, int(thickness)))
        self.cfg_data["marker_thickness"] = thickness
        self._save_cfg()
        if hasattr(self, "image_fusion_editor"):
            self.image_fusion_editor.set_marker_thickness(thickness)

    def _run_auto_alignment(self, index):
        if (
            self._alignment_job is not None
            or not 0 <= index < len(self.proj_image_entries) - 1
        ):
            return
        entries = (
            self.proj_image_entries[index],
            self.proj_image_entries[index + 1],
        )
        # The worker edits private copies so the live project changes
        # only on success.
        job = _AlignmentJob(
            {
                "video_data": self.proj_video_settings,
                "images_data": [dict(entry) for entry in entries],
            },
            self,
        )
        job.index = index
        job.entries = entries
        job.finished.connect(lambda: self._alignment_finished(job))
        self._alignment_job = job
        self._alignment_jobs.add(job)
        self.image_fusion_editor.set_alignment_running(True)
        job.start()

    def _interrupt_alignment(self):
        # SIFT cannot be stopped mid-call; the thread finishes in the
        # background and its result is dropped.
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
        current = self.proj_image_entries[index : index + 2]
        still_valid = len(current) == 2 and all(
            a is b for a, b in zip(current, job.entries)
        )
        if job.error is not None:
            print(job.error)
        if not job.aligned:
            QMessageBox.warning(
                self,
                "Find alignment points",
                "Unable to find alignment points.",
            )
        elif (
            job.correlation is not None
            and job.correlation < self.cfg_correlation_threshold_spin.value()
        ):
            QMessageBox.warning(
                self,
                "Find alignment points",
                "It seems the auto alignment didn't work.\n"
                f"The images correlation is too low ({job.correlation:.2f}).\n"
                "\nSuggestions:\n"
                "- Temporarily resize both frames to about the same area "
                "and try again.\n"
                "- Reduce the Correlation threshold in the Options menu.\n"
                "- Perform the alignment manually by dragging the crosses "
                "in the images.",
            )
        elif still_valid:
            self._edit_burst_timer.stop()
            self._record_history()
            results = job.proj_data["images_data"]
            for offset, field in ((0, "next_points"), (1, "prev_points")):
                points = results[offset][field]
                self.proj_image_entries[index + offset][field] = [
                    [float(x), float(y)] for x, y in points
                ]
            self._normalize_boundary_points()
            self.save_autosave()
            self._show_pair(index)
        job.deleteLater()

    @staticmethod
    def _image_path(image_entry):
        image_object = image_entry["image"]
        if isinstance(image_object, ImageClass):
            return Path(image_object.get_image_path())
        return Path(image_object)

    def _path_for_entry(self, image_entry):
        path = self._image_path(image_entry)
        return path if path.is_absolute() else self.proj_directory / path

    def _organizer_files_changed(self, filenames):
        entries_by_path = {
            self._path_for_entry(entry).resolve(): entry
            for entry in self.proj_image_entries
        }
        remaining_paths = {Path(filename).resolve() for filename in filenames}
        removed = any(path not in remaining_paths for path in entries_by_path)
        updated_entries = []
        for filename in filenames:
            path = Path(filename).resolve()
            entry = entries_by_path.get(path)
            if entry is None:
                entry = self._new_image_entry(path)
            updated_entries.append(entry)
        unchanged = len(updated_entries) == len(
            self.proj_image_entries
        ) and all(
            new is old
            for new, old in zip(updated_entries, self.proj_image_entries)
        )
        if not unchanged:
            self._record_history()
        self.proj_image_entries = updated_entries
        self.proj_data["images_data"] = updated_entries
        self._normalize_boundary_points()
        if removed:
            message = (
                "Updating video preview"
                if len(updated_entries) >= 2
                else "Add at least two images to preview the video"
            )
            self.image_files_and_preview_area.preview_area.set_video_error(
                message
            )
        self.save_autosave(mark_modified=not unchanged)
        organizer = self.image_files_and_preview_area.image_files_organizer
        current_row = organizer.image_list.currentRow()
        self._show_pair(max(0, current_row))

    def _snapshot(self):
        snapshot = {
            key: copy.deepcopy(value)
            for key, value in self.proj_data.items()
            if key != "images_data"
        }
        snapshot["images_data"] = []
        for entry in self.proj_image_entries:
            saved = {
                key: copy.deepcopy(value)
                for key, value in entry.items()
                if key != "image"
            }
            saved["image"] = str(self._image_path(entry))
            snapshot["images_data"].append(saved)
        return snapshot

    def _record_history(self, coalesce=False):
        self._set_project_modified(True)
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
        current_images = {
            str(self._image_path(entry)): entry["image"]
            for entry in self.proj_image_entries
        }
        try:
            proj_restored = self._restore_snapshot(source[-1], current_images)
        except ValueError as error:
            print(error)
            return
        target.append(self._snapshot())
        source.pop()
        self._edit_burst_timer.stop()
        self._apply_restored_config(proj_restored)
        self._set_project_modified(True)

    @staticmethod
    def _restore_snapshot(snapshot, current_images):
        proj_restored = {
            key: copy.deepcopy(value)
            for key, value in snapshot.items()
            if key != "images_data"
        }
        proj_restored["images_data"] = []
        for saved in snapshot["images_data"]:
            entry = copy.deepcopy(saved)
            path = entry["image"]
            image = current_images.get(path)
            entry["image"] = image if image is not None else ImageClass(path)
            proj_restored["images_data"].append(entry)
        return proj_restored

    def _apply_restored_config(self, proj_restored):
        organizer = self.image_files_and_preview_area.image_files_organizer
        row = organizer.image_list.currentRow()
        self.proj_data.clear()
        self.proj_data.update(proj_restored)
        self.proj_video_settings = self.proj_data.setdefault("video_data", {})
        self.proj_image_entries = self.proj_data["images_data"]
        organizer.blockSignals(True)
        organizer.set_image_files(
            [self._path_for_entry(entry) for entry in self.proj_image_entries]
        )
        organizer.image_list.setCurrentRow(
            min(max(row, 0), organizer.image_list.count() - 1)
        )
        organizer.blockSignals(False)
        self.save_autosave(mark_modified=False)
        self._show_pair(max(0, organizer.image_list.currentRow()))
        self._set_project_modified(False)

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
        image_object = ImageClass(str(image_path))
        image = image_object.get_cv_image()
        if image is None:
            raise ValueError(f"Unable to load image: {image_path}")
        video_width, video_height = self.proj_video_settings.get(
            "size", (960, 540)
        )
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
            "prev_points": self._initial_alignment_triangle(
                frame_x, frame_y, frame_width, frame_height
            ),
            "next_points": self._initial_alignment_triangle(
                frame_x, frame_y, frame_width, frame_height
            ),
        }

    @staticmethod
    def _initial_alignment_triangle(
        frame_x, frame_y, frame_width, frame_height
    ):
        margin = 0.1 * min(frame_width, frame_height)
        left = frame_x + margin
        right = frame_x + frame_width - margin
        top = frame_y + margin
        bottom = frame_y + frame_height - margin
        return [
            [(left + right) / 2, top],
            [left, bottom],
            [right, bottom],
        ]

    def save_autosave(self, mark_modified=True):
        self._schedule_video_preview()
        self.recovery_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.recovery_path.with_name(
            self.recovery_path.name + ".tmp"
        )
        save_project(str(temporary_path), self.proj_data)
        temporary_path.replace(self.recovery_path)
        if mark_modified:
            self._set_project_modified(True)

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
            selected_index = min(
                max(0, organizer.image_list.currentRow()), len(paths) - 1
            )
            self.image_files_and_preview_area.preview_area.set_image(
                self.proj_image_entries[selected_index]["image"]
            )
        else:
            self.image_files_and_preview_area.preview_area.set_image("")
        organizer.set_highlighted_paths(
            paths[pair_index : pair_index + 2] if len(paths) > 1 else []
        )
        self.image_fusion_editor.set_pair(
            self.proj_image_entries, paths, pair_index
        )
        if len(paths) < 2:
            self.image_files_and_preview_area.preview_area.set_fusion_frame(
                None
            )
        self._update_recommended_alpha_range()

    def _update_recommended_alpha_range(self):
        editor = self.image_fusion_editor
        pair_index = editor.pair_index
        if not 0 <= pair_index < len(self.proj_image_entries) - 1:
            editor.set_recommended_alpha_range(None)
            return
        try:
            _, mask = get_pair_blend_alpha_range(self.proj_data, pair_index)
        except Exception as error:
            print(error)
            mask = None
        editor.set_recommended_alpha_range(mask)

    def _refresh_fusion_editor(self):
        self._update_recommended_alpha_range()
        self.image_fusion_editor.refresh_fusion_preview()

    def _navigate_pair(self, pair_index):
        organizer = self.image_files_and_preview_area.image_files_organizer
        if organizer.image_list.currentRow() == pair_index:
            self._show_pair(pair_index)
        else:
            organizer.image_list.setCurrentRow(pair_index)

    def _update_fusion_preview(self, pair_index, size_alpha, blend_alpha):
        if not 0 <= pair_index < len(self.proj_image_entries) - 1:
            self.image_files_and_preview_area.preview_area.set_fusion_frame(
                None
            )
            return
        try:
            frame = create_blended_frame(
                self.proj_data,
                pair_index,
                size_alpha,
                blend_alpha,
            )
        except Exception as error:
            print(error)
            self.image_files_and_preview_area.preview_area.set_fusion_error(
                "Invalid fusion parameters"
            )
            return
        keep_view = pair_index == self._fusion_view_pair_index
        self._fusion_view_pair_index = pair_index
        self.image_files_and_preview_area.preview_area.set_fusion_frame(
            frame, keep_view=keep_view
        )

    def _alpha_range_auto_set(self, pair_index, alpha_range):
        # Derived value: it is kept in memory only, so it neither enters the
        # undo history, rewrites the autosave nor marks the project modified.
        # The next real edit or save persists it.
        if not 0 <= pair_index < len(self.proj_image_entries):
            return
        self.proj_image_entries[pair_index]["alpha_range"] = list(alpha_range)
        self._schedule_video_preview()

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
        if (
            field == "next_points"
            and image_index == len(self.proj_image_entries) - 1
        ):
            return
        self._record_history(coalesce=True)
        entry = self.proj_image_entries[image_index]
        if field == "frame":
            upper_left = value["upper_left"]
            entry["frame"] = [
                [upper_left[0], upper_left[1]],
                [
                    upper_left[0] + value["width"],
                    upper_left[1] + value["height"],
                ],
            ]
        else:
            entry[field] = [[point[0], point[1]] for point in value]
        self.save_autosave()
        self._fusion_preview_timer.start()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="zoomer", description="Create zoom videos from image pairs."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.cwd() / CFG_FILENAME,
        help=f"application config file (default: ./{CFG_FILENAME})",
    )
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    cfg_path = args.config.resolve()
    try:
        with cfg_path.open("r", encoding="utf-8") as cfg_file:
            cfg_data = {**CFG_DEFAULTS, **json.load(cfg_file)}
    except (OSError, json.JSONDecodeError):
        cfg_data = dict(CFG_DEFAULTS)
    window = MainApp(cfg_data=cfg_data, cfg_path=cfg_path)
    window.resize(1000, 700)
    window.show()
    recovery_path = window.recovery_path
    cfg_last_project = cfg_data.get("last_project", "")
    last_project_path = Path(cfg_last_project) if cfg_last_project else None
    recovery_matches_saved_project = False
    if (
        recovery_path.is_file()
        and last_project_path is not None
        and last_project_path.is_file()
    ):
        try:
            with recovery_path.open("r", encoding="utf-8") as recovery_file:
                recovery_json = json.load(recovery_file)
            with last_project_path.open("r", encoding="utf-8") as project_file:
                project_json = json.load(project_file)
            recovery_matches_saved_project = recovery_json == project_json
        except (OSError, json.JSONDecodeError):
            recovery_matches_saved_project = False
    if recovery_matches_saved_project:
        recovery_path.unlink(missing_ok=True)
    if recovery_path.is_file():
        recover = QMessageBox.question(
            window,
            "Recover autosave",
            "An autosaved project was found. Recover it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if recover == QMessageBox.StandardButton.Yes:
            try:
                window.set_image_workspace([], cfg_path.parent)
                recovered_data = window._load_project_with_progress(
                    str(recovery_path)
                )
                recovered_data.setdefault("project_name", recovery_path.stem)
                window.proj_filename = None
                window.proj_directory = recovery_path.parent
                window._apply_restored_config(recovered_data)
                window._set_project_modified(True)
                window._update_window_title()
                return app.exec()
            except (
                OSError,
                ValueError,
                KeyError,
                json.JSONDecodeError,
            ) as error:
                QMessageBox.warning(
                    window,
                    "Recover autosave",
                    f"Unable to recover {recovery_path}:\n{error}",
                )
        else:
            recovery_path.unlink(missing_ok=True)
    window.set_image_workspace([], cfg_path.parent)
    if (
        cfg_data.get("auto_open_last_project")
        and cfg_last_project
        and Path(cfg_last_project).is_file()
    ):
        window.proj_filename = cfg_last_project
        try:
            proj_loaded = window._load_project_with_progress(cfg_last_project)
            proj_loaded.setdefault("project_name", Path(cfg_last_project).stem)
            window.proj_directory = Path(cfg_last_project).resolve().parent
            window._apply_restored_config(proj_loaded)
            if window._normalize_boundary_points():
                window.save_autosave()
            window._remember_project(cfg_last_project)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            QMessageBox.warning(
                window,
                "Open project",
                f"Unable to open {cfg_last_project}:\n{error}",
            )
            QTimer.singleShot(0, window.new_project)
    else:
        QTimer.singleShot(0, window.new_project)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
