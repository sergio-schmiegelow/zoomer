import json
import time
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from PyQt6.QtCore import Qt, QThread, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from conftest import triangle
from zoomer import gui, widgets
from zoomer.backend import (
    ImageClass,
    get_supported_video_formats,
    load_project,
    save_project,
)
from zoomer.widgets import NewProjectDialog


@pytest.fixture
def window(qapp, tmp_path, proj_data, no_dialogs):
    project_path = tmp_path / "demo.zmr"
    save_project(str(project_path), proj_data)
    main = gui.MainApp(proj_data, project_path, {}, tmp_path / "zoomer.cfg")
    main.set_image_workspace(proj_data["images_data"], tmp_path)
    main.show()
    yield main
    main.close()


def stub_dialogs(monkeypatch, tmp_path, name="Fresh"):
    monkeypatch.setattr(NewProjectDialog, "exec", lambda self: 1)
    monkeypatch.setattr(NewProjectDialog, "project_name", lambda self: name)
    monkeypatch.setattr(
        NewProjectDialog,
        "settings",
        lambda self: {
            "format": get_supported_video_formats()[0][0],
            "size": [640, 360],
            "FPS": 30,
            "duration": 3,
            "interpolation_method": "log",
        },
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / name), "")),
    )


class TestProjects:
    def test_project_is_clean_until_edited_then_title_marks_dirty(
        self, window
    ):
        assert not window._project_modified
        window._image_edited(
            0, "frame", {"upper_left": (2, 3), "width": 50, "height": 25}
        )
        assert window._project_modified
        assert window.windowTitle().endswith(" *")

    def test_new_project_creates_zmr_and_updates_title(
        self, window, tmp_path, monkeypatch
    ):
        stub_dialogs(monkeypatch, tmp_path)
        window.new_project()
        saved = json.loads((tmp_path / "Fresh.zmr").read_text())
        recovered = json.loads((tmp_path / gui.AUTOSAVE_FILENAME).read_text())
        assert saved["project_name"] == "Fresh"
        assert recovered["project_name"] == "Fresh"
        assert saved["video_data"]["size"] == [640, 360]
        assert saved["images_data"] == []
        assert window.windowTitle() == "Zoomer - Fresh"

    def test_new_project_rejects_path_separators(
        self, window, tmp_path, monkeypatch, no_dialogs
    ):
        stub_dialogs(monkeypatch, tmp_path, name="a/b")
        window.new_project()
        assert no_dialogs
        assert not (tmp_path / "a").exists()

    def test_open_project_loads_images_and_remembers_it(
        self, window, tmp_path, proj_file, monkeypatch
    ):
        other = tmp_path / "other.zmr"
        other.write_text(proj_file.read_text())
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **k: (str(other), "")),
        )
        window.open_project()
        assert window.proj_filename == str(other)
        assert len(window.proj_image_entries) == 3
        cfg = json.loads((tmp_path / "zoomer.cfg").read_text())
        assert cfg["last_project"] == str(other.resolve())

    def test_loading_banner_animates_until_project_is_loaded(
        self, window, tmp_path, proj_file, monkeypatch
    ):
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *args, **kwargs: (str(proj_file), "")),
        )
        finished_loading = Event()
        observed = {}

        def slow_load(filename):
            observed["worker_thread"] = (
                QThread.currentThread() != QApplication.instance().thread()
            )
            if not finished_loading.wait(3):
                raise TimeoutError("Loading was not released")
            return load_project(filename)

        def observe_banner():
            dialog = QApplication.activeModalWidget()
            observed["visible"] = dialog.isVisible()
            observed["label"] = dialog.findChild(gui.QLabel).text()
            observed["spinner_running"] = dialog.spinner._timer.isActive()
            observed["angle"] = dialog.spinner._angle
            dialog.reject()
            observed["reject_kept_visible"] = dialog.isVisible()
            finished_loading.set()

        monkeypatch.setattr(gui, "load_project", slow_load)
        QTimer.singleShot(180, observe_banner)
        window.open_project()
        assert observed == {
            "worker_thread": True,
            "visible": True,
            "label": "Loading project",
            "spinner_running": True,
            "angle": observed["angle"],
            "reject_kept_visible": True,
        }
        assert observed["angle"] != 0
        assert QApplication.activeModalWidget() is None
        assert window.proj_filename == str(proj_file)

    def test_loading_failure_closes_banner_and_keeps_project(
        self, window, monkeypatch, no_dialogs
    ):
        previous_data = window.proj_data.copy()
        previous_filename = window.proj_filename
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *args, **kwargs: ("missing.zmr", "")),
        )

        def fail_load(_filename):
            raise ValueError("load failed")

        monkeypatch.setattr(gui, "load_project", fail_load)
        window.open_project()
        assert QApplication.activeModalWidget() is None
        assert window.proj_data == previous_data
        assert window.proj_filename == previous_filename
        assert "load failed" in no_dialogs[-1][-1]

    def test_save_as_forces_zmr_suffix(self, window, tmp_path, monkeypatch):
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(tmp_path / "copy.json"), "")),
        )
        window.save_as()
        assert (tmp_path / "copy.zmr").exists()
        assert window.windowTitle() == "Zoomer - copy"

    def test_save_as_cannot_overwrite_recovery_file(
        self, window, tmp_path, monkeypatch, no_dialogs
    ):
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        recovery_path.write_text("recovery sentinel")
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(recovery_path), "")),
        )
        window.save_as()
        assert recovery_path.read_text() == "recovery sentinel"
        assert window.proj_filename == str(tmp_path / "demo.zmr")
        assert no_dialogs

    def test_edits_are_autosaved_without_overwriting_named_project(
        self, window, tmp_path
    ):
        named_path = tmp_path / "demo.zmr"
        original_named_data = load_project(str(named_path))
        window._image_edited(
            0, "frame", {"upper_left": (1, 2), "width": 100, "height": 50}
        )
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        recovered = load_project(str(recovery_path))
        named_after_edit = load_project(str(named_path))
        assert recovered["images_data"][0]["frame"] == [[1, 2], [101, 52]]
        assert (
            named_after_edit["images_data"][0]["frame"]
            == original_named_data["images_data"][0]["frame"]
        )

    def test_save_project_writes_named_file_and_keeps_recovery(
        self, window, tmp_path
    ):
        window._image_edited(
            0, "frame", {"upper_left": (3, 4), "width": 80, "height": 40}
        )
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        window.save_project()
        named = load_project(str(tmp_path / "demo.zmr"))
        recovered = load_project(str(recovery_path))
        expected_frame = [[3, 4], [83, 44]]
        assert named["images_data"][0]["frame"] == expected_frame
        assert recovered["images_data"][0]["frame"] == expected_frame

    def test_save_action_has_ctrl_s_shortcut(self, window):
        actions = window.file_menu_action.menu().actions()
        save_action = next(
            action for action in actions if action.text() == "Save project"
        )
        assert (
            save_action.shortcut().matches(gui.QKeySequence.StandardKey.Save)
            == gui.QKeySequence.SequenceMatch.ExactMatch
        )

    def test_save_without_named_project_prompts_for_a_name(
        self, window, tmp_path, monkeypatch
    ):
        window.proj_filename = None
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(
                lambda *args, **kwargs: (str(tmp_path / "recovered"), "")
            ),
        )
        window.save_project()
        assert window.proj_filename == str(tmp_path / "recovered.zmr")
        assert (tmp_path / "recovered.zmr").is_file()
        assert (tmp_path / gui.AUTOSAVE_FILENAME).is_file()


