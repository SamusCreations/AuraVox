# Instrucciones para Agentes de IA (AGENTS.md / CLAUDE.md)

Este proyecto (**AuraVox**) es mantenido y modificado colaborativamente por múltiples asistentes de IA.

## Reglas obligatorias antes y después de cualquier cambio

1. **Lectura inicial obligatoria:**
   Lee siempre [`CONTEXTO_PROYECTO.md`](./CONTEXTO_PROYECTO.md) antes de proponer o aplicar cambios. Allí está documentada toda la arquitectura del servidor (`app/webui/`, `app/core/`, `app/skills/`, `app/voice/`, `plugins/`), la SPA vanilla (`app.js`, `features.js`, `i18n.js`, `style.css`), el sistema de perfiles y las rutas HTTP.

2. **Actualización continua del contexto:**
   Si agregas, renombras o modificas vistas, rutas `/api/*`, herramientas del LLM, esquemas de `config/` o reglas de `.gitignore`, **actualiza [`CONTEXTO_PROYECTO.md`](./CONTEXTO_PROYECTO.md) en la misma sesión** para que cualquier otra IA que trabaje después encuentre el contexto al día.

3. **Privacidad y Git (`.gitignore`):**
   Nunca elimines exclusiones de `.gitignore` ni subas datos personales, coordenadas reales, voces clonadas, historiales de chat o archivos generados a las plantillas `config/*.example.yaml`.

4. **Interfaz bilingüe y sin frameworks:**
   - Agrega toda cadena nueva de interfaz en `STRINGS.es` y `STRINGS.en` (`app/webui/static/i18n.js`) y en `MESSAGES["es"]` / `MESSAGES["en"]` (`app/webui/i18n.py`).
   - Mantén el frontend en HTML/CSS/JS vanilla (sin bundlers ni frameworks externos) y cuida el diseño adaptable en móvil (`max-width: 900px` y `max-width: 720px`).
