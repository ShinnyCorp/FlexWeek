"""A Spotify alarm plays in the student's own Spotify app, is never silent while it starts, and stops
when the alarm does. Every test talks to a pretend Spotify: none may reach a real one."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from desktop.native import spotify
    from desktop.native.settings import AlarmRingDialog
    from desktop.native.spotify import LISTENING, SHOWN, STARTING, SpotifyPlayer
    from desktop.tests.logic_support import wait_until

TRACK = "https://open.spotify.com/track/4LUJzSLpBtgH3dpOH7J7Nf?si=abc123"
PLAYLIST = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
METADATA = (
    '{"type":"a{sv}","data":{"mpris:trackid":{"type":"s","data":"/com/spotify/track/4LUJzSLpBtgH3dpOH7J7Nf"},'
    '"xesam:title":{"type":"s","data":"Voices of the Chord"},'
    '"xesam:artist":{"type":"as","data":["Sawano Hiroyuki","mpi"]}}}'
)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-spotify-test"])


class PretendSpotify:
    """The Spotify app on the session bus, as far as FlexWeek can see it."""

    def __init__(self, running: bool = True, plays: bool = True, starts_after: int = 0) -> None:
        self.is_running, self.plays, self.starts_after = running, plays, starts_after
        self.asked: list[str] = []
        self.paused = 0
        self._is_playing = False

    def reachable(self) -> bool:
        return True

    def running(self) -> bool:
        if not self.is_running and self.starts_after:
            self.starts_after -= 1
            self.is_running = self.starts_after == 0
        return self.is_running

    def play(self, address: str) -> None:
        self.asked.append(address)
        self._is_playing = self.plays

    def playing(self) -> bool:
        return self._is_playing

    def pause(self) -> None:
        self.paused += 1
        self._is_playing = False

    def now_playing(self) -> tuple[str, str, str]:
        return spotify.read_metadata(METADATA)


def player(remote: Any, keys: list[str] | None = None) -> SpotifyPlayer:
    made = SpotifyPlayer(remote=remote, stop_key=lambda: (keys if keys is not None else []).append("stop"))
    made.grace_ms, made.give_up_ms, made.poll_ms, made.ask_again_ms = 120, 600, 20, 60
    return made


def opening(monkeypatch: pytest.MonkeyPatch, answer: bool = True) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(spotify, "open_address", lambda address: opened.append(address) or answer)
    return opened


def test_a_share_link_becomes_the_apps_own_address() -> None:
    assert spotify.app_address(TRACK) == "spotify:track:4LUJzSLpBtgH3dpOH7J7Nf"
    assert spotify.app_address(PLAYLIST) == "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
    assert spotify.app_address("https://example.com/track/abc") is None


def test_the_song_and_artists_are_read_from_spotifys_answer() -> None:
    assert spotify.read_metadata(METADATA) == (
        "Voices of the Chord",
        "Sawano Hiroyuki, mpi",
        "/com/spotify/track/4LUJzSLpBtgH3dpOH7J7Nf",
    )
    assert spotify.read_metadata("not json") == ("", "", "")
    assert spotify.playing_words("Voices of the Chord", "Sawano Hiroyuki") == (
        "Playing “Voices of the Chord” by Sawano Hiroyuki"
    )
    assert spotify.playing_words("", "") == "Playing in Spotify"


def test_a_running_spotify_is_told_to_play_and_is_heard(qapp: QApplication) -> None:
    app = PretendSpotify()
    made = player(app)
    heard: list[str] = []
    late: list[bool] = []
    made.heard.connect(heard.append)
    made.late.connect(lambda: late.append(True))
    assert made.play(TRACK) == LISTENING
    assert app.asked == ["spotify:track:4LUJzSLpBtgH3dpOH7J7Nf"]
    # Lateness is counted in the player's own polls, so a busy machine only delays the first one.
    wait_until(qapp, lambda: heard, timeout=5)
    assert heard == ["Playing “Voices of the Chord” by Sawano Hiroyuki, mpi"]
    assert late == [], "heard in time, so the tone never rings"


def test_a_spotify_that_is_not_heard_lets_the_tone_ring(qapp: QApplication) -> None:
    app = PretendSpotify(plays=False)
    made = player(app)
    late: list[bool] = []
    made.late.connect(lambda: late.append(True))
    assert made.play(PLAYLIST) == LISTENING
    QTest.qWait(250)
    assert late == [True]
    QTest.qWait(250)
    assert len(app.asked) >= 1


def test_a_spotify_that_is_not_open_is_started_then_told_to_play(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = opening(monkeypatch)
    app = PretendSpotify(running=False, starts_after=3)
    made = player(app)
    heard: list[str] = []
    made.heard.connect(heard.append)
    assert made.play(PLAYLIST) == LISTENING
    assert opened == ["spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"], "opening its address starts the app"
    assert app.asked == []
    QTest.qWait(200)
    assert app.asked == ["spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"], "and once it is up, it is told to play"
    assert heard


def test_stopping_pauses_what_flexweek_started_and_only_that(qapp: QApplication) -> None:
    app = PretendSpotify()
    made = player(app)
    made.stop()
    assert app.paused == 0, "nothing was started, so the student's own music is left alone"
    made.play(TRACK)
    QTest.qWait(60)
    made.stop()
    assert app.paused == 1


def test_where_spotify_cannot_be_asked_a_track_is_opened_and_a_playlist_needs_the_tone(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows: a track starts by itself when opened in the app, and the Stop key stops it. A playlist
    does not start, so it is only shown."""
    opened = opening(monkeypatch)
    keys: list[str] = []
    made = player(spotify.NoRemote(), keys)
    assert made.play(TRACK) == STARTING
    made.stop()
    assert keys == ["stop"]
    assert made.play(PLAYLIST) == SHOWN
    made.stop()
    assert keys == ["stop"], "the Stop key is not pressed for what FlexWeek did not start"
    assert opened == ["spotify:track:4LUJzSLpBtgH3dpOH7J7Nf", "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"]


