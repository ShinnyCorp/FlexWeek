"""Where minutes are on a track, down a column, across a lane, and on a card laid at an angle."""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPointF, QRectF

    from desktop.native.hours.geometry import Axis, LinearTrack, overlap_columns, snap


def column() -> LinearTrack:
    # 06:00 to 23:00 over 1020 pixels: one pixel a minute, from y = 100.
    return LinearTrack(3, QRectF(50, 100, 200, 1020), first=6 * 60, last=23 * 60)


def test_a_column_reads_minutes_down_from_its_top_edge() -> None:
    track = column()
    assert track.minute_at(QPointF(120, 100)) == 6 * 60
    assert track.minute_at(QPointF(120, 100 + 13 * 60)) == 19 * 60
    assert track.minute_at(QPointF(120, 40)) == 6 * 60 - 60, "above the track still has a time"
    assert track.point_for(19 * 60) == QPointF(150, 100 + 13 * 60)


def test_a_lane_reads_minutes_across_from_its_left_edge() -> None:
    lane = LinearTrack(4, QRectF(72, 10, 2040, 60), Axis.ACROSS, first=6 * 60, last=23 * 60)
    assert lane.minute_at(QPointF(72 + 2 * 13 * 60, 30)) == 19 * 60
    assert lane.point_for(12 * 60) == QPointF(72 + 2 * 6 * 60, 40)


def test_a_span_is_drawn_between_its_minutes_and_shares_the_width_when_it_overlaps() -> None:
    track = column()
    alone = track.rect_for(19 * 60, 20 * 60)
    # A pixel in from its start and two from its end: three between blocks back to back.
    assert (alone.top(), alone.height()) == (100 + 13 * 60 + 1, 57)
    assert (alone.left(), alone.width()) == (52, 194)
    second = track.rect_for(19 * 60, 20 * 60, column=1, columns=2)
    assert (second.left(), second.width()) == (52 + 98, 96)


def test_a_turned_card_reads_minutes_along_the_card_not_the_screen() -> None:
    card = LinearTrack(2, QRectF(0, 0, 100, 1020), turn=90, first=6 * 60, last=23 * 60)
    # Turned a quarter clockwise about its centre (50, 510): the card's top now points left.
    top = card.point_for(6 * 60)
    assert (round(top.x()), round(top.y())) == (560, 510)
    assert round(card.minute_at(QPointF(560 - 300, 510))) == 11 * 60
    assert card.contains(QPointF(300, 510)) and not card.contains(QPointF(50, 100))


def test_snapping_is_to_the_step_the_student_chose() -> None:
    assert [snap(m, 15) for m in (1147, 1148, 1152.4, 1153)] == [1140, 1155, 1155, 1155]
    assert [snap(m, 5) for m in (1057, 1057.6, 1102.4, 1103)] == [1055, 1060, 1100, 1105]


def test_overlapping_spans_get_a_column_each_and_equal_spans_still_do() -> None:
    assert overlap_columns([(420, 480), (450, 510), (720, 750)]) == [(0, 2), (1, 2), (0, 1)]
    assert overlap_columns([(480, 540), (480, 540)]) == [(0, 2), (1, 2)]


def test_a_midnight_track_puts_00_00_at_its_top_edge() -> None:
    track = LinearTrack(0, QRectF(0, 0, 100, 1440))
    assert track.minute_at(QPointF(50, 0)) == 0
    assert track.minute_at(QPointF(50, 1440)) == 24 * 60
