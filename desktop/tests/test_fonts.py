"""Inter, shipped with the app, and times written in figures of one width."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetricsF
    from PySide6.QtWidgets import QApplication

    from desktop.native.fonts import FACES, FONT_DIR, load_fonts, time_font


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-fonts-test"])


def test_every_bundled_face_loads_as_inter(qapp: QApplication) -> None:
    assert "Inter" in load_fonts()
    for face in FACES:
        # A second registration of a file Qt already holds still names its family.
        ident = QFontDatabase.addApplicationFont(str(FONT_DIR / face))
        assert ident >= 0, face
        assert "Inter" in QFontDatabase.applicationFontFamilies(ident), face
    for weight, style in (
        (QFont.Weight.Normal, "Regular"),
        (QFont.Weight.Medium, "Medium"),
        (QFont.Weight.DemiBold, "SemiBold"),
        (QFont.Weight.Bold, "Bold"),
    ):
        font = QFont("Inter", 12)
        font.setWeight(weight)
        assert (QFontInfo(font).family(), QFontInfo(font).styleName()) == ("Inter", style)


def test_a_time_takes_as_much_room_whatever_its_figures(qapp: QApplication) -> None:
    load_fonts()
    plain = QFont("Inter", 12)
    ones, zeros = "11:11", "00:00"
    metrics = QFontMetricsF(plain)
    # Inter's own figures are proportional, so without the feature the two differ.
    assert metrics.horizontalAdvance(ones) < metrics.horizontalAdvance(zeros)
    even = QFontMetricsF(time_font(plain))
    assert even.horizontalAdvance(ones) == even.horizontalAdvance(zeros)
    assert time_font(plain).pointSizeF() == plain.pointSizeF() and time_font(plain).family() == "Inter"