def test_without_the_spotify_app_the_link_goes_to_the_browser_and_does_not_count_as_playing(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        spotify, "open_address", lambda address: opened.append(address) or address.startswith("https:")
    )
    made = player(spotify.NoRemote())
    assert made.play(TRACK) == SHOWN
    assert opened == ["spotify:track:4LUJzSLpBtgH3dpOH7J7Nf", TRACK]


class Bells:
    def __init__(self) -> None:
        self.rung: list[str] = []
        self.stopped = 0

    def start(self, tone: str, _volume: float) -> bool:
        self.rung.append(tone)
        return True

    def once(self, tone: str, _volume: float) -> bool:
        self.rung.append(tone)
        return True

    def stop(self) -> None:
        self.stopped += 1


def alarm_window(qapp: QApplication, app: Any) -> Any:
    """Just what ringing an alarm uses of the window: its bell, its Spotify, its ringing dialog."""
    from desktop.native.window import NativeWindow

    window = SimpleNamespace(
        _bell=Bells(),
        _spotify=player(app),
        session=SimpleNamespace(preferences={"alert_volume": 60}, spotify_url=lambda value=None: value or ""),
        _alarm_dialog=AlarmRingDialog(None, {"name": "Wake up", "time": "07:00"}, TRACK),
    )
    window._spotify.late.connect(lambda: NativeWindow._spotify_late(window))
    window._spotify.heard.connect(lambda words: NativeWindow._spotify_heard(window, words))
    return window


def test_an_alarm_plays_in_spotify_names_the_song_and_rings_no_tone_once_heard(qapp: QApplication) -> None:
    from desktop.native.window import NativeWindow

    app = PretendSpotify()
    window = alarm_window(qapp, app)
    NativeWindow._ring(window, {"name": "Wake up", "sound": "spotify"}, TRACK)
    assert window._bell.rung == []
    QTest.qWait(80)
    assert window._alarm_dialog.playing.text() == "Playing “Voices of the Chord” by Sawano Hiroyuki, mpi"
    assert window._bell.rung == []


def test_an_alarm_whose_song_does_not_start_rings_the_tone_until_it_does(qapp: QApplication) -> None:
    from desktop.native.window import NativeWindow

    app = PretendSpotify(plays=False)
    window = alarm_window(qapp, app)
    NativeWindow._ring(window, {"name": "Wake up", "sound": "spotify"}, TRACK)
    QTest.qWait(200)
    assert window._bell.rung == ["chime"], "never silent"
    app.plays = True
    QTest.qWait(250)
    assert window._bell.stopped >= 1, "the music takes over from the tone"
    assert window._alarm_dialog.playing.text().startswith("Playing")


def test_on_linux_without_the_spotify_app_the_browser_gets_the_link_and_the_tone_rings(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bus is there but no Spotify is on it, and nothing takes its address: a browser tab, which
    will not play by itself, so the alarm is not counted as heard."""
    opened: list[str] = []
    monkeypatch.setattr(
        spotify, "open_address", lambda address: opened.append(address) or address.startswith("https:")
    )
    made = player(PretendSpotify(running=False))
    assert made.play(TRACK) == SHOWN
    assert opened == ["spotify:track:4LUJzSLpBtgH3dpOH7J7Nf", TRACK]
