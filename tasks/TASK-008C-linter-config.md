# TASK-008C: Linter & Type-Check Configuration

**Status:** Complete
**Spec sections:** SPEC-007 §14.1 (lint, type-check stages)
**ADRs:** —
**Depends on:** TASK-001 (dev dependencies installed)

## Objective

Write the `[tool.ruff]` and `[tool.mypy]` sections in `backend/pyproject.toml` so that `ruff check` and `mypy app/` enforce meaningful rules, not defaults. Without this task, CI (TASK-008B) would run the lint and type-check stages against empty configuration and pass trivially. This task is the prerequisite that gives those stages teeth.

## Acceptance Criteria

- [x] `backend/pyproject.toml` contains a `[tool.ruff]` section with an explicit rule selection (at minimum: `E`, `F`, `W`, `I`, `B`, `UP`, `SIM`, `RUF`) and an explicit `line-length`
- [x] `[tool.ruff.lint.per-file-ignores]` carves out reasonable exceptions for test files (e.g., allow `S101` assert usage, unused-argument for fixtures) and Alembic migrations (auto-generated — ignore `E501`, `F401`)
- [x] `[tool.ruff.format]` section present so `ruff format` behaviour is stable across machines
- [x] `[tool.mypy]` section with `strict = true` per SPEC-007 §14.1, plus `python_version = "3.12"`
- [x] `[[tool.mypy.overrides]]` blocks relax strictness for test files and third-party modules that lack type stubs (e.g., `factory_boy`), so strict mode is achievable without rewriting tests
- [x] `docker compose exec backend ruff check app/ tests/` runs clean on the existing codebase (fix lint violations or add targeted ignores — do not disable whole rule families to make the suite pass)
- [x] `docker compose exec backend mypy app/` runs clean on the existing codebase (add type annotations or targeted `# type: ignore[code]` comments; do not lower strictness globally to pass)
- [x] The commands documented in `CLAUDE.md` (`ruff check app/ tests/`, `ruff format app/ tests/`, `mypy app/`) continue to work unchanged — this task only adds config, not new commands

## Files

- `backend/pyproject.toml` (add `[tool.ruff]`, `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.format]`, `[tool.mypy]`, `[[tool.mypy.overrides]]` sections)

## Non-goals

- Wiring lint/type-check into GitHub Actions — owned by TASK-008B, which depends on this task
- Pre-commit hooks — out of scope; CI enforcement is sufficient for MVP
- Frontend linting (ESLint/Prettier) — post-MVP, activates when a frontend lands

## Notes

Keep the rule selection pragmatic, not maximal. The goal is to catch real bugs and style drift cheaply, not to impose a rule set the team will disable in frustration. If a rule fires on more than a handful of existing sites and the fixes aren't clearly improvements, drop the rule rather than papering it over with ignores.
