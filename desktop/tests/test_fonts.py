"""The bundled faces, shipped with the app, and times written in figures of one width."""

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
    from PySide6.QtWidgets import QApplication, QLineEdit, QTimeEdit

    from desktop.native.fonts import (
        FACES,
        FAMILIES,
        FONT_DIR,
        TABULAR,
        caption,
        load_fonts,
        time_font,
        weighted,
    )
    from desktop.native.tokens import WEIGHT_STRONG, type_pt
    from desktop.native.widgets import use_app_style


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-fonts-test"])


def test_every_bundled_face_loads_as_its_family_at_its_weight(qapp: QApplication) -> None:
    """Inter, Newsreader and JetBrains Mono for the Serif and Mono fonts, and Retro desktop's Pixelify
    Sans and VT323, each drawn at the weight asked for. The mock-up's variable fonts, registered as they
    were, drew a 600 heading at 400."""
    assert {"Inter", "Newsreader", "JetBrains Mono", "Pixelify Sans", "VT323"} <= set(load_fonts())
    weights = {
        "Regular": QFont.Weight.Normal,
        "Medium": QFont.Weight.Medium,
        "SemiBold": QFont.Weight.DemiBold,
        "Bold": QFont.Weight.Bold,
    }
    for family, faces in FACES.items():
        for face in faces:
            # A second registration of a file Qt already holds still names its family.
            ident = QFontDatabase.addApplicationFont(str(FONT_DIR / face))
            assert ident >= 0, face
            assert family in QFontDatabase.applicationFontFamilies(ident), face
        for style in FAMILIES[family][1]:
            font = QFont(family, 12)
            font.setWeight(weights[style])
            assert (QFontInfo(font).family(), QFontInfo(font).styleName()) == (family, style)


def test_retros_face_takes_its_figures_from_vt323(qapp: QApplication) -> None:
    """Pixelify Sans draws its 5 as an S and, at the caption size, its 2 as an 8, so Retro's face has
    VT323's figures and colon, a third larger (the mock-up's size-adjust of 128 %), at every weight,
    and keeps its own letters."""
    load_fonts()
    vt = QFontMetricsF(QFont("VT323", 100))
    for weight in (QFont.Weight.Normal, QFont.Weight.DemiBold):
        pixel = QFont("Pixelify Sans", 100)
        pixel.setWeight(weight)
        metrics = QFontMetricsF(pixel)
        for figure in "0258:":
            wide = vt.horizontalAdvance(figure) * 1.28
            assert metrics.horizontalAdvance(figure) == pytest.approx(wide, abs=1), (weight, figure)
        assert metrics.horizontalAdvance("S") != pytest.approx(vt.horizontalAdvance("S") * 1.28, abs=1)


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


def test_the_hours_small_words_are_the_scales_caption_at_every_text_size(qapp: QApplication) -> None:
    """Hour labels, block times and the now line's time were the body shrunk by 0.86, a size of their
    own at every Text knob. They are the caption beside the body the knob chose."""
    for text in ("small", "normal", "large"):
        body = QFont("Inter")
        body.setPointSizeF(type_pt("body", text))
        assert caption(body).pointSizeF() == type_pt("caption", text), text
    # A design's own size, off the scale, keeps its proportion until its lane redraws it.
    own = QFont("Inter")
    own.setPointSizeF(20)
    assert caption(own).pointSizeF() == pytest.approx(17.2)


def test_a_strong_word_is_600_not_bold(qapp: QApplication) -> None:
    load_fonts()
    strong = weighted(QFont("Inter", 13), WEIGHT_STRONG)
    assert strong.weight() == QFont.Weight.DemiBold
    assert QFontInfo(strong).styleName() == "SemiBold"


def test_every_time_box_writes_its_figures_at_one_width(qapp: QApplication) -> None:
    use_app_style(qapp)
    time, line = QTimeEdit(), QLineEdit()
    for box in (time, line):
        box.ensurePolished()
    assert time.font().featureValue(QFont.Tag(TABULAR)) == 1
    assert QFont.Tag(TABULAR) not in line.font().featureTags()
