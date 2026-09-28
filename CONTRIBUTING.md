# Contributing to BranchRift

Thanks for considering a contribution.

## Principles

BranchRift aims to stay:

- read-only by default
- fail-fast on invalid internal/config contracts
- explicit rather than magical
- deterministic in machine-readable output
- conservative about conclusions derived from incomplete Git signals
- small enough to audit

## Development setup

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

All tests should pass before opening a pull request.

## Pull requests

Prefer focused changes with:

- a clear behavior change or bug fix
- tests that lock the intended behavior
- documentation updates when the public contract changes

For parser, config, ownership, or security changes, include edge/failure cases rather than only the happy path.

## Security issues

Do not open a public issue containing exploit details. Follow `SECURITY.md`.
