import json

import numpy as np
import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog

from conftest import triangle
from zoomer import gui
from zoomer.backend import ImageClass, load_config
from zoomer.widgets import VideoSettingsDialog


@pytest.fixture
def window(qapp, tmp_path, proj_data, no_dialogs):
    main = gui.MainApp(
        proj_data, tmp_path / "demo.zmr", {}, tmp_path / "zoomer.cfg"
    )
    main.set_image_workspace(proj_data["images_data"], tmp_path)
    main.show()
    yield main
    main.close()


def stub_dialogs(monkeypatch, tmp_path, name="Fresh"):
    monkeypatch.setattr(VideoSettingsDialog, "exec", lambda self: 1)
    monkeypatch.setattr(VideoSettingsDialog, "project_name", lambda self: name)
    monkeypatch.setattr(
        VideoSettingsDialog,
        "settings",
        lambda self: {
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
    def test_new_project_creates_zmr_and_updates_title(
        self, window, tmp_path, monkeypatch
    ):
        stub_dialogs(monkeypatch, tmp_path)
        window.new_project()
        saved = json.loads((tmp_path / "Fresh.zmr").read_text())
        assert saved["project_name"] == "Fresh"
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

    def test_save_as_forces_zmr_suffix(self, window, tmp_path, monkeypatch):
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(tmp_path / "copy.json"), "")),
        )
        window.save_as()
        assert (tmp_path / "copy.zmr").exists()
        assert window.windowTitle() == "Zoomer - copy"

    def test_edits_are_autosaved_to_the_project_file(self, window, tmp_path):
        window._image_edited(
            0, "frame", {"upper_left": (1, 2), "width": 100, "height": 50}
        )
        saved = load_config(str(tmp_path / "demo.zmr"))
        assert saved["images_data"][0]["frame"] == [[1, 2], [101, 52]]


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

    def test_defaults(self, qapp, tmp_path):
        main = gui.MainApp(cfg_path=tmp_path / "zoomer.cfg")
        assert main.cfg_frame_crosshair_action.isChecked()
        assert not main.cfg_auto_open_last_project_action.isChecked()
        assert main.windowTitle() == "Zoomer - No project"


class TestMain:
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