class TestCfgOptions:
    def test_toggles_are_persisted(self, window, tmp_path):
        window.cfg_auto_open_last_project_action.setChecked(True)
        window.cfg_frame_crosshair_action.setChecked(False)
        cfg = json.loads((tmp_path / "zoomer.cfg").read_text())
        assert cfg["auto_open_last_project"] is True
        assert cfg["frame_crosshair"] is False

    def test_crosshair_toggle_reaches_editors(self, window):
        window.cfg_frame_crosshair_action.setChecked(False)
        editor = window.image_fusion_editor
        assert editor.cfg_frame_crosshair_enabled is False
        assert all(
            editor.pair_splitter.widget(i).editor.cfg_frame_crosshair_enabled
            is False
            for i in range(2)
        )

    def test_marker_thickness_persists_and_updates_both_editors(
        self, window, tmp_path
    ):
        spin = window.cfg_marker_thickness_spin
        assert (spin.minimum(), spin.maximum(), spin.value()) == (1, 10, 2)
        spin.setValue(5)
        saved = json.loads((tmp_path / "zoomer.cfg").read_text())
        assert saved["marker_thickness"] == 5
        editor = window.image_fusion_editor
        assert editor.cfg_marker_thickness == 5
        assert all(
            editor.pair_splitter.widget(index).editor.cfg_marker_thickness == 5
            for index in range(2)
        )

    def test_defaults(self, qapp, tmp_path):
        main = gui.MainApp(cfg_path=tmp_path / "zoomer.cfg")
        assert main.cfg_frame_crosshair_action.isChecked()
        assert main.cfg_marker_thickness_spin.value() == 2
        assert not main.cfg_auto_open_last_project_action.isChecked()
        assert main.windowTitle() == "Zoomer - No project"


