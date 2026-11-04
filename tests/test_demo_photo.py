from PIL import Image

from tools.demo_photo import clean_photo


def test_a_demo_photo_loses_its_location_data_and_is_resized(tmp_path):
    source, target = tmp_path / "phone.jpg", tmp_path / "out" / "exit.jpg"
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (37.0, 46.0, 10.0)}
    exif[0x0112] = 6
    Image.new("RGB", (4000, 3000), "gray").save(source, exif=exif)
    w, h = clean_photo(source, target)
    with Image.open(target) as out:
        assert not out.getexif(), "no EXIF, so no GPS position"
        assert out.size == (w, h) and max(w, h) <= 1600
    assert h > w, "turned upright from the orientation tag"
