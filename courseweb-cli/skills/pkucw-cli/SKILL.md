---
name: pkucw-cli
description: Use the local pkucw CLI to work with PKU course.pku.edu.cn safely through repeatable terminal commands. Handle login, course lookup, announcements, materials, assignments, and recordings without live assignment submission unless the user explicitly asks.
version: 0.2.0
metadata:
  hermes:
    tags: [pku, blackboard, cli, pkucw, course, announcements, recordings, assignments]
    related_skills: [pku-course-web]
---

# pkucw CLI

## Required Setup

- Command entry: `/Users/1cxm1/.local/bin/pkucw`
- Hermes launch directory: `/Users/1cxm1/.openclaw/workspace/hermes-agent-main`
- CLI working directory: `/Users/1cxm1/.openclaw/workspace/hermes-agent-main/hermes-workspace`
- Credentials file: `/Users/1cxm1/.openclaw/workspace/hermes-agent-main/hermes-workspace/env.md`
- Artifact root: `/Users/1cxm1/.openclaw/workspace/hermes-agent-main/hermes-workspace/pkucw`

`env.md` format:
- line 1: username
- line 2: password

## Safety Rules

- Never run `pkucw assignments submit` with `--save-draft` or `--final-submit` unless the user explicitly approves a live write.
- In unattended runs, do not create or update any assignment draft.
- For assignment inspection, stick to `assignments list`, `assignments show`, or a dry-run `assignments submit` without live flags.
- When a course name is approximate, do not guess from memory. Use `pkucw ls --current --json`, `pkucw use "<name>" --json`, or `pkucw __complete -- use <prefix>` to surface exact titles first.
- If a course cannot be resolved confidently, return candidates and stop.

## Default Command Pattern

Prefer `--json` whenever the next step depends on parsing output. Start from the Hermes repo root, then switch into the workspace before calling `pkucw`.

```bash
cd /Users/1cxm1/.openclaw/workspace/hermes-agent-main
cd hermes-workspace
pkucw status --json
pkucw ls --current --json
```

If unauthenticated, run:

```bash
pkucw login --json
```

After a course is resolved, set it once so later commands can omit the course name:

```bash
pkucw use "<exact course title or id>" --json
```

## Common Workflows

### Session Bootstrap

1. Run `pkucw status --json`.
2. If unauthenticated, run `pkucw login --json`.
3. Run `pkucw ls --current --json`.
4. Return a short summary with course count and likely next actions.

### Course Snapshot

For a target course, prefer exact titles copied from `ls` output:

```bash
pkucw use "<course>" --json
pkucw info --json
pkucw announcements list --json
pkucw contents list --json
pkucw assignments list --json
pkucw recordings list --json
```

Summarize the resolved title plus announcement, content, assignment, and recording counts.

### Read Announcement Details

```bash
pkucw announcements list --json
pkucw announcements show "<announcement title fragment>" --json
```

Include course name, title, publish time, and any linked assets.

### Inspect Materials

```bash
pkucw contents list --json
pkucw contents tree --json
pkucw contents show "<content title fragment>" --json
```

If the user asks to download a file, keep it under the shared artifact root:

```bash
pkucw contents download "<content title fragment>" --output /Users/1cxm1/.openclaw/workspace/hermes-agent-main/hermes-workspace/pkucw/downloads/<slug>
```

### Inspect Recordings

```bash
pkucw recordings list --json
pkucw recordings show "<recording title fragment>" --json
```

Only download when the user explicitly wants the file because recordings may be large:

```bash
pkucw recordings latest --output /Users/1cxm1/.openclaw/workspace/hermes-agent-main/hermes-workspace/pkucw/recordings/latest
```

### Safe Assignment Inspection

```bash
pkucw assignments list --json
pkucw assignments show "<assignment title fragment>" --json
```

If the user asks what would be submitted, dry-run only:

```bash
pkucw assignments submit "<assignment title fragment>" --comment "probe" --json
```

Do not add `--save-draft` or `--final-submit` unless the user explicitly approves a live write.

## Agent Hints

- Prefer exact course titles or IDs copied from `pkucw ls --current --json`.
- When a user says something like `有机化学一`, try `pkucw use "有机化学一" --json` first; the CLI normalizes common numeral variants.
- When the user gives only a prefix, `pkucw __complete -- use <prefix>` is the fastest way to surface candidates.
- Keep downloads under the shared `pkucw` artifact root so later Hermes runs can reuse them.
- If Hermes terminal commands fail with `No such file or directory: 'hermes-workspace'`, relaunch Hermes from `/Users/1cxm1/.openclaw/workspace/hermes-agent-main` and keep the terminal working directory anchored there.
