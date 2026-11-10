import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Keep QSettings out of the developer's real ~/.config during tests.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="canon-eos-test-config-")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from canon_eos_utility.mock import MockCameraServer  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_worker_streams_the_gallery(qapp):
    import canon_eos_utility.ui.camera_worker as cw

    server = MockCameraServer(port=0)
    server.start()
    worker = cw.CameraWorker("test", bytes(16))

    objects: list = []
    progress: list[tuple[int, int]] = []
    resets: list[bool] = []
    worker.objectsLoaded.connect(lambda objs: objects.extend(objs))
    worker.galleryProgress.connect(lambda shown, total: progress.append((shown, total)))
    worker.galleryReset.connect(lambda: resets.append(True))

    try:
        # Direct-drive the worker (no thread): connect streams the first object,
        # then we step through the rest exactly as the worker loop would.
        worker._do_connect(f"127.0.0.1:{server.port}")
        while worker._gallery_loading:
            worker._gallery_step()

        # Newest first: the highest handle (IMG_0004) leads.
        assert [obj.filename for obj in objects] == [
            "IMG_0004.JPG",
            "IMG_0003.JPG",
            "IMG_0002.JPG",
            "IMG_0001.JPG",
        ]
        assert resets == [True]
        assert progress[0] == (0, 4)
        assert progress[-1] == (4, 4)
        assert not worker._gallery_loading
    finally:
        server.stop()


def test_gallery_panel_appends_and_reports_counts(qapp):
    from canon_eos_utility.models import CameraObject
    from canon_eos_utility.ui.gallery_panel import GalleryPanel

    panel = GalleryPanel()
    first = [CameraObject(handle=2, storage_id=1, format=0x3801, size=1, filename="b.jpg")]
    second = [CameraObject(handle=1, storage_id=1, format=0x3801, size=1, filename="a.jpg")]

    panel.begin_load()
    assert panel.list.count() == 0
    assert panel.summary_label.text() == "Reading camera contents…"

    panel.add_objects(first)
    panel.set_counts(1, 10)
    assert panel.list.count() == 1
    assert panel.summary_label.text() == "Showing 1 of 10 items"

    panel.add_objects(second)
    panel.add_objects(second)  # a duplicate handle is ignored
    assert panel.list.count() == 2
    assert panel.all_handles() == [2, 1]

    panel.set_counts(2, 2)
    assert panel.summary_label.text() == "Showing 2 of 2 items"
