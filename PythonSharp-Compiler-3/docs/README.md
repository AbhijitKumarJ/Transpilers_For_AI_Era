# PythonSharp Documentation

**Status:** Active
**Last updated:** 2026-10-31

PythonSharp is a C#-flavored, statically checked language that compiles to clean,
readable Python 3.11+ source and to line-pinned Python bytecode. The compiler is
`psc`.

This folder is the implementation-oriented documentation set derived from the raw
design notes in [`../Ideation`](../Ideation). The ideation notes remain the design
archive; the documents here are the maintained source of truth for scope,
architecture, and execution status.

## Document map

| Document | Purpose | Primary audience |
| --- | --- | --- |
| [PRD.md](PRD.md) | Problem, vision, users, requirements, success criteria | Product, engineering |
| [TECH-STACK.md](TECH-STACK.md) | Technology choices, dependencies, repository layout | Engineering |
| [ROADMAP.md](ROADMAP.md) | Phased plan, milestones, dependencies, exit gates | Product, engineering |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Compiler pipeline, passes, runtime contracts, module map | Compiler engineers |
| [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md) | Syntax, type system, lowering rules, compatibility | Language and tooling engineers |
| [CORE-API.md](CORE-API.md) | Standard library surface, lowering targets, behavioral differences | Engineers, users |
| [DIAGNOSTICS.md](DIAGNOSTICS.md) | Diagnostic format, codes, severities, exit behavior, hints | Compiler engineers, users |
| [LSP.md](LSP.md) | Language Server Protocol server, capabilities, editor setup | Tooling, engineers |
| [TESTING.md](TESTING.md) | Test strategy, fixtures, CI gates, coverage targets | Engineering |
| [PROGRESS.md](PROGRESS.md) | Live status, completed tasks, decision log, next actions | Everyone |
| [PENDING-WORK.md](PENDING-WORK.md) | Prioritized backlog of pending targets, language features, and Level 3 blogs | Product, engineering |
| [Triple Surface/README.md](Triple%20Surface/README.md) | Triple-Surface Architecture, tri-modal ladder, and scientific library roadmap | Everyone, architects |
| [RELEASE-NOTES-PHASE-2.md](RELEASE-NOTES-PHASE-2.md) | Phase 2 completion, deliverables, metrics, and differences | Everyone |
| [blogs/PLAN.md](blogs/PLAN.md) | Level 1: 12-part beginner-friendly blog series and curriculum guide | Everyone, newcomers |
| [blogs/2/PLAN.md](blogs/2/PLAN.md) | Level 2: 26-part technical deep dive (compiler internals, 17 ported case studies, retrospective) | Compiler engineers, practitioners |

## Reading order

1. **New to the project:** PRD, then ROADMAP, then [blogs/PLAN.md](blogs/PLAN.md).
2. **Implementing the compiler:** ARCHITECTURE, LANGUAGE-SPEC, DIAGNOSTICS, TESTING.
3. **Deep dive & real-world samples:** [blogs/2/PLAN.md](blogs/2/PLAN.md).
4. **Tracking work:** PROGRESS (update it whenever a milestone task changes state).

## Status legend

| Marker | Meaning |
| --- | --- |
| `DONE` | Implemented and verified; committed unless marked uncommitted |
| `DONE (uncommitted)` | Verified locally; commit pending |
| `IN PROGRESS` | Actively being worked |
| `BLOCKED` | Cannot proceed without a decision or dependency |
| `TODO` | Planned, not started |
| `DEFERRED` | Intentionally moved beyond the current phase |

## Conventions

- Source files use `.ps`, `.pysharp`, or `.pys` extensions with UTF-8 encoding.
- Declaration-only ambient/stub files use `.d.ps`, `.d.pysharp`, or `.d.pys`.
- Projects use `.psproj` or `.pysharpproj` project files in XML or TOML.
- Namespace prefixes map to Python package paths during emission.
- Diagnostic codes use the `PSnnn` format (for example `PS001` through `PS005`).
- Milestones are numbered `M0` through `M6` inside Phase 1, `P2.1`–`P5.4` in Phases 2–5, and `U1`–`U5` in Triple Surface Architecture.
- Phases are numbered `Phase 0` through `Phase 5`.

## Scope of this documentation

These documents describe the Phase 1 compiler (`psc`) in depth and the later
phases at roadmap level. When a design detail is not yet frozen, it is marked as
an open question rather than presented as settled.
