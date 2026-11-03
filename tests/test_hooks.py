"""The pattern hooks in `.pre-commit-config.yaml`, against what each must refuse."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
import yaml

CONFIG = Path(__file__).resolve().parent.parent / ".pre-commit-config.yaml"


def pygrep_hook(hook_id: str) -> tuple[re.Pattern[bytes], bool]:
    """A pygrep hook's pattern compiled as pre-commit compiles it, and its mode."""
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo["hooks"]:
            if hook["id"] == hook_id:
                assert hook["language"] == "pygrep"
                multiline = "--multiline" in hook.get("args", [])
                flags = re.MULTILINE | re.DOTALL if multiline else 0
                return re.compile(hook["entry"].encode(), flags), multiline
    raise LookupError(hook_id)


def refused(hook_id: str, text: str) -> bool:
    """Whether the hook would fail on a file holding `text`."""
    pattern, multiline = pygrep_hook(hook_id)
    data = text.encode()
    if multiline:
        return pattern.search(data) is not None
    return any(pattern.search(line) for line in io.BytesIO(data))


@pytest.mark.parametrize(
    "message",
    [
        "feat: route\n\nwith a body\n",
        "feat: route\n\nCo-Authored-By: someone <noreply@example.com>\n",
        "feat: route\nstraight after the subject\n",
        "feat: route\n\nno newline at the end",
        "feat: route\r\n\r\nwith a body\r\n",
        "feat: route\n\n  # indented, so git keeps it\n",
    ],
)
def test_a_body_is_refused(message: str):
    assert refused("one-line-commit-message", message)


@pytest.mark.parametrize(
    "message",
    [
        "feat: route\n",
        "feat: route",
        "feat: route\r\n",
        "feat: route\n\n\n \t\n",
        "feat: route\n\n# Please enter the commit message for your changes.\n",
        "feat: route\n# ------------------------ >8 ------------------------\n"
        "diff --git a/x b/x\n+added\n",
    ],
)
def test_a_subject_alone_passes(message: str):
    assert not refused("one-line-commit-message", message)


@pytest.mark.parametrize(
    "text",
    [
        "/home/someone/x",
        "HOME=/home/someone",
        '"/home/someone"',
        "cd /home/someone",
        "file:///home/someone/notes",
        r"\\wsl.localhost\Ubuntu\home\someone\x",
        "/home/runnerx/",
        r"C:\Users\someone",
        r"C:\\Users\\someone",
        "c:/users/someone",
        "/mnt/c/Users/someone/",
        r"C:\Users\Publicity",
    ],
)
def test_a_personal_path_is_refused(text: str):
    assert refused("no-personal-paths", text)


@pytest.mark.parametrize(
    "text",
    [
        "/home/runner/work",
        "/home/runner",
        r"C:\Users\Public",
        r"C:\Users\Public\Desktop",
        "/mnt/c/Users/Public/",
        "~/hands-free",
        "https://www.home-assistant.io/voice_control/android/",
        "https://example.com/home/docs",
        "the Home key on the watch",
    ],
)
def test_text_that_only_looks_like_a_path_passes(text: str):
    assert not refused("no-personal-paths", text)
