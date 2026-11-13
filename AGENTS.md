# Instructions for AI Coding Agents (AGENTS.md / CLAUDE.md)

This project (**AuraVox**) is collaboratively maintained and extended by multiple AI coding assistants.

## Mandatory Rules Before and After Any Change

1. **Mandatory Initial Reading:**
   Always read [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md) before proposing or applying changes. It documents the complete architecture of the backend (`app/webui/`, `app/core/`, `app/skills/`, `app/voice/`, `plugins/`), the zero-framework vanilla SPA (`app.js`, `features.js`, `i18n.js`, `style.css`), the multi-profile security model, and all HTTP/SSE routes.

2. **Continuous Context Synchronization:**
   Whenever you add, rename, or modify views, `/api/*` endpoints, LLM tools, `config/` schemas, or `.gitignore` rules, **update [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md) in the same session** so any subsequent AI agent has an up-to-date architectural map.

3. **Privacy & Git Hygiene (`.gitignore` & Plug-and-Play Templates):**
   Never remove exclusions from `.gitignore` or commit personal data, real coordinates, cloned voices, chat histories, or generated files into `config/*.example.yaml`. Ensure `app/paths.py` (`ensure_default_configs()`) continues to bootstrap missing config files automatically so fresh clones work out of the box.

4. **Language & Framework Conventions:**
   - All project documentation (`README.md`, `PROJECT_CONTEXT.md`, `plugins/README.md`, config templates) and all terminal/console log outputs (`print`, `server_log.log`, `.bat` launchers) must be written in **English**.
   - Keep the Web UI bilingual: add every new UI string to both `STRINGS.es` and `STRINGS.en` (`app/webui/static/i18n.js`) and `MESSAGES["es"]` / `MESSAGES["en"]` (`app/webui/i18n.py`).
   - Keep the frontend in vanilla HTML/JS (no bundlers or JS frameworks) and preserve mobile responsiveness (mobile first; `max-width: 900px` and `max-width: 720px` breakpoints for legacy components).
   - Styles are written for **Tailwind CSS v4** in `app/webui/static/src/` (`tailwind.css` entry, `tokens.css`, `components.css`, `aura.css`, `shell.css`, `mobile.css`) and compiled with the standalone Tailwind CLI (no Node) into `app/webui/static/style.css`, which **is committed** so the app runs without a build step. After editing anything in `src/` (or adding Tailwind classes in `index.html`, `app.js` or `features.js`), run `extras\build-css.bat` and commit the regenerated `style.css`. Never edit `style.css` by hand.
   - Colors come from the design tokens in `src/tokens.css` (light in `:root`, dark in `:root[data-theme="dark"]`); use the variables (`var(--accent)`) or the matching Tailwind colors (`bg-surface`, `text-muted`, `border-line`…), never hard-coded theme colors.