class TestMain:
    @pytest.mark.parametrize("recover", [False, True])
    def test_startup_loading_shows_animated_banner(
        self, qapp, tmp_path, proj_file, monkeypatch, recover
    ):
        cfg_path = tmp_path / "zoomer.cfg"
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        if recover:
            cfg_path.write_text("{}")
            recovery_path.write_text(proj_file.read_text())
            monkeypatch.setattr(
                QMessageBox,
                "question",
                staticmethod(
                    lambda *args, **kwargs: QMessageBox.StandardButton.Yes
                ),
            )
        else:
            cfg_path.write_text(
                json.dumps(
                    {
                        "auto_open_last_project": True,
                        "last_project": str(proj_file),
                    }
                )
            )

        finished_loading = Event()
        observed = {}

        def slow_load(filename):
            if not finished_loading.wait(3):
                raise TimeoutError("Loading was not released")
            return load_project(filename)

        def observe_banner():
            dialog = QApplication.activeModalWidget()
            observed["visible"] = dialog.isVisible()
            observed["parent_visible"] = dialog.parentWidget().isVisible()
            observed["label"] = dialog.findChild(gui.QLabel).text()
            observed["angle"] = dialog.spinner._angle
            finished_loading.set()

        monkeypatch.setattr(gui, "load_project", slow_load)
        monkeypatch.setattr(QApplication, "exec", lambda _app: 0)
        QTimer.singleShot(180, observe_banner)
        assert gui.main(["--config", str(cfg_path)]) == 0
        assert observed["visible"] and observed["parent_visible"]
        assert observed["label"] == "Loading project"
        assert observed["angle"] != 0
        assert QApplication.activeModalWidget() is None

    def test_skips_recovery_prompt_when_autosave_matches_named_project(
        self, qapp, tmp_path, proj_file, monkeypatch
    ):
        cfg_path = tmp_path / "zoomer.cfg"
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        recovery_path.write_text(proj_file.read_text())
        cfg_path.write_text(
            json.dumps(
                {
                    "auto_open_last_project": True,
                    "last_project": str(proj_file),
                }
            )
        )
        observed = {}

        class Capture(gui.MainApp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                observed["window"] = self

        def unexpected_recovery_prompt(*_args, **_kwargs):
            pytest.fail("matching autosave should not ask for recovery")

        monkeypatch.setattr(gui, "MainApp", Capture)
        monkeypatch.setattr(
            QMessageBox, "question", staticmethod(unexpected_recovery_prompt)
        )
        monkeypatch.setattr(QApplication, "exec", lambda _app: 0)

        assert gui.main(["--config", str(cfg_path)]) == 0
        assert json.loads(recovery_path.read_text()) == json.loads(
            proj_file.read_text()
        )
        assert observed["window"].proj_filename == str(proj_file)
        assert observed["window"].windowTitle() == "Zoomer - Demo"

    def test_offers_recovery_when_autosave_differs_from_named_project(
        self, qapp, tmp_path, proj_file, monkeypatch
    ):
        cfg_path = tmp_path / "zoomer.cfg"
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        recovered_data = json.loads(proj_file.read_text())
        recovered_data["project_name"] = "Recovered changes"
        recovery_path.write_text(json.dumps(recovered_data))
        cfg_path.write_text(
            json.dumps(
                {
                    "auto_open_last_project": True,
                    "last_project": str(proj_file),
                }
            )
        )
        observed = {}

        class Capture(gui.MainApp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                observed["window"] = self

        monkeypatch.setattr(gui, "MainApp", Capture)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(
                lambda *args, **kwargs: QMessageBox.StandardButton.Yes
            ),
        )
        monkeypatch.setattr(QApplication, "exec", lambda _app: 0)

        assert gui.main(["--config", str(cfg_path)]) == 0
        recovered_window = observed["window"]
        assert recovered_window.proj_filename is None
        assert (
            recovered_window.proj_data["project_name"] == "Recovered changes"
        )
        assert recovered_window._project_modified

    def test_declining_recovery_discards_autosave(
        self, qapp, tmp_path, proj_file, monkeypatch
    ):
        cfg_path = tmp_path / "zoomer.cfg"
        cfg_path.write_text("{}")
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        recovery_path.write_text(proj_file.read_text())
        observed = {}

        class Capture(gui.MainApp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                observed["window"] = self

        monkeypatch.setattr(gui, "MainApp", Capture)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(
                lambda *args, **kwargs: QMessageBox.StandardButton.No
            ),
        )
        monkeypatch.setattr(
            QApplication,
            "exec",
            lambda _app: 0,
        )
        monkeypatch.setattr(gui.QTimer, "singleShot", lambda *_args: None)

        assert gui.main(["--config", str(cfg_path)]) == 0
        assert not recovery_path.exists()
        assert observed["window"].proj_filename is None

    def test_startup_offers_recovery_and_does_not_assign_named_project(
        self, qapp, tmp_path, proj_file, monkeypatch
    ):
        cfg_path = tmp_path / "zoomer.cfg"
        cfg_path.write_text("{}")
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        recovery_path.write_text(proj_file.read_text())
        observed = {}

        class Capture(gui.MainApp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                observed["window"] = self

        monkeypatch.setattr(gui, "MainApp", Capture)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(
                lambda *args, **kwargs: QMessageBox.StandardButton.Yes
            ),
        )
        monkeypatch.setattr(
            QApplication,
            "exec",
            lambda _app: 0,
        )

        assert gui.main(["--config", str(cfg_path)]) == 0
        recovered_window = observed["window"]
        assert recovered_window.proj_filename is None
        assert recovered_window.proj_data["project_name"] == "Demo"
        assert len(recovered_window.proj_image_entries) == 3

    def test_auto_opens_the_last_project(
        self, qapp, tmp_path, proj_file, monkeypatch, no_dialogs
    ):
        cfg = tmp_path / "zoomer.cfg"
        cfg.write_text(
            json.dumps(
                {
                    "auto_open_last_project": True,
                    "frame_crosshair": False,
                    "last_project": str(proj_file),
                }
            )
        )
        observed = {}

        class Capture(gui.MainApp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                observed["window"] = self

        def fake_exec(_app):
            window = observed["window"]
            observed["title"] = window.windowTitle()
            observed["entries"] = len(window.proj_image_entries)
            observed["crosshair"] = (
                window.cfg_frame_crosshair_action.isChecked()
            )
            return 0

        monkeypatch.setattr(gui, "MainApp", Capture)
        monkeypatch.setattr(QApplication, "exec", fake_exec)
        assert gui.main(["--config", str(cfg)]) == 0
        assert observed["title"] == "Zoomer - Demo"
        assert observed["entries"] == 3
        assert observed["crosshair"] is False


class TestClosePrompt:
    def dirty_window(self, window):
        window._image_edited(
            0, "frame", {"upper_left": (4, 5), "width": 60, "height": 30}
        )
        assert window._project_modified
        return window

    def test_close_save_writes_named_project(
        self, window, tmp_path, monkeypatch
    ):
        window = self.dirty_window(window)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(
                lambda *args, **kwargs: QMessageBox.StandardButton.Save
            ),
        )
        assert window.close()
        saved = load_project(str(tmp_path / "demo.zmr"))
        assert saved["images_data"][0]["frame"] == [[4, 5], [64, 35]]
        assert not window._project_modified

    def test_close_discard_removes_recovery_and_closes(
        self, window, tmp_path, monkeypatch
    ):
        window = self.dirty_window(window)
        recovery_path = tmp_path / gui.AUTOSAVE_FILENAME
        assert recovery_path.exists()
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(
                lambda *args, **kwargs: QMessageBox.StandardButton.Discard
            ),
        )
        assert window.close()
        assert not recovery_path.exists()
        assert not window._project_modified

    def test_close_cancel_keeps_window_open_and_dirty(
        self, window, monkeypatch
    ):
        window = self.dirty_window(window)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(
                lambda *args, **kwargs: QMessageBox.StandardButton.Cancel
            ),
        )
        assert not window.close()
        assert window._project_modified


