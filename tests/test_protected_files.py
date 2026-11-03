"""The append-only check over `DECISIONS.md` and the research record."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from protected_files import (
    IN_PLACE_MARKER,
    PROTECTED_PATHS,
    commit_subject,
    main,
    override_requested,
    parse_removals,
)

INSERTION = """\
diff --git a/DECISIONS.md b/DECISIONS.md
--- a/DECISIONS.md
+++ b/DECISIONS.md
@@ -120,0 +121,2 @@
+### ADR-099
+Something new.
"""

REWRITE = """\
diff --git a/DECISIONS.md b/DECISIONS.md
--- a/DECISIONS.md
+++ b/DECISIONS.md
@@ -42 +42 @@
-Overhead stays under 1.5 s.
+Overhead stays under 2.5 s.
"""

DELETION = """\
diff --git a/research/voice-room-switchboard.md b/research/voice-room-switchboard.md
--- a/research/voice-room-switchboard.md
+++ /dev/null
@@ -1,2 +0,0 @@
-# Research
-Bar: under 5% wrong words.
"""

# A removed line whose own text starts with `--` reaches the parser as `--- ...`,
# which is also the shape of a file header. The second file is here so a header read
# by mistake has somewhere wrong to point.
DASHES_IN_CONTENT = """\
diff --git a/DECISIONS.md b/DECISIONS.md
--- a/DECISIONS.md
+++ b/DECISIONS.md
@@ -7,2 +7 @@
--- a/somewhere/else.md
-+++ b/somewhere/else.md
+A replacement.
diff --git a/research/somewhere-else.md b/research/somewhere-else.md
--- a/research/somewhere-else.md
+++ b/research/somewhere-else.md
@@ -3 +3 @@
-Bluetooth capture is unverified.
+Bluetooth capture is verified.
"""


def test_a_pure_insertion_removes_nothing():
    assert parse_removals(INSERTION) == []


def test_an_empty_diff_removes_nothing():
    assert parse_removals("") == []


def test_a_rewritten_line_is_reported_where_it_stood():
    (removal,) = parse_removals(REWRITE)
    assert removal.path == "DECISIONS.md"
    assert removal.line_number == 42
    assert removal.text == "Overhead stays under 1.5 s."


def test_deleting_the_file_reports_every_line_under_its_old_path():
    removals = parse_removals(DELETION)
    assert [r.line_number for r in removals] == [1, 2]
    assert {r.path for r in removals} == {"research/voice-room-switchboard.md"}


CONTEXT_INSIDE_A_HUNK = """\
diff --git a/DECISIONS.md b/DECISIONS.md
--- a/DECISIONS.md
+++ b/DECISIONS.md
@@ -40,4 +40,4 @@
 Kept above.
-Overhead stays under 1.5 s.
+Overhead stays under 2.5 s.
 Kept below.
\\ No newline at end of file
"""


def test_context_inside_a_hunk_moves_the_line_count():
    # `diff.interHunkContext` or `GIT_DIFF_OPTS` can put context lines into a diff
    # asked for with none, and each one pushes the next removal a line further down.
    (removal,) = parse_removals(CONTEXT_INSIDE_A_HUNK)
    assert removal.line_number == 41


def test_header_shaped_content_stays_inside_its_own_hunk():
    removals = parse_removals(DASHES_IN_CONTENT)
    assert [(r.path, r.line_number) for r in removals] == [
        ("DECISIONS.md", 7),
        ("DECISIONS.md", 8),
        ("research/somewhere-else.md", 3),
    ]


@pytest.mark.parametrize(
    ("subjects", "taken"),
    [
        ([f"docs: fix a typo {IN_PLACE_MARKER}"], True),
        (["docs: fix a typo"], False),
        ([], False),
        (["docs: adr-002", f"docs: fix a typo {IN_PLACE_MARKER}"], True),
    ],
)
def test_one_marked_subject_anywhere_takes_the_exception(subjects, taken: bool):
    assert override_requested(subjects) is taken


@pytest.mark.parametrize(
    ("message", "subject"),
    [
        ("docs: fix a typo [in-place]", "docs: fix a typo [in-place]"),
        (f"# {IN_PLACE_MARKER}\n\ndocs: fix a typo\n", "docs: fix a typo"),
        ("", ""),
    ],
)
def test_the_subject_is_what_the_marker_is_read_from(message: str, subject: str):
    assert commit_subject(message) == subject


def test_the_subject_skips_blanks_and_comments():
    assert commit_subject("\n# a comment\n\nfeat: the subject\nmore\n") == (
        "feat: the subject"
    )


def git(repository: Path, *arguments: str) -> None:
    """Run git in `repository`, failing the test on a non-zero exit."""
    subprocess.run(("git", "-C", str(repository), *arguments), check=True)


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository on `main` with one protected file already landed."""
    # CI runs the tests inside a pull request, which sets this for the whole process.
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    git(tmp_path, "init", "-b", "main", "--quiet")
    git(tmp_path, "config", "user.email", "noreply@github.com")
    git(tmp_path, "config", "user.name", "DanBoringName")
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    for path in PROTECTED_PATHS:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(
            "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.05.\n"
        )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "--quiet", "-m", "docs: the first decision")
    return tmp_path


