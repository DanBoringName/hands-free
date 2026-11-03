# hands-free

Hands-free voice for a fleet of Claude Code sessions, from a phone in a pocket with the screen off.

The phone stays on an open-mic voice call to the desktop. A switchboard daemon in WSL listens to the call and transcribes what I say. It routes each utterance by the session name it opens with and speaks the replies back into the call. Anything said without a name goes to a coordinator Claude Code session, which hands work to the named sessions and reports back on what they did.

The switchboard doesn't exist yet. What runs is Phase 0, a kill test of screen-off capture from a Bluetooth headset mic, and the transport changes if the phone fails it. `hands-free murmur` runs the room the phone joins, and `hands-free kill-test` judges a run from Murmur's log and a recording of the room. `research/phase-0-kill-test.md` has the protocol. `DECISIONS.md` has the design (ADR-2026-11-03-voice-room-switchboard) and what would reverse it.

## Where things are

| Path | What it holds |
| --- | --- |
| `research/voice-room-switchboard.md` | The research behind the design: what existing products do, the Android limits, the ranked architectures and the phased build plan. Written in October 2026. |
| `research/phase-0-kill-test.md` | The Phase 0 kill test: what it decides, how each check is measured, the protocol, and each run's result. Append-only, like the research report. |
| `src/hands_free/` | The `hands-free` command. `murmur.py` and `murmur.ini` run the room, and `kill_test/` judges a run. |
| `DECISIONS.md` | Architecture decisions, append-only. |
| `CHANGELOG.md` | What changed, by release. |
| `CONTRIBUTING.md` | Setup, the gate and the rules it enforces. |
| `SECURITY.md` | How to report a vulnerability. |

## Development

The gate is pre-commit, and CI runs the same hooks. Install them once after cloning:

```bash
uv sync --locked
uv run --no-sync pre-commit install
```

Run the whole gate and the tests before pushing:

```bash
uv run --no-sync pre-commit run --all-files
uv run --no-sync pytest --cov
```

Commit messages are one line and follow [Conventional Commits](https://www.conventionalcommits.org/). The commit-msg hooks check both, and CI checks every commit of a pull request against the same hooks.

`main` is protected. A change starts as an issue, gets its branch from the issue with `gh issue develop <number>`, and lands as a pull request that closes it.