class TestHistory:
    def test_undo_and_redo_a_frame_edit(self, window):
        original = [list(p) for p in window.proj_image_entries[0]["frame"]]
        window._image_edited(
            0, "frame", {"upper_left": (5, 5), "width": 80, "height": 40}
        )
        edited = [list(p) for p in window.proj_image_entries[0]["frame"]]
        window.undo()
        assert window.proj_data["images_data"][0]["frame"] == original
        window.redo()
        assert window.proj_data["images_data"][0]["frame"] == edited

    def test_a_drag_is_a_single_history_step(self, window):
        for step in range(5):
            window._image_edited(
                0,
                "frame",
                {"upper_left": (step, 0), "width": 80, "height": 40},
            )
        assert len(window._undo_stack) == 1

    def test_history_keeps_ten_steps(self, window):
        for step in range(15):
            window._edit_burst_timer.stop()
            window._alpha_range_edited(0, [0.0, 0.5 + step / 100])
        assert len(window._undo_stack) == gui.HISTORY_LIMIT == 10

    def test_new_edit_clears_redo(self, window):
        window._alpha_range_edited(0, [0.1, 0.9])
        window.undo()
        assert window._redo_stack
        window._edit_burst_timer.stop()
        window._alpha_range_edited(0, [0.2, 0.8])
        assert not window._redo_stack

    def test_history_stores_filenames_not_images(self, window):
        window._alpha_range_edited(0, [0.1, 0.9])
        snapshot = window._undo_stack[-1]
        assert all(
            isinstance(e["image"], str) for e in snapshot["images_data"]
        )

    def test_undo_reuses_images_and_recreates_removed_ones(self, window):
        organizer = window.image_files_and_preview_area.image_files_organizer
        before = [e["image"] for e in window.proj_image_entries]
        organizer.image_list.takeItem(2)
        organizer._emit_image_files_changed()
        assert len(window.proj_image_entries) == 2
        window.undo()
        after = [e["image"] for e in window.proj_image_entries]
        assert after[0] is before[0] and after[1] is before[1]
        assert isinstance(after[2], ImageClass) and after[2] is not before[2]
        assert after[2].get_image_path() == before[2].get_image_path()

    def test_undo_with_missing_file_keeps_state(self, window, tmp_path):
        organizer = window.image_files_and_preview_area.image_files_organizer
        removed = window.proj_image_entries[2]["image"].get_image_path()
        organizer.image_list.takeItem(2)
        organizer._emit_image_files_changed()
        removed.unlink()
        window.undo()
        assert len(window.proj_image_entries) == 2
        assert window._undo_stack


