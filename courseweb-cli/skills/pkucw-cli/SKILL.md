---
name: pkucw-cli
description: Use the local pkucw CLI to operate PKU course.pku.edu.cn safely through structured terminal commands. Support account management, login, session recovery, course resolution, announcements, teaching contents, assignments, downloads, and recordings while avoiding unsafe live writes unless the user explicitly approves them.
version: 0.4.0b1
metadata:
  tags: [pku, blackboard, cli, pkucw, course, announcements, contents, assignments, recordings, downloads]
---

# pkucw CLI

Use this skill when the task is about PKU teaching-site workflows that should go through `pkucw` instead of direct browser automation.

## Required Setup

- `pkucw` must be available on `PATH`
- Prefer a workspace-local artifact root such as `./pkucw-artifacts`
- Prefer saved accounts over ad hoc credentials:
  `pkucw accounts add`
  `pkucw login`

## Core Rules

- Prefer `pkucw` over opening a browser when the CLI already supports the task.
- Prefer `--json` whenever the next step depends on parsing output.
- Never guess course names from memory. Resolve them from CLI output first.
- Never guess paths, versions, or installation state. For verification tasks, execute concrete commands and report their real outputs.
- Never invent CLI argument shapes. When summarizing `--help`, preserve which positional arguments are optional and which are required.
- Never run live assignment writes unless the user explicitly approves them.
- Treat `assignments submit --save-draft` and `assignments submit --final-submit` as live writes.
- If a course or resource cannot be resolved confidently, return candidates and stop.

## Safety Boundaries

- Safe read operations:
  `status`, `accounts list/show`, `ls`, `use`, `current`, `info`
  `announcements list/show`
  `contents list/tree/show/download`
  `assignments list/show/download`
  `recordings list/show/download`
- Dry-run assignment inspection is safe:
  `pkucw assignments submit "<assignment>" --comment "probe" --json`
- Live assignment writes require explicit approval:
  `--save-draft`
  `--final-submit`
- Some assignments open directly into a read-only review page after grading or final submission. In that state, `pkucw assignments submit` may fail with a read-only message because no resubmission form exists.

## Default Command Pattern

Start every task with session and course resolution:

```bash
pkucw status --json
pkucw ls --current --json
```

If not authenticated, run:

```bash
pkucw login --json
```

After the exact course title is known, set it once:

```bash
pkucw use "<exact course title or course id>" --json
```

Then omit the course argument for later commands when possible.

## Account And Session Workflows

### First-Time Setup

```bash
pkucw accounts add
pkucw login
pkucw ls --current
```

### Inspect Session State

```bash
pkucw status --json
pkucw current --json
pkucw doctor --json
```

### Install Verification

For install or environment checks, use exact terminal evidence:

```bash
command -v pkucw
pkucw --version
pwd
readlink ~/.openclaw/workspace/skills/pkucw-cli 2>/dev/null || ls -la ~/.openclaw/workspace/skills/pkucw-cli
```

Report the exact path strings returned by the shell. Do not infer repository or skill paths from memory.

### Account Management

```bash
pkucw accounts list --json
pkucw accounts show --json
pkucw accounts use "<username-or-label>" --json
pkucw accounts remove "<username-or-label>" --json
```

### Session Recovery

- `pkucw` can automatically reuse saved browser state.
- If browser state is stale, course-related commands may auto-login with the saved default account.
- If the site is unstable, retry `pkucw login --json` once before escalating.

## Course Resolution

Use one of these patterns:

```bash
pkucw ls --current --json
pkucw ls --archived --json
pkucw use "<course>" --json
pkucw current --json
pkucw info --json
```

When the user provides an approximate title such as `有机化学一`, try:

```bash
pkucw use "有机化学一" --json
```

The CLI normalizes common numeral variants. If that still fails, use:

```bash
pkucw __complete -- use 有机
```

## Common Read Workflows

### Session Bootstrap

1. Run `pkucw status --json`.
2. If unauthenticated, run `pkucw login --json`.
3. Run `pkucw ls --current --json`.
4. Return a short summary with course count and likely next actions.

### Course Snapshot

```bash
pkucw use "<course>" --json
pkucw info --json
pkucw announcements list --json
pkucw contents list --json
pkucw assignments list --json
pkucw recordings list --json
```

