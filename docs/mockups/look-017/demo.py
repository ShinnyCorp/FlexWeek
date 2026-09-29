"""Open the 0.17 mock-up of the revised designs and looks in the system browser.

Run from the repo root:

    python docs/mockups/look-017/demo.py

It serves the repository read-only on 127.0.0.1 (the page uses the app's own Inter from
desktop/assets/fonts) and opens the mock-up. Ctrl+C stops it. This is a mock-up, not FlexWeek: it
reads and writes no FlexWeek data. Picks are kept in the browser and shown under "Your picks".
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import socketserver
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = "docs/mockups/look-017/index.html"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass


def main() -> int:
    handler = functools.partial(Quiet, directory=str(ROOT))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        url = f"http://127.0.0.1:{server.server_address[1]}/{PAGE}"
        print(f"FlexWeek 0.17 mock-up: {url}  (Ctrl+C stops it)")
        webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
