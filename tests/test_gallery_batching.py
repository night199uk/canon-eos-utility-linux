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


def test_worker_pages_the_gallery(qapp, monkeypatch):
    import canon_eos_utility.ui.camera_worker as cw

    monkeypatch.setattr(cw, "GALLERY_BATCH_SIZE", 2)

    server = MockCameraServer(port=0)
    server.start()
    worker = cw.CameraWorker("test", bytes(16))

    batches: list[list] = []
    more: list[bool] = []
    resets: list[bool] = []
    worker.objectsLoaded.connect(lambda objs: batches.append(list(objs)))
    worker.hasMoreObjects.connect(more.append)
    worker.galleryReset.connect(lambda: resets.append(True))

    try:
        worker._do_connect(f"127.0.0.1:{server.port}")

        # Newest first: the highest handle (IMG_0004) leads.
        assert len(batches) == 1
        assert [obj.filename for obj in batches[0]] == ["IMG_0004.JPG", "IMG_0003.JPG"]
        assert more == [True]

        worker._do_load_more()
        assert [obj.filename for obj in batches[1]] == ["IMG_0002.JPG", "IMG_0001.JPG"]
        assert more == [True, False]

        # Once everything is shown further requests are no-ops.
        worker._do_load_more()
        assert len(batches) == 2
        assert resets == [True]
    finally:
        server.stop()


def test_gallery_panel_appends_and_toggles_load_more(qapp):
    from canon_eos_utility.models import CameraObject
    from canon_eos_utility.ui.gallery_panel import GalleryPanel

    panel = GalleryPanel()
    first = [CameraObject(handle=2, storage_id=1, format=0x3801, size=1, filename="b.jpg")]
    second = [CameraObject(handle=1, storage_id=1, format=0x3801, size=1, filename="a.jpg")]

    panel.begin_load()
    assert panel.list.count() == 0
    assert panel.load_more_button.isHidden()

    panel.add_objects(first)
    assert panel.list.count() == 1
    assert panel.summary_label.text() == "1 objects"

    panel.set_more_available(True)
    assert not panel.load_more_button.isHidden()

    panel.add_objects(second)
    panel.add_objects(second)  # a duplicate handle is ignored
    assert panel.list.count() == 2
    assert panel.all_handles() == [2, 1]

    panel.set_more_available(False)
    assert panel.load_more_button.isHidden()
