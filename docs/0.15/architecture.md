# 0.15 hours engine: as built

Every design draws its own Day and Week, and Month is shared, but there is one way to move time
around: one `Hand` per window runs every gesture, and surfaces only lay out, paint and say what is
under a point. This file describes the engine as it ships in 0.15.0.
The code in `desktop/native/hours/` is the authority; each module's docstring says what it owns.

## Modules

| Module | Owns |
| --- | --- |
| `geometry.py` | Where minutes are. `Span(day, start, end)`, `snap` (to a step), `DRAG_STEPS`, `overlap_columns`, and the `Track` contract with two shapes: `LinearTrack(day, area, axis, first, last, turn)` runs down or across, covers part of a day or all of it, and can be tilted; `DialTrack(day, centre, inner, outer, first, last, sweep)` is My day's ring. Pure arithmetic, tested with numbers. |
| `hand.py` | What the pointer is doing. `Hand`, `Held`, `Preview`, `Verdict`, and the changes it reports: `Move`, `Place`, `Create`, `MoveDate`. The threshold between a tap and a drag, finding the surface under the pointer, snapping to its `step` with the grab offset, the track's own bounds, the window's judge, the words that follow the pointer, dwell auto-scroll, Escape, losing the window, and holding renders. |
| `canvas.py` | Painted hours. `HoursCanvas` lays out tracks, draws rules, blocks, the held block where it would land, the create ghost, the free-time hint and the now line through a `BlockPainter`, and answers the rig. A design replaces the painter, not the gestures. |
| `zoom.py` | Hours that scroll and zoom. `HoursScroll(canvas, Scale, length_for, name=, gutter=, axis=)` zooms about the pointer (Ctrl and the wheel) or the middle (two corner buttons, and Ctrl with `=`, `-`, `0`, which are the window's shortcuts for whichever hours it shows, wherever the keyboard is), keeps a header beside the hours (above them when time runs down, left of them when it runs across), and remembers each surface's level in the look file. |
| `chips.py` | `TrayChip`: homework with no time, anywhere in a design, dragged onto any hours; a click opens it. |
| `month.py` | Month as Daily Scheduler draws it. `month_cells` builds each date's chips; `MonthCanvas` paints them and carries a chip with a time to another date; `MonthGrid` is what Today's app and every design show. |
| `classic.py` | Today's app's Day and Week, the worked example a design copies from. |

## The contract a surface keeps

A surface is any widget with `takes_blocks = True` and `track_at(point) -> Track | None`, in its own
coordinates. `HoursCanvas` is one; the test design in `desktop/tests/test_hours_targets.py` shows a
dial surface in a dozen lines. The hand finds the surface under the pointer with
`QApplication.widgetAt` and up the parents, then tries overlapping siblings, so tilted cards work.
Nothing registers, so nothing goes stale when a design re-renders.

A month is any widget with `takes_dates = True` and `date_at(point) -> str | None`.

For the rig and the tests, hours surfaces also offer `track_for(day, minute)`, `point_for(day,
minute)`, `block_rect(block_id, day)`, `day_name(day)`, `reveal(day, first, last)`, `in_view(day,
minute)` and `held_words()`; months offer `index_of(iso)`, `chip_boxes(index)`, `chip_words(block_id,
iso)`, `chip_point(block_id, iso)`, `cell_point(iso)` and `reveal(iso)`. All points are global.

## How a design uses it

```python
class MissionView(LayoutView):
    def __init__(self, parent=None, *, hand=None):
        super().__init__(parent, hand=hand)          # the window's hand; never make one
        self.scroll: HoursScroll | None = None
        self.tray = TrayChip(self.hand, waiting)       # anywhere in the design

    def render(self, scene, week_changed):
        if self.scroll is None:
            # Made in the first render, not in __init__: the window hands a design the remembered
            # zoom levels after making it. Made once, so the hours keep their place on every render.
            def lanes(area: QRectF) -> list[LinearTrack]:
                tall = area.height() / 7
                return [LinearTrack(day, QRectF(area.left(), area.top() + day * tall, area.width(),
                                                tall), Axis.ACROSS) for day in range(7)]

            self.week = HoursCanvas(self.hand, MissionPainter(scene.tokens), lanes, header=24)
            self.scroll = self.keep_zoom(HoursScroll(self.week, Scale("mission.week", (32, 48, 64, 96), 48),
                                                     lambda px: 24 * px + 16, name="missionWeek",
                                                     gutter=72, axis=Axis.ACROSS))
            self.scroll.set_header(lane_names)         # stays beside the lanes while hours scroll
        self.week.set_painter(MissionPainter(scene.tokens))
        self.week.set_week(scene.week.occurrences, scene.today, scene.minute)

    # Month: keep calling render_month; it shows MonthGrid in this design's tokens.
```

`LayoutView.hours_surfaces()` and `month_surfaces()` already list every visible surface for the rig,
and `keep_zoom` opens a design's hours at the level this device last chose and hands a new one to the
window to keep.
A design never writes a threshold, a snap, a judge, a save or a `QDrag`;
`scripts/mutations/targets.json` proves the shared rules were not copied, and
`test_nothing_in_the_app_uses_system_drag_and_drop` fails if Qt's system drag and drop comes back
anywhere in `desktop/native/`.

## What the window does

```python
self.hand = Hand(self._hand_judge, self)            # the one rule for hours: span_problem and due
self.hand.step = drag_step(preferences.get("drag_step_min"))   # in _sync_chrome, on every change
self.hand.date_judge = self._date_judge             # the one rule for dates: session.date_problem
self.hand.committed.connect(self._apply_change)     # Move, Place, Create or MoveDate
self.hand.refused.connect(self.session._say)
self.hand.holding.connect(self._hold_renders)       # from the press to the release
```

- A change goes to the controller: `_move_block` (waiting while a save is running), `place_session`,
  `_create_range`, or `move_to_date` (one write of both weeks through `/api/changes`, retry-safe,
  shown only once the server accepts it; a drop after a save that failed is refused in words).
- Once a change's save lands, the toast says what it did ("Moved History essay to Fri 18:00."),
  with Undo for that one change. Since 0.16 it floats over the foot of the hours rather than
  taking a row of the page, so its coming and going never moves the hours. One that lands while
  something is held waits for the release, and it goes once a later save makes its step no longer
  the last, or on a switch to another view.
- Renders are held from the press, so nothing the press started on is deleted by a re-render; the
  last scene arrives on release.
- Asking for anywhere else while a block is held (another view, week, day or design) cancels the
  hold, as Escape does. A save or a clock tick landing mid-drag is not asking for anywhere else.

## Rules the engine keeps

- A drag moves in the student's step: 5 minutes, or 15 if their `drag_step_min` preference says so.
  A move, a resize and a new block land on a multiple of the step, even a block that started off it;
  a resized edge stays at least a step from the other one. A block keeps the distance between the
  pointer and its edge, so nothing jumps on the first move. Typed times are any minute.
- Every bound is the track's own: a move, a resize or a new block stops at the end of the tile or
  column it is on, not at midnight. A block longer than its track starts where the track starts.
- Resize from within 7 pixels of an edge of a block at least 20 pixels long, but never more than a
  fifth of it, so a 15-minute block moves when pressed a quarter, half or three quarters in.
- A press that never becomes a drag is a tap, and a tap on a block opens it (0.16). A double-click
  opens one editor, not two, and its second click never lands on the editor the first opened. A
  right-click selects the block under the pointer and asks for its menu through the hand
  (`menu_requested`); it never picks the block up.
- After a new week or plan, `HoursCanvas.set_week` slides each block that moved from where it was
  and fades in the new ones, unless animations are off; a block just dropped does not slide.
- Overlaps are allowed and drawn side by side.
- The pointer resting 300 ms within 36 pixels of a scroll area's edge scrolls it; passing through
  does not. With scroll areas inside one another, the nearest one that has room to scroll that way
  does: at the bottom of a page over sideways hours, the page scrolls down.
- A long block's name stays in sight at the start of what shows, whichever way time runs: at the
  top of a column, at the left of a lane. It is placed from the viewport, not from the part being
  repainted.
- Month: a chip with a time can be carried; a deadline cannot. While it is held, the date under the
  pointer is outlined, and outlined in red with the reason when the date says no. A chip let go on
  its own date, or clicked, moves nothing; a click opens the date's Day.
- Nothing in the engine keeps a Python reference to its Qt parent. A widget left in a reference
  cycle is freed by the garbage collector at a moment of its choosing, which once hung the app in
  the middle of a paint.

## How it is proven

Unit tests (`test_hours_geometry`, `test_hours_hand`, `test_hours_zoom`, `test_hours_targets`,
`test_hours_month`, `test_classic_hours`) send Qt events and prove the rules. The rig
(`scripts/rig/drive.py`) drives the real pointer on a hidden desktop and reads the week back from the
server: Today's app passes Day 14/14, Week 17/17 and Month 9/9, and every design and both My day
screens pass theirs. The `rig` job in `.github/workflows/verify.yml` runs Today's app's Day and Week
on every push under Xvfb and Openbox; it first ran on GitHub on 25 September, 14/14 and 17/17.
`scripts/mutate.py` breaks one rule at a time; every spec in `scripts/mutations/` is caught.

## Why this shape

One window-level hand, not an engine per canvas with a broker for drags that cross widgets. Two
copies of the gesture policy (snap, grab offset, judge, labels, auto-scroll) are where the 0.14 bugs
lived; with one, a design brings tracks and paint and gets every gesture, the judge and the rig
interface. From the per-canvas idea we kept this: a canvas owns several tracks in one painted
widget, so a week of columns or lanes is one widget with one paint pass. Accepted in exchange: a
canvas repaints on every change to the held block, one gesture at a time per window, and
`widgetAt` on every move instead of a registry. `QGraphicsView` scenes were rejected because every
design's widgets and stylesheets would have been rewritten as scene items; system drag and drop
because it is where Wayland and X11 differ and where the rig cannot see what the student sees.

## Open

- Nothing. Every design, Today's app and both My day screens move blocks through the one hand, and
  the old drag path is gone.