def stage(repository: Path, text: str) -> None:
    """Write the protected file and stage it."""
    (repository / PROTECTED_PATHS[0]).write_text(text)
    git(repository, "add", "-A")


def test_a_clean_index_passes(repository: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(repository)
    assert main([]) == 0


@pytest.mark.parametrize("disguise", ["binary attribute", "nul byte", "textconv"])
def test_a_rewrite_still_fails_when_git_would_not_show_it_as_text(
    repository: Path, monkeypatch: pytest.MonkeyPatch, disguise: str
):
    monkeypatch.chdir(repository)
    rewritten = "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n"
    if disguise == "binary attribute":
        (repository / ".gitattributes").write_text(f"{PROTECTED_PATHS[0]} -diff\n")
    elif disguise == "nul byte":
        rewritten += "\x00"
    else:
        (repository / ".gitattributes").write_text(f"{PROTECTED_PATHS[0]} diff=blank\n")
        git(repository, "config", "diff.blank.textconv", "true")
    # Each of these makes `git diff` print "Binary files differ" or nothing at all,
    # with no removed line for the check to see.
    stage(repository, rewritten)
    assert main([]) == 1


def test_fused_hunks_report_each_line_where_it_stood(
    repository: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.chdir(repository)
    git(repository, "config", "diff.interHunkContext", "10")
    stage(repository, "# Decision log\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    assert main([]) == 1
    printed = capsys.readouterr().out
    assert f"{PROTECTED_PATHS[0]}:1  # Decisions" in printed
    assert f"{PROTECTED_PATHS[0]}:4  The bar is 0.05." in printed


def test_merging_main_in_brings_its_landed_corrections_along(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/next")
    (repository / "notes.md").write_text("Branch work.\n")
    git(repository, "add", "-A")
    git(repository, "commit", "--quiet", "-m", "docs: branch work")
    git(repository, "switch", "--quiet", "main")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    git(
        repository,
        "commit",
        "--quiet",
        "-m",
        f"docs: correct the bar {IN_PLACE_MARKER}",
    )
    git(repository, "switch", "--quiet", "feat/next")
    git(repository, "merge", "--quiet", "--no-ff", "--no-commit", "main")
    # The correction is already on `main`, so the merge rewrites nothing that landed.
    message = repository / "COMMIT_EDITMSG"
    message.write_text("Merge branch 'main' into feat/next\n")
    assert main([str(message)]) == 0


def test_merging_in_an_unlanded_rewrite_still_fails(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/other")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    git(repository, "commit", "--quiet", "-m", "docs: correct the bar")
    git(repository, "switch", "--quiet", "-c", "feat/next", "main")
    git(repository, "merge", "--quiet", "--no-ff", "--no-commit", "feat/other")
    message = repository / "COMMIT_EDITMSG"
    message.write_text("Merge branch 'feat/other' into feat/next\n")
    assert main([str(message)]) == 1


def test_a_marker_on_the_merged_branch_counts(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/other")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    git(
        repository,
        "commit",
        "--quiet",
        "-m",
        f"docs: correct the bar {IN_PLACE_MARKER}",
    )
    git(repository, "switch", "--quiet", "-c", "feat/next", "main")
    git(repository, "merge", "--quiet", "--no-ff", "--no-commit", "feat/other")
    message = repository / "COMMIT_EDITMSG"
    message.write_text("Merge branch 'feat/other' into feat/next\n")
    assert main([str(message)]) == 0


def test_appending_to_a_landed_file_passes(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    stage(
        repository,
        "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.05.\n"
        "\n### ADR-002 2026-02-01\nADR-001's bar was replaced.\n",
    )
    assert main([]) == 0


def test_rewriting_a_landed_line_fails(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    assert main([]) == 1


def test_the_marker_lets_a_rewrite_through(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    message = repository / "COMMIT_EDITMSG"
    message.write_text(f"docs: correct the heading {IN_PLACE_MARKER}\n")
    assert main([str(message)]) == 0


def test_a_message_without_the_marker_still_fails(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    message = repository / "COMMIT_EDITMSG"
    message.write_text("docs: correct the bar\n")
    assert main([str(message)]) == 1


def test_a_block_drafted_on_a_branch_can_still_be_reworked(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/next")
    stage(
        repository,
        "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.05.\n"
        "\n### ADR-002 2026-02-01\nDarft.\n",
    )
    git(repository, "commit", "--quiet", "-m", "docs: adr-002")
    stage(
        repository,
        "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.05.\n"
        "\n### ADR-002 2026-02-01\nDraft.\n",
    )
    # The typo was fixed in a line that never reached `main`, so nothing a reader
    # could have seen was rewritten.
    assert main([]) == 0


def test_rewriting_a_landed_line_from_a_branch_fails(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/next")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    assert main([]) == 1


def test_a_declared_path_that_is_not_tracked_fails_loudly(
    repository: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.chdir(repository)
    git(repository, "rm", "--quiet", PROTECTED_PATHS[1])
    # Nothing is rewritten in the file that remains, so the run would otherwise pass
    # while one entry in the list silently guarded nothing.
    assert main([]) == 1
    assert "not tracked" in capsys.readouterr().out


def test_moving_a_protected_file_out_from_under_the_rule_fails(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "mv", PROTECTED_PATHS[0], "ADRS.md")
    # The pathspec names the source, so a move reads as a whole-file deletion however
    # the diff is configured. Every line of it counts as rewritten, which is the
    # intended answer rather than an accident of the shape.
    assert main([]) == 1


def test_the_override_survives_the_next_commit_on_the_branch(
    repository: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/next")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    message = repository / "COMMIT_EDITMSG"
    message.write_text(f"docs: correct the bar {IN_PLACE_MARKER}\n")
    assert main([str(message)]) == 0
    git(
        repository,
        "commit",
        "--quiet",
        "-m",
        f"docs: correct the bar {IN_PLACE_MARKER}",
    )
    # The diff against the merge base still carries that removal. A plain append after
    # it must not have to call itself an in-place edit to be recorded.
    stage(
        repository,
        "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n"
        "\n### ADR-002 2026-02-01\nAppended.\n",
    )
    message.write_text("docs: adr-002\n")
    assert main([str(message)]) == 0
    assert "allowed by" in capsys.readouterr().out


def test_the_ci_shape_honours_a_marker_already_on_the_branch(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/next")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    git(
        repository,
        "commit",
        "--quiet",
        "-m",
        f"docs: correct the bar {IN_PLACE_MARKER}",
    )
    # No message file, which is how the job runs it. The exception has to survive into
    # CI or the hook lets a commit through that the job then refuses for good.
    assert main([]) == 0


def test_the_ci_shape_still_refuses_an_unmarked_branch(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/next")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    git(repository, "commit", "--quiet", "-m", "docs: correct the bar")
    assert main([]) == 1


def test_the_base_branch_is_read_from_the_environment(
    repository: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(repository)
    # `feat/lower` rewrites a landed line and owns that decision. `feat/upper` stacks on
    # it and only appends.
    git(repository, "switch", "--quiet", "-c", "feat/lower")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    git(repository, "commit", "--quiet", "-m", "docs: correct the bar")
    git(repository, "switch", "--quiet", "-c", "feat/upper")
    stage(
        repository,
        "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n"
        "\n### ADR-002 2026-02-01\nAppended.\n",
    )
    git(repository, "commit", "--quiet", "-m", "docs: adr-002")
    # Against `main` the cumulative diff carries the rewrite `feat/upper` never made,
    # and there is no subject on this branch that could clear it.
    assert main([]) == 1
    monkeypatch.setenv("GITHUB_BASE_REF", "feat/lower")
    assert main([]) == 0


def test_the_ci_shape_refuses_to_pass_when_it_compared_nothing(
    repository: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.chdir(repository)
    git(repository, "switch", "--quiet", "-c", "feat/next")
    git(repository, "branch", "--quiet", "-D", "main")
    stage(repository, "# Decisions\n\n### ADR-001 2026-01-01\nThe bar is 0.10.\n")
    # With no landed ref the diff against `HEAD` is what a fresh checkout would produce:
    # empty. Passing on that reports green having looked at nothing.
    assert main([]) == 1
    assert "nothing was compared" in capsys.readouterr().out
