import datetime

from canon_eos_utility.metadata import parse_ptp_datetime, read_metadata


def test_parse_ptp_datetime():
    assert parse_ptp_datetime("20260912T150605.0") == datetime.datetime(2026, 9, 12, 15, 6, 5)
    assert parse_ptp_datetime("") is None
    assert parse_ptp_datetime("garbage") is None


def _write_jpeg_with_exif(path) -> None:
    from PIL import Image

    image = Image.new("RGB", (10, 10), (120, 30, 30))
    exif = image.getexif()
    exif[0x010F] = "Canon"
    exif[0x0110] = "Canon EOS R5"
    exif[0x0132] = "2026:09:12 15:06:05"
    image.save(path, "JPEG", exif=exif)


def test_read_jpeg_exif(tmp_path):
    path = tmp_path / "a.jpg"
    _write_jpeg_with_exif(str(path))

    metadata = read_metadata(str(path))
    assert metadata.model == "Canon EOS R5"
    assert metadata.make == "Canon"
    assert metadata.taken == datetime.datetime(2026, 9, 12, 15, 6, 5)
    assert metadata.source == "exif"


def test_read_jpeg_without_exif_uses_fallback(tmp_path):
    from PIL import Image

    path = tmp_path / "b.jpg"
    Image.new("RGB", (10, 10)).save(str(path), "JPEG")

    metadata = read_metadata(
        str(path),
        fallback_datetime=datetime.datetime(2020, 1, 2, 3, 4, 5),
        fallback_size=(640, 480),
    )
    assert metadata.taken == datetime.datetime(2020, 1, 2, 3, 4, 5)
    assert (metadata.width, metadata.height) == (640, 480)


def test_read_cr3_extracts_cmt_boxes(tmp_path):
    from PIL import Image

    tiff_path = tmp_path / "tiff"
    image = Image.new("RGB", (10, 10))
    exif = image.getexif()
    exif[0x0110] = "Canon EOS R5"
    exif[0x0132] = "2026:09:12 15:06:05"
    image.save(str(tiff_path), "TIFF", exif=exif)
    tiff = tiff_path.read_bytes()

    box = (len(tiff) + 8).to_bytes(4, "big") + b"CMT1" + tiff
    container = b"\x00\x00\x00\x18ftypcrx " + box
    cr3 = tmp_path / "a.CR3"
    cr3.write_bytes(container)

    metadata = read_metadata(str(cr3))
    assert metadata.source == "cr3"
    assert metadata.model == "Canon EOS R5"
    assert metadata.taken == datetime.datetime(2026, 9, 12, 15, 6, 5)


def test_read_mp4_creation_time(tmp_path):
    epoch = 1_700_000_000 + 2_082_844_800
    body = (
        b"\x00\x00\x00\x00"
        + epoch.to_bytes(4, "big")
        + (1000).to_bytes(4, "big")
        + (0).to_bytes(4, "big")
    )
    box = (len(body) + 8).to_bytes(4, "big") + b"mvhd" + body
    data = b"\x00\x00\x00\x10ftypisom" + box

    movie = tmp_path / "clip.MP4"
    movie.write_bytes(data)

    metadata = read_metadata(str(movie))
    assert metadata.source == "mp4"
    assert metadata.taken == datetime.datetime(2023, 11, 14, 22, 13, 20)


def _tiff_with_exif(path) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (10, 10))
    exif = image.getexif()
    exif[0x0110] = "Canon EOS R5"
    exif[0x0132] = "2026:09:12 15:06:05"
    image.save(str(path), "TIFF", exif=exif)
    return path.read_bytes()


def test_wrap_tiff_as_app1_truncates_oversized_tiff():
    from canon_eos_utility.metadata import _wrap_tiff_as_app1

    # A CMT box can be far larger than the 16-bit APP1 length field allows.
    wrapped = _wrap_tiff_as_app1(b"\x00" * (100 * 1024))

    assert wrapped[:2] == b"\xff\xe1"
    # marker (2) + length (2) + payload (<= 65535) + EOI (2)
    assert len(wrapped) <= 2 + 0xFFFF + 2


def test_read_cr3_with_oversized_cmt_box(tmp_path):
    tiff = _tiff_with_exif(tmp_path / "tiff")

    # Simulate a CMT1 box whose TIFF carries > 64 KiB of trailing image data.
    body = tiff + b"\x00" * (70 * 1024)
    box = (len(body) + 8).to_bytes(4, "big") + b"CMT1" + body
    container = b"\x00\x00\x00\x18ftypcrx " + box
    cr3 = tmp_path / "big.CR3"
    cr3.write_bytes(container)

    metadata = read_metadata(str(cr3))  # must not raise struct.error
    assert metadata.source == "cr3"
    assert metadata.model == "Canon EOS R5"
    assert metadata.taken == datetime.datetime(2026, 9, 12, 15, 6, 5)


def test_read_large_tiff_without_overflow(tmp_path):
    tiff = _tiff_with_exif(tmp_path / "tiff")

    # A CR2 (or any raw TIFF) is far larger than the APP1 length field allows;
    # it is wrapped whole, so this reproduces the same 16-bit overflow.
    cr2 = tmp_path / "big.CR2"
    cr2.write_bytes(tiff + b"\x00" * (5 * 1024 * 1024))

    metadata = read_metadata(str(cr2))  # must not raise struct.error
    assert metadata.source == "exif"
    assert metadata.model == "Canon EOS R5"
