# Contributing to OpenCS2

Thank you for considering a contribution!

## Getting Started

1. **Fork** the repository and clone your fork.
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and commit: `git commit -m "feat: describe your change"`
4. Push and open a **Pull Request** against `main`.

## Development Setup

```bash
cd panel
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in values, then:

```bash
export FLASK_APP=run:app
flask run
```

## Code Style

- Python: follow [PEP 8](https://peps.python.org/pep-0008/). Run `flake8 panel/` before committing.
- Keep functions focused and avoid unnecessary complexity.
- Do not commit `.env` files or credentials.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Use for |
|---|---|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `docs:` | Documentation only |
| `refactor:` | Code cleanup without behaviour change |
| `ci:` | CI/CD changes |

## Translations

See [CONTRIBUTING_TRANSLATIONS.md](CONTRIBUTING_TRANSLATIONS.md).

## Reporting Bugs

Open an issue using the **Bug Report** template and include:
- Steps to reproduce
- Expected vs. actual behaviour
- Docker / OS version

## Security Issues

Please **do not** open public issues for security vulnerabilities.  
See [SECURITY.md](SECURITY.md) for the responsible disclosure process.

## License

By contributing, you agree that your work will be licensed under the [AGPL v3](LICENSE).
