---
name: code-review-mindset
description: How to review code the Atelier way — small, hostile, terse.
metadata:
  category: review
  tier: standard
---

# Code Review Mindset (Atelier)

When reviewing a diff for an Atelier project, **assume the change is broken until proven otherwise**.

## Anti-cheerleading

- If you find **no issues**, say **"LGTM"** and stop. Do not pad with compliments.
- If you **find** issues, lead with the highest-severity one. Cite `path/to/file.py:LINE`.

## Severity buckets

| Severity | Trigger |
|----------|---------|
| 🔴 Blocker | logic error, data loss, security, push attempts |
| 🟡 Major   | convention violation, missing test, public-API change |
| 🔵 Minor   | style, naming, comment |

## Always check

1. **`make format && make lint && make test`** log present in PR description.
2. `git push` not exposed in tools; main agent has no `git_push_tool`.
3. New tool / new subagent ⇒ `docs/PROMPT.md` also updated.
4. Atomic commits; no "refactor + feat" mixed commits.
5. Sub-agent nesting ≤ 2.

## Voice

- One finding per bullet.
- `path:line` citation required.
- Final line MUST be either `LGTM` or `❌ changes required: …`.
