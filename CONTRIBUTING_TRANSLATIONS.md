# Contributing Translations

This project uses [Flask-Babel](https://python-babel.github.io/flask-babel/) for internationalization.  
All source strings are in **English**. Turkish (`tr`) is bundled. You can add any language by following the steps below.

---

## Adding a New Language

### Prerequisites

```bash
pip install flask-babel
```

### Steps

**1. Clone the repository and navigate to the `panel/` directory:**

```bash
git clone https://github.com/your-org/cs2-panel.git
cd cs2-panel/panel
```

**2. Extract all translatable strings into a `.pot` template:**

```bash
pybabel extract -F babel.cfg -o messages.pot .
```

**3. Initialize a new language catalog** (replace `<lang>` with an [ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes) code, e.g. `de`, `fr`, `es`):

```bash
pybabel init -i messages.pot -d app/translations -l <lang>
```

This creates `app/translations/<lang>/LC_MESSAGES/messages.po`.

**4. Edit the `.po` file** — fill in `msgstr` for each `msgid`:

```po
msgid "Login"
msgstr "Anmelden"   # ← your translation here
```

Use a tool like [Poedit](https://poedit.net/) for a graphical interface.

**5. Compile the catalog:**

```bash
pybabel compile -d app/translations
```

**6. Register your language** in `app/__init__.py`:

```python
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'tr': 'Türkçe',
    '<lang>': 'Your Language Name',   # ← add this line
}
```

**7. Test it** — start the panel, click the language switcher in the top bar, and verify your translations appear.

**8. Submit a Pull Request** with:
- `app/translations/<lang>/LC_MESSAGES/messages.po`
- The updated `app/__init__.py`

---

## Updating Existing Translations

When new strings are added to the codebase, update the template and merge:

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d app/translations
```

Then fill in any new `msgstr ""` entries and recompile:

```bash
pybabel compile -d app/translations
```

---

## Notes

- Strings with variables use `%(name)s` format: `"Player %(name)s banned."` — keep the placeholders as-is.
- Multi-line strings in templates use `{{ _('...') }}` syntax.
- The `.mo` compiled files are not committed to git (they are rebuilt in Docker). Only commit the `.po` source files.
