"""Reading the tsunami inundation raster: pixel to depth class, tile maths, and failure handling."""
import base64
import io

import pytest
from PIL import Image

from safezone.japan.tiles import (DEPTH_CLASSES, UNREAD, InundationMap, TileUnavailable, classify_rgba, tile_bounds,
                                  tile_of)
from safezone.transport import Response


def png(rgba):
    buf = io.BytesIO()
    Image.new("RGBA", (256, 256), rgba).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class OneTile:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def send(self, request):
        self.calls += 1
        return self.response


def test_transparent_is_outside_and_each_legend_colour_is_its_class():
    assert classify_rgba((0, 0, 0, 0)) is None
    for i, cls in enumerate(DEPTH_CLASSES):
        assert classify_rgba((*cls.rgb, 255)) == i


def test_unknown_colour_reads_inside_at_the_deepest_class():
    assert classify_rgba((10, 200, 30, 255)) == UNREAD


def test_tile_of_round_trips_with_tile_bounds():
    p = (139.5466, 35.3192)
    x, y, px, py = tile_of(p, 15)
    w, s, e, n = tile_bounds(x, y, 15)
    assert w <= p[0] < e and s < p[1] <= n and 0 <= px < 256 and 0 <= py < 256


def test_depth_reads_the_pixel_and_fetches_each_tile_once():
    t = OneTile(Response(200, png((*DEPTH_CLASSES[3].rgb, 255)), "recorded"))
    m = InundationMap(t)
    assert m.depth((139.5466, 35.3192)) == 3
    assert m.depth((139.54661, 35.31921)) == 3
    assert t.calls == 1 and m.provenance() == "recorded"


@pytest.mark.parametrize("response", [Response(404, "", "live"), Response(200, "", "recorded")])
def test_missing_tile_is_no_mapped_inundation(response):
    assert InundationMap(OneTile(response)).depth((139.5, 35.3)) is None


@pytest.mark.parametrize("response", [Response(599, "timeout", "live"), Response(200, "not base64 png!", "live")])
def test_failed_or_garbled_tile_is_unknown_not_outside(response):
    with pytest.raises(TileUnavailable):
        InundationMap(OneTile(response)).depth((139.5, 35.3))
