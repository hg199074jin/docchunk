# Contributing to docchunk

Thanks for helping make long-document reading workflows more reliable.

`docchunk` is especially interested in contributions grounded in real documents and reproducible edge cases.

## Good first contributions

- PDF / DOCX parsing edge cases
- heading, paragraph, sentence or table splitting failures
- `verify` false positives / false negatives
- page provenance problems
- cross-platform installation issues
- clearer documentation and examples
- integrations with Codex, Claude Code, Agent Skills or other long-document workflows

## Before opening an issue

Please include, when possible:

1. `docchunk` version / commit SHA;
2. operating system;
3. Python version;
4. output of `docchunk doctor` relevant to the problem;
5. exact command you ran;
6. the smallest document or synthetic sample that reproduces the problem;
7. expected behavior and actual behavior.

Do **not** upload confidential or copyrighted source material you are not permitted to share. A minimal synthetic reproduction is preferred.

## Development setup

```bash
git clone https://github.com/hg199074jin/docchunk.git
cd docchunk
uv sync
uv run pytest
```

Static checks:

```bash
uv run ruff check .
uv run mypy src
```

External-tool tests may require Pandoc and/or MinerU.

## Pull requests

Keep pull requests focused. For behavioral changes, add or update tests that demonstrate the failure before the fix and the expected behavior afterward.

Please avoid unrelated refactors in the same PR.

## Design principle

The central invariant is:

> **Chunking is lossless. Distillation may be lossy.**

Changes should preserve the ability to reconstruct and verify normalized source material, keep provenance explicit, and avoid silently changing source semantics.

## Integration contributions

If you integrate `docchunk` with another Agent, Skill, knowledge workflow, or document tool, an example under documentation is welcome. Prefer loose coupling: downstream tools should consume the Corpus contract rather than require `docchunk` to embed vendor-specific logic.
