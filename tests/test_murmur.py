"""Running the room from the tracked config."""

from __future__ import annotations

import io
import stat
from pathlib import Path

import pytest

from hands_free import murmur
from hands_free.murmur import (
    DATABASE_NAME,
    PASSWORD,
    Layout,
    read_or_make_password,
    run,
    runtime_config,
    tracked_config,
)

PASSWORD_OK = "Abc-def_ghi-123"  # noqa: S105, a made-up one for the tests


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_layout_follows_the_xdg_directories(tmp_path: Path):
    layout = Layout.from_environment(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
        }
    )
    assert layout.state_dir == tmp_path / "state" / "hands-free" / "murmur"
    assert (
        layout.password_file == tmp_path / "config" / "hands-free" / "murmur-password"
    )
    assert layout.config_file == layout.state_dir / "murmur.ini"
    assert layout.database == layout.state_dir / DATABASE_NAME


@pytest.mark.parametrize("unset", [{}, {"XDG_STATE_HOME": "", "XDG_CONFIG_HOME": ""}])
def test_the_layout_falls_back_to_the_home_directory(
    tmp_path: Path, unset: dict[str, str]
):
    layout = Layout.from_environment({"HOME": str(tmp_path), **unset})
    assert layout.state_dir == tmp_path / ".local" / "state" / "hands-free" / "murmur"
    assert (
        layout.password_file == tmp_path / ".config" / "hands-free" / "murmur-password"
    )


def test_the_added_settings_come_before_any_section():
    config = runtime_config(
        "port=64738\n[Ice]\nIce.Warn.UnknownProperties=1\n", PASSWORD_OK
    )
    before_section = config.split("[Ice]")[0]
    assert f"database={DATABASE_NAME}\n" in before_section
    assert f"serverpassword={PASSWORD_OK}\n" in before_section
    assert config.endswith("port=64738\n[Ice]\nIce.Warn.UnknownProperties=1\n")


@pytest.mark.parametrize(
    "line",
    ["database=/var/lib/murmur.sqlite", "serverpassword=hunter2", "  Database = x"],
)
def test_a_tracked_config_may_not_set_what_is_added(line: str):
    with pytest.raises(ValueError, match="tracked config sets"):
        runtime_config(f"port=64738\n{line}\n", PASSWORD_OK)


def test_a_commented_out_setting_is_not_a_setting():
    assert runtime_config("; database=elsewhere\n", PASSWORD_OK)


@pytest.mark.parametrize(
    "password",
    [
        "",
        "short-pw",
        "has,a,comma-in-it",
        "has a space in it",
        'has"quote"marks',
        "é" * 16,
    ],
)
def test_a_password_outside_the_safe_characters_is_refused(password: str):
    with pytest.raises(ValueError, match="server password"):
        runtime_config("port=64738\n", password)


def test_the_tracked_config_leaves_the_added_settings_out():
    assert runtime_config(tracked_config(), PASSWORD_OK)


def test_the_tracked_config_is_settings_comments_and_blank_lines():
    for line in tracked_config().splitlines():
        assert not line or line.startswith(";") or "=" in line, line


def test_a_missing_password_is_made_and_kept_private(tmp_path: Path):
    path = tmp_path / "config" / "hands-free" / "murmur-password"
    password, made = read_or_make_password(path)
    assert made
    assert PASSWORD.fullmatch(password)
    assert path.read_text(encoding="utf-8") == f"{password}\n"
    assert mode(path) == 0o600
    assert mode(path.parent) == 0o700


def test_an_existing_password_is_read_and_left_alone(tmp_path: Path):
    path = tmp_path / "murmur-password"
    path.write_text(f"{PASSWORD_OK}\n", encoding="utf-8")
    assert read_or_make_password(path) == (PASSWORD_OK, False)


@pytest.fixture
def layout(tmp_path: Path) -> Layout:
    return Layout(tmp_path / "state", tmp_path / "config" / "murmur-password")


def test_without_murmur_installed_it_says_how_to_install_it(layout: Layout):
    out = io.StringIO()
    assert run(layout, which=lambda _: None, execute=_never, out=out) == 1
    assert "sudo apt install mumble-server" in out.getvalue()
    assert "systemctl disable --now mumble-server" in out.getvalue()
    assert not layout.password_file.exists()


def test_it_writes_the_config_and_becomes_murmur(layout: Layout):
    calls: list[tuple[str, list[str]]] = []
    out = io.StringIO()
    status = run(
        layout,
        which=lambda name: f"/usr/bin/{name}",
        execute=lambda path, argv: calls.append((path, argv)),
        out=out,
    )
    assert status == 0
    assert calls == [
        (
            "/usr/bin/mumble-server",
            ["/usr/bin/mumble-server", "-ini", str(layout.config_file), "-fg"],
        )
    ]
    password = layout.password_file.read_text(encoding="utf-8").strip()
    config = layout.config_file.read_text(encoding="utf-8")
    assert f"serverpassword={password}\n" in config
    assert config.endswith(tracked_config())
    assert mode(layout.config_file) == 0o600
    assert "Made a server password" in out.getvalue()


def test_a_second_start_reuses_the_password_quietly(layout: Layout):
    def start() -> str:
        out = io.StringIO()
        run(layout, which=lambda n: n, execute=lambda *_: None, out=out)
        return out.getvalue()

    start()
    first = layout.password_file.read_text(encoding="utf-8")
    assert start() == ""
    assert layout.password_file.read_text(encoding="utf-8") == first


def test_the_tracked_config_ships_inside_the_package():
    assert (Path(murmur.__file__).parent / "murmur.ini").read_text(
        encoding="utf-8"
    ) == tracked_config()


def _never(*_: object) -> None:
    raise AssertionError("Murmur should not have been started")
