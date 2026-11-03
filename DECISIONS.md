# Architecture Decisions

Decisions are append-only. Each one records what was chosen and why. A correction or a change of mind is a new ADR that names the one it replaces, and `protected_files.py` refuses an edit to a line that has already landed.

An ADR is named `ADR-YYYY-MM-DD-slug`, from the ISO date it was written and a few words on what it decides. The name is fixed when the ADR is drafted and doesn't change when it lands, so ADRs written on branches in parallel can't claim the same number. Two ADRs never share a slug.

A path inside an ADR is the path as of that ADR's date. `CHANGELOG.md` is where a path goes when it moves.

---

## ADR-2026-11-03-voice-room-switchboard — a voice-room switchboard with one coordinator Claude

**Status:** Accepted, until the Phase 0 kill test says otherwise
**Evidence:** `research/voice-room-switchboard.md`

### Decision

The phone stays on an open-mic voice call to the desktop, and a switchboard daemon in WSL sits on the other end of it. Mumla on the phone connects to a Murmur server on the desktop. The switchboard joins the room as a bot, segments my speech with Silero voice activity detection (VAD), transcribes each utterance with faster-whisper on the desktop's GPU, routes the text, and speaks replies back into the room with Kokoro, or with Piper where there is no GPU.

Routing is by spoken name. An utterance that opens with a session's name goes straight to that session. Anything else goes to the coordinator, a Claude Code session with a switchboard MCP server for listing, starting, messaging and checking on the other sessions. Every spoken reply starts with the name of the session that sent it.

The workers are interactive `claude` processes in tmux, one per repository, each running the voice-inbox channel. The channel gains a `reply` tool that posts back to the switchboard. It also carries the channel permission relay, so a permission prompt is asked and answered by voice.

Cloud sessions are send-only. `claude -p "…" --cloud <id>` queues a message and returns no reply, so the switchboard says "sent" and the coordinator reads results from the branch or the pull request. claude.ai chats are out of scope, because there is no supported way to reach them and the Claude app's own voice mode already covers them.

### Why

Nothing available does screen-off, headset-mic, multi-session voice to Claude Code from an Android phone. The research report's table of existing products has the detail.

Android refuses to start a microphone foreground service from the background, which is what sank the MacroDroid attempts. A call app starts its service in the foreground and keeps it running with the screen off, so treating the phone as being on a call is the one design that stays inside the rules.

Interactive sessions keep the workers on the subscription as ordinary use. Billing for `claude -p` and the Agent SDK changed three times in 2026, and an interactive session is outside that churn.

### What would reverse it

Phase 0 is a kill test. With the phone locked and pocketed for 30 minutes, audio has to arrive continuously, the headset mic has to be the one in use, and nothing may drop when Samsung's sleep timers fire. If Mumla fails it, the transport moves to a Discord voice channel (option 2 in the report), and after that to a small custom Android app. Everything behind the transport stays as decided here.

If channels change shape or leave the research preview badly, the workers move to the Agent SDK with session resume, and the billing question comes back with them.

### Consequences

- Speech-to-text runs on the desktop. The laptop has no GPU, so it hosts worker sessions and receives their messages as text over the tailnet. Groq's free Whisper tier is the fallback for transcription away from the desktop.
- Talk mode costs music quality. The headset mic travels over Bluetooth HFP, and while that link is open the headphones play call-quality audio.
- Away from home the room is reached over Tailscale, with Murmur bound to the tailnet and protected by a server password and certificate auth. Nothing is port-forwarded.
- The build follows the report's phases 0 to 6, and each phase has its own kill test.

---

## ADR-2026-11-03-repository-gate — the repository gate

**Status:** Accepted

### Decision

Every hook runs locally from pre-commit and again in CI, so a commit that passes them here passes them there. The pull request title is the one thing only CI can check. The hooks cover file hygiene, ruff (lint and format), ty, markdownlint, cspell, actionlint, zizmor, schema checks for the workflows and Dependabot, and a refusal of Windows user folders and home directories in files and commit messages. ruff and ty run from the lock through `uv run`, so each has one pin. ruff selects flake8-bandit (`S`) as well, because this project turns speech into commands, and a shell call built from a transcript is what those rules look for.

