# Changelog

Everything worth noting lands here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [semantic versioning](https://semver.org).

## [Unreleased]

### Added

- The research report behind the design, `research/voice-room-switchboard.md`, and the first two decisions in `DECISIONS.md`. ADR-2026-11-03-voice-room-switchboard chooses the voice-room switchboard with one coordinator Claude. ADR-2026-11-03-repository-gate sets out the repository gate.
- The repository gate. pre-commit runs ruff, ty, markdownlint, cspell, actionlint, zizmor and schema checks, and refuses personal paths. CI runs the same hooks, the tests, a check of every commit message and the pull request title, and the append-only check over `DECISIONS.md` and the research report.
- Dependency updates that wait seven days, a weekly `uv audit` of the lock and CodeQL on each pull request.
- Claude reviews of each pull request, and of Dependabot's against the release notes.
- Tests for the pattern hooks, against the messages and paths each must refuse and the ones each must pass.
- Issue forms, a pull request template and a security policy.
