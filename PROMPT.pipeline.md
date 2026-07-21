# Ralph Pipeline Prompt

- project_root: `./`
- preset: `builtin:ce-executor-pipeline`
- prompt_file: `PROMPT.pipeline.md`

This is a safe bootstrap fallback. The selected preset requires a real plan supplied with `ralph run --plan <repo-relative-path>`. If this fallback prompt reaches an agent, stop and report that the required plan was not supplied; do not perform project work. Do not invent preset
contents, do not look up hat collections by name, and do not
read any runtime-managed block from the target project. The
runtime injects the preset-specific instructions downstream.