class TestVideoPreview:
    def preview(self, window):
        return window.image_files_and_preview_area.preview_area.video_preview

    def test_preview_follows_the_project(self, window):
        QTest.qWait(500)
        assert self.preview(window)._total_frames == 10

    def test_preview_includes_pauses(self, window):
        window.proj_video_settings.update(pause_before=0.2, pause_after=0.3)
        window._refresh_video_preview()
        assert self.preview(window)._total_frames == 15

    def test_video_settings_save_pauses_and_refresh_preview(
        self, window, tmp_path, monkeypatch
    ):
        def accept_settings(dialog):
            dialog.video_settings.pause_before_spin.setValue(0.2)
            dialog.video_settings.pause_after_spin.setValue(0.3)
            return 1

        monkeypatch.setattr(gui.VideoSettingsDialog, "exec", accept_settings)
        window.open_video_settings()
        window._refresh_video_preview()
        assert self.preview(window)._total_frames == 15
        window.save_project()
        settings = load_project(str(tmp_path / "demo.zmr"))["video_data"]
        assert settings["pause_before"] == 0.2
        assert settings["duration"] == 1
        assert settings["pause_after"] == 0.3

    def test_calculation_errors_are_shown_on_the_canvas(self, window):
        window._image_edited(1, "prev_points", triangle(1.0))
        QTest.qWait(500)
        preview = self.preview(window)
        assert "increasing" in preview.canvas.text()
        assert not preview.slider.isEnabled()

    def test_fewer_than_two_images_shows_a_hint(self, qapp, tmp_path):
        main = gui.MainApp(
            None, tmp_path / "empty.zmr", {}, tmp_path / "zoomer.cfg"
        )
        main.set_image_workspace([], tmp_path)
        main._refresh_video_preview()
        assert "two images" in self.preview(main).canvas.text()

    def test_removing_images_updates_or_clears_all_previews(self, window):
        area = window.image_files_and_preview_area.preview_area
        organizer = window.image_files_and_preview_area.image_files_organizer
        video = area.video_preview
        area.tabs.setCurrentWidget(video)
        window._refresh_video_preview()
        assert not video.canvas._source_pixmap.isNull()
        assert not area._fusion_pixmap.isNull()
        video.play()
        assert video.is_playing()

        organizer.image_list.setCurrentRow(1)
        previous_fusion = area._fusion_pixmap.toImage()
        QTest.keyClick(organizer.image_list, Qt.Key.Key_Delete)
        assert len(window.proj_image_entries) == 2
        assert organizer.image_list.currentRow() == 1
        selected_image = window.proj_image_entries[1]["image"]
        expected = QPixmap.fromImage(selected_image.get_qt_image()).toImage()
        assert area._input_pixmap.toImage() == expected
        assert not area._fusion_pixmap.isNull()
        assert area._fusion_pixmap.toImage() != previous_fusion
        assert video.canvas._source_pixmap.isNull()
        assert not video.slider.isEnabled()
        assert not video.is_playing()
        QTest.qWait(300)
        assert not video.canvas._source_pixmap.isNull()
        assert video.slider.isEnabled()
        generator = window._video_generator
        expected_frame = generator.generate_video_frame_on_position(
            video.slider.value()
        )
        expected_video = QPixmap.fromImage(
            widgets._array_to_qimage(expected_frame)
        ).toImage()
        assert video.canvas._source_pixmap.toImage() == expected_video

        QTest.keyClick(organizer.image_list, Qt.Key.Key_Delete)
        assert len(window.proj_image_entries) == 1
        assert not area._input_pixmap.isNull()
        assert area._fusion_pixmap.isNull()
        assert area.fusion_image_label.text() == "Fusion preview unavailable"
        assert video.canvas._source_pixmap.isNull()
        assert not video.slider.isEnabled()
        assert "two images" in video.canvas.text()

        QTest.keyClick(organizer.image_list, Qt.Key.Key_Delete)
        assert not window.proj_image_entries
        assert area._input_pixmap.isNull()
        assert area.input_image_label.text() == "Select an image to preview"
        assert area._fusion_pixmap.isNull()
        assert video.canvas._source_pixmap.isNull()
        QTest.qWait(300)
        assert "two images" in video.canvas.text()
        assert not video.slider.isEnabled()

    def test_undo_removal_restores_fusion_and_video_previews(self, window):
        area = window.image_files_and_preview_area.preview_area
        organizer = window.image_files_and_preview_area.image_files_organizer
        organizer.image_list.setCurrentRow(2)
        QTest.keyClick(organizer.image_list, Qt.Key.Key_Delete)
        QTest.keyClick(organizer.image_list, Qt.Key.Key_Delete)
        assert area._fusion_pixmap.isNull()
        window.undo()
        assert len(window.proj_image_entries) == 2
        assert not area._fusion_pixmap.isNull()
        QTest.qWait(300)
        assert area.video_preview.slider.isEnabled()


