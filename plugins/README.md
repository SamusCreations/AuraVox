# Plugins de AuraVox

Cada carpeta de aquí es un plugin: herramientas nuevas que los asistentes
pueden usar (el modelo decide cuándo llamarlas).

```
plugins/
  mi_plugin/            ← el id: minúsculas, números y _ (2 a 40)
    manifest.json
    plugin.py
```

## manifest.json

```json
{
  "id": "mi_plugin",
  "name": "Nombre para mostrar",
  "description": "Qué hace, en una frase.",
  "version": "1.0",
  "author": "Tu nombre",
  "min_role": "guest",
  "tools": [
    {
      "name": "nombre_de_la_herramienta",
      "description": "En inglés: cuándo usarla (el modelo lee esto).",
      "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    }
  ]
}
```

- `min_role`: quién puede usarlo: `guest` (todos), `user` (perfiles) o
  `admin` (solo administradores). El administrador lo puede cambiar.
- `tools`: en el formato de herramientas de Ollama (JSON Schema).

## plugin.py

```python
def call(name, args, ctx):
    # name: la herramienta que llamó el modelo; args: sus argumentos (dict).
    # ctx: quién pregunta (ctx.role, ctx.profile, ctx.assistant, ctx.lang…),
    #      o None en los modos de consola.
    return "Texto con el resultado, para que el modelo redacte la respuesta."
```

Opcionales:
- `tools(ctx)`: devuelve la lista de herramientas si dependen de algo (en
  vez de las del manifiesto).
- `context(ctx)`: texto que se suma a las instrucciones del asistente.
- `check(settings)`: `(ok, texto)` para el botón "Probar" de sus ajustes.
- `http(method, action, data, ctx)`: rutas propias en
  `/api/plugin/<id>/<acción>` (GET con los parámetros de la URL, POST con
  JSON); devuelve un dict o `(estado, dict)`. Las puede llamar quien tenga
  el rol mínimo del plugin; lo que sea solo para administradores lo
  comprueba el plugin con `ctx.role`. `ctx.emit(evento)` manda un evento al
  chat durante una respuesta (el de ComfyUI manda `{"type": "job"}` y la
  página dibuja la tarjeta de progreso, ver `features.js`).

## Ajustes

`"settings"` en el manifiesto: lo que llena un administrador en Ajustes →
Plugins y el plugin lee con `plugins.settings("<id>")`. Tipos: `text`,
`secret` (no se vuelve a mostrar), `number`, `select` (con `"options":
[{"value", "label": {"es", "en"}}]`) y `bool` (se guarda `"true"`/`"false"`).

`comfyui` es el ejemplo más completo: ajustes, rutas propias, trabajos en
segundo plano y su propio panel en Ajustes.

## Activarlo

Un plugin nuevo arranca **desactivado** (es código que corre en tu PC):
actívalo en **Ajustes → Plugins** (solo administradores), donde también
se elige su rol mínimo. Si tiene un error al cargar, ahí se ve cuál.

Los que vienen con AuraVox (búsqueda web y lugares, clima, Spotify) son
plugins también y se pueden desactivar igual. `dice_example` es un
ejemplo mínimo para copiar.