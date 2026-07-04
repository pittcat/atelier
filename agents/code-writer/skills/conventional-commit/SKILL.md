---
name: conventional-commit
description: Write commits the Atelier way — atomic, conventional, English, terse.
metadata:
  category: git
  tier: standard
---

# Conventional Commit (Atelier)

```
<type>(<scope>): <subject>
```

- Subject ≤ 72 chars, imperative, no period.
- Body explains **why**, not what.
- One commit = one concern.
- Auto-reject: `update stuff`, `wip`, mixed `feat+refactor`.