class TestVideoExport:
    def test_export_job_writes_pause_frames(self, window, monkeypatch):
        window.proj_video_settings.update(pause_before=0.2, pause_after=0.3)
        window._refresh_video_preview()
        generator = window._video_generator
        written = []
        monkeypatch.setattr(generator, "open_video_writer", lambda: True)
        monkeypatch.setattr(generator, "close_video_writer", lambda: None)
        monkeypatch.setattr(
            generator,
            "generate_video_frame",
            lambda index, alpha: (index, alpha),
        )
        monkeypatch.setattr(generator, "save_video_frame", written.append)
        job = gui._VideoExportJob(generator, generator.get_total_frames())
        job.run()
        assert not job.error_message
        assert len(written) == 15
        assert written[:3] == [written[2]] * 3
        assert written[-4:] == [written[-4]] * 4
        assert written[2] != written[-4]

    def prepare_generator(self, window, monkeypatch, frame_count=4):
        QTest.qWait(300)
        generator = window._video_generator
        calls = []

        monkeypatch.setattr(
            generator,
            "perform_video_calculations",
            lambda: (calls.append("calculate") or True, None),
        )
        monkeypatch.setattr(
            generator,
            "get_total_frames",
            lambda: calls.append("total") or frame_count,
        )
        monkeypatch.setattr(
            generator,
            "open_video_writer",
            lambda: calls.append("open") or True,
        )

        def generate(position):
            calls.append(("generate", position))
            return np.full((90, 160, 3), position, dtype=np.uint8)

        monkeypatch.setattr(
            generator, "generate_video_frame_on_position", generate
        )
        monkeypatch.setattr(
            generator,
            "save_video_frame",
            lambda frame: calls.append(("save", int(frame[0, 0, 0]))),
        )
        monkeypatch.setattr(
            generator,
            "close_video_writer",
            lambda: calls.append("close"),
        )
        return generator, calls

    def test_export_uses_preview_generator_and_updates_video_tab(
        self, window, tmp_path, monkeypatch
    ):
        generator, calls = self.prepare_generator(window, monkeypatch)
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(tmp_path / "export.avi"), "")),
        )
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda *args, **kwargs: None),
        )

        window.select_export_filename()
        QTest.qWait(500)

        preview_area = window.image_files_and_preview_area.preview_area
        preview = preview_area.video_preview
        assert preview_area.tabs.currentWidget() is preview
        assert window._video_generator is generator
        assert generator.filename == str(tmp_path / "export.avi")
        assert calls[:3] == ["calculate", "total", "open"]
        assert [call for call in calls if isinstance(call, tuple)] == [
            ("generate", 0),
            ("save", 0),
            ("generate", 1),
            ("save", 1),
            ("generate", 2),
            ("save", 2),
            ("generate", 3),
            ("save", 3),
        ]
        assert calls[-1] == "close"
        assert preview.canvas._source_pixmap.width() == 160
        assert preview.slider.value() == 3
        assert preview.slider.isEnabled()
        assert not preview.export_banner.isVisible()
        assert window.file_menu_action.isEnabled()

    def test_export_interrupt_stops_after_current_frame_and_closes_writer(
        self, window, tmp_path, monkeypatch
    ):
        _generator, calls = self.prepare_generator(
            window, monkeypatch, frame_count=20
        )

        def slow_generate(position):
            time.sleep(0.08)
            calls.append(("generate", position))
            return np.full((90, 160, 3), position, dtype=np.uint8)

        monkeypatch.setattr(
            window._video_generator,
            "generate_video_frame_on_position",
            slow_generate,
        )
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(tmp_path / "cancel.avi"), "")),
        )
        window.select_export_filename()
        preview = (
            window.image_files_and_preview_area.preview_area.video_preview
        )
        assert preview.export_banner.isVisible()
        QTimer.singleShot(20, preview.export_interrupt_button.click)
        QTest.qWait(350)

        generated = [call for call in calls if isinstance(call, tuple)]
        assert 0 < len(generated) < 40
        assert calls[-1] == "close"
        assert not preview.export_banner.isVisible()
        assert "interrupted" in preview.position_label.text().lower()
        assert window.file_menu_action.isEnabled()

    def test_selected_project_format_sets_export_extension(
        self, window, tmp_path, monkeypatch
    ):
        supported_format = get_supported_video_formats()[0][0]
        window.proj_video_settings["format"] = supported_format
        self.prepare_generator(window, monkeypatch, frame_count=0)
        target = tmp_path / "chosen.other"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(target), "")),
        )
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda *args, **kwargs: None),
        )

        window.select_export_filename()
        QTest.qWait(300)

        assert Path(window.export_filename).suffix == f".{supported_format}"


