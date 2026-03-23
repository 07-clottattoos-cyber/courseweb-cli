# courseweb-cli

PKU teaching-site CLI with browser-backed workflows.

## What exists today

- A stable command tree based on the observed Blackboard flows
- Primary command entry: `pkucw`
- Compatibility aliases: `cw`, `courseweb`
- Active-course context via `pkucw use`, `pkucw current`, and course-aware shortcuts
- One-line install via `./install.sh`
- One-line deployment test for the linked Mac mini via `./scripts/deploy-mac-mini.sh`
- Generic SSH deployment via `./scripts/deploy-remote.sh user@host`
- Built-in shell completion via `pkucw completion zsh|bash|fish`
- `pkucw --version` and `./scripts/smoke-test.sh` for quick validation
- Local state management for session metadata
- Real browser-backed `auth login` that saves Playwright storage state
- Real `courses list`, `courses list --current`, and `courses list --archived`
- Real `courses show <course>` and `course info <course>`
- Real `course announcements list <course>` and `course announcements show <course> <announcement>`
- Real `course contents list <course>`, `course contents tree <course>`, and `course contents show <course> <content>`
- Real `course contents download <course> <content>` for Blackboard-hosted files and folders
- Real `course recordings list/show/download/download-latest`
- Segment progress output during recording downloads
- Automatic `.ts -> .mp4` remux for recording downloads on macOS via Swift + AVFoundation
- Download receipts include file size, SHA-256, and media probe metadata
- Real `course assignments list <course>` and `course assignments show <course> <assignment>`
- Safe `course assignments submit` flow with dry-run by default and live draft save via `--save-draft`
- Draft attachment replacement/removal via `--replace-files` and `--clear-files`
- Draft text/comment cleanup via `--clear-text` and `--clear-comment`
- Double-confirm protection for `--final-submit`
- JSON and human-readable output modes

## Quick start

```bash
cd /Users/maixinchao/Documents/New\ project/courseweb-cli
./install.sh
pkucw login
pkucw ls --current
pkucw use "有机化学 (一)"
pkucw doctor
pkucw recordings list
pkucw recordings latest --output ./output/downloads/recordings/latest
pkucw announcements list
pkucw contents tree "音乐与数学"
pkucw assignments list
```

## Local install

```bash
cd /Users/maixinchao/Documents/New\ project/courseweb-cli
./install.sh
```

The installer creates `pkucw` plus the compatibility aliases `courseweb` and `cw`.
It also updates your shell profile so new terminals can resolve `pkucw` directly, and it installs shell completion for the current shell when possible.

Quick sanity check:

```bash
pkucw --version
./scripts/smoke-test.sh
```

## Mac mini deploy

From this machine:

```bash
cd /Users/maixinchao/Documents/New\ project/courseweb-cli
./scripts/deploy-mac-mini.sh
```

This copies the project to `1cxm1@1cxm1demac-mini.local`, installs it, and runs the smoke test script remotely.

For other SSH-reachable machines:

```bash
cd /Users/maixinchao/Documents/New\ project/courseweb-cli
./scripts/deploy-remote.sh user@host
```

## State directory

By default the prototype stores local state in:

```text
~/.courseweb
```

The real login flow stores:

```text
~/.courseweb/session.json
~/.courseweb/storage_state.json
```

Recording downloads always produce a decrypted `.ts` file first, then try to remux it to `.mp4`.
Use `--no-remux` to keep only the `.ts` output.
Use `--no-progress` to suppress the segment progress line.
The final JSON payload includes validation metadata for the downloaded artifacts.

## Friendly command patterns

```bash
pkucw login
pkucw ls
pkucw use "有机化学 (一)"
pkucw current
pkucw info
pkucw recordings list
pkucw recordings latest
pkucw contents list
pkucw announcements show "课程群二维码"
pkucw assignments submit "L4作业提交入口" --text "draft body" --save-draft
```

Once `pkucw use <course>` has been run, most course-aware commands can omit the course argument.

## Shell completion

Quick one-off setup:

```bash
eval "$(pkucw completion zsh)"
```

The installer already writes a persistent completion hook for the current shell on macOS and other common SSH targets.

## Credentials discovery

`pkucw login` looks for credentials in this order:

1. `--credentials-file`
2. `COURSEWEB_CREDENTIALS_FILE`
3. The nearest `env.md` found by walking upward from the current working directory

The credentials file format is:

```text
line 1: username
line 2: password
```

You can override it with:

```bash
COURSEWEB_HOME=/custom/path pkucw status
```
