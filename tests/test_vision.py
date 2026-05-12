"""Tests for wardrobe.vision pure functions.

All tests use synthetic PIL images so no real photos are required.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from wardrobe.vision import (
    COLOR_NAMES,
    dominant_colors,
    image_embedding,
    nearest_color_name,
    visual_tags,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _solid(rgb: tuple[int, int, int], size: int = 64) -> Image.Image:
    return Image.new("RGB", (size, size), rgb)


def _checkerboard(
    a: tuple[int, int, int], b: tuple[int, int, int], size: int = 64
) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = a if (x + y) % 2 == 0 else b
    return img


def _h_gradient(lo: int = 0, hi: int = 255, size: int = 64) -> Image.Image:
    """Image that varies sharply along the x-axis (horizontal stripes)."""
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for x in range(size):
        arr[:, x, :] = int(lo + (hi - lo) * x / (size - 1))
    return Image.fromarray(arr, "RGB")


def _v_gradient(lo: int = 0, hi: int = 255, size: int = 64) -> Image.Image:
    """Image that varies sharply along the y-axis (vertical stripes)."""
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(size):
        arr[y, :, :] = int(lo + (hi - lo) * y / (size - 1))
    return Image.fromarray(arr, "RGB")


# ── nearest_color_name ────────────────────────────────────────────────────────


class TestNearestColorName:
    _known = {name for name, _ in COLOR_NAMES}

    def test_black(self):
        assert nearest_color_name((0, 0, 0)) == "black"

    def test_white(self):
        assert nearest_color_name((255, 255, 255)) == "white"

    def test_red(self):
        assert nearest_color_name((200, 30, 30)) == "red"

    def test_blue(self):
        assert nearest_color_name((30, 80, 210)) == "blue"

    def test_always_returns_known_name(self):
        for rgb in [(100, 100, 100), (0, 128, 0), (200, 150, 100)]:
            assert nearest_color_name(rgb) in self._known

    def test_returns_string(self):
        assert isinstance(nearest_color_name((128, 128, 128)), str)


# ── visual_tags ───────────────────────────────────────────────────────────────


class TestVisualTags:
    def test_uniform_image_is_solid(self):
        tags = visual_tags(_solid((128, 128, 128)))
        assert "solid" in tags

    def test_checkerboard_not_solid(self):
        tags = visual_tags(_checkerboard((0, 0, 0), (255, 255, 255)))
        assert "solid" not in tags

    def test_returns_list(self):
        assert isinstance(visual_tags(_solid((100, 100, 100))), list)

    def test_horizontal_gradient_not_solid(self):
        tags = visual_tags(_h_gradient())
        assert "solid" not in tags

    def test_vertical_gradient_not_solid(self):
        tags = visual_tags(_v_gradient())
        assert "solid" not in tags

    def test_horizontal_detail_detected(self):
        # dx >> dy → horizontal-detail tag
        tags = visual_tags(_h_gradient(0, 255, size=128))
        assert "horizontal-detail" in tags

    def test_vertical_detail_detected(self):
        # dy >> dx → vertical-detail tag
        tags = visual_tags(_v_gradient(0, 255, size=128))
        assert "vertical-detail" in tags


# ── image_embedding ───────────────────────────────────────────────────────────


class TestImageEmbedding:
    # 3*32 (RGB hists) + 36+16+16 (HSV hists) + 4 (texture stats) = 168
    EXPECTED_DIM = 168

    def test_shape(self):
        emb = image_embedding(_solid((100, 150, 200)))
        assert emb.shape == (self.EXPECTED_DIM,)

    def test_dtype_float32(self):
        emb = image_embedding(_solid((100, 150, 200)))
        assert emb.dtype == np.float32

    def test_unit_norm(self):
        emb = image_embedding(_solid((100, 150, 200)))
        assert abs(float(np.linalg.norm(emb)) - 1.0) < 1e-5

    def test_deterministic(self):
        img = _solid((100, 100, 100))
        np.testing.assert_array_equal(image_embedding(img), image_embedding(img))

    def test_different_colors_different_embeddings(self):
        red = image_embedding(_solid((200, 30, 30)))
        blue = image_embedding(_solid((30, 80, 200)))
        assert not np.allclose(red, blue)

    def test_cosine_similarity_identical_images(self):
        e = image_embedding(_solid((128, 128, 128)))
        assert abs(float(np.dot(e, e)) - 1.0) < 1e-5


# ── dominant_colors ───────────────────────────────────────────────────────────


class TestDominantColors:
    _known = {name for name, _ in COLOR_NAMES}

    def test_returns_list(self):
        assert isinstance(dominant_colors(_solid((200, 30, 30))), list)

    def test_count_upper_bound(self):
        colors = dominant_colors(_solid((0, 0, 0)), count=2)
        assert len(colors) <= 2

    def test_names_are_known(self):
        colors = dominant_colors(_solid((0, 0, 0)), count=3)
        for c in colors:
            assert c in self._known, f"Unknown color name: {c}"

    def test_no_duplicates(self):
        colors = dominant_colors(_checkerboard((200, 30, 30), (30, 80, 200)), count=3)
        assert len(colors) == len(set(colors))
