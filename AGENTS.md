# AGENTS.md – Repository Guidelines & Commands

---

## 1️⃣ Project Overview
- **Package**: `integreat_chat`
- **Python**: >=3.13 (project uses Python 3.13)
- **Django**: 6.x (current major version)
- **Entry point**: `manage.py`
- **Build system**: `setuptools` (see `pyproject.toml`)

---

## 2️⃣ Installation / Build
| Goal | Command | Notes |
|------|---------|-------|
| Install editable (dev) | `pip install -e .` | Installs the package and runtime dependencies. |
| Re‑install clean | `pip uninstall -y integreat_chat && pip install -e .` | Use after dependency changes. |
| Create DB (first run) | `python manage.py migrate` | Applies Django migrations. |
| Load fixtures (optional) | `python manage.py loaddata <fixture>.json` | Fixtures live in `integreat_chat/fixtures/`. |
| Run dev server | `python manage.py runserver` | Default port 8000; use `--port <p>` to change. |
| Build wheel | `python -m build` | Requires the `build` package. |

---

## 3️⃣ Test Suite
- **Test runner**: **pytest** (auto‑discovers `tests.py` in each app). Django settings are loaded automatically via `DJANGO_SETTINGS_MODULE=integreat_chat.settings` (pytest‑django plugin is not required; the project sets the env in `manage.py`).

```bash
# Run all tests
pytest
```

```bash
# Run a single test (module, class, method)
pytest path/to/tests.py::TestClass::test_method
```

```bash
# Run a single test file
pytest integreat_chat/chatanswers/tests.py
```

- Parallel execution (if `pytest-xdist` installed): `pytest -n auto`.
- Show only failures with traceback: `pytest -xvv`.

---

## 4️⃣ Lint & Formatting
| Tool | Command | Purpose |
|------|---------|---------|
| **black** | `black .` | Code formatter (line‑length 88). |
| **isort** | `isort .` | Import sorting (compatible with black). |
| **ruff** | `ruff .` | Fast linting (PEP 8, flake8, pyflakes). |
| **mypy** (optional) | `mypy .` | Static type checking. |
| **django‑check** | `python manage.py check` | Django‑specific lint. |

> **Tip:** Add a pre‑commit hook (`pre-commit install`) with `black`, `isort`, and `ruff` to enforce style on every commit.

---

## 5️⃣ Code‑Style Guidelines
### 📦 Imports
```python
# 1️⃣ Standard library
import os
import pathlib

# 2️⃣ Third‑party
import requests
from django.conf import settings

# 3️⃣ Local application
from integreat_chat.core.utils import chat_message
```
- Blank line between groups.
- Alphabetical order inside each group.
- Use absolute imports; avoid relative (`..`) unless within the same app.

### 🐍 Naming
| Element | Convention |
|---------|------------|
| Modules / packages | `snake_case` |
| Classes / Exceptions | `PascalCase` |
| Functions / methods | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| Django models | `PascalCase` (singular) |
| Database fields | `snake_case` |
| Test classes | `Test<Thing>` (PascalCase) |
| Test methods | `test_<scenario>` (snake_case) |

### 📐 Formatting
- Indentation: **4 spaces** (no tabs).
- Max line length: **88** (black default).
- Trailing commas on multi‑line collections.
- One blank line between top‑level definitions.

### 🧩 Types & Annotations
- Add **type hints** on public functions & methods.
- Use `from __future__ import annotations` (Python 3.11 already supports postponed evaluation).
- Return types explicitly; avoid `Any` unless unavoidable.

```python
def get_user(id: int) -> User | None:
    ...
```

### ⚡️ Error Handling
- Prefer **Django‑specific exceptions** (`Http404`, `PermissionDenied`).
- Catch only expected errors; re‑raise otherwise.
- Log with the project logger (`logger = logging.getLogger(__name__)`).

```python
try:
    obj = Model.objects.get(pk=pk)
except Model.DoesNotExist:
    raise Http404("Object not found")
```
- Do **not** swallow exceptions silently.

### 📚 Documentation Strings
- Use **Google‑style** or **NumPy‑style** docstrings for public APIs.
- One‑line summary, followed by optional `Args:` / `Returns:` sections.

---

## 6️⃣ Django 6.x Specifics
- Async views are now first‑class; use `async def` only when awaiting I/O.
- `path()` replaces the old `url()` for simple routes.
- Default `request` object is now **async‑compatible**; avoid blocking calls inside async views.
- Settings should be loaded from environment variables (`os.getenv`) – never commit secrets.
- Celery tasks live in `search/tasks.py` and are decorated with `@shared_task`.
- Static files reside in each app’s `static/` directory and are referenced via `static()`.
- Translations use `gettext_lazy` for model verbose names and UI strings.
- After model changes run `python manage.py makemigrations`; never edit migration files manually.

---

## 7️⃣ Cursor / Copilot Rules
- No `.cursor/rules/` or `.cursorrules` directories were found.
- No `.github/copilot‑instructions.md` file detected.
- If such files appear, copy their contents verbatim into this section.

---

## 8️⃣ Frequently Used One‑Liners
| Task | Command |
|------|---------|
| Run a single test file | `pytest integreat_chat/chatanswers/tests.py` |
| Reformat & sort imports | `black . && isort .` |
| Lint only changed files | `ruff $(git diff --name-only --diff-filter=ACM)` |
| Check migrations status | `python manage.py showmigrations` |
| Create superuser | `python manage.py createsuperuser` |
| Run dev server on custom port | `python manage.py runserver 127.0.0.1:8080` |

---

*Keep this file up‑to‑date as tooling evolves.*
