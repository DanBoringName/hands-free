# hands-free

Hands-free voice for a fleet of Claude Code sessions, from a phone in a pocket with the screen off.

The phone stays on an open-mic voice call to the desktop. A switchboard daemon in WSL listens to the call and transcribes what I say. It routes each utterance by the session name it opens with and speaks the replies back into the call. Anything said without a name goes to a coordinator Claude Code session, which hands work to the named sessions and reports back on what they did.

Nothing here runs yet. The first step is a kill test of screen-off capture from a Bluetooth headset mic, and the transport changes if the phone fails it. `DECISIONS.md` has the design (ADR-001) and what would reverse it.

## Where things are

| Path | What it holds |
| --- | --- |
| `research/voice-room-switchboard.md` | The research behind the design: what existing products do, the Android limits, the ranked architectures and the phased build plan. Written in October 2026. |
| `DECISIONS.md` | Architecture decisions, append-only. |
| `CHANGELOG.md` | What changed, by release. |
| `CONTRIBUTING.md` | Setup, the gate and the rules it enforces. |
| `SECURITY.md` | How to report a vulnerability. |

## Development

The gate is pre-commit, and CI runs the same hooks. Install them once after cloning:

```bash
uv sync --locked
uv run --no-sync pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Run the whole gate and the tests before pushing:

```bash
uv run --no-sync pre-commit run --all-files
uv run --no-sync pytest --cov
```

Commit messages are one line and follow [Conventional Commits](https://www.conventionalcommits.org/). The commit-msg hooks check both, and CI checks every commit of a pull request against the same hooks.

`main` is protected. A change starts as an issue, gets its branch from the issue with `gh issue develop <number>`, and lands as a pull request that closes it.