class TestAlignment:
    def fake_alignment(self, proj, index):
        proj["images_data"][index]["next_points"] = np.array(
            [[1, 2], [3, 4], [5, 6]], dtype=np.float32
        )
        proj["images_data"][index + 1]["prev_points"] = np.array(
            [[7, 8], [9, 10], [11, 12]], dtype=np.float32
        )
        return True

    def test_result_is_applied_as_plain_lists(self, window, monkeypatch):
        monkeypatch.setattr(gui, "auto_align_images", self.fake_alignment)
        window.image_fusion_editor.find_alignment_button.click()
        QTest.qWait(400)
        entries = window.proj_image_entries
        assert entries[0]["next_points"] == [[1, 2], [3, 4], [5, 6]]
        assert entries[1]["prev_points"] == [[7, 8], [9, 10], [11, 12]]
        assert len(window._undo_stack) == 1
        json.dumps(window.proj_data["images_data"][0]["next_points"])

    def test_failure_leaves_the_project_untouched(
        self, window, monkeypatch, no_dialogs
    ):
        before = [list(p) for p in window.proj_image_entries[0]["next_points"]]
        monkeypatch.setattr(gui, "auto_align_images", lambda p, i: False)
        window.image_fusion_editor.find_alignment_button.click()
        QTest.qWait(400)
        assert window.proj_image_entries[0]["next_points"] == before
        assert not window._undo_stack
        assert no_dialogs

    def test_interrupt_discards_the_result(self, window, monkeypatch):
        def slow(proj, index):
            QTest.qWait(0)
            import time

            time.sleep(0.3)
            return self.fake_alignment(proj, index)

        monkeypatch.setattr(gui, "auto_align_images", slow)
        before = [list(p) for p in window.proj_image_entries[0]["next_points"]]
        editor = window.image_fusion_editor
        editor.find_alignment_button.click()
        assert editor.alignment_banner.isVisible()
        editor.alignment_interrupt_button.click()
        assert not editor.alignment_banner.isVisible()
        QTest.qWait(600)
        assert window.proj_image_entries[0]["next_points"] == before
        assert not window._undo_stack