Summarize the exact resolved title plus counts for notifications, contents, assignments, and recordings.

### Announcement Details

```bash
pkucw announcements list --json
pkucw announcements show "<announcement title fragment>" --json
```

Return course name, announcement title, publish time, body, and asset URLs.

### Teaching Contents

```bash
mkdir -p ./pkucw-artifacts/downloads
pkucw contents list --json
pkucw contents tree --json
pkucw contents show "<content title fragment>" --json
pkucw contents download "<content title fragment>" --output ./pkucw-artifacts/downloads/<slug>
```

Use `tree` when folders or nested content matter. Download only when the user explicitly wants the file.

### Recordings

```bash
mkdir -p ./pkucw-artifacts/recordings
pkucw recordings list --json
pkucw recordings show "<recording title fragment>" --json
pkucw recordings latest --output ./pkucw-artifacts/recordings/latest
```

Notes:

- Recordings may be large.
- Downloads may produce `.ts` plus remuxed `.mp4`.
- Prefer `show` first so the user understands size and duration before downloading.

## Assignment Workflows

### Safe Assignment Inspection

```bash
pkucw assignments list --json
pkucw assignments show "<assignment title fragment>" --json
pkucw assignments download "<assignment title fragment>" --output ./pkucw-artifacts/assignments/<slug>
pkucw assignments submit "<assignment title fragment>" --comment "probe" --json
```

What each command gives you:

- `list`: assignment entries for the course
- `show`: due time, points, mode, instructions, attachments, and submitted file names
- `download`: exports `作业说明.md` and downloads assignment attachments when available
- `submit` without live flags: dry-run only

### Draft And Final Submission

Only use these when the user explicitly authorizes a live write:

```bash
pkucw assignments submit "<assignment>" --file ./answer.txt --save-draft --json
pkucw assignments submit "<assignment>" --file ./answer.txt --final-submit --confirm-final-submit "<exact assignment id or title>" --json
```

Important behaviors:

- `--replace-files` replaces existing draft attachments
- `--clear-files` removes existing draft attachments
- `--clear-text` clears the text body
- `--clear-comment` clears the comment field
- `--final-submit` is protected and requires an exact confirmation string

### Read-Only Assignment Caveat

If `assignments show` or a direct assignment page resolves to `复查提交历史记录` and there is no upload form, the assignment is effectively read-only for the current user state. In that case:

- do not retry blindly
- do not assume the CLI is wrong
- report that the assignment appears already submitted, graded, closed, or not open for resubmission

## Download Conventions

Prefer a shared artifact root:

```bash
mkdir -p ./pkucw-artifacts/{downloads,assignments,recordings}
```

Suggested layout:

- `./pkucw-artifacts/downloads` for teaching contents
- `./pkucw-artifacts/assignments` for assignment exports and attachments
- `./pkucw-artifacts/recordings` for recordings

When reporting back to the user, include the saved path.

## Help And Usage Interpretation

- If the task is “how do I use this command”, run the real `--help` command first.
- Quote the command structure from help faithfully.
- If a positional argument is optional, say that it is optional.
- If a command can rely on `pkucw use "<course>"`, mention that the course argument may be omitted after context is set.

## Output Expectations

- For machine-followed workflows, always use `--json`.
- For human summaries, keep the report short and include:
  exact course title
  action performed
  count or key status
  saved paths for downloads
- If a command fails because the site is slow or unstable, say that explicitly.

## Troubleshooting

- If portal loading times out, retry once after `pkucw login --json`.
- If course resolution fails, run `pkucw ls --current --json` and surface candidates.
- If assignment submission fails on a review page, inspect whether the page is read-only before retrying.
- If downloads are large, warn before starting and save under the shared artifact root.

## Agent Hints

- Prefer exact course titles copied from `pkucw ls --current --json`.
- Use `pkucw use "<course>" --json` once, then omit course arguments.
- Use `pkucw __complete -- use <prefix>` for fast candidate expansion.
- Keep artifacts under a stable shared directory so later runs can reuse them.
- For assignment operations, distinguish clearly between:
  inspection
  download
  dry-run submit
  live draft save
  final submit
- When the user asks “查看作业内容”, prefer `assignments show` or `assignments download`, not `assignments submit`.