`main` is protected by a ruleset with no bypass, so nobody pushes to it directly, me included. A pull request needs four checks to merge: `pre-commit gate`, `test`, `commit messages` and `append-only`. Renaming one of those jobs leaves every pull request waiting on a check that never reports, so the ruleset changes with it. The repository settings make merge and squash commits take the pull request title as their whole message, and the `commit messages` job holds the title to the same rules as a commit.

Commit messages are one line and a Conventional Commit. Why a change was made belongs in the pull request or here, since both outlive a log line.

This file and the research report are append-only. `protected_files.py` enforces it at commit-msg time and again in the `append-only` job, which runs the base branch's copy of the check, so a pull request can't loosen the rule it is judged by. The check compares against the merge base, so a block drafted and reworked on a branch is left alone until it lands. It refuses a removed or rewritten line and leaves an inserted one alone, because an amendment goes in the section it corrects. Every diff is read as text, so a binary attribute or a textconv driver can't hide a rewrite.

Dependencies wait seven days. `[tool.uv] exclude-newer = "7 days"` holds the lock to versions that have been on the index that long, and Dependabot's seven-day cooldown matches it so that it doesn't propose a version uv would refuse. Dependabot proposes grouped minor and patch updates once a month for the lock, the hook revisions and the action pins, and a major update arrives on its own. `audit.yml` runs `uv audit` against the OSV database when the lock changes and every Monday, because an advisory against a package already in the lock arrives with no change to start a run. Dependabot alerts and security updates, secret scanning with push protection and private vulnerability reporting are switched on. CodeQL scans the Python and the workflows on each pull request.

Actions are pinned to a full commit SHA. The repository allows GitHub's own actions plus `astral-sh/setup-uv`, `anthropics/claude-code-action` and `oven-sh/setup-bun`, which the Claude action runs inside itself. The default `GITHUB_TOKEN` is read-only.

Claude reviews each pull request, on Opus when it opens and on Sonnet for each later push. It also reviews Dependabot's pull requests against the release notes, on Opus every time. Both name the model by Claude Code's alias, so a new model reaches the reviews without an edit. Neither review is a required check, and neither approves or merges anything. `.claude/settings.json` denies agent sessions the merge commands, so merging stays with me.

There is one interpreter, Python 3.12, named in `.python-version`. The switchboard is an application that runs on one machine, so CI tests the version that runs rather than a matrix. The root holds the development environment and the repository's own checks (`package = false`). The switchboard arrives as a package in the first phase that needs code, and joins the 80% coverage floor in `pyproject.toml` then.

### Consequences

- `CLAUDE_CODE_OAUTH_TOKEN` has to be stored in both the Actions and the Dependabot secret stores. A run Dependabot starts reads only the second.
- A pull request that changes `claude-review.yml` is not reviewed, because the action skips a run whose copy of the workflow differs from the one on `main`. That includes the pull request that adds it.
- Dependabot's review passes its own token, so that skip doesn't reach it. It fetches the pull request with git rather than `actions/checkout`, which leaves the Claude action as the only action that runs beside the OAuth token. An update to the Claude action itself is not reviewed, because the new release would run with the token before anyone had read it. Dependabot gives that update a group of its own, so it takes no other update's review with it.
- The review jobs don't log their full output. The repository is public, and the log would carry every tool call and what it returned.
- Dependabot's `uv` entry moves the packages `pyproject.toml` names. A package that only another package requires moves when `uv lock --upgrade` is run by hand, or when an advisory turns the Monday audit red.
- The uv version CI installs (`.tool-versions`), the Node version under the markdown hooks (`default_language_version`) and shellcheck-py inside the actionlint hook have no Dependabot ecosystem, so they move by hand. Each is pinned in one place. `required-version` is the oldest uv the relative `exclude-newer` was checked against, and moves only when that check is made again.
- A security fix younger than seven days can't reach the lock either. It goes in by hand through `exclude-newer-package` for that one package, which names the exception in the diff.
- `uv audit` is experimental and needs `--preview-features audit`. A change to its interface shows as a red audit run.
- The deny rules in `.claude/settings.json` guard against an accidental merge. They are not a security boundary, and the ruleset allows a merge with no approvals because I open pull requests from the same account.
