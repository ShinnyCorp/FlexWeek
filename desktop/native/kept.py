"""Keep me signed in: the session a student chose to keep on this computer, for one database.

The token is the opaque one the server set as a cookie. Anyone who can read this file can already read
the database it opens, so on a student's own computer it adds no reach. The choice exists for a shared
computer, and Log out removes the file. The server still ends the session seven days after sign-in.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path

# secrets.token_urlsafe(32) in backend/storage.py. Anything else is not a session, and it goes into a
# cookie header, so it is refused rather than sent.
_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,128}")


class KeptSession:
    def __init__(self, path: Path) -> None:
        self.path = path
        # Someone has signed in here before, kept or not. Log out forgets the session, not this, so
        # the sign-in card can greet a first launch differently from a return.
        self.seen = path.with_name(path.stem + ".seen")

    def signed_in_before(self) -> bool:
        return self.seen.exists() or self.path.exists()

    def note_sign_in(self) -> None:
        self.seen.parent.mkdir(parents=True, exist_ok=True)
        self.seen.touch()

    def token(self) -> str | None:
        try:
            stored = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None
        token = stored.get("token") if isinstance(stored, dict) else None
        return token if isinstance(token, str) and _TOKEN.fullmatch(token) else None

    def keep(self, token: str) -> None:
        if not _TOKEN.fullmatch(token):
            raise ValueError("That is not a FlexWeek session.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        # Created readable by this user only, then moved into place, so no one else ever sees it and a
        # crash never leaves half a file.
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, "w") as out:
            json.dump({"token": token}, out)
        os.replace(temporary, self.path)

    def forget(self) -> None:
        self.path.unlink(missing_ok=True)
