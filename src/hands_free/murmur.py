"""Run the room from the tracked config (ADR-2026-11-03-voice-room-switchboard).

`murmur.ini` beside this module holds what is the same on every machine. Two settings
are not. One is where the database lives. The other is the server password, which is a
secret and can't sit in a public repository. `hands-free murmur` writes a copy of the
config with both added into the state directory and runs Murmur in the foreground from
that copy, so stopping the room is Ctrl-C in its terminal.

Murmur resolves a relative path in its config against the config's own directory, so the
database is named rather than given a full path. That was checked against 1.5.517.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TextIO

SERVER = "mumble-server"
"""Murmur's binary, as Ubuntu's `mumble-server` package installs it."""

DATABASE_NAME = "murmur.sqlite"
"""The database's file name, beside the copy of the config that names it."""

UNTRACKED_KEYS = ("database", "serverpassword")
"""The settings this module adds, which the tracked config must therefore leave out."""

PASSWORD = re.compile(r"[A-Za-z0-9_-]{12,}")
"""What a server password may be.

Murmur reads its config through Qt, which treats a comma as a list separator and some
other characters as markup, so a password stays inside the characters
`secrets.token_urlsafe` uses, where no quoting is needed.
"""

PASSWORD_BYTES = 12
"""The randomness in a password this module makes, which comes out as 16 characters."""

Exec = Callable[[str, list[str]], object]
"""Something that replaces this process with a program, as `os.execv` does."""

Which = Callable[[str], str | None]
"""Something that finds a program on `PATH`, as `shutil.which` does."""


@dataclass(frozen=True)
class Layout:
    """Where the room keeps what the repository doesn't track.

    Attributes:
        state_dir: the database and the copy of the config Murmur runs from.
        password_file: the server password, one line, readable by its owner only.
    """

    state_dir: Path
    password_file: Path

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] = os.environ) -> Layout:
        """The XDG base directories, or their defaults under `HOME`.

        Args:
            environ: the environment to read.

        Returns:
            The layout for this user.
        """
        home = Path(environ["HOME"])
        state = Path(environ.get("XDG_STATE_HOME") or home / ".local" / "state")
        config = Path(environ.get("XDG_CONFIG_HOME") or home / ".config")
        return cls(
            state_dir=state / "hands-free" / "murmur",
            password_file=config / "hands-free" / "murmur-password",
        )

    @property
    def config_file(self) -> Path:
        """The copy of the config that Murmur runs from."""
        return self.state_dir / "murmur.ini"

    @property
    def database(self) -> Path:
        """Murmur's database, which also holds its log."""
        return self.state_dir / DATABASE_NAME


def tracked_config() -> str:
    """The config the repository tracks."""
    return resources.files("hands_free").joinpath("murmur.ini").read_text("utf-8")


def runtime_config(tracked: str, password: str) -> str:
    """The tracked config with the database and the server password added.

    The added lines go first. A section header later in the file would otherwise claim
    them.

    Args:
        tracked: the tracked config.
        password: the server password.

    Returns:
        The config Murmur runs from.

    Raises:
        ValueError: the tracked config sets one of the added keys itself, or the
            password is outside the characters `PASSWORD` allows.
    """
    for line in tracked.splitlines():
        key = line.partition("=")[0].strip().lower()
        if key in UNTRACKED_KEYS:
            msg = f"the tracked config sets `{key}`, which is added when Murmur starts"
            raise ValueError(msg)
    if not PASSWORD.fullmatch(password):
        msg = (
            "the server password must be at least 12 letters, digits, `-` or `_`, "
            "because Murmur's config parser treats other characters as markup"
        )
        raise ValueError(msg)
    added = (f"database={DATABASE_NAME}", f"serverpassword={password}")
    return "\n".join((*added, "", tracked))


def read_or_make_password(path: Path) -> tuple[str, bool]:
    """The password in `path`, made and stored there first if the file is missing.

    Args:
        path: the password file.

    Returns:
        The password, and whether it was made just now.
    """
    if path.exists():
        return path.read_text(encoding="utf-8").strip(), False
    password = secrets.token_urlsafe(PASSWORD_BYTES)
    write_private(path, f"{password}\n")
    return password, True


def write_private(path: Path, text: str) -> None:
    """Write `text` to `path`, readable by its owner only, from the moment it exists.

    Args:
        path: the file to write, replaced if it is there.
        text: what goes in it.
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)
    path.chmod(0o600)


def run(
    layout: Layout,
    *,
    which: Which = shutil.which,
    execute: Exec = os.execv,
    out: TextIO | None = None,
) -> int:
    """Write the config Murmur runs from, then become Murmur.

    Args:
        layout: where the database, the config copy and the password live.
        which: finds Murmur's binary.
        execute: replaces this process with Murmur.
        out: where to say what happened, standard output unless given.

    Returns:
        1 when Murmur is not installed. On success this process becomes Murmur and
        nothing returns, unless `execute` is a stand-in that does.
    """
    out = out or sys.stdout
    server = which(SERVER)
    if server is None:
        out.write(
            f"{SERVER} is not installed. Install it with `sudo apt install {SERVER}`, "
            f"then stop the service the package starts, with `sudo systemctl disable "
            f"--now {SERVER}`, so it doesn't hold the port.\n"
        )
        return 1
    password, made = read_or_make_password(layout.password_file)
    if made:
        out.write(
            f"Made a server password in {layout.password_file}. Mumla asks for it "
            f"the first time it joins.\n"
        )
    write_private(layout.config_file, runtime_config(tracked_config(), password))
    execute(server, [server, "-ini", str(layout.config_file), "-fg"])
    return 0
