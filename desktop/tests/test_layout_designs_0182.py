"""0.18.2 lane 3: 0.17.3 design regressions on this build."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from desktop.native.fonts import at_scale
    from desktop.native.hours.geometry import Axis, LinearTrack
    from desktop.native.layouts.bento import BentoPainter, DayHead
    from desktop.native.layouts.mission import LEAD, MissionCanvas, MissionPainter
    from desktop.native.layouts.registry import MATCH, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.tokens import WEIGHT_STRONG
    from desktop.native.weekmodel import set_clock_24h
    from desktop.tests.test_layout_bento import shown as bento_shown
    from desktop.tests.test_layout_bento import text
    from desktop.tests.test_layout_mission import BLOCKS, block
    from desktop.tests.test_layout_mission import shown as mission_shown


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-designs-0182-test"])


def test_bentos_now_pill_sits_in_the_gutter_not_inside_todays_column(qapp: QApplication) -> None:
    tokens = tokens_for("bento", MATCH, resolved_palette("light-frost", False, None))
    painting = BentoPainter(tokens, wide=False)
    painting.now_minute = 10 * 60 + 20
    pills: list[QRectF] = []
    track = LinearTrack(3, QRectF(80, 10, 120, 400))

    class Marks(QPainter):
        def drawRoundedRect(self, box, *args):  # noqa: N802
            pills.append(QRectF(box))
            return super().drawRoundedRect(box, *args)

    picture = QImage(400, 500, QImage.Format.Format_ARGB32)
    paint = Marks(picture)
    paint.setFont(QFont("Inter", 12))
    try:
        painting.hour_labels(paint, track, 56)
    finally:
        paint.end()
    assert len(pills) == 1
    assert pills[0].right() <= track.area.left() - 2


def test_missions_beside_block_name_is_not_crossed_by_the_now_line(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop.native.hours import canvas as canvas_module

    piano = block("piano", "locked", [3], "15:40", 45, title="Piano lesson", category="extra")
    view = mission_shown(qapp, blocks=[*BLOCKS, piano], minute="15:40")
    hours = view.findChild(MissionCanvas, "missionHours")
    laid: list[tuple[str, QRectF]] = []

    class Laid(QPainter):
        def drawText(self, *args):  # noqa: N802
            if isinstance(args[0], QRectF) and isinstance(args[-1], str):
                laid.append((args[-1], QRectF(args[0])))
            return super().drawText(*args)

    monkeypatch.setattr(canvas_module, "QPainter", Laid)
    hours.set_week(hours.occurrences, 3, None)
    hours.repaint()
    names = [(t, b) for t, b in laid if t == "Piano lesson"]
    assert len(names) == 1
    name = names[0][1]
    bare = hours.grab().toImage()
    hours.set_week(hours.occurrences, 3, 15 * 60 + 40)
    lit = hours.grab().toImage()
    near = name.adjusted(-2, -2, 2, 2).toAlignedRect()
    changed = sum(
        lit.pixel(x, y) != bare.pixel(x, y)
        for x in range(near.left(), near.right() + 1)
        for y in range(near.top(), near.bottom() + 1)
    )
    assert changed == 0


def test_missions_midnight_hour_label_is_not_left_of_the_lanes(qapp: QApplication) -> None:
    tokens = tokens_for("mission", MATCH, resolved_palette("light-frost", False, None))
    painter = MissionPainter(tokens)
    track = LinearTrack(0, QRectF(LEAD + 40, 80, 800, 36), Axis.ACROSS, first=0, last=24 * 60)
    labels: list[QRectF] = []

    class Wrote(QPainter):
        def drawText(self, box, _flags, words):  # noqa: N802
            if words in ("00:00", "12:00 AM"):
                labels.append(QRectF(box))
            return super().drawText(box, _flags, words)

    picture = QImage(900, 200, QImage.Format.Format_ARGB32)
    paint = Wrote(picture)
    paint.setFont(QFont("JetBrains Mono", 11))
    set_clock_24h(True)
    try:
        painter.hour_labels(paint, track, 56, visible=QRectF(LEAD + 40, 0, 700, 120))
    finally:
        paint.end()
    assert labels
    assert min(box.left() for box in labels) >= track.area.left() + LEAD - 0.5


def test_bentos_week_header_does_not_shorten_to_a_single_letter_and_digit(qapp: QApplication) -> None:
    tokens = tokens_for("bento", MATCH, resolved_palette("light-frost", False, None))
    head = DayHead(4)
    head.show_date(2, True, head.ink, tokens, 1.25)
    head.resize(52, 36)
    head.update()
    base = at_scale(head.font(), "body", 1.25, WEIGHT_STRONG)
    assert QFontMetricsF(base).horizontalAdvance("F") + 30 < head.width() - 4
    assert head.text() != "F 2"


def test_bento_says_nothing_free_now_after_the_last_study_hour(qapp: QApplication) -> None:
    view = bento_shown(qapp, "day", clock="22:49")
    assert text(view, "bentoFreeNone") == "Nothing free now"

