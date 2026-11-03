# Contributing to hands-free

Thanks for taking a look. Here's how to get set up and what the tooling expects.

## The quality bar

The code here follows Martin Fowler's refactoring practices and the SOLID principles. Test-driven development is encouraged: write the failing test first, then the code that passes it. Anything that turns speech into an action is tested against utterances that should not trigger it as well as ones that should.

A pull request has to clear the same bar. Code that is obviously machine-generated and dumped in without consideration of the points above will be rejected. I'm happy to help anyone who wants to contribute and is unsure how to meet them.

## Setup

The project uses [uv](https://docs.astral.sh/uv/). Once you've cloned it:

```bash
uv sync --locked
uv run --no-sync pre-commit install
```

The second line wires up the git hooks, both the ones that check your files and the ones that check your commit message. You only do it once. After that the checks run every time you commit, so you find problems before CI does.

## How the rules are enforced

The rules live in the repository's config files, and nothing depends on which editor you use. `pyproject.toml` holds the ruff, ty and pytest settings, `.markdownlint-cli2.yaml` the markdown rules and `cspell.json` the dictionary. Both pre-commit and CI read them:

- **pre-commit**, locally, on every commit (see `.pre-commit-config.yaml`).
- **CI**, on every pull request and every push to `main`, running the same hooks.

So a commit that's green locally passes the same hooks in CI. The pull request title is the one thing only CI checks, because it doesn't exist until you open the pull request. The VSCode extensions in `.vscode/extensions.json` read the same files, but the hooks are what count.

## What the hooks check

- **ruff** lints and formats the code, at a line length of 88. Its rule set includes flake8-bandit, because this project turns speech into commands.
- **ty** type-checks everything outside `.venv`.
- **docstrings** are required on public modules, classes, functions and methods (Google style). Tests are exempt, because their names are the documentation.
- **markdown** is linted by [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2). It fixes the mechanical things itself, so most of the time it tidies your edit and asks you to re-stage. Prose is one line per paragraph, so line length isn't checked.
- **spelling** in markdown and in docstrings is checked by [cspell](https://cspell.org) in British English. If it flags a real term it doesn't know yet, add the word to `cspell.json` in the same change.
- **workflows** are linted by actionlint, audited by zizmor and checked against their schema, as is the Dependabot config. Every action is pinned to a full commit SHA.
- **personal paths**, meaning a Windows user folder or a home directory, are refused in files and in commit messages. The repository is public, and those paths carry a name.
- **hygiene**: no trailing whitespace, LF line endings, files end in a newline, YAML, TOML and JSON parse, no conflict markers, no private keys and no large files.
- **commit messages** are one line and follow [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `docs:`, `test:`, `chore:` and so on. Why a change was made goes in the pull request or `DECISIONS.md`.
- **protected files** stay append-only. The next section says what that means.

## Protected files

`DECISIONS.md` and `research/voice-room-switchboard.md` are records of what was known when. A reader of them can tell a claim made before a result existed from one made after, and an in-place edit destroys that without leaving a trace.

So corrections, qualifications and new results go in as a new dated entry. In `DECISIONS.md` that is a new ADR, which names the one it supersedes. The superseded line keeps its place. An amendment to the research report goes in the section it corrects, which is why the check allows an inserted line and refuses a removed or rewritten one.

An ADR is named `ADR-YYYY-MM-DD-slug`, from the ISO date you write it and a few words on what it decides, such as `ADR-2026-11-03-repository-gate`. Name it when you start drafting. The name doesn't change when the pull request lands, so two branches writing ADRs at the same time can't end up with the same number.

`protected_files.py` holds the list and does the checking. The commit-msg hook runs it over your index, and the `append-only` CI job runs `main`'s copy of it over the whole pull request. It compares against the merge base with the branch you're landing on, so a block you add and then rework on your own branch is left alone. Merging `main` into your branch brings its landed corrections with it.

Locally the check assumes you're landing on `main`. On a branch stacked on another, it will refuse a change that CI, which knows the real base, would allow. Commit with `GITHUB_BASE_REF=<the branch below> git commit` and it judges the way CI does.

Typos and broken markdown are the exception, and even then not a number, a date, a claim or a result. Put `[in-place]` in the subject of a commit on the branch to take it.

## Pull requests

A change starts as an issue. Take its branch with `gh issue develop <number>`, and open the pull request with `Closes #<number>` in the body. `main` accepts nothing else: there is no direct push for anyone, and four checks must pass (`pre-commit gate`, `test`, `commit messages` and `append-only`). The pull request title becomes the merge commit's message, so it follows the commit rules too.

Claude reviews each pull request and posts one comment, tagging each finding as a blocker or a nit. Dependabot's pull requests get a review against the packages' release notes, except an update to the Claude action itself. Neither review is required to merge.

## Dependencies

A version reaches `uv.lock` once it has been on the index for seven days. `[tool.uv] exclude-newer` enforces that for every `uv lock`, and Dependabot waits the same seven days before proposing an update. Dependabot moves only the packages `pyproject.toml` names, so the rest of the lock moves with an occasional `uv lock --upgrade`. `audit.yml` checks the lock with `uv audit` when it changes and every Monday. A security fix that can't wait goes in through `exclude-newer-package` for that one package, so the exception shows in the diff. ADR-2026-11-03-repository-gate has the reasoning.

## Running things by hand

```bash
uv run --no-sync pytest                      # the tests
uv run --no-sync pytest --cov                # what CI runs, with the 80% coverage floor
uv run --no-sync ty check                    # types
uv run --no-sync pre-commit run --all-files  # the whole gate
uv audit --locked --preview-features audit   # the dependency audit
```
