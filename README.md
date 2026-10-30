# AuraVox — asistentes de IA locales por chat y por voz

**AuraVox** es el nombre de la aplicación (antes "Asistentes"): sus
asistentes (JARVIS, BELLA, ZIGGY y los que crees) corren en esta PC con
Ollama, y se usan desde la interfaz web (`AuraVox.bat`), también desde
el celular por la red local.

Esta carpeta es autocontenida: tiene su propio Python (`python\`), sus
propios modelos de voz ya descargados (`cache\`) y los scripts. No depende
de ComfyUI ni de nada instalado bajo `F:\AI\ComfyUI`.

Todos los asistentes (JARVIS, BELLA, y cualquiera que agregues) se definen
en **un solo archivo, [config/assistants.yaml](config/assistants.yaml)** — voz,
velocidad, idioma, parámetros del modelo y personalidad completa de cada
uno. No hay Modelfiles ni `ollama create`: cada asistente llama directo a
su `base_model` de Ollama en cada petición, con la personalidad/parámetros
de ese archivo. Agregar un asistente nuevo es copiar una sección y
cambiarle el nombre — no hace falta tocar ningún `.py`. O, más cómodo,
desde la interfaz web (ver abajo).

## Estructura de la carpeta

```
AuraVox\
├─ AuraVox.bat              Arranca todo: la interfaz web (galería, chat/voz y configuración)
├─ README.md, CONTEXTO_PROYECTO.md
├─ extras\                  Los demás .bat (se abren igual con doble clic):
│  ├─ run_voice_loop.bat    Asistente por voz continuo en consola (todos a la vez)
│  ├─ run_assistant.bat     Modo texto de un asistente: extras\run_assistant.bat jarvis
│  ├─ switch_model.bat      Cambiar el modelo base de un asistente
│  ├─ free_ollama_memory.bat  Liberar la memoria de Ollama si quedó algo cargado
│  └─ spotify_setup.bat     Conectar Spotify (una sola vez)
├─ config\                  Lo que se edita: assistants.yaml, wake_words.txt,
│                           languages.txt, spotify_config.yaml
├─ app\                     El código (paquete de Python)
│  ├─ paths.py              Todas las rutas del proyecto, en un solo lugar
│  ├─ core\                 Configuración, motor de conversación, bucle de voz
│  │                        (assistant_common, assistant_engine, config_store, voice_loop,
│  │                        attachments: texto de los archivos adjuntos)
│  │                        y transliteración de nombres (romanize)
│  ├─ voice\                Oído y voz: micrófono continuo (mic_stream), Whisper,
│  │                        Supertonic, push to talk, palabras de activación, DLLs de CUDA
│  ├─ tools\                Herramientas del modelo: búsqueda web, lugares, Spotify
│  ├─ webui\                Servidor de la interfaz, chat de prueba y escucha
│  │  │                     manos libres (voice_listener);
│  │  └─ static\            la página (index.html, app.js, style.css, i18n.js, orb.js)
│  └─ scripts\              Lo que corren switch_model / free_ollama_memory / spotify_setup
├─ audio\                   Audio generado: respuestas del modo texto y muestras de voz
├─ cache\                   Modelos de Whisper y Supertonic (no tocar)
└─ python\                  Python portable con todas las dependencias (no tocar)
```

En la raíz solo quedan `AuraVox.bat` y la documentación; los otros `.bat`
están en `extras\` (buscan la raíz con `%~dp0..\`). Cada uno arranca su
script de `app\`; las rutas a `config\`, `audio\` y la página
salen de [app/paths.py](app/paths.py), así que la carpeta se puede mover
entera sin tocar nada.

## Interfaz web de configuración — AuraVox.bat

Abre en el navegador (`http://127.0.0.1:8765/`) un panel para hablar con
los asistentes y administrar todo lo de `assistants.yaml` sin editarlo a
mano:

- **Galería de inicio:** la primera página muestra los asistentes como
  tarjetas, cada uno con su orbe de color, modelo, voz, idiomas y forma de
  activación (y un aviso si su modelo no está instalado). "Chat" lo abre
  en el chat escrito; "Voz" lo abre directo en la conversación por voz y
  empieza a escuchar. La última tarjeta crea un asistente nuevo.
- **Al abrir un asistente** lo principal es el chat (o la voz), en el
  centro. Su configuración va en un panel a la derecha que se muestra u
  oculta con el botón de ajustes (la página recuerda si lo dejaste
  abierto). En pantallas angostas el panel pasa a ser un cajón por encima
  del chat. Cada vista tiene su dirección (`#/a/jarvis`, `#/new`,
  `#/shared`): atrás/adelante del navegador y recargar funcionan.
- **Idioma del chat** (junto a los modos):
  - *Escribir* → "Responde en": **el idioma en que escribas** (por defecto,
    entre los idiomas del asistente) o uno fijo. Lo decide el propio modelo
    (responde en el idioma de tu mensaje; si es muy corto, como "ok", sigue
    el de la conversación) y el revisor de la respuesta dice en qué idioma
    salió, para la voz.
  - *Conversación por voz* → "Entiende y habla": **todos los configurados**
    (Whisper elige entre ellos en cada frase) o **solo uno** (entiende y
    responde únicamente en ese).
- **Varios asistentes en la misma conversación** (botón "Invitar" junto a
  los modos): se suman otros asistentes que usen el **mismo modelo** que el
  de la página (así nunca se cargan dos modelos a la vez; los demás
  aparecen deshabilitados con su modelo). En la conversación por voz cada
  uno aparece como un aro con su color, a los costados del principal; el
  que habla reacciona a su voz y se resalta, el que piensa gira.
  - Todos escuchan toda la conversación: a cada uno le llega lo que dijeron
    los demás marcado como "[NOMBRE]: …", y una nota de que es una charla
    grupal y debe hablar solo por sí mismo.
  - Solo responde aquel a quien le hablas: nombrado al principio ("Bella,
    ¿qué opinas?", "Jarvis y Bella, despídanse") o al final ("¿Y tú,
    Bella?"), por su nombre, nombre en pantalla o variantes de activación.
    Nombrarlo en medio de la frase ("lo que dijo Jarvis") no cuenta. Si no
    le hablas a nadie, responde el de la página. Si nombras a varios,
    responden en orden y el segundo ya oyó al primero.
  - Cada uno con su voz y su velocidad; en el chat escrito cada respuesta
    lleva el nombre de quien la dijo.
  - **Preguntas para todos** ("todos", "ustedes", "los dos", "chicos",
    "¿qué opinan?", "everyone", "you guys", "vocês"…): responden todos, uno
    por uno. Empieza el que indiques ("empezando por Bella", "Jarvis
    primero", o nombrándolo al principio: "Bella, ¿qué opinan todos?"); si
    no indicas, el orden es al azar. Cada uno recibe las respuestas de los
    anteriores y la indicación de reaccionar a ellas ("Coincido con Jarvis
    en…", "A diferencia de Bella…") y dar su propia postura desde su
    personalidad (sin escudarse en "como asistente no tengo gustos").
    "¿Qué opinan los expertos…?" o "todos los gatos" no cuentan como
    pregunta al grupo. En voz, "Interrumpir" corta la ronda.
  - Todos los aros miden lo mismo; solo crece el del que está hablando
    (hacia arriba, sin mover su nombre). El modo voz usa toda la pantalla:
    los aros se dimensionan con el espacio real disponible (alto libre y
    ancho repartido entre los aros) y el estado, los subtítulos y los
    botones quedan abajo.
  - **Tocar el aro de un invitado lo hace el asistente de la página** (el
    panel pasa a mostrar y editar SU configuración) y el anterior queda
    como invitado; la conversación sigue igual. No se puede mientras alguno
    está respondiendo ni desde un asistente nuevo sin guardar.
- **Pausa para pensar** (modo voz): cuánto silencio se espera antes de dar
  la frase por terminada (1 a 4 s, 2 s por defecto; antes 0,9 s fijos
  cortaban la pregunta). Además, si la frase suena cortada (termina en "y",
  "de", "the"… o es solo "busca en internet"), se espera el resto: "Sigue,
  te escucho…". `voice_loop` pasó de 0,8 s a 1,6 s.
- **Mapa de lugares cercanos:** cuando el asistente busca lugares "cerca de
  mí", el chat muestra un mapa (OpenStreetMap) con tu ubicación y los
  lugares numerados, la lista con distancias y un enlace "Cómo llegar" a
  cada uno (Google Maps). Tocar un lugar de la lista lo centra en el mapa.
  En la conversación por voz aparece debajo del aro.
- **Color de cada asistente** (panel → Identidad → Color): automático
  (sale de su nombre), uno de los sugeridos o cualquiera con el selector
  libre. Pinta el aro y el aura del modo voz (vivo cuando habla el
  asistente, en pastel del mismo tono cuando te escucha a ti), el fondo de
  ese modo, su orbe en el chat y su tarjeta en la galería. El cambio se ve
  al instante, y al guardar queda como `color: "#rrggbb"` en
  `assistants.yaml` (sin ese campo = automático).
- **Español o inglés:** toda la interfaz, incluidos los errores del
  servidor. Se elige arriba a la derecha y el navegador lo recuerda.
- **Crear, editar, duplicar y eliminar asistentes.** Al eliminar se quitan
  también sus variantes de `wake_words.txt`.
- **Voz:** las 10 voces de Supertonic-3 con botón ▶ para escuchar una
  muestra en el idioma de la interfaz ("Esto es una muestra de esta voz.
  Puedes usarla para el modelo que desees." / su versión en inglés). Se
  reproduce a la velocidad elegida (aproximado: la voz real se sintetiza ya
  a esa velocidad). Las muestras están en `audio\voice_previews\es\` y
  `...\en\`; si falta alguna, el servidor la genera y la guarda la primera
  vez que se pide.
- **Modelo:** lista solo los modelos BASE instalados en Ollama, con tamaño,
  cuantización y capacidades (avisa si alguno no tiene `tools`, que hace
  falta para búsqueda web, lugares y música). Oculta los personalizados,
  como los viejos `jarvis:latest`/`bella:latest` de la época de los
  Modelfiles: su prompt propio se sumaría al del asistente. Se reconocen
  porque su `parent_model` es otro modelo instalado o porque traen un
  prompt de sistema. También descarga modelos nuevos (`ollama pull`) con
  barra de progreso.
- **Respuestas del chat escrito con formato:** en el modo escrito el
  modelo responde con detalle cuando la pregunta lo pide, en Markdown
  (negritas, listas, tablas), con emojis como iconos (🌡️ 🌧️ 📍 💰…) y las
  cifras con sus unidades (25 °C, 12,5 km, 80 %). La página lo muestra con
  formato (sin dejar entrar HTML del modelo) y, si la voz está encendida,
  lo lee sin símbolos ni emojis y con las unidades dichas ("km/h" →
  "kilómetros por hora"). En la conversación por voz no cambia nada: frases
  cortas y sin símbolos. La regla está en `RESPONSE_STYLES["text"]`
  (`assistant_common.py`); la de "nada de emojis ni símbolos" de las reglas
  compartidas ahora dice que es solo para la voz, y el revisor ya no marca
  el formato como problema en el modo escrito.
- **Acceso desde otros dispositivos** (Ajustes compartidos → Acceso desde
  otros dispositivos): además de http://127.0.0.1:8765 (solo esta PC), la
  interfaz se abre por **HTTPS en el puerto 8443** para toda la red local,
  con todo (chat, voz, cámara, adjuntos). La tarjeta muestra el enlace con la
  clave de acceso y un código QR para el celular.
  - HTTPS porque los navegadores solo dejan usar micrófono y cámara en páginas
    seguras. El certificado lo genera la app (autofirmado, para las IP de la
    PC; se regenera si cambian) en Python puro (`app/webui/network.py`): la
    primera vez el navegador avisa y hay que tocar "Avanzado → Continuar".
  - Con clave: el enlace lleva `?key=…` y queda en una cookie. Sin ella no se
    entra; "Cambiar la clave" desconecta a todos. Desde otro dispositivo no se
    puede usar la escucha manos libres (es el micrófono de la PC) ni apagar el
    acceso por red. Se puede desactivar en la misma tarjeta.
  - La primera vez Windows pregunta si deja a Python usar las redes privadas:
    hay que permitirlo (si no, desde el celular no carga).
- **Editar y reintentar cualquier mensaje tuyo:** junto a cada mensaje
  (al pasar el mouse; en el celular, tocándolo) están ✎ (editarlo) y ↻
  (volver a enviarlo). Se borra lo que vino después y se manda de nuevo, igual
  o editado, con sus adjuntos. Un error tiene "Reintentar".
- **Menús:** las opciones del chat (voz del asistente en el chat escrito,
  invitar, reiniciar, liberar memoria) están en el ⋯ de la cabecera. En el
  celular, la barra superior se resume en ⋯ (manos libres, ajustes
  compartidos, consola, idioma) y se oculta dentro de un asistente; el clip y
  la cámara son un solo +.
- **Idioma de la conversación:** ya no hay selector ("Entiende y habla…"):
  se entiende y se responde en los idiomas configurados en el asistente.
- **Pausa para pensar:** ahora es un ajuste de cada asistente (panel →
  Comportamiento, `think_pause` en assistants.yaml, 1,5 s por defecto).
- **Abrir adjuntos:** al adjuntar, además del texto para el modelo se guarda
  el original (`config\chats\files\`, `file_store.py`). En el chat la
  imagen se abre en grande, y los archivos y audios con "Abrir"/"Escuchar"
  (visor del navegador, reproductor; si no está el original, su texto). Lo
  que podría ejecutar código en la página (HTML, SVG, XML, JS) se muestra
  como texto. Los originales que ya no usa ninguna conversación se borran
  solos al día siguiente.
- **Conversación guardada:** el historial (escrito y por voz, con los
  invitados) de cada asistente se guarda en `config\chats\<asistente>.json`
  al cambiar: no se pierde al ir a la galería, al recargar ni al abrirlo desde
  otro dispositivo. "Reiniciar" lo borra. Se guardan los últimos 120 mensajes
  y las imágenes solo de los 6 últimos que las tienen (`chat_store.py`).
- **Cámara:** con un modelo con visión, el botón de la cámara del cuadro de
  texto saca una foto y la adjunta (en el celular abre la cámara del sistema;
  en la computadora, una vista previa con botón para disparar y cambiar de
  cámara).
- **Silenciar (barra superior)** ahora solo apaga la escucha manos libres
  (llamar por nombre con el micrófono de la PC); la conversación por voz desde
  el aro sigue funcionando.
- **Recarga en caliente** (`app/webui/dev_reload.py`): `run_config_ui.bat`
  arranca un vigilante que lanza el servidor como proceso hijo. Si cambia un
  `.py` de `app\`, lo cierra ordenadamente y lo vuelve a lanzar (si el código
  nuevo tiene un error, espera al próximo cambio). La página pregunta cada 2 s
  por `/api/dev/version`: un cambio de CSS se aplica al vuelo y uno de HTML o
  JavaScript (o un reinicio del servidor) recarga la página en cuanto no se
  esté usando (sin conversación por voz, respuesta en camino, cambios sin
  guardar ni texto a medio escribir); la conversación sigue porque está
  guardada. Así los cambios se ven también desde el celular. `--no-reload`
  lo desactiva; `--log` usa otro archivo de registro (para pruebas).
- **Convertir archivos** (`app/core/converters.py`, herramienta
  `convert_file`): pídele al asistente "pásalo a PDF", "conviértelo a Excel",
  "a png"… con un archivo adjunto (o uno que ya mandó él). Usa Microsoft
  Office por automatización (invisible, macros desactivadas) para Word
  (docx, doc, rtf, odt, txt, md, html → pdf, docx, doc, rtf, odt, html),
  Excel (xlsx, xls, csv, ods → xlsx, xls, csv, ods, pdf, html) y PowerPoint
  (pptx, ppt, odp → pdf, pptx, ppt, odp), ffmpeg para imágenes (jpg, png,
  webp, bmp, gif, tiff, ico), audio (mp3, wav, ogg, opus, m4a, flac) y video
  (mp4, webm, mkv, mov, avi, gif), e imagen → PDF con Word. El resultado
  aparece en el chat con "Abrir" y "Descargar". PDF → Word no está: Word abre
  un aviso que no se puede cerrar estando invisible y se colgaba.
- **Adjuntos sin describir:** el asistente no describe ni resume una imagen o
  un documento a menos que se lo pidas; si solo adjuntas algo, dice que lo
  recibió y pregunta qué quieres hacer (a un audio solo sí lo transcribe).
- **Modelos de IA** (Ajustes compartidos): la lista de los modelos instalados
  en Ollama con su tamaño, memoria, capacidades, qué asistentes los usan y si
  hay versión nueva; botones para **actualizar**, **eliminar** (si lo usa algún
  asistente, el aviso dice cuáles dejarán de responder) y **agregar** uno
  nuevo por su nombre de ollama.com (`ollama pull`, con barra de progreso).
- **Chat:** pestañas "Texto" y "Voz"; las opciones (leer en voz alta,
  invitar, reiniciar, liberar memoria) van en el menú ⋯ de la cabecera. La
  lectura en voz alta del chat escrito empieza apagada. Ya no hay selector
  de idioma: se entiende y responde en los idiomas del asistente. Cada
  mensaje tuyo se puede **editar** o **volver a enviar** (✎ / ↻, al pasar el
  mouse o al tocarlo en el celular): se borra lo que vino después. La
  **pausa para pensar** de la voz es un ajuste de cada asistente
  (`think_pause`, en Comportamiento).
- **Voz:** un solo botón: micrófono para empezar, X para terminar; mientras
  el asistente habla, la X lo interrumpe.
- **Celular:** sin la barra de la app dentro de un asistente, botones en
  menús (⋯ arriba, + para adjuntar), alto real de la pantalla (`100dvh`),
  márgenes y letra de 16 px en los campos (iOS no hace zoom), avisos abajo,
  sin barras de desplazamiento al mostrar texto, y animaciones (mensajes
  nuevos, menús, diálogos, tarjetas) que se apagan con "reducir movimiento".
- **Versión de cada modelo** (panel del asistente → Modelo de IA, debajo de
  la memoria): dice si el modelo elegido es la última versión o si hay una
  nueva (con su tamaño), y las tarjetas de modelos con versión nueva llevan
  la etiqueta "nueva versión". Se compara el `digest` local (sha256 del
  manifest) con el de la misma etiqueta en su registro (registry.ollama.ai
  para los de ollama.com, hf.co para los de Hugging Face).
  - **Actualizar:** el mismo `ollama pull` con su barra de progreso; Ollama
    baja solo las capas que cambiaron y borra las de la versión anterior.
    Después se comprueba que quedó la versión nueva y cuántas capas viejas se
    borraron (en la consola).
  - **Actualizar automáticamente** (por defecto activado, se guarda por modelo
    en `config\model_updates.json`): el servidor comprueba a los 3 minutos de
    abrir la interfaz y cada 6 horas, y actualiza solo los que lo tengan
    activado (`app/webui/model_updates.py`).
- **Actualizar Ollama** (Ajustes compartidos → Ollama): muestra la versión
  instalada y la última (la consulta a ollama.com igual que la app de
  Ollama) y la instala con un botón: usa el instalador que la app de Ollama
  ya bajó (o lo descarga de GitHub con barra de progreso), comprueba su firma
  digital (Ollama Inc.) y lo instala en silencio; Ollama se cierra alrededor
  de un minuto. Los modelos y la configuración (`OLLAMA_MODELS`,
  `OLLAMA_CONTEXT_LENGTH`) no se tocan (`app/webui/ollama_update.py`).
- **Adjuntos en el chat escrito:** botón del clip, arrastrar archivos sobre
  el chat o pegar una imagen. Lo que se puede adjuntar depende del modelo:
  - **Imágenes** (PNG, JPG, WebP, GIF, BMP, AVIF; hasta 4 por mensaje), solo
    si el modelo tiene "visión" (`capabilities` de Ollama). Se reducen a
    1536 px y se mandan en JPEG. Con un modelo sin visión el botón no las
    ofrece y, si quedó alguna en el historial, se le avisa al modelo que hay
    una imagen que no ve. El modelo sigue viendo las imágenes de los 2
    últimos mensajes que las tengan.
  - **Documentos** (cualquier modelo): PDF (se lee en el navegador con
    pdf.js; si es escaneado y el modelo tiene visión, van las primeras 4
    páginas como imágenes), Word, Excel, PowerPoint, OpenDocument, EPUB,
    RTF, HTML, y texto o código en cualquier codificación. El servidor saca
    el texto sin librerías extra (`app/core/attachments.py`). Hasta 24 000
    caracteres por archivo (lo que entra en el contexto de 16k de Ollama
    sin desplazar el prompt de sistema); los 2 últimos mensajes con archivos
    mantienen el texto completo y los anteriores, el principio.
  - **Audio o video** (MP3, WAV, M4A, OGG, OPUS, FLAC, WebM, MP4, MOV, MKV…,
    hasta 150 MB): Whisper lo pasa a texto en el idioma que sea. La
    transcripción se ve desplegable en el mensaje y se le pasa al modelo.
  - En el mensaje del chat se ven las miniaturas y cada archivo con su texto
    desplegable. Al modelo le llega lo escrito primero y después cada
    adjunto entre `<<< >>>`.
- **Memoria de cada modelo:** cada tarjeta muestra cuánta VRAM ocupa
  usándolo, y debajo de la lista va el desglose del elegido: el modelo
  (con el contexto que usa Ollama), Whisper, Supertonic y, si el asistente
  tiene voz clonada, Qwen3-TTS; el total de una conversación por voz contra
  la VRAM de la GPU (nvidia-smi), con aviso si no entra o queda justo.
  - **Medido:** lo que reporta Ollama del modelo cargado (`/api/ps`) más
    ~1 GB del proceso de Ollama. Se guarda solo cada vez que se ve un
    modelo cargado, o con el botón "Medir" (lo carga un momento y, si no
    estaba en uso, lo descarga). Queda en `config\model_memory.json`.
  - **Estimado** (con `*`), mientras no hay medición: pesos + caché del
    contexto según la forma del modelo (capas, cabezas, ventana deslizante
    de Gemma, capas sin caché de Qwen 3.5) + el mismo margen.
  - Ojo: Gemma 4 E4B pesa 8,9 GB en disco pero ocupa ~4,2 GB de VRAM (deja
    parte fuera de la GPU); su estimado teórico se pasa mucho, por eso
    manda la medición.
- **Comportamiento explicado:** cada parámetro (temperature, Top P, Top K,
  memoria, rondas de herramientas) muestra en vivo una etiqueta para el
  valor actual ("Equilibrado", "Errático"…). Además tiene un desplegable
  con qué hace, cómo se nota al subirlo o bajarlo y el rango recomendado.
- **Activación:** por nombre y/o push to talk con la tecla que elijas (ver
  la sección de push to talk más abajo).
- **Chat:** usa la configuración que se está editando en el panel,
  aunque no esté guardada. Guardar o descartar cambios no borra la
  conversación; cambiar de asistente sí. Tiene dos modos:
  - *Escribir:* tú escribes y el asistente responde hablando; la voz se
    puede apagar. Mientras habla, su avatar "respira".
  - *Conversación por voz:* bucle con el micrófono del navegador. Detecta
    cuándo empiezas y terminas de hablar, transcribe con Whisper, responde
    y vuelve a escuchar. Se puede interrumpir mientras habla. Se muestra
    sobre fondo oscuro con un **aro con aura** ([orb.js](app/webui/static/orb.js))
    que reacciona en vivo al audio: se deforma con el espectro de tu voz
    mientras escucha (tonos cian/verde) y con el de la voz del asistente
    mientras habla (violeta/rosa/naranja), y el halo crece con el volumen.
    Pensando o transcribiendo, un brillo da vueltas por el aro. Debajo van
    como subtítulos lo último que dijiste y lo que respondió. Tocar el aro
    empieza o termina la conversación.

  Usa las mismas herramientas reales: una búsqueda web muestra "Buscando en
  internet…" y dice el `search_announcement`, y "pon música" abre Spotify
  de verdad.

  La voz de las respuestas va por trozos (oraciones; si la primera es muy
  larga, se corta en su primera coma). El primero empieza a sonar en
  cuanto está listo y el siguiente se genera mientras suena el anterior.
  Todo lo generado queda en caché: en la página por mensaje, con la voz y
  velocidad con que se generó, y en el servidor (últimos 200 audios).
  "Escuchar de nuevo" y los anuncios repetidos no vuelven a sintetizar
  nada. El modelo de Ollama se queda cargado 15 minutos tras el último
  mensaje (no indefinidamente como en `voice_loop`). Whisper y Supertonic
  se cargan en el proceso de la interfaz solo al usar el chat, y
  "Liberar memoria" descarga todo.
- **Idiomas:** los 31 que soportan Whisper y Supertonic-3 a la vez
  (calculados de las propias librerías), todos o solo algunos por
  asistente, más el idioma por defecto.
- **El resto de campos:** temperature, top_k, top_p, memoria, rondas de
  herramientas, mensajes fijos, personalidad y "Nombre en pantalla".
- **Palabra de activación:** variantes (alias) de cada asistente y, en
  vivo, qué palabras comunes lo despertarían por error, con un botón para
  excluirlas.
- **Largo de las respuestas según el modo** (`RESPONSE_STYLES` en
  [app/core/assistant_common.py](app/core/assistant_common.py)):
  - *Chat escrito* (y el modo texto de consola): respuestas completas y
    detalladas cuando la pregunta lo amerita, de dos a cuatro párrafos.
  - *Conversación por voz* (y `voice_loop`): una o dos frases cortas y
    naturales.
  - En ambos modos las preguntas simples (la hora, un saludo) siguen
    siendo breves.
  - Pisa las indicaciones de brevedad de cada personalidad sin tener que
    tocarlas.
  - Los modelos chicos (qwen3.5:4b) obedecían poco la regla del system
    prompt, así que también se agrega un recordatorio corto al último
    mensaje del usuario (solo en lo que se manda a Ollama, no en el
    historial).
  - Medido: JARVIS (gemma4:E4B) ≈15 palabras en voz frente a 150–185 en
    texto. BELLA (qwen3.5:4b) 24–48 en voz frente a 124–166 en texto.
- **Ubicación en un mapa** ("Ajustes compartidos" → "Elegir en el mapa"):
  Leaflet con mapas de OpenStreetMap, gratis y abierto, sin API key.
  - **Carga:** Leaflet se baja del CDN recién al abrir el mapa, con
    verificación de integridad (SRI).
  - **Por defecto:** marca la ubicación actual del navegador (pide permiso
    la primera vez). Si no hay permiso, queda la ubicación guardada.
  - **Elegir:** clic en el mapa para mover el punto, o buscar un lugar por
    nombre (con Enter).
  - **Aplicar:** "Usar esta ubicación" llena latitud y longitud y, si se
    marca, también ciudad y país.
  - **Nominatim:** la búsqueda y el nombre del lugar pasan por el servidor
    (`/api/geo/*`) respetando su política de uso: User-Agent propio, 1
    petición/s y sin autocompletar mientras se escribe. Los resultados se
    guardan en memoria.
- **Consola** (barra lateral o Ctrl+`): panel abajo con lo que el servidor
  va haciendo en todo momento. Muestra:
  - cada ronda de Ollama y cuánto de eso fue cargar el modelo;
  - los reintentos cuando el modelo "narra" en vez de usar una herramienta;
  - qué herramienta usó, con qué argumentos y qué devolvió;
  - cada trozo de voz: dispositivo, tiempo y RTF, o si salió de la caché;
  - las transcripciones de Whisper, las peticiones HTTP y los errores.

  También incluye todo lo que imprimen Whisper y Supertonic. Tiene filtro
  de texto, "solo avisos y errores", seguimiento automático y altura
  ajustable arrastrando el borde. Lo mismo sigue saliendo en la ventana de
  `run_config_ui` ([app/webui/server_log.py](app/webui/server_log.py)).
- **Ajustes compartidos:** `user_context` (con botón para tomar la
  ubicación del navegador), `shared_context` y la lista global de palabras
  excluidas.

Detalles:

- Solo usa la librería estándar (sin dependencias nuevas). Escucha
  únicamente en 127.0.0.1; rechaza peticiones de otros orígenes/hosts.
- Al guardar reescribe `assistants.yaml` conservando los bloques de
  comentarios entre secciones (el encabezado de ayuda, el de
  `user_context`...) y los finales de línea del archivo. Antes de escribir
  relee el resultado y verifica que coincida con lo que se quería guardar.
  Deja siempre el archivo anterior en `config\assistants.yaml.bak`.
- Si editaste `assistants.yaml`/`wake_words.txt` a mano con la página
  abierta, no pisa tus cambios: avisa y pide recargar.
- Una sola interfaz a la vez. Si `run_config_ui.bat` ya está abierto en la
  misma versión, el segundo solo abre el navegador. Si el que está abierto
  es de una versión anterior, avisa y usa otro puerto, y la página vieja
  muestra "conectada a una versión anterior del servidor".
  - Bug que motivó esto: `http.server` activa `SO_REUSEADDR`, y en Windows
    eso dejaba que dos procesos escucharan el mismo puerto. Una ventana
    vieja seguía atendiendo a la página nueva y todo fallaba a medias:
    idiomas como `[object Object]`, push to talk sin registrar teclas y la
    activación que no se guardaba.
  - Ahora el puerto se abre con `SO_EXCLUSIVEADDRUSE`.
- Los cambios se aplican la próxima vez que arranquen `run_voice_loop.bat`
  o el modo texto. Mientras no uses el chat la interfaz no carga ningún
  modelo, así que puede quedar abierta mientras el asistente corre.
- Archivos: `app\webui\config_ui.py` es el servidor,
  `app\core\config_store.py` lee y escribe la configuración,
  `app\webui\chat_runtime.py` se ocupa de la voz, el oído y el chat, e
  `app\webui\i18n.py` guarda los mensajes del servidor. En
  `app\webui\static\` está la página, con los textos y las explicaciones
  en `i18n.js` y el aro del modo voz en `orb.js`.

## Manos libres en la interfaz web

Con `run_config_ui.bat` abierto ya no hace falta `run_voice_loop.bat`: el
servidor de la interfaz trae su propio bucle de voz
([voice_listener.py](app/webui/voice_listener.py)).

- **Llamar por el nombre desde cualquier página:** di el nombre de
  cualquier asistente que tenga activa "Responder a su nombre" (o mantén su
  tecla de push to talk), al principio o al final ("Jarvis, ¿qué hora es?",
  "Adiós, Ziggy"). La página abre a ese asistente en la conversación por
  voz, con su aura, y responde. "Jarvis" solo → pitido y te escucha.
- **La conversación por voz usa el micrófono del navegador** (con
  cancelación de eco). Mientras está abierta, la escucha del servidor queda
  en pausa: su micrófono se cierra y el botón muestra "En conversación". Al
  terminarla, la escucha vuelve sola.
  - Abierta llamando por el nombre: se cierra sola tras 8 s de silencio
    después de la última respuesta.
  - Empezada desde el aro: sigue hasta que la termines con el botón.
  - Si todavía no hiciste ningún clic en la página, el navegador no deja
    usar el micrófono ni sonar. En ese caso la conversación usa el
    micrófono del servidor y, mientras el asistente habla, solo cuenta lo
    que empiece con un nombre.
- **Invitar y sacar por voz** (solo asistentes con el mismo modelo, como
  desde el botón "Invitar"): se lo pides a la conversación con tus
  palabras, en cualquier idioma («invita a Jarvis», «¿puede venir Ziggy?»,
  «Bella, déjanos solos», «Джарвис, позови Беллу»…).
  - Son herramientas del modelo (`invite_to_conversation` /
    `remove_from_conversation`, ver `chat_runtime.group_tools`). Si el
    asistente ya estaba (o se pide invitarse a sí mismo), la herramienta lo
    dice y no pasa nada.
  - **El que entra saluda y el que sale se despide**, cada uno con su
    personalidad.
  - Sacar al asistente de la página pasa la conversación al primer
    invitado; si no hay otro, la termina.
- **Nombrar a alguien que no está en la conversación:** el modelo decide
  aparte si le estás hablando a él («Ziggy, ¿y tú qué opinas?», «Adiós,
  Ziggy»: se suma si usa el mismo modelo, o se abre su página si no) o si
  le pides a la conversación que lo traiga («invita a Jarvis»: lo invita el
  que está). Medido: 22 de 22 aciertos, con y sin historial.
- **Silenciar el micrófono:** el botón "Micrófono" de la barra superior lo
  silencia de forma general (se cierra el micrófono del servidor y tampoco
  se puede usar el del navegador). Queda guardado en
  `config\voice_listener.json` hasta que lo vuelvas a activar.
- **Varias pestañas:** responde una sola, la última que usaste; las demás
  muestran "En otra pestaña" en el botón del micrófono.
- **Sin ninguna página abierta,** o silenciado, el micrófono del servidor se
  cierra.
- **El navegador no deja sonar audio** en una página en la que todavía no
  hiciste ningún clic: si te avisa, haz clic una vez en cualquier parte.
- **Registro de cada ejecución:** todo lo que muestra la consola de la
  página se guarda también en `logs\webui_server.log`, que se sobreescribe
  cada vez que abres `run_config_ui.bat`. Sirve para revisar después qué
  pasó (errores, a quién se ruteó cada frase, qué herramientas se usaron).
- **Sin manos libres:** `run_config_ui.bat --no-voice` (o `python
  config_ui.py --no-voice`) no abre el micrófono del servidor; la
  conversación por voz usa el del navegador, como antes.
- No abras `run_voice_loop.bat` al mismo tiempo que la interfaz: los dos
  escucharían el mismo micrófono y responderían los dos.
- **Nombres en cualquier alfabeto:** Whisper escribe el nombre según el
  idioma en que hablaste ("Джарвис", "ジャービス", "جارفيس"). Para
  compararlos se pasan a letras latinas
  ([romanize.py](app/core/romanize.py)), y en la conversación se escriben
  como se llama el asistente ("Harvis, …" → "Jarvis, …").

## Push to talk

Cada asistente puede tener una tecla (o botón del mouse) de push to talk,
`push_to_talk_key` en `assistants.yaml`, que se elige desde la interfaz
apretándola:

- **Uso:** en `run_voice_loop.bat` y en la escucha manos libres de la
  interfaz, mientras la mantienes apretada se graba
  el micrófono y al soltarla lo dicho va directo a ese asistente, sin decir
  su nombre. Suena un pitido corto al empezar.
- **Interrumpir:** apretarla mientras cualquier asistente está hablando lo
  corta y graba lo nuevo, igual que decir un nombre (barge-in).
- **Solo push to talk:** con `wake_word: false` el asistente deja de
  responder a su nombre. Después de contestar no deja el micrófono abierto
  para seguir la conversación: cada turno es apretando la tecla otra vez.
  Con los dos activos, tras un turno por tecla la sesión sigue abierta como
  siempre.
- **Cómo detecta la tecla:** de forma global, aunque la consola no tenga el
  foco. Usa `GetAsyncKeyState` de Windows vía ctypes (`push_to_talk.py`),
  sin dependencias nuevas. Mientras espera una frase se consulta en cada
  bloque de audio (~30 ms) dentro de `MicStream.listen()`, sin hilos
  extra.
- **Qué tecla elegir:** la tecla también le llega a la ventana que tenga el
  foco, así que una letra se escribiría ahí. Por eso la interfaz recomienda
  F13–F24, Pausa, Bloq Despl o los botones laterales del mouse, y avisa con
  cualquier otra.

## Si algo se traba y Ollama se queda con memoria ocupada

Correr `free_ollama_memory.bat`. Libera de inmediato TODO lo que Ollama
tenga cargado en RAM/VRAM en ese momento, sin tener que cerrar y volver a
abrir Ollama. Pensado para cuando `voice_loop.py`/el modo texto terminan de
forma anormal (se cierra la ventana a la fuerza, un crash, doble Ctrl+C
encima de la limpieza) y por eso el modelo se queda cargado — probado
exactamente en ese escenario.

## Qué SÍ sigue siendo una dependencia externa

- **Ollama** (la app): tiene que estar instalado e iniciado en la máquina
  donde se ejecute esto (`ollama serve`, o el tray app de Windows).
- **El/los `base_model` de cada asistente** (assistants.yaml) ya
  descargados en Ollama — ver `switch_model.bat` para cambiarlos/instalarlos.
- Una GPU NVIDIA con drivers CUDA. Whisper y Supertonic corren en GPU con
  CUDA 12. Si no hay GPU, los dos caen solos a CPU.
  - **Librerías:** vienen como paquetes pip dentro de `python\` (no hace
    falta el CUDA Toolkit): `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`,
    `nvidia-cuda-nvrtc-cu12`, `nvidia-cuda-runtime-cu12`,
    `nvidia-cufft-cu12`, `nvidia-curand-cu12` y `nvidia-nvjitlink-cu12`.
  - **Carga:** [app/voice/cuda_setup.py](app/voice/cuda_setup.py) las prepara para los dos.
  - **Supertonic en CPU hasta septiembre 2026:** trae la CPU fija en su
    configuración (`DEFAULT_ONNX_PROVIDERS`). Además el `onnxruntime-gpu`
    instalado (1.27) era para CUDA 13, que no estaba. Se bajó a
    `onnxruntime-gpu==1.26.0`, el último para CUDA 12, que es el mismo CUDA
    que ya usa Whisper; así no hay dos cuDNN con el mismo nombre de DLL en
    el mismo proceso. `supersonictts.create_tts()` pide CUDA solo si sus
    DLL cargan de verdad, y si no, avisa por qué queda en CPU.
  - **Medido:** 2.3 s → 0.06 s para 9.3 s de audio (RTF 0.25 → 0.007), con
    Whisper cargado en el mismo proceso sin conflicto.
  - **No actualizar a ciegas:** si actualizas `onnxruntime-gpu` a 1.27 o
    más, vuelve a pedir CUDA 13 y Supertonic cae a CPU. El log lo dice, no
    falla.
- **Solo para las voces clonadas:** un Python con `torch`, `transformers`
  5 y `librosa`. Por defecto se usa el de
  `..\ComfyUI-Easy-Install\python_embeded` (ver "Voces clonadas"). Sin él,
  todo lo demás funciona igual y los asistentes con voz clonada hablan con
  su voz de respaldo de Supertonic.

## Voces clonadas (Qwen3-TTS)

Además de las 10 voces de Supertonic, cada asistente puede hablar con una
voz **clonada a partir de un audio**. Se crean en *Ajustes compartidos →
Voces y oído*:

1. **Audio de referencia:** se sube un archivo (WAV, MP3, OGG, WebM) o se
   graba en el momento. Conviene que sean 8 a 15 s de una sola persona,
   sin música, porque se usan como máximo 20 s.
2. **Texto de referencia:** Whisper transcribe lo que se dice. El texto se
   puede corregir, y con el texto exacto el clon se parece más.
3. **Uso:** la voz aparece en la sección *Voz* de cada asistente, en
   "Voces clonadas", con su muestra (▶). En `assistants.yaml` queda como
   `voice: custom:<id>`.

Detalles:

- **Modelo:** Qwen3-TTS "Base", que es el que clona; los "CustomVoice" que
  ya tenía ComfyUI solo traen voces fijas. Hay dos tamaños descargados en
  `cache\qwen-tts` y se elige en la misma tarjeta:
  - **0.6B** (por defecto): ~2,8 GB de VRAM.
  - **1.7B**: se parece más a la voz original, ~4,8 GB de VRAM.

  Los dos van a la misma velocidad (ver abajo).
- **Idiomas:** Qwen3-TTS habla español, inglés, portugués, francés,
  alemán, italiano, ruso, japonés, coreano y chino. En los otros 21 idiomas
  del pipeline, la voz clonada usa su **voz de respaldo** de Supertonic,
  que se elige para cada voz. Tampoco cambia de velocidad: el control
  "velocidad" no se aplica a estas voces.
- **Proceso aparte:** Qwen3-TTS necesita `torch`, que el Python portable de
  esta carpeta no trae (agregarlo serían ~5 GB más). Por eso corre en su
  propio proceso ([qwen_worker.py](app/voice/qwen_worker.py)) con otro
  Python, por defecto el de ComfyUI-Easy-Install, configurable en la misma
  tarjeta. La librería `qwen_tts` va copiada en [app/vendor](app/vendor)
  (Apache-2.0, la versión adaptada a transformers 5). El proceso arranca
  con la primera voz clonada y se cierra con "Liberar memoria" o al salir.
- **Rendimiento:** con "Acelerar" (activado por defecto) genera a RTF
  ~1,2, unas 3 veces más rápido que sin acelerar (~3,5), aunque sigue lejos
  de Supertonic (~0,05).
  - Para lograrlo, el modelo se compila al arrancar: ~4 min la primera vez
    y ~1,5 min después.
  - La app lo prepara en segundo plano si algún asistente usa una voz
    clonada; mientras tanto ese asistente habla con su voz de respaldo.
  - Detalles en la nota 12.
- **Archivos:**
  - [voice_settings.py](app/core/voice_settings.py) y
    `config\voice_settings.yaml`: los ajustes y la lista de voces.
  - `config\custom_voices\`: los audios de referencia.
  - [qwen_tts.py](app/voice/qwen_tts.py): habla con el proceso aparte y
    elige la voz de respaldo cuando hace falta.

## Cómo recrear esto en otra máquina

1. Copiar toda esta carpeta (`F:\AI\Assistant`) tal cual a la máquina nueva.
2. Instalar Ollama.
3. Fijar dónde guarda sus modelos: en esta máquina se hizo desde la propia
   app de Ollama (Settings → Models location), no como variable de entorno
   de Windows — apunta a `F:\AI\Models` (45 GB, no se mueve/copia con esta
   carpeta porque ya contiene los pesos). En la máquina nueva, decide dónde
   quieres que viva esa carpeta de modelos y configúralo igual.
4. Descargar los `base_model` que use `assistants.yaml` (hoy
   `gemma4:E4B` para JARVIS y `qwen3.5:4b` para BELLA) — no hace falta hacerlo a mano: la primera vez
   que corras `run_voice_loop.bat` o cualquier modo texto, se revisan solos
   contra `ollama list` y se ofrece descargar los que falten.
5. Ajustar `user_context` en `assistants.yaml` (nombre, ubicación y,
   recomendado, coordenadas) si el usuario/ubicación cambian — es
   compartido por todos los asistentes; la personalidad de cada uno está
   en su propia sección, no aquí.
6. Ejecutar `run_voice_loop.bat` (modo continuo, estilo Alexa, con todos
   los asistentes de assistants.yaml a la vez) o `run_assistant.bat
   <nombre>` (modo texto, p. ej. `run_assistant.bat jarvis`, para probar
   rápido sin usar el micrófono).

## Configurar/agregar asistentes — assistants.yaml

Un solo archivo. Tiene una clave especial de nivel superior y luego una
sección por asistente:

- **`shared_context`**: reglas de comportamiento OPERATIVAS comunes a
  TODOS los asistentes (cómo usar `web_search`/`find_nearby_places`, no
  usar emojis/markdown, no revelar el razonamiento interno, qué hacer si
  una petición es ambigua, etc.). Se agrega sola a la personalidad de cada
  asistente en cada petición — no hay que repetir estas reglas en cada
  uno, y un asistente nuevo las hereda automáticamente con solo definirse
  más abajo.
- **`user_context`**: quién sos y dónde vivís — `nombre`, `pais`,
  `ubicacion` (texto) y, opcional pero recomendado, `latitud`/`longitud`
  exactas. Sin coordenadas, `find_nearby_places` ("cerca de mí") geocodifica
  `ubicacion` por nombre cada vez (depende de que Nominatim/OpenStreetMap
  la reconozca bien); con coordenadas, las usa directas — más preciso y sin
  esa llamada de red. También compartido por todos los asistentes.
- **Una sección por asistente** (`jarvis`, `bella`, la que agregues):

  | Campo | Qué hace |
  |---|---|
  | `base_model` | Modelo de Ollama. Cámbialo con `switch_model.bat`, o simplemente escribe uno nuevo aquí y arranca cualquier script — se detecta solo y se ofrece instalarlo, igual que los demás. |
  | `voice` | Código de voz de Supertonic-3: F1-F5, M1-M5. Escucha las muestras en `audio\voice_previews\`. |
  | `speed` | Velocidad de habla (1.0 = normal, rango 0.5-2.0). |
  | `language` | Idioma por defecto (ISO 639-1). `voice_loop.py` lo sobreescribe turno a turno con el idioma detectado por Whisper; este es el que se usa en modo texto, si la detección falla o si le hablan en un idioma que no está en `languages`. |
  | `languages` | Idiomas en los que puede responder, p. ej. `[es, en]`. `[]` o ausente = los 31 que soportan Whisper y Supertonic-3. Whisper detecta entre la unión de los idiomas de todos los asistentes; si le hablan a uno en un idioma que no tiene, responde en su `language`. |
  | `temperature`, `top_k`, `top_p` | Parámetros de muestreo del LLM, van directo en cada petición a Ollama (`options`). |
  | `max_history` | Mensajes (usuario+asistente) que se mantienen de contexto. |
  | `max_tool_rounds` | Llamadas a herramientas encadenadas como máximo por turno. |
  | `search_announcement` | Qué dice antes de buscar en internet. |
  | `fallback_message` | Qué dice si se le traba la respuesta del todo. |
  | `label` | Nombre a mostrar en el log (por defecto, el nombre de la sección en mayúsculas). |
  | `wake_word` | `true` (por defecto) = se lo llama diciendo su nombre; `false` = solo push to talk. |
  | `push_to_talk_key` | Tecla que se mantiene apretada para hablarle sin decir su nombre (`"F13"`, `"SCROLLLOCK"`, `"XBUTTON1"`…); `""` = sin push to talk. Ver "Push to talk". |
  | `personality` | Lo ESPECÍFICO de este asistente nada más — quién es, su tono, cómo se dirige al usuario. Las reglas operativas ya están en `shared_context`, no hace falta repetirlas. La fecha/hora actual y `USER_CONTEXT` se agregan solos después de todo esto en cada petición. |

Valores inválidos (voz que no existe, velocidad/temperatura fuera de
rango) se avisan por consola y se usa el valor por defecto en su lugar —
no rompen nada. Los cambios se aplican la próxima vez que arranques el
script, no hace falta recrear nada en Ollama.

**Para agregar un asistente nuevo**: copia una sección completa de
`assistants.yaml` (no `shared_context`, esa es única y compartida), cámbiale
el nombre (ese nombre es a la vez su identificador interno y la palabra de
activación por voz) y ajusta los valores. Si el `base_model` que pusiste
no está instalado, se ofrece descargar solo al arrancar. `voice_loop.py`
detecta el asistente nuevo solo la próxima vez que arranque — probado
agregando un tercer asistente de prueba (con un modelo que tampoco estaba
instalado) durante el desarrollo de esto: se ofreció descargar el modelo,
apareció automáticamente en el reconocimiento de voz y funcionó en modo
texto (`run_assistant.bat <nombre>`) sin tocar ningún `.py`.

## Cambiar el modelo de IA (LLM) base de un asistente

Correr `switch_model.bat`. Es interactivo: lista los asistentes que haya en
`assistants.yaml`, preguntas cuál y qué modelo de Ollama usar — si no está
instalado, ofrece descargarlo (`ollama pull`) con el progreso en pantalla.
Luego:

- Actualiza solo la línea `base_model:` de ese asistente en
  `assistants.yaml` (deja un respaldo `.bak` del archivo completo; el resto
  —comentarios, personalidad, otros asistentes— queda intacto).
- Avisa si el modelo elegido no tiene la capacidad `tools` en Ollama (la
  búsqueda web y "lugares cercanos" dependen de eso).
- Hace una prueba rápida de que responde.

No hay que tocar nada más: como no hay Modelfile ni modelo personalizado en
Ollama, cambiar `base_model` en el YAML ES todo el cambio. Si el modelo
nuevo necesita otros `temperature`/`top_k`/`top_p`, ajústalos a mano ahí
mismo — el script no los toca.

## Notas

- `MODEL_KEEP_ALIVE` (`assistant_common.py`) está en `-1`: el modelo NUNCA
  se descarga solo por inactividad mientras esté corriendo, para no pagar
  nunca la recarga en frío (~15s) entre turnos. Esto es a propósito —
  decisión explícita, no un descuido: si algo termina de forma anormal
  (ventana cerrada a la fuerza, un crash, doble Ctrl+C encima de la
  limpieza normal) y el modelo se queda cargado, liberalo a mano con
  `free_ollama_memory.bat` (ver arriba) en vez de esperar un timeout
  automático. De paso, `handle_command()` (`voice_loop.py`) y el modo texto
  (`assistant_engine.py`) atrapan `requests.exceptions.RequestException`
  completo (no solo `ConnectionError`): un timeout o error HTTP de Ollama
  ya no corta toda la sesión, solo ese turno.
- `HF_HOME` y `SUPERTONIC_CACHE_DIR` se fijan en los `.bat` para que Whisper
  y Supertonic usen los modelos ya incluidos en `cache\` en vez de
  descargarlos de nuevo o de usar el caché del perfil de Windows.
- `python\` es un Python 3.12.10 embebido mínimo (sin torch ni el resto del
  entorno de ComfyUI): solo lleva lo que usan estos asistentes
  (`faster-whisper`/`ctranslate2` para STT, `supertonic`/`onnxruntime-gpu`
  para TTS, `pyyaml` para la config, `requests`/`ddgs` para las
  herramientas). Si se reinstala algo con `pip install -U supertonic`
  alguna vez, revisa que no reinstale la variante CPU de `onnxruntime`
  encima de `onnxruntime-gpu` (`supertonic` declara `onnxruntime` como
  dependencia normal; si pasa, corre:
  `python\python.exe -m pip install --force-reinstall --no-deps onnxruntime-gpu==1.27.0`).
- `qwentts.py` (motor TTS alternativo, no usado por `voice_loop.py`) se
  quedó fuera a propósito: depende del custom node Qwen-TTS de ComfyUI y no
  se puede desacoplar de él.
- `assistant_engine.py` es el motor genérico que usan tanto `voice_loop.py`
  como el modo texto (`run_assistant.bat <nombre>`, que sirve para
  cualquier asistente de `assistants.yaml`).
- Auto-instalación de modelos (`ensure_models_installed()` en
  `assistant_common.py`): al arrancar `voice_loop.py` o el modo texto, se
  revisa el `base_model` de cada asistente contra `ollama list`; si falta
  alguno, se pregunta por consola antes de descargarlo (nunca se descarga
  nada de varios GB sin confirmar). Así, agregar un asistente con un
  modelo que aún no tienes en `assistants.yaml` lo deja listo para usarse
  igual que los demás, sin tener que acordarte de correr `ollama pull` a
  mano aparte.
- `shared_context` vs `personality` (`assistants.yaml`): separé las reglas
  operativas comunes (uso de herramientas, formato de respuesta, no
  revelar razonamiento) de la personalidad específica de cada asistente
  para no repetirlas. Medí si convenía escribir `shared_context` en inglés
  en vez de español (por tokens): con las mismas reglas, mismo modelo y
  las herramientas reales incluidas, español usó 557 tokens de prompt e
  inglés 533 (~4% menos) — pero AMBOS formaron la llamada a `web_search`
  igual de bien (con fecha exacta en la consulta), sin diferencia de
  calidad. Se dejó en español por consistencia con el resto del prompt
  (personalidades, `USER_CONTEXT`, fecha/hora ya están en español) — el
  ahorro de tokens no compensa el riesgo de mezclar idiomas dentro de un
  mismo system prompt.
- Barge-in: mientras un asistente está hablando, cualquier voz captada que
  NO empiece con su nombre se ignora (para no reaccionar a su propio eco
  por el micrófono). Decir su nombre corta la respuesta al instante.
- Multilenguaje: `voice_loop.py` detecta automáticamente el idioma de cada
  frase (Whisper, `stt_whisper.py`) y responde en ese mismo idioma (LLM y
  voz de Supertonic-3, que soporta ~31 idiomas). El `language` de
  `assistants.yaml` es el que se usa en modo texto o si la detección da
  baja confianza. Medido: cambiar de idioma no agrega tiempo de
  síntesis/transcripción perceptible frente a tenerlo fijo.
- [config/languages.txt](config/languages.txt): qué idiomas puede reconocer/hablar el
  pipeline. Por defecto (archivo vacío) usa TODOS los que soportan a la vez
  Whisper y Supertonic-3 — nunca "detecta" un idioma que la voz no pueda
  hablar de verdad. Si escribes uno o más códigos ahí, se restringe solo a
  esos (los que no soporte ninguno de los dos modelos se ignoran con un
  aviso en el log). Es un tope GLOBAL; lo normal ahora es elegir los
  idiomas por asistente (`languages` en `assistants.yaml`, o desde la
  interfaz web), que se cruzan con este tope. Detectar dentro de una lista restringida usa
  `detect_language()` de Whisper antes de transcribir (~0.2s extra por
  frase) en vez de dejar que `transcribe()` autodetecte libremente.
- TTS por trozos (streaming), `CONFIG["tts_chunking"]` en `voice_loop.py`
  (activado por defecto): en respuestas de más de una oración, un hilo
  sintetiza la oración siguiente mientras se reproduce la actual, en vez de
  esperar a tener toda la respuesta lista. Medido con Supertonic-3: baja el
  tiempo hasta el primer audio (~12s → ~5s en una respuesta de 3 oraciones)
  y también el RTF total (0.90x → 0.76x). El barge-in sigue funcionando
  igual de trozo en trozo — si se detecta el nombre a mitad de una oración,
  se corta ahí y se descarta lo que faltaba por sintetizar. En el log
  aparece el RTF de cada trozo (lo imprime `supersonictts.py`) y, al final
  de la respuesta completa (o al cortarse por interrupción), una línea con
  el RTF agregado de toda la respuesta: `⏱ RTF total de la respuesta: Xs
  cómputo / Ys audio = Zx`. Si algo se siente peor (cortes raros entre
  oraciones, etc.), `"tts_chunking": False` vuelve exactamente al
  comportamiento anterior sin tocar nada más.
- Reproducción de audio: usa un `sounddevice.OutputStream` continuo
  (`_ChunkPlayer` en `voice_loop.py`) en vez de una llamada a
  `winsound.PlaySound` por trozo. Motivo: con trozos separados por
  `winsound` se oía un corte de ~1s en el empalme entre trozo y trozo. Ojo
  si tocas esto: el hilo que reproduce (`_feed_player`) escribe en bloques
  chicos (~100ms) y es el ÚNICO que puede llamar a
  `write()`/`abort()`/`finish()` del stream — llamar a `abort()` desde OTRO
  hilo mientras este está bloqueado en un `write()` en curso provocó un
  **segfault** del intérprete en las pruebas (PortAudio no soporta eso
  entre hilos); por diseño la interrupción solo pone una bandera
  (`cancel_event`) y se espera a que ese mismo hilo la note entre bloques y
  cierre el stream él mismo. Probado con 15 interrupciones seguidas en
  distintos puntos sin crashear.
- Números pronunciados por palabras (`supersonictts.py`, paquete
  `num2words`): el LLM ya suele escribir los números en palabras (se lo
  pide la personalidad de cada asistente), pero cuando cita algo textual de
  una búsqueda (precios, años, porcentajes) a veces se cuela un número en
  dígitos, y Supertonic los deletrea mal. Ahora se convierten a palabras
  antes de sintetizar, en el idioma detectado de esa respuesta. `num2words`
  no cubre los 31 idiomas de Supertonic-3 (le faltan bg, el, et, hi, hr);
  para esos los números se dejan tal cual en vez de fallar. Separadores de
  miles y decimales (bug corregido: "1.500 colones" se leía "uno punto
  cinco colones"). Un separador repetido ("1.500.000") o uno solo seguido
  de exactamente 3 dígitos ("1.500", "2,000") se toma como miles. Con "." y
  "," a la vez, el último es el decimal ("1.234,5"). Lo demás es decimal, y
  en español se lee con la palabra del separador que se usó ("27,5" →
  "veintisiete coma cinco"; num2words decía siempre "punto"). Lo que no
  tiene forma de número (una versión "3.10.2") se deja tal cual.
- [config/wake_words.txt](config/wake_words.txt): apodos/variantes de cada asistente que
  quieres que también se reconozcan, además de la coincidencia difusa
  automática que ya existe (`CONFIG["wake_word_ratio"]` en
  `voice_loop.py`). Se cargan al arrancar (log: "Variantes de ...
  cargadas"). Útil para apodos que suenan parecido a la persona pero no al
  nombre real (p. ej. "capitán" para Jarvis) — se comparan exacto y,
  además, por parecido igual que el nombre real. La lógica vive en
  `wake_word_utils.py` (la comparten `voice_loop.py` y la interfaz web).
- Sección `[excluir]` de `wake_words.txt`: palabras comunes que nunca
  cuentan como parecido aproximado a ningún nombre. Bug que la motivó:
  `SequenceMatcher("ella", "bella")` da 0.89 (umbral 0.62), así que
  cualquier frase que empezara con "ella…" despertaba a BELLA. Lo mismo
  pasaba con "bello", "ellas", "varios", "paris", "travis"… (medido contra
  una lista de palabras frecuentes). Una coincidencia EXACTA con un nombre
  o con una variante escrita sigue ganando aunque la palabra esté
  excluida. Contrapartida: si Whisper transcribe "Bella" como "Ella",
  ahora no despierta. Se prefirió eso a que se active sola con
  conversaciones normales.
- Datos en tiempo real para el LLM: `get_realtime_facts()` en
  `assistant_common.py` es el punto central de donde todos los asistentes
  sacan fecha/hora actual — se recalcula en cada turno y se inyecta sola en
  el system prompt (`build_system_message()`), así que nunca hace falta
  decírsela ni que la busque en internet. Es el lugar donde agregar
  cualquier otro dato "en vivo" que se necesite en el futuro (zona horaria,
  etc.): todo lo que devuelva ese dict se vuelve disponible automáticamente
  para todos los asistentes sin tocar nada más.
- Precisión de `web_search` (`websearch.py`) para preguntas de actualidad
  ("qué partido se juega hoy", "el clima ahora", "el precio del dólar
  ahora"): usa `region="wt-wt"` (sin sesgo geográfico — el default de
  `ddgs`, "us-en", sesgaba a fuentes en inglés/EE. UU. aunque la consulta
  viniera en español) y detecta consultas del tipo "hoy/ahora" (en varios
  idiomas) para primero restringir a resultados de las últimas 24h
  (`timelimit="d"`, con reintento sin ese filtro si no hay nada). La
  `personality` de cada asistente (assistants.yaml) le pide incluir la
  fecha exacta y nombres propios en la consulta, además de reintentar con
  una consulta más precisa si el primer resultado sale genérico, en vez de
  rendirse o remitir al usuario a buscarlo él mismo (probado con fútbol,
  clima y tipo de cambio — no es algo específico de deportes).
  `max_tool_rounds` (assistants.yaml) da margen a ese reintento. Límite
  conocido: un modelo pequeño/cuantizado a veces "narra" que va a buscar en
  vez de llamar realmente a la herramienta — pasó de verdad con
  `find_nearby_places` en un segundo turno de una conversación (el modelo
  ya la había usado antes y, en vez de llamarla de nuevo, se puso a
  describirla: "es mejor usar la función de búsqueda de negocios
  cercanas... con esa herramienta"). `_looks_like_leaked_tool_call()`
  (`assistant_common.py`) ahora detecta esto de tres formas — sintaxis de
  llamada como texto, el nombre exacto de la herramienta mencionado suelto,
  o la mención genérica de "herramienta"/"función [de búsqueda]"/"tool" —
  y fuerza un reintento explícito. Probado 5/5 veces reproduciendo el caso
  real que falló. Sigue sin ser perfecto (a veces el reintento contesta de
  memoria en vez de volver a llamar la herramienta, o hace una pregunta de
  aclaración) pero ya no se queda diciendo el nombre de una función en voz
  alta ni se traba del todo; si sigue molestando seguido, la salida es
  probar un modelo más grande/menos cuantizado con `switch_model.bat`.
- `find_nearby_places` (`nearby_places.py`) ahora busca con **Overpass
  API** (consulta por etiquetas OSM reales — `amenity=gym`,
  `shop=supermarket`, etc. — dentro de un radio) en vez de solo Nominatim
  (búsqueda de texto libre). Motivo: pedirle "gimnasio" a Nominatim podía
  devolver una CALLE llamada "Calle El Gimnasio" en vez de un gimnasio de
  verdad — no hay forma de decirle "solo negocios de esta categoría".
  Overpass sí filtra por lo que el lugar REALMENTE ES en OpenStreetMap.
  `_CATEGORY_TAGS` mapea las categorías conocidas (las mismas de antes:
  restaurante, farmacia, gimnasio, supermercado, etc.) a sus etiquetas OSM;
  agregar una categoría nueva es un renglón ahí. Para nombres propios
  ("Walmart", "Starbucks") o categorías sin mapear, sigue cayendo a
  Nominatim como respaldo. El servidor público de Overpass a veces da
  504/timeout bajo carga (~1 de cada 3-5 veces en las pruebas) — reintenta
  una vez más antes de rendirse y caer a Nominatim.

## Música con Spotify

Los asistentes pueden poner música por voz: canciones, artistas, playlists,
o pedidos por género/ambiente/actividad ("pon algo de fondo para
estudiar", "pon reggaeton", "pon la canción X de Y"). Funciona en dos
niveles según si la persona que usa el asistente tiene Spotify Premium o
no — pensado para que este mismo sistema lo pueda usar cualquiera, cada
quien con sus propias credenciales:

- **Sin Premium (o sin configurar todavía)**: busca la canción/playlist en
  Spotify y la lanza con el protocolo `spotify:...`, que abre la app de
  Spotify que ya tengas instalada (celular o PC) y empieza a reproducir
  ahí. No requiere haber iniciado sesión con este sistema — usa la sesión
  que ya tengas abierta en tu Spotify. Limitación: el asistente no puede
  pausar, saltar ni subir/bajar el volumen por voz en este modo, porque
  eso si requiere control remoto real (ver abajo).
- **Con Premium**: además de lo anterior, controla la reproducción de
  verdad a través de la Spotify Connect API — pausar, reanudar, saltar,
  volver a la anterior, subir/bajar volumen, todo por voz. Requiere haber
  iniciado sesión una vez con `spotify_setup.bat` (ver más abajo).

### Configuración inicial (una sola vez, por instalación)

1. Andá a [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard),
   iniciá sesión con tu cuenta de Spotify (sirve la gratuita) y creá una
   app nueva ("Create app"). Nombre y descripción, lo que quieras.
2. En el formulario de creación (o después en Settings → Edit) agregá este
   **Redirect URI** exacto — es obligatorio, sin esto el login falla:
   `http://127.0.0.1:8888/callback`
3. Marcá que vas a usar la Web API cuando te lo pregunte, guardá.
4. Entrá a Settings de la app y copiá el **Client ID** y el **Client
   Secret** (el secret está oculto detrás de un botón "View client
   secret").
5. Corré `spotify_setup.bat`. Te va a pedir el Client ID y el Client
   Secret (pegalos), después si tenés Premium o no. Si decís que sí, se
   abre el navegador para iniciar sesión en Spotify y autorizar el acceso
   — es un login único, después queda guardado. Todo se guarda en
   `spotify_config.yaml`.
6. Listo — no hace falta tocar ningún otro archivo. Los asistentes ya
   detectan solos que Spotify está configurado la próxima vez que
   arranques `voice_loop.py` o `assistant_engine.py`.

Si más adelante cambiás de cuenta o querés reconfigurar, volvé a correr
`spotify_setup.bat`.

### Detalles técnicos

- `spotify_config.yaml`: `client_id`, `client_secret`, `premium` (true/
  false), `refresh_token` (solo si sos Premium y ya hiciste el login).
  Vacío/`premium: false` por defecto — sin esto, `play_music` responde con
  un mensaje claro pidiendo correr `spotify_setup.bat`, en vez de fallar
  feo.
- `spotify_skill.py`: `play_music(query, tipo)` busca con la Client
  Credentials API (no necesita login) y luego, si hay `refresh_token`,
  reproduce con la Connect API (`_play_on_device`); si no, lanza el URI
  `spotify:` local (`_launch_locally`, usa `os.startfile` en Windows). Las
  herramientas de control (`pause_music`, `resume_music`, `skip_music`,
  `previous_music`, `set_music_volume`) solo se agregan a `TOOLS` si hay
  Premium + `refresh_token` — un asistente sin esas condiciones ni se
  entera de que existen, así que nunca intenta llamarlas.
- Se integra al resto de herramientas (`websearch.py`) en
  `assistant_engine.py`: `TOOLS = _WEB_TOOLS + _SPOTIFY_TOOLS`, y
  `call_tool()` prueba primero `spotify_skill.call_tool()` (devuelve
  `None` si no reconoce el nombre) antes de caer a `websearch.call_tool()`
  — así cada módulo de skill puede agregarse sin tocar el otro.
- **Bug encontrado y arreglado al probar esto**: pedirle música al modelo
  ("pon musica de reggaeton") a veces NO llamaba a `play_music` en
  absoluto — el modelo contestaba con toda confianza "listo, te pongo
  música de reggaetón" sin invocar la herramienta de verdad, así que la
  música nunca sonaba. A diferencia del bug de `find_nearby_places`, acá
  no había ninguna pista rara en el texto (nada de "herramienta" ni
  sintaxis de tool call) — sonaba como una respuesta perfectamente normal,
  solo que mentía. Se resolvió con dos cambios en `assistant_common.py`:
  (1) `_FORCED_TOOL_KEYWORDS` — si el último pedido del usuario tiene
  pinta de pedido de música o de lugar cercano y esa herramienta todavía
  no se llamó ni una vez en el turno, se fuerza un reintento explícito
  ("tenés que llamar la herramienta de verdad, no alcanza con decir que
  ya lo hiciste"); sigue insistiendo en rondas sucesivas (acotado por
  `max_tool_rounds`) hasta que la llame de verdad, pero deja de insistir
  apenas la llamó una vez, para no interferir con la respuesta final
  legítima que sigue después del resultado real. (2) se encontró además
  que el propio mensaje del modelo que trae el `tool_calls` a veces
  incluye texto tipo "te pongo la música" en el mismo turno, y dejar ese
  texto en el historial confundía al modelo en la ronda siguiente
  (después de recibir el resultado de la herramienta, contestaba con
  `content` vacío una y otra vez hasta agotar `max_tool_rounds` y caer al
  mensaje de fallback) — ahora se vacía ese `content` antes de guardarlo
  en el historial. Este mismo mecanismo resultó clave también para
  `find_nearby_places` al comparar modelos (ver "Comparación de modelos
  base" abajo): con Qwen3.5-9B, cuando fallaba, no narraba ni se quedaba
  callado — **inventaba nombres de negocios y distancias falsas** ("hay
  un Power Gym a 300 metros") sin haber buscado nada, un fallo más grave
  que el de Gemma. `_FORCED_TOOL_KEYWORDS` cubre ambos casos con la misma
  lógica genérica.

## Comparación de modelos base (búsqueda del mejor modelo, julio 2026)

Investigación de qué modelo de Ollama conviene más como `base_model` de
los asistentes, pensando en entendimiento, velocidad y uso de
cómputo/memoria, con la restricción real de que tiene que andar bien en
una RTX 4080 SUPER (16 GB VRAM) con tool calling confiable — no alcanza
con mirar benchmarks genéricos, hay que probarlo contra las herramientas
reales de este proyecto (`web_search`, `find_nearby_places`,
`play_music`).

**Candidato investigado a fondo: Qwen3.5-9B** (Alibaba, lanzado marzo
2026), el más recomendado en varias fuentes para la franja de 8-10 GB
VRAM por su cobertura multilingüe (201 idiomas vs. la de Gemma, bastante
más angosta), su IFEval más alto (91.5) y su footprint más chico en disco
(6.3 GB en Ollama a Q4_K_M vs. los 9.16 GB de `gemma4:E4B`). Se descargó
(`ollama pull qwen3.5:9b`) y se probó en serio contra las tres
herramientas reales del proyecto, con exactamente el mismo
`shared_context`/personalidad que usan JARVIS y BELLA.

**Resultado**: en velocidad cruda, Qwen genera bastante más rápido
(~90 tokens/s vs. lo que da Gemma), pero en la práctica el tiempo total
por pregunta terminó siendo prácticamente el mismo (~8s de promedio en
ambos, en una tanda de 18 preguntas variadas) porque Qwen necesitó más
reintentos por fallar más seguido en llamar la herramienta correcta a la
primera. En confiabilidad de tool calling —la parte que más importa para
un asistente de voz que ya se pasó gran parte de esta sesión endureciendo
ese mismo punto para Gemma— Qwen3.5-9B quedó claramente atrás: 60-89%
de aciertos según la corrida (con `_FORCED_TOOL_KEYWORDS` puesto) contra
el 100% de `gemma4:E4B` en la misma tanda de 18 preguntas. Peor aún, el
modo de falla de Qwen fue más grave: en vez de narrar o quedarse en
blanco (lo que sí hace Gemma cuando falla), Qwen inventaba negocios y
distancias falsas con total naturalidad — un riesgo real de que el
asistente le dé al usuario una dirección o nombre de lugar que no existe.
En calidad de respuesta general (razonamiento simple, explicaciones) los
dos están a la par, sin diferencia notable en español.

**Conclusión**: se mantiene `gemma4:E4B` como modelo por defecto de
JARVIS y BELLA — después de todo el trabajo de esta sesión endureciendo
`assistant_common.py` contra sus fallos específicos, termina siendo más
confiable en la práctica que la alternativa mejor puntuada en benchmarks
genéricos. `qwen3.5:9b` queda descargado y disponible igual (`ollama
list` lo muestra) por si en algún momento se prioriza el footprint más
chico o la cobertura multilingüe por encima de la confiabilidad de tool
calling — para probarlo alcanza con `switch_model.bat` y poner
`qwen3.5:9b` como modelo de cualquiera de los dos asistentes; no hace
falta tocar ningún otro archivo. Si Google saca una versión más nueva de
Gemma o aparece otro modelo candidato, vale la pena repetir esta misma
comparación (tanda de preguntas + `_FORCED_TOOL_KEYWORDS`) antes de
cambiar el default, en vez de guiarse solo por benchmarks publicados.

### Segunda ronda: modelos más chicos (mismo julio 2026)

Con el objetivo de mejorar rendimiento y consumo de recursos, se probaron
tres modelos bastante más chicos que `gemma4:E4B` (9.16 GB): `gemma4:e2b`
(Gemma más chico, 6.83 GB), `qwen3.5:4b` (3.23 GB) y `granite4.1:3b`
(2.00 GB, IBM). Misma metodología — tanda de 24 preguntas reales contra
`web_search`/`find_nearby_places`/`play_music` con
`_FORCED_TOOL_KEYWORDS` puesto, más preguntas de razonamiento simple.

| Modelo | Tamaño | Tool-calling | Tiempo total (24 preguntas) |
|---|---|---|---|
| `gemma4:E4B` (actual) | 9.16 GB | 24/24 (100%) | 149.0s |
| `gemma4:e2b` | 6.83 GB | 16/24 (67%) | 110.1s |
| `qwen3.5:4b` | 3.23 GB | 24/24 (100%) | 130.9s |
| `granite4.1:3b` | 2.00 GB | 24/24 (100%) | 84.8s |

- **`gemma4:e2b` — descartado.** La versión chica de Gemma cae a 67% de
  aciertos llamando herramientas, consistente en dos corridas separadas
  (falla sobre todo en `find_nearby_places`, agotando los reintentos de
  `_FORCED_TOOL_KEYWORDS` sin nunca llamarla — aunque al menos falla
  "limpio", con el mensaje de fallback, sin inventar nada). El ahorro de
  memoria (2.3 GB menos) no compensa perder un tercio de las respuestas.
- **`granite4.1:3b` — descartado a pesar de ganar en velocidad y tamaño.**
  Llama las herramientas de forma perfecta (100%, y el más rápido con
  diferencia), pero **falla en la fidelidad de la respuesta** una vez que
  ya tiene el resultado real: preguntado "qué tiempo hace hoy en Buenos
  Aires" tres veces seguidas (ya con `web_search` funcionando), devolvió
  tres climas incompatibles entre sí (soleado 27°C, templado 22°C,
  nublado 22°C); preguntado por el campeón de la Champions League 2025
  con los mismos resultados de búsqueda que veían los otros modelos,
  inventó nombres de equipo que no existen — "Paris Saint-Girondins",
  "Paris Saint-Grenoble" (mezclando PSG con clubes franceses distintos) —
  y hasta dijo directamente "Liverpool" sin ninguna base. En preguntas
  fácticas simples y no ambiguas ("capital de Australia") acertó 3/3 sin
  problema, así que el fallo es específico a cuando tiene que sintetizar
  un resultado de búsqueda con varios datos numéricos o nombres propios
  parecidos entre sí — ahí un modelo de 3B parece quedarse corto. Para un
  asistente que la gente usa para pedir datos reales, ese tipo de
  fabricación con total naturalidad es peor que ser lento.
- **`qwen3.5:4b` — confiable, sin fabricación de datos observada, pero
  sin ganancia real de velocidad.** 100% en tool-calling y no mostró el
  problema de fidelidad de Granite en las mismas preguntas (relata bien
  el resultado real de búsqueda, con un tono un poco más conversador que
  Gemma pero correcto). El tiempo total no bajó respecto al modelo
  actual (130.9s vs. 149.0s, dentro del margen de variación entre
  corridas — en una corrida anterior había sido más lento). Donde sí gana
  claro es en tamaño: 3.23 GB contra 9.16 GB, un ahorro real de ~6 GB de
  VRAM si eso importa más que unos segundos de latencia.

**Conclusión de la segunda ronda**: ningún modelo más chico ofrece una
mejora limpia de rendimiento/recursos sin sacrificar algo que importa.
Se mantiene `gemma4:E4B` como default. Si en algún momento el footprint
de memoria se vuelve un problema real (por ejemplo, correr esto en una
GPU con mucha menos VRAM), `qwen3.5:4b` es la alternativa más segura de
las probadas — no `granite4.1:3b`, a pesar de sus números de velocidad
más lindos, por el riesgo de fabricación de datos. Los cuatro modelos
quedan descargados (`ollama list`) y disponibles vía `switch_model.bat`
sin tocar código. El detector `_FORCED_TOOL_KEYWORDS` (que ahora también
cubre `web_search` además de `play_music`/`find_nearby_places`, agregado
durante esta ronda) mejora la confiabilidad de invocar la herramienta
correcta en cualquiera de los modelos — pero no puede arreglar que el
modelo, ya con el resultado real en mano, lo redacte mal; eso depende
solo de la capacidad del modelo elegido.

## Bugs reportados por el usuario tras la comparación de modelos (julio 2026)

Dos bugs reales encontrados usando el sistema en la práctica, no
relacionados entre sí:

### 1. "Vivo en Madrid" — la ubicación real nunca llegaba al modelo

Preguntar por el clima o la ubicación actual (con Gemma 4 E4B y con
Qwen3.5, así que no era un problema de un modelo en particular) hacía que
el asistente contestara con total confianza que el usuario vivía en
Madrid — sin ninguna relación con las coordenadas reales de
`assistants.yaml` (otro país).

Causa real, en `_usuario_ctx()` (`assistant_common.py`): la configuración
recomendada en este mismo README es dejar `ubicacion`/`pais` comentados y
usar solo `latitud`/`longitud` (más preciso). Pero `_usuario_ctx()` solo
armaba la frase de ubicación a partir de `ubicacion`/`pais` en texto —
nunca miraba las coordenadas. Con esos dos campos vacíos, la función
generaba literalmente `"...y vive en  ()."` (con espacio y paréntesis
vacíos) y aun así instruía al modelo a "dar por hecho estos datos... para
el clima" — una instrucción de "contestá con seguridad" combinada con un
dato en blanco es justo la clase de cosa que hace que un LLM alucine algo
plausible para cumplir la instrucción en vez de admitir que no sabe.

Arreglo: `_resolve_location_name()` (nueva, en `assistant_common.py`)
hace reverse geocoding de `latitud`/`longitud` vía Nominatim
(`/reverse`) una sola vez por proceso, cacheado — igual patrón que
`_home_coords()` en `nearby_places.py` pero para el system prompt en vez
de las búsquedas. `_usuario_ctx()` ahora usa `ubicacion`/`pais` en texto
si están, y si no, cae a este nombre resuelto. Ya probado: el asistente
ahora contesta el pueblo y el país correctos y arma bien la consulta de
`web_search` para el clima incluyendo esa ubicación real (antes ni
siquiera llegaba a formar una consulta con sentido). Sin coordenadas NI
ubicación/país configurados, sigue sin inyectar nada (comportamiento de
siempre).

### 2. Whisper alucina "Thanks for watching. Have a nice day. Peace."

Alucinación clásica de Whisper (entrenado con subtítulos de YouTube):
sobre silencio o ruido de fondo sin habla real, a veces "inventa" frases
de cierre de video en inglés — pasa incluso con `vad_filter`,
`no_speech_threshold`, `compression_ratio_threshold` y
`log_prob_threshold` ya activados (`stt_whisper.py`), que reducen el
problema pero no lo eliminan del todo. El detector que ya existía,
`_is_repetition_hallucination()`, solo agarraba frases REPETIDAS 3+
veces seguidas — esta alucinación aparece una sola vez, así que se
colaba.

Arreglo: `_is_known_hallucination_phrase()` (nueva, en `stt_whisper.py`)
descarta la transcripción si contiene alguna de una lista conocida de
frases típicas de cierre de video ("thanks for watching", "please
subscribe", "see you in the next video", "subtitles by", etc., más sus
equivalentes en español) — igual que Whisper "no dijo nada", como pasa
hoy con clicks/ruido puntual. Señal clave para no generar falsos
positivos: son casi siempre en inglés aunque el resto de la sesión sea en
español (el corpus de estas alucinaciones específicas es mayormente en
inglés), y ningún comando real a un asistente de voz suena así. Probado
8/8 contra la frase reportada y variantes, sin descartar comandos
normales de control (incluida la palabra suelta "thanks", que si podría
decir un usuario real).

### 3. La ubicación resuelta seguía siendo imprecisa (zoom insuficiente)

Después del arreglo del punto 1, el usuario reportó que las coordenadas
reales no caen exactamente en el pueblo que devolvía — probado en vivo: con
`zoom=10` (nivel "ciudad") el reverse geocoding de Nominatim devuelve el
pueblo contenedor entero, no el barrio real. Con `zoom=16` ("calle"/
barrio) para las mismas coordenadas exactas, Nominatim sí resuelve el
barrio correcto además del pueblo. `_resolve_location_name()`
ahora usa `zoom=16` y arma la cadena barrio → pueblo → país
(`"Barrio, Pueblo, País"`) en vez de solo pueblo → país.

### 4. "Vivero" — no era alucinación, pero el respaldo era frágil

El usuario reportó que preguntar por el vivero más cercano dos veces
seguidas devolvió primero un fallo ("se me trabó") y después una
respuesta con un nombre y distancia específicos, sospechando que se
inventó el dato sin buscar. Se reprodujo la conversación exacta con
tracing del tool call real: `find_nearby_places` SÍ se llamó en el
segundo turno y devolvió un resultado real y verificable ("1. Vivero — a
3.3 km") que coincide con lo que dijo el asistente — no fue alucinación,
la única rareza fue un comentario de BELLA medio confuso ("¿no era eso lo
que te dije antes?", cuando su turno anterior en realidad había sido el
mensaje de fallback, no una respuesta real) — un problema de coherencia
de tono en esa muestra puntual, no de datos falsos.

Sí había un problema real de fondo: "vivero" no estaba en
`_CATEGORY_TAGS` (`nearby_places.py`), así que dependía de que Nominatim
encontrara por casualidad un negocio con ese nombre EXACTO en el texto —
frágil, porque un vivero real llamado de otra forma (p. ej. "Jardín Los
Pinos") no aparecería nunca en una búsqueda de texto libre por "vivero".
Se agregó `"vivero": [("shop", "garden_centre"), ("shop", "florist")]`
(más algunas categorías comunes que faltaban de paso: `libreria`,
`electronica`, `ropa`, `zapateria`, `carniceria`) — ahora busca por la
etiqueta OSM real y devuelve varios negocios reales categorizados en vez
de depender de una coincidencia de nombre.

### 5. Preguntaba en inglés/portugués y respondía en español (o traducía lo dicho)

Tres fallos que se sumaban, en la interfaz web y en `voice_loop`:

- **Whisper traducía.** Si la detección de idioma dudaba (acento, frase
  corta), se forzaba `fallback_language` ("es"). Forzarle a Whisper un
  idioma que no es el hablado hace que traduzca lo dicho a ese idioma.
  Ahora ([stt_whisper.py](app/voice/stt_whisper.py), `_transcribe_allowed`)
  ante la duda transcribe en los candidatos (el más probable, el segundo y
  el idioma de la conversación) y gana el de mejor puntaje: la
  log-probabilidad de Whisper (una traducción forzada puntúa peor), un poco
  de la detección, ventaja para el idioma de la conversación y castigo si el
  texto salió en otro idioma que el forzado (p. ej. forzado a "es" pero
  devuelve "how are you today?"). Con una sola palabra ("sí", "sim") decide
  el idioma de la conversación.
  - Medido con 88 frases de TTS en inglés, portugués y español, con acento
    español y ruido: si el idioma de la conversación es el hablado, acierta
    86/88 (antes 61/88). Con frases nuevas que no se usaron para ajustar:
    53/56.
  - La consola dice cómo se decidió cada vez: `idioma: detección en 0.69,
    es 0.23; probé en -0.30, es -1.02 → en (mejor puntaje)`.
- **La conversación por voz pisaba el idioma elegido** con esa detección
  dudosa. Ahora la página manda el idioma elegido (o en el que va la
  conversación) como pista (`hint`) a `/api/chat/transcribe`. `voice_loop`
  usa como pista el idioma del turno anterior.
- **El modelo recibía casi todo en español.** La orden de idioma era solo el
  código ISO al final del prompt, y al mensaje del usuario se le pegaba un
  recordatorio en español ("Responde hablando…"). Los modelos chicos
  (BELLA, `gemma4:e2b`) contestaban en español 7 de cada 10 veces. Ahora
  ([assistant_common.py](app/core/assistant_common.py)):
  - La orden nombra el idioma ("English", "Portuguese (português)") y va al
    principio y al final del prompt.
  - El recordatorio va en inglés y repite el idioma.
  - Si igual la respuesta sale claramente en otro idioma
    ([text_language.py](app/core/text_language.py), por palabras
    funcionales; cubre es/en/pt/fr/de/it), se le pide al modelo que la
    reescriba.
  - Medido: 20/20 respuestas en el idioma pedido entre JARVIS y BELLA, en
    voz y texto, incluido un caso con conversación previa en español. La
    reescritura no hizo falta en ninguno; queda como red de seguridad.

### 6. Herramientas que no se llamaban, clima genérico y "mmm" (septiembre 2026)

Visto en una conversación por voz con BELLA (`gemma4:e2b`):

- **"Uy, se me trabó"** al pedir el clima o restaurantes cercanos. El modelo
  respondía "voy a buscar…" en vez de llamar la herramienta; cada empujón
  para que la llamara gastaba una de las `max_tool_rounds` y, cuando por fin
  la llamaba, no quedaba ronda para responder. Ahora
  ([assistant_common.py](app/core/assistant_common.py), `ask_with_tools`):
  - Los empujones no gastan rondas de herramientas.
  - Si tras el empujón sigue sin llamarla, la llama el sistema directo
    (clima, lugares, búsqueda; nunca la música, porque hace falta saber
    qué poner).
  - Siempre queda una última ronda sin herramientas para responder.
  - Medido: BELLA casi nunca llama herramientas sola; en las pruebas la
    respuesta salió gracias a la llamada directa.
- **"Busca en internet…" sin buscar.** No estaba entre los disparadores.
  Ahora sí, en español, inglés y portugués, y con las variantes que
  transcribe mal Whisper ("Pusca en internet", "Buscan internet"). La
  consulta directa quita la orden ("busca en internet quién es X" → "quién
  es X").
- **Clima: páginas genéricas en vez del dato.** Nueva herramienta
  `get_weather` ([weather.py](app/tools/weather.py)) con Open-Meteo
  (gratis, sin API key): ahora, hoy, mañana y dos días más en la ubicación
  del usuario.
- **Lugares a 17 km teniendo a 2 km:** el servidor de Overpass estaba
  saturado y se caía al respaldo (Nominatim), que solo busca la palabra en
  el nombre. Ahora se prueban espejos de Overpass en paralelo si falla el
  principal, y se descartan resultados fuera del radio.
- **"mmm"** se mandaba como mensaje y el asistente respondía. Ahora las
  muletillas solas ("mmm", "eh", "ajá") cuentan como "no te entendí".
- **"¿Cómo sabes eso?"** → inventaba "me lo dijiste al inicio". Ahora sabe
  que los datos vienen de la configuración.
- **Transcripciones malas** ("Tienes Sam Altman", "¿Cuántos años
  deberías?"): límite del modelo Whisper `small`. `large-v3-turbo` mejora
  mucho nombres propios y acentos; se cambia en `CONFIG["model_size"]` de
  [stt_whisper.py](app/voice/stt_whisper.py) (se descarga solo, ~1,6 GB).

### 7. Segunda ronda de pruebas por voz (septiembre 2026)

- **"¿Qué día va a estar soleado?"** no consultaba el clima ("soleado",
  "nublado", "paraguas" no eran palabras de clima) y **"Revísalo tú"**
  decía "déjame revisar" sin hacerlo. Ahora esas palabras cuentan y un
  pedido corto de seguimiento ("revísalo", "búscalo", "check it") usa el
  pedido anterior.
- **Distancia a un lugar** ("¿a cuánta distancia está el Estadio
  Nacional?") se inventaba ("15 km"). Nueva herramienta `find_place`
  ([nearby_places.py](app/tools/nearby_places.py)): ubica el lugar
  (Nominatim, prefiriendo el país del usuario y el resultado más
  importante: "centro de San José" es la capital, no un distrito
  homónimo) y da la distancia en línea recta y por carretera con el tiempo
  en auto (OSRM, gratis). El lugar aparece en el mapa del chat.
- **Lugares en inglés y por cocina:** "restaurant", "gym", "pharmacy",
  "academia"… se reconocen (`_CATEGORY_SYNONYMS`), y "Italian restaurant",
  "comida china", "sushi"… filtran por la cocina de OpenStreetMap
  (`_CUISINES`); si no hay de esa cocina, da los restaurantes más
  cercanos avisándolo. Primero se busca a 5 km y solo si hay menos de 3 a
  15 km. "near" solo ya cuenta como "cerca".
- **"Calle El Gimnasio"** como gimnasio: el respaldo (Nominatim) ya no
  devuelve calles, barrios ni ríos.
- **Overpass lento o saturado:** se le pide al principal y, si a los 2,5 s
  no respondió, también a un espejo; gana el primero. Los resultados se
  guardan 15 min. Ojo: admite pocas consultas simultáneas por IP; muchas
  búsquedas seguidas pueden tardar o caer al respaldo un rato.
- **"PUSCA EN INTERNET"** (frase cortada) buscaba eso literal: ahora sin
  tema no se busca nada (y en voz se espera el resto de la frase).
- **"¿Cuál es mi ubicación actual?"** → "no tengo acceso": ahora la
  ubicación configurada cuenta también como la actual.
- **Edad de personas** ("¿cuántos años tiene…?") se busca en internet: la
  edad cambia y el modelo la calculaba mal.
- **Ruido transcrito como frase** ("So, let's take a look at the quality of
  the work." con detección 0,11): si ningún idioma convence a la detección
  y ninguna transcripción es natural para Whisper, se descarta.
- La búsqueda web reintenta una vez si falla la conexión.

### 8. Conversación grupal por voz (septiembre 2026)

- **"Jarvis, ¿a qué distancia está el centro de San José?"** → "3,5 km"
  inventado: solo se reconocía "a cuánta distancia". Ahora "a qué
  distancia", "distancia", "lejos" (y en inglés/portugués) llaman a
  `find_place`, y el nombre del asistente al principio ("Jarvis, …") no se
  incluye en la búsqueda. Medido: 46 km por carretera, ~1 h.
- **"Bella, revisa lo que dijo Jarvis, ¿está correcto?"** → "te recomiendo
  usar una aplicación de mapas". "¿Es cierto?", "verifica", "confirma"…
  cuentan como seguimiento del pedido anterior (sin contar lo que dijeron
  los otros asistentes) y BELLA verifica con la herramienta.
- **Mandar al usuario a averiguar por su cuenta** ("te recomiendo
  revisar…", "you might want to check…"): se le pide una vez al modelo que
  lo resuelva él (herramienta u opinión directa).
- **"¿Qué piensas de la AI de Google?"** forzaba una búsqueda por la palabra
  "Google": ahora solo cuenta "búscalo en Google". Y "Gemini es una
  herramienta muy útil" ya no se toma como narrar una herramienta.
- **El brillo del aro se cortaba en un cuadrado** en los aros chicos: el
  lienzo ahora es 1,5 veces el aro y el brillo y los trazos van a escala
  de su tamaño ([orb.js](app/webui/static/orb.js)).

### 9. Revisión del pipeline de voz (octubre 2026)

- **Micrófono continuo:** antes cada frase abría el micrófono de nuevo y
  medía el ruido durante 0,5 s: lo dicho en ese medio segundo (o justo
  después del pitido) se perdía, y si se empezaba a hablar durante la
  medición el umbral subía. Ahora el stream queda abierto
  ([mic_stream.py](app/voice/mic_stream.py)), el ruido ambiente se sigue
  midiendo solo con los bloques en silencio (y se congela mientras habla el
  asistente) y se guardan 0,3 s de antes del arranque de la frase para no
  comerse la primera sílaba.
- **Un solo modelo Supertonic:** `voice_loop.py` cargaba uno por asistente
  (dos copias iguales en memoria/VRAM); ahora todas las voces comparten uno
  y solo cambia el estilo (`supersonictts.shared_tts`).
- **Pista de idioma por asistente:** Whisper desempataba el idioma con lo
  último que se habló con CUALQUIER asistente (lo hablado con BELLA en
  portugués sesgaba lo siguiente dicho a JARVIS). Ahora cada asistente
  lleva la suya; si una frase empieza con un nombre y la detección fue
  dudosa, se transcribe otra vez con la pista y los idiomas de ese
  asistente.
- **"¡Hola <nombre>!" fijo en el código:** el recordatorio de no volver a
  saludar usa el nombre de `user_context`.
- **Palabras de 1-2 letras como nombre:** "¿y mañana **va** a llover?"
  despertaba a BELLA ("va" ~ "vela" = 0,67). Ahora solo cuentan si son
  exactamente una variante.
- **Personalidades en inglés** (`personality` de JARVIS y BELLA); responden
  igual en el idioma de la conversación, y la instrucción de idioma va
  también al principio del prompt para el español.
- **`languages` siempre explícito** en `assistants.yaml`: "todos" se
  guarda como la lista de los 31 códigos en vez de `[]`.

### 10. El modelo razona en vez de buscar palabras clave (octubre 2026)

Antes muchas decisiones salían de listas de palabras fijas en español,
inglés y portugués: forzar el clima si el mensaje decía "clima", "lluvia",
"weather" o "paraguas"; buscar en internet con "busca", "noticias" o "precio
de"; "cerca de mí" para lugares; "a cuánta distancia" para distancias;
detectar con "te recomiendo revisar…" que mandaba al usuario a averiguar;
"todos" o "ustedes" para preguntarles a todos; "y", "de" o "the" al final
para una frase a medias; el idioma del chat por sus palabras más comunes;
y, dentro de las herramientas, sinónimos de cada categoría de lugar, "hoy"
o "ahora" para buscar noticias del día y "centro de…" para las ciudades.
Fallaba en los dos sentidos: "me encantan los días de lluvia" forzaba el
clima, y lo mismo dicho con otras palabras (o en otro idioma) no lo
activaba. Además había que escribir las palabras en cada idioma.

Ahora hay una sola configuración, en inglés, que sirve para los 31 idiomas:

- **Revisor de la respuesta** (`assistant_common._review_draft`): antes de
  decir una respuesta, el mismo modelo (ya cargado, sin gastar más VRAM)
  lee la conversación y su borrador. Con salida JSON restringida a un
  esquema (Ollama `format`), dice tres cosas:
  - si hacía falta una herramienta que no llamó;
  - si el borrador promete hacer algo en vez de hacerlo, o manda al usuario
    a averiguar por su cuenta;
  - en qué idioma salió.

  Si hacía falta una herramienta, primero se le pide que la llame (solo con
  esa disponible). Si aun así no lo hace, se la llama directo con
  argumentos que el modelo genera a partir del esquema de la propia
  herramienta, lo que sirve igual para cualquier herramienta nueva.
  Medido con `gemma4:E4B`: acertó 12 de 12 casos en ~0,5 s cada uno (el
  clima en ruso sí; "me encantan los días de lluvia" o "gracias por el
  pronóstico" no). Cuesta una petición corta más por turno.
- **Parámetros en vez de adivinar:**
  - `find_nearby_places`: elige la categoría de una lista cerrada en
    inglés ("botica" → `pharmacy`) y, aparte, el tipo de cocina o un
    nombre concreto.
  - `web_search`: un `recent` para lo que está pasando hoy.
  - `find_place`: `place_type` para distinguir una ciudad de un lugar
    concreto. Para las ciudades, la herramienta además prueba el nombre
    quitando palabras del principio y prefiere el país del usuario, salvo
    que en el mundo haya una mucho más importante ("París").
- **A quién se le habla en el grupo** (`chat_runtime.route_addressees`):
  lo decide el modelo, incluido "¿qué opinan todos? Que empiece Ziggy" y
  que "Jarvis, saca a Bella" va solo a JARVIS.
- **Invitar y sacar asistentes:** son herramientas del modelo (ver arriba,
  "Manos libres").
- **Frase a medias:** solo por la puntuación que pone Whisper ("…", coma
  al final); si quedó incompleta, el modelo pregunta lo que falta.
- **Todo el prompt compartido en inglés:** `shared_context`, la fecha y la
  hora, los datos del usuario, los estilos de respuesta, los empujones y
  las descripciones de las herramientas. El idioma de la respuesta lo fija
  la instrucción de idioma.

Lo que queda con listas fijas no decide qué quiso decir el usuario:
- las frases que Whisper inventa sobre el silencio ("thanks for
  watching"…) y las muletillas ("mmm");
- las palabras funcionales de
  [text_language.py](app/core/text_language.py), que solo son una señal
  dentro del puntaje de Whisper;
- las variantes de los nombres en `wake_words.txt` (nombres, no frases).

Las secciones anteriores de estas notas describen el mecanismo viejo
(`_FORCED_TOOL_KEYWORDS`, `_CATEGORY_SYNONYMS`…) tal como era entonces.

**ZIGGY:** asistente nuevo de ejemplo, caótico y divertido: cambia de estilo
en cada respuesta y tiene teorías conspirativas sobre los calcetines. Usa
el mismo modelo que JARVIS y BELLA, así que pueden estar los tres en la
misma conversación. Voz M4, temperatura 1,05.

### 11. Correcciones tras probar la voz grupal (octubre 2026)

Visto en el registro de una sesión real:

- **"Invita a Jarvis" metía a Ziggy:** la conversación con BELLA se había
  cerrado por silencio, así que el servidor tomó "Jarvis" como un llamado y
  le pasó la frase a JARVIS. Él no podía invitarse (no estaba en la lista de
  la herramienta), el revisor igual lo obligó a usarla y el modelo eligió al
  único que quedaba: ZIGGY. Tres arreglos:
  - quién debe atender lo decide el modelo, también para los que no están
    en la conversación;
  - la herramienta acepta a cualquier asistente y contesta "ya está" o "no
    está" en vez de forzar a otro;
  - el revisor sabe quién responde.
- **"Adiós, Ziggy" no obtenía respuesta:** el resto de la frase eran solo
  las palabras después del nombre (nada), y se tomaba como decir el nombre
  solo. Ahora cuenta lo de antes y lo de después.
- **"¡Hola, CG!":** así escribió Whisper "Ziggy"; quedó como variante en
  `wake_words.txt`.
- **ZIGGY leía sus acotaciones** ("(Voz de presentador de concurso…)"):
  - su personalidad dice que muestre el estilo solo con las palabras;
  - el revisor marca lo que no se puede leer en voz alta;
  - por la puntuación (paréntesis, corchetes, asteriscos), se le pide
    reescribirlo y, si insiste, se quita.
- **Una respuesta que contradice a la herramienta** ("ya retiré a Ziggy"
  cuando la herramienta dijo que no estaba): el revisor lo marca y se le
  pide corregirla.
- **La conversación abierta por nombre no se cerraba sola** si había ruido:
  ahora solo cuenta como actividad lo que se entendió.

### 12. Whisper pesado, voces clonadas y un modelo desbloqueado (octubre 2026)

**Whisper: ¿vale la pena uno más pesado?** Sí, `large-v3-turbo`, que
queda como el modelo por defecto (se cambia en *Ajustes compartidos →
Voces y oído*).

Cómo se midió: 45 frases típicas (15 por idioma en español, inglés y
portugués: comandos, nombres de los asistentes, "Sí", números),
sintetizadas de dos formas:
- con Supertonic (voces nativas);
- con Qwen3-TTS CustomVoice, con hablantes chinos y japoneses leyendo en
  esos idiomas, o sea con acento.

Cada audio se probó limpio y con ruido rosa a 10 dB, sin pista de idioma
(entre los 31) y con pista. Son 1.080 transcripciones por modelo, con el
mismo procesamiento que usa la app.

| Modelo | Errores (WER) | Idioma | Nombres | Tiempo/frase | VRAM |
|---|---|---|---|---|---|
| small | 14,3 % | 95,2 % | 83,3 % | 150 ms | +0,9 GB |
| **large-v3-turbo** | **10,4 %** | 95,9 % | **89,2 %** | 227 ms | +2,1 GB |
| large-v3 | 9,1 % | 97,4 % | 88,6 % | 373 ms | +3,9 GB |

- **Turbo:** baja un 27 % los errores. Con voces nativas reconoce los
  nombres el 98 % de las veces (small: 89 %). Cuesta 77 ms más por frase,
  que no se notan al lado de la respuesta del modelo.
- **Large-v3:** mejora poco más con casi el doble de tiempo y de VRAM, así
  que no se ofrece.
- **Lo que ninguno resuelve:** "Sí"/"Sim" sueltos, sin pista de idioma,
  siguen saliendo "See" (en inglés). Por eso importa la pista del idioma de
  la conversación.
- **Limitación de la medición:** son voces sintéticas. Con micrófono real,
  la diferencia a favor del pesado debería ser igual o mayor.

**Voces clonadas con Qwen3-TTS:** ver "Voces clonadas (Qwen3-TTS)" más
arriba. Sobre la velocidad:
- **Sin optimizar:** generaba a RTF ~3,5 (12 s para 3,5 s de audio) con la
  GPU al 10-40 %, igual con el modelo 0.6B que con el 1.7B y con
  transformers 4 o 5. El modelo hace cientos de pasadas chicas por segundo
  de audio y Python no alcanza a alimentar la GPU.
- **Medido por partes:** el sub-modelo que genera los 15 códigos de cada
  cuadro se llevaba 8,5 de los 13 s (750 pasadas de 11 ms).
- **Arreglos:**
  - un bucle de muestreo propio en vez de `generate()` de Hugging Face por
    cada cuadro (parche marcado `[assistant]` en
    `app/vendor/qwen_tts/core/models/modeling_qwen3_tts.py`);
  - `torch.compile` de los dos modelos (con el triton que ya trae
    ComfyUI).
- **Resultado:** RTF ~1,2. Whisper entiende lo que dice la voz clonada.

**Modelo desbloqueado:** `huihui_ai/gemma-4-abliterated:E4B`, instalado
en Ollama. Es el mismo Gemma 4 E4B (8B, Q4_K_M, 9,6 GB) sin los rechazos:
hace el insulto creativo o el chiste de humor negro que el original
esquiva.
- **Revisor:** acierta 10 de 10 igual que el original, pero tarda más (1,4
  s frente a 0,6 s).
- **Herramientas:** es un poco más torpe con ellas (con el clima necesitó
  un empujón).
- **Uso:** no se asignó a ningún asistente; se elige como `base_model`. Si
  solo uno lo usa, deja de poder estar en la conversación grupal con los
  otros (otro modelo) y suma ~7 GB de VRAM.

**Interfaz:** con el aro grande, su brillo se cortaba en el borde del área
de voz y arriba quedaba una franja oscura. Ahora pasa por detrás de la
cabecera, que es transparente.

### 13. Modelos de roleplay desbloqueados y memoria por modelo (octubre 2026)

**Modelos probados** (Q4_K_M, 7,48 GB en disco, bajados de Hugging Face con
`ollama pull hf.co/...`). Los dos traen la plantilla de chat de Mistral con
`[AVAILABLE_TOOLS]`/`[TOOL_CALLS]`, así que Ollama les habilita `tools` sin
Modelfile:

- `hf.co/bartowski/TheDrummer_Rocinante-X-12B-v1-GGUF:Q4_K_M` (Rocinante-X,
  fine-tune de roleplay de Mistral Nemo 12B).
- `hf.co/mradermacher/Mistral-Nemo-Instruct-2407-abliterated-GGUF:Q4_K_M`
  (el Nemo original sin rechazos).

Prueba con la personalidad de BELLA por `/api/chat` (clima, lugares,
búsqueda, distancia, charla, inglés, insulto creativo, humor negro):

| Modelo | Herramientas | Con herramienta | Sin rechazos | VRAM medida (16k ctx) |
|---|---|---|---|---|
| Nemo abliterated | 8/8 | 4-8 s | sí | 10,4 GB |
| Rocinante-X | 7/8 (no buscó "el último Mundial" e inventó el resultado) | 4,6-6,4 s | a medias | 10,4 GB |
| gemma4:E4B (referencia) | 8/8 | 4-8 s | no (se niega a insultar y al humor negro) | 4,2 GB |

Arreglos que hicieron falta para que funcionaran:
- **Llamadas escritas como texto:** Rocinante a veces escribe la llamada
  (`[{"name": "find_nearby_places", "arguments": {...}}]`) en vez de usar el
  token especial. Ahora se reconoce y se ejecuta igual
  (`assistant_common._text_tool_calls`) en vez de pedirle que reintente.
- **El revisor censuraba:** al ser el mismo modelo, marcaba el insulto
  pedido como "inapropiado". Ahora solo juzga lo técnico, no el contenido
  ni el tono.
- **Respondía a la instrucción** ("Understood! I'll answer your questions
  directly…"): los empujones del revisor terminan pidiendo solo la
  respuesta nueva, sin comentar la nota.
- **"Lo último" puede estar viejo:** el revisor sabe la fecha y que lo más
  reciente (último campeón, versión actual, edades) necesita buscarse.
- **Argumentos inventados** en la llamada directa (un nombre de restaurante
  que nadie dijo): el generador deja vacíos los campos opcionales que el
  usuario no dio.

Pendiente: aun buscando, "¿quién ganó el último Mundial?" devuelve 2022:
la consulta que arma el modelo es genérica y los resultados no traen el de
2026.

**Memoria:** una conversación por voz con un Nemo 12B suma ~13 GB (10,4 del
modelo + 2,1 de Whisper turbo + 0,6 de Supertonic); con voz clonada
(Qwen3-TTS 0.6B, +2,8 GB) queda justo en 16 GB. Además, los asistentes con
modelos distintos no pueden estar en la misma conversación grupal.

**Nemo abliterated "lento y raro" (3 de octubre):**
- **Lento (55-68 s por ronda en vez de 1-2 s):** la GPU estaba llena
  (15,8 de 16 GB): Nemo (9,4 GB) + Whisper turbo + Supertonic + el proceso
  de voces clonadas (Qwen3-TTS, ~2,8 GB, precargado porque al arrancar
  algún asistente tenía voz clonada) + Zoom, Brave, Discord y Wallpaper
  Engine. Windows pasa entonces memoria a la RAM compartida y Ollama sigue
  diciendo "100% GPU". Ahora el proceso de voces clonadas se cierra al
  guardar los asistentes si ya ninguno la usa, y el log avisa cuando una
  ronda es lenta con la GPU llena.
- **Respuestas "vacías":** cuando no sabe qué decir (tras un empujón o con
  herramientas a mano) su token más probable es un espacio de ancho cero
  (U+200B) o guiones suaves, y eso se daba por respuesta. Ahora cuenta como
  vacía; a la segunda seguida se le pide sin herramientas.
- Además busca en internet cosas que no hace falta ("2 más 2", "cuéntame un
  chiste"): no rompe nada, pero suma 2-3 s.
- Comparado con la personalidad de ZIGGY: Rocinante-X se queda mucho más
  en el personaje (Nemo abliterated responde genérico y a veces sin
  sentido), aunque a veces escribe acotaciones o contesta en inglés.
  Las plantillas de chat de ambos GGUF usan `[SYSTEM_PROMPT]`, que no es un
  token de Nemo (se lee como texto); probado con el formato oficial de Nemo
  (system dentro del último `[INST]`): deja de inventar búsquedas pero casi
  nunca llama herramientas, así que se dejó la plantilla como está.

### 14. Adjuntos en el chat escrito (octubre 2026)

Ver "Adjuntos en el chat escrito" en la sección de la interfaz web. Probado
con BELLA (gemma4:E4B): una imagen, un .txt, un PDF y una nota de voz en el
mismo mensaje; sumó bien datos de la lista y de la factura y citó la nota de
voz (18 s). Con ZIGGY (Nemo, sin visión) la imagen se rechaza con aviso y los
documentos entran igual.

**Problema de Ollama, no de la app:** con Ollama 0.33.3 la visión de Gemma 4
(gemma4:E4B, e2b y huihui_ai/gemma-4-abliterated) no funciona: la imagen se
codifica (256 tokens, en la posición correcta del prompt) pero el modelo
contesta que no le mandaron ninguna, aun llamando a `/api/chat` directo. La
entrada de audio nativa de Gemma 4 sale igual de rota ("lo lo lo…"), por eso
el audio se pasa a texto con Whisper. Cuando Ollama lo arregle (o con otro
modelo con visión que funcione) las imágenes van a llegar sin tocar nada.

### 15. Respuestas detalladas en el chat escrito y Ollama 0.40.8 (octubre 2026)

- Antes las respuestas escritas eran vagas porque las reglas compartidas
  pedían "solo prosa hablada, sin emojis ni símbolos" en todos los modos,
  el revisor marcaba el markdown como "no se puede leer en voz alta" y se
  borraban los emojis. Ahora eso es solo para la voz. Probado con BELLA:
  el clima de mañana con 🌡️/🌧️, máxima y mínima en °C, lluvia en % y mm;
  "SSD NVMe vs SATA" con una tabla comparativa, secciones y una
  recomendación (6,5 s). Por voz siguen siendo dos frases sin símbolos.
- Ollama se actualizó de 0.33.3 a 0.40.8 con el botón nuevo (40 s; usó el
  instalador que ya había bajado la app de Ollama). Siguen los 5 modelos y
  `OLLAMA_CONTEXT_LENGTH=16384`.
- La visión de Gemma 4 sigue sin funcionar bien en 0.40.8: ahora "ve" algo,
  pero lo inventa (a un círculo rojo, un rectángulo verde y el texto
  "PRECIO: 42" los describe como "arte abstracto oscuro"). El audio nativo
  sale en otro alfabeto. **Resuelto en la nota 16:** había que actualizar
  el modelo (la versión nueva de gemma4 en ollama.com sí ve las imágenes).

### 16. Actualización de modelos (octubre 2026)

Al revisar los 5 modelos instalados, `gemma4:E4B` y `gemma4:e2b` tenían
versión nueva en ollama.com (los de Hugging Face y huihui_ai estaban al
día). Detalle: registry.ollama.ai responde 401 si la petición dice ser de
Ollama (`User-Agent: ollama/...`, entonces exige firma); sin ese encabezado
responde el manifest público. La carpeta de modelos se toma de
`OLLAMA_MODELS` y, si la configuró la app de Ollama (no es variable de
Windows), del log del servidor de Ollama.

Resultado: `gemma4:E4B` se actualizó con el botón (5,5 GB en ~2,5 min) y
`gemma4:e2b` lo actualizó solo el servidor a los 3 minutos (actualización
automática). Ollama borró las capas viejas (las que siguen en disco las
comparte otro modelo; no quedó ninguna huérfana) y la carpeta de modelos
bajó de 39,4 a 34,1 GB. **Con las versiones nuevas la visión de Gemma 4
funciona:** E4B y e2b describen bien la imagen de prueba (círculo rojo,
cuadrado verde, "PRECIO: 42"). Lo que fallaba era la versión vieja del
modelo con el Ollama nuevo. `huihui_ai/gemma-4-abliterated:E4B` sigue sin
ver (su autor no lo actualizó: inventa "una pintura abstracta oscura").

### 17. Voz concreta, audios, imágenes, red local (octubre 2026)

- **Voz vaga:** la regla de voz pedía "una o dos frases, menos de 30 palabras,
  sin enumerar datos" y salía "Los servicios tienen límites definidos por
  montos máximos…" sin decir ninguno. Ahora pide lo concreto (nombres,
  cifras, montos, condiciones) en 2 a 4 frases; con una lista, los 3 más
  importantes. Probado con una póliza adjunta: "la asistencia vial tiene un
  tope de $150 por evento y solo 3 eventos al año, la cerrajería 2 eventos
  con tope de $60, y no aplica a vehículos de más de 3,5 toneladas".
- **"Los Jarvis":** dicho por voz, "las limitaciones de los servicios" llegaba
  como "…de los Jarvis" y entraba JARVIS: "servicios", al final de la frase,
  se parecía un 67 % al alias "yervis". Ahora un parecido aproximado no cuenta
  si la palabra tiene más de 2 letras de diferencia de largo con el nombre
  (`wake_word_utils.match_ratio`).
- **Audio sin mensaje:** contestaba "no puedo procesar archivos de audio".
  El adjunto ahora dice que ya está transcrito y, sin mensaje, se le pide
  empezar por la transcripción entre comillas y después comentarla.
- **Imágenes:** el modelo seguía viendo las 2 últimas imágenes y al describir
  una nueva mezclaba datos de la anterior; además adivinaba quién era una
  persona por el nombre del archivo. Ahora solo ve la última, y con la imagen
  va la indicación de describir solo lo visible y copiar el texto tal cual.
  Probado con dos imágenes seguidas: textos, horarios, teléfono y oferta
  exactos y sin mezclarse.

### 18. Acceso desde el celular, reintentar, adjuntos y AuraVox (octubre 2026)

- **"Falta la clave" tras escanear el QR:** el log mostraba "dispositivo
  autorizado" y enseguida `GET / → 401`. El enlace con la clave respondía con
  una redirección a "/" y la cookie con `SameSite=Strict`; como la navegación
  venía de otra app (el escáner), el navegador no mandaba esa cookie en la
  redirección. Ahora se sirve la página directamente (con la cookie, ya
  `SameSite=Lax`) y la página quita `?key` de la dirección. La pantalla de
  "falta la clave" también deja escribirla a mano.
- **Marca:** AuraVox en el título, la barra superior (logo del aro), el
  ícono de la pestaña, la consola (`run_config_ui.bat`) y el log. Con
  `manifest.webmanifest` el celular la puede "Agregar a la pantalla de
  inicio" como app.

### 19. Celular, menús, editar mensajes, chat que se borraba (octubre 2026)

- **El chat se seguía borrando al ir a la galería y volver:** al volver, la
  página guardaba la conversación vacía antes de que llegara la guardada, y
  ese guardado borraba el archivo del servidor. Ahora no se guarda nada
  mientras se carga, se descarta lo pendiente y una conversación vacía solo
  se manda al pulsar "Reiniciar". Probado: ir a la galería y volver, y
  recargar la página, conservan los mensajes.
- **"Subtítulos por la comunidad de Amara.org"** (alucinación típica de
  Whisper con silencio) llegaba como si lo hubieras dicho y BELLA lo buscaba
  en internet. El filtro ya tenía "amara.org", pero al normalizar el texto
  quitaba el punto y nunca coincidía; ahora las frases se normalizan igual y
  hay variantes en español y portugués.
- **Sin barras de desplazamiento al mostrar texto:** los subtítulos del modo
  voz muestran lo último con un difuminado arriba (sin barra; el aro se
  achica si hace falta), las tablas y el código se acomodan al ancho, el
  cuadro de texto no muestra barra y la del chat solo aparece al pasar el
  mouse. En el celular el alto usa `100dvh` (con 100vh la barra del navegador
  tapaba el cuadro de texto) y el aviso del cuadro es corto.

### 19 b. Interfaz móvil, mensajes editables y chat que no se borra (octubre 2026)

- **El chat se seguía reiniciando:** al volver de la galería, la página
  guardaba la conversación vacía antes de que llegara la guardada y el
  servidor la borraba (en `config\chats\` no quedaba ningún archivo). Ahora
  no se guarda nada mientras carga, y una conversación vacía solo se guarda
  (= se borra) con "Reiniciar".
- **"Subtítulos por la comunidad de Amara.org":** alucinación de Whisper con
  silencio/ruido que se tomaba como pregunta. El filtro tenía "amara.org" pero
  al texto se le quitaba el punto antes de comparar ("amara org"); ahora las
  frases se normalizan igual y hay más variantes en español y portugués.

### 20. Recarga en caliente y conversión de archivos (octubre 2026)

- Log revisado: sin errores (solo avisos de librerías opcionales de la voz
  clonada y reintentos normales del revisor).
- Probado: un cambio de CSS se aplicó sin recargar; uno de JavaScript esperó
  a que se vaciara el cuadro de texto y recargó con la conversación intacta;
  un cambio en un `.py` reinició el servidor solo.
- Conversiones probadas: txt → docx → pdf / txt, csv → xlsx → csv / pdf,
  csv → tsv, png → jpg / webp / pdf, wav → mp3. En el chat: un csv a Excel
  y ese Excel a PDF (16 s); al adjuntar solo una imagen respondió "He
  recibido el archivo, ¿qué le gustaría que hiciera con él?".
- Arreglado de paso: el servidor HTTPS de la red no tenía el puerto en uso
  exclusivo y en Windows dos procesos podían escuchar el 8443 a la vez.


### 21. Perfiles: administrador, normal e invitado (octubre 2026)

- **Entrar con un perfil:** la página empieza en "¿Quién eres?" (como en las
  plataformas de video). La primera vez pide crear el **administrador**
  (nombre y PIN); las conversaciones guardadas y los datos de `user_context`
  que ya había pasan a ese perfil. La sesión queda en una cookie
  (`auravox_session`, HttpOnly); en `config/profiles.json` solo se guarda su
  hash, así no se cierra con la recarga en caliente. Los PIN van con PBKDF2 y
  5 intentos fallidos bloquean el perfil un minuto (`app/webui/profiles.py`).
- **Roles:**
  - **Administrador:** todo. Lo delicado es solo suyo: eliminar, descargar y
    actualizar modelos, actualizar Ollama, el acceso por red (y su clave),
    las voces clonadas y el Whisper elegido, las reglas compartidas, las
    exclusiones, la consola del servidor (muestra lo que conversan todos) y
    crear, cambiar o borrar perfiles. Necesita PIN.
  - **Normal:** chatea, crea sus asistentes y edita o borra los suyos, y
    cambia sus datos, su nombre y su PIN (el PIN es opcional). Ve los modelos
    y Ollama pero sin los botones de borrar o actualizar.
  - **Invitado:** no es un perfil guardado. Usa los asistentes compartidos
    (puede probar cambios en el chat, pero no guardarlos) y sus datos y
    conversaciones quedan en el navegador (`sessionStorage`): se borran al
    salir del modo invitado o al cerrar la pestaña. Su cookie tampoco dura
    más que el navegador abierto.
  El servidor decide qué rol hace falta para cada ruta (`required_role` en
  `config_ui.py`), no la página: ocultar un botón no alcanza.
- **Asistentes compartidos o privados:** al crear uno aparece "Compartir con
  los demás perfiles" (encendido por defecto para el administrador, apagado
  para un perfil normal). En `assistants.yaml` cada asistente lleva `owner`
  (el perfil que lo creó) y `shared`. Uno privado solo lo ve quien lo creó
  (tampoco el administrador); uno compartido lo ven todos y lo cambian quien
  lo creó y los administradores. Los de antes de los perfiles quedan
  compartidos y de los administradores. En la galería, "Privado" o "de Ana".
  Al borrar un perfil, sus asistentes pasan a quien lo borra.
- **Datos de cada persona:** "Sobre ti" (nombre, país, ubicación) es ahora
  de cada perfil. Dos personas pueden chatear a la vez sin pisarse: mientras
  se responde a alguien, `USER_CONTEXT` lee los datos de ese perfil
  (`assistant_common.user_context_for`, por hilo); el clima, los lugares
  cercanos y el saludo usan los suyos. El `user_context` de
  `assistants.yaml` queda para los modos de consola.
- **Conversaciones por perfil:** `config/chats/<perfil>/<asistente>.json`.
  Los adjuntos que ya no usa ninguna conversación se siguen borrando solos
  (ahora se miran las carpetas de todos los perfiles).
- **Barra superior:** el perfil con su menú (Mis datos, Cambiar de perfil, o
  Salir para el invitado). "Ajustes compartidos" se llama "Ajustes" para quien
  no es administrador, y la consola solo aparece para el administrador.
- API_VERSION 6 (una página vieja abierta avisa).

### Base común de las funciones 22–31: habilidades por perfil (octubre 2026)

Las herramientas que dependen de QUIÉN pregunta (memoria, recordatorios,
listas, documentos, rutinas, plugins, MCP) son "habilidades"
(`app/core/skills.py`): cada una da sus herramientas y, si hace falta, un
texto para el system prompt, según el perfil, su rol y el asistente.
`config_ui._chat` arma un `skills.Ctx` por pregunta y `chat_runtime.chat` las
suma. Las habilidades integradas están en `app/skills/`. En la página, todo
lo nuevo está en `static/features.js` (se carga antes que `app.js` y se
engancha con `featureCards`, `featureChatBody`, `FEATURE_EVENTS` y
`FEATURE_VIEWS`); sus textos van al final de `i18n.js` e `i18n.py`.
Para probar sin tocar la instancia de uso diario: la variable
`AURAVOX_CONFIG` apunta a otra carpeta de configuración (`app/paths.py`).

### 22. Memoria a largo plazo por perfil (octubre 2026)

- El modelo guarda hechos duraderos que le cuentas ("mi hija se llama Ana",
  "soy vegetariano") con `remember_fact` y los olvida con `forget_fact`
  ("olvida eso", "ya no soy vegetariano"). Lo decide el modelo, sin palabras
  clave. Van al prompt de todos los asistentes de ese perfil
  (`app/skills/memory.py`, `config/memory/<perfil>.json`).
- Ajustes → "Lo que recuerdan de ti": ver, agregar, corregir, olvidar uno u
  olvidar todo. El invitado la tiene en su navegador (la página la manda con
  cada pregunta).
- Con más de 40 hechos y `nomic-embed-text` instalado, van los más
  parecidos a lo que se habla (embeddings, `app/core/embeddings.py`) más los
  últimos; sin ese modelo, los más recientes.
- Probado: Jarvis guardó dos hechos; Bella los usó en otra conversación; "ya
  no soy vegetariano, olvida eso" borró ese.

### 23. Resumen de chats largos (octubre 2026)

- Cuando la conversación pasa el "historial" del asistente, la mitad más
  vieja se resume con el mismo modelo (`chat_runtime.summarize`) y se une al
  resumen anterior, en vez de cortarse. El resumen va al system prompt, se
  guarda con el chat (`chat_store`, campo `summary`) y la página lo manda en
  cada pregunta (evento `summary` del NDJSON: cuántos mensajes ya resumió).
  En pantalla los mensajes siguen visibles.
- Probado con historial 4: datos dados cinco turnos antes (días en Kioto,
  presupuesto, una alergia) se recordaron todos por el resumen.

### 24. Recordatorios, alarmas y temporizadores (octubre 2026)

- `set_reminder` / `cancel_reminder` (`app/skills/reminders.py`): hora
  relativa o exacta, repetición (diaria, lunes a viernes, semanal) y la frase
  que dirá, en el estilo del asistente. `config/reminders.json`; un hilo del
  servidor los mira cada segundo. Los vencidos con AuraVox cerrado se avisan
  al arrancar como "perdidos" (si pasó menos de 6 h).
- Aviso (`app/webui/notify.py`, consulta larga `GET /api/notify`): la página
  de la PC lo dice con la voz del asistente (la primera que lo reclama); en
  el celular, notificación del sistema y vibración; tarjeta con "Posponer
  10 min" y "Listo". Si en la PC no hay página abierta (o es de otro
  perfil), lo dice el servidor por los altavoces. `/sw.js`: service worker
  mínimo para las notificaciones en Android (con el certificado autofirmado
  Chrome puede no registrarlo: queda el aviso dentro de la página; con la
  app cerrada haría falta Web Push y un certificado válido).
- Ajustes → "Recordatorios": pendientes, cancelar, recientes y activar las
  notificaciones en ese dispositivo.

### 25. Listas y notas (octubre 2026)

- `add_to_list`, `update_list_items`, `delete_list` (`app/skills/lists.py`):
  listas de cada perfil (`config/lists/<perfil>.json`) y de la casa,
  compartidas (`config/lists/home.json`; el invitado solo usa estas). El
  modelo las ve en el prompt, así que "¿qué queda en la lista de compras?"
  se responde sin herramienta.
- Vista "Listas" en la barra superior: listas para marcar o de notas, editar
  en el lugar, marcar, quitar marcados, renombrar y borrar. Se actualiza sola
  si cambian por chat o desde otro dispositivo.
- Arreglado al probar: a "ya compré la leche, márcala" el modelo la marcaba y
  la volvía a agregar en la misma ronda.

### 26. Documentos del asistente: RAG local (octubre 2026)

- Cada asistente tiene `config/knowledge/<asistente>/` (panel → "Documentos").
  El texto sale de `app/core/attachments.py` (docx, xlsx, pptx, odt, epub,
  rtf, html, txt…; `extract_text` tiene ahora `limit`) y los PDF los lee la
  página completos con pdf.js. Se parten en trozos de ~1000 caracteres.
- `search_documents` (`app/skills/knowledge.py`): por significado si está
  `nomic-embed-text` (embeddings en segundo plano) o por palabras (BM25) si
  no; responde citando el archivo ("📚 Consulté: …" en el chat). Los
  documentos siguen al asistente al renombrarlo y se borran con él.
- Probado con el manual de una cafetera: el código de error exacto, y con
  embeddings "¿cómo le quito el sarro?" encontró la descalcificación.

### 27. Rutinas (octubre 2026)

- `run_routine` (`app/skills/routines.py`, `config/routines/<perfil>.json`):
  "Buenos días" = fecha + clima + recordatorios de hoy + listas + titulares;
  cada una con "cuándo usarla" (en tus palabras), bloques, tema de noticias e
  indicación extra. El modelo decide cuándo llamarla.
- Con hora (y días y asistente) el servidor la corre sola y la avisa como un
  recordatorio. Ajustes → "Rutinas". El invitado tiene solo la de ejemplo.

### 28. Exportar / importar asistentes (.auravox) (octubre 2026)

- Panel del asistente → "Exportar": JSON con personalidad, parámetros, color,
  idiomas, modelo, alias y voz (la clonada con su audio de referencia
  adentro) y, opcional, el texto de sus documentos. Sin dueño, chats,
  memoria ni tecla de push to talk (`app/webui/assistant_io.py`).
- Galería → "Importar": crea uno nuevo, privado, de quien lo importa (nombre
  con número si ya existe; entonces sin alias). La voz clonada solo la crea
  un administrador; si no, su voz de respaldo. Avisa si falta el modelo.

### 29. Sistema de plugins (octubre 2026)

- Carpeta `plugins/`: cada plugin es `<id>/manifest.json` (nombre,
  descripción, rol mínimo, herramientas) + `plugin.py` con
  `call(name, args, ctx)` (opcionales `tools(ctx)` y `context(ctx)`). Ver
  `plugins/README.md` y el ejemplo `dice_example`. Cargador:
  `app/core/plugins.py`; estado en `config/plugins.json`.
- Búsqueda web y lugares, clima y Spotify son plugins integrados (envuelven
  `app/tools`, mismo orden de herramientas); `assistant_engine` (consola)
  también los toma de ahí. Un plugin nuevo arranca desactivado.
- Ajustes → "Plugins" (admin): activar, rol mínimo, errores de carga y
  volver a leer la carpeta.

### 30. Cliente MCP (octubre 2026)

- `app/core/mcp_client.py`, solo biblioteca estándar: transporte stdio (lanza
  el programa, p. ej. `npx …`, JSON-RPC por línea) y Streamable HTTP (JSON o
  SSE, `Mcp-Session-Id`). `initialize`, `tools/list` paginado, `tools/call`.
  Se conectan en segundo plano; sus herramientas son `<servidor>__<herramienta>`
  y por defecto solo para administradores. `config/mcp.json`.
- Ajustes → "Servidores MCP" (admin): agregar por comando o URL (variables de
  entorno o cabeceras para tokens, que no se vuelven a mostrar), estado,
  activar, rol, reconectar, quitar.
- Probado con un servidor de prueba (stdio, HTTP y lanzado vía `.cmd`, como
  `npx` en Windows). No se probó un paquete real de npm.

### 31. Escucha por nombre desde el celular (octubre 2026)

- En un dispositivo que no es la PC (o con `--no-voice`), el botón del
  micrófono pasa a "Escuchar": el navegador detecta la voz (VAD por energía,
  como la conversación por voz), manda cada frase a `POST /api/wake/listen`
  (Whisper en el servidor + los nombres y alias de los asistentes que ese
  perfil puede usar) y, si empieza con un nombre, abre su conversación por
  voz igual que una llamada desde la PC. Pide mantener la pantalla encendida
  (Wake Lock): con la pantalla apagada el navegador corta el micrófono.
- Probado en Chrome con un micrófono simulado: "Jarvis, ¿qué hora es en
  Tokio?" abrió a Jarvis por voz y respondió.

- API_VERSION 7 (rutas nuevas y `/sw.js`).

### 32. Pantalla de diagnóstico (octubre 2026)

- Ajustes → "Diagnóstico" (admin), vista `#/diag` (`app/webui/diagnostics.py`):
  Ollama (si corre, versión y actualización, modelos y si alguno tiene
  "tools", lo cargado y si quedó parte fuera de la GPU), GPU/VRAM, disco,
  Whisper/Supertonic/voces clonadas, micrófono de la PC, puertos (y quién
  ocupa el 8443 si está tomado), firewall de Windows y tipo de red, ffmpeg,
  Office y el modelo de embeddings; más las pruebas de este dispositivo
  (https, notificaciones, service worker, micrófono y altavoz).
- "Arreglar": iniciar Ollama, liberar VRAM, descargar el modelo recomendado
  según la VRAM, activar/reintentar el micrófono, reintentar el acceso por
  red, permitir el puerto en el firewall (solo redes privadas) y marcar la
  red como privada. Los que tocan Windows piden UAC en la PC y no se aplican
  desde otro dispositivo.
- El firewall se consulta por programa y por puerto (recorrer todas las
  reglas tardaba más de 40 s); una red pública solo avisa si ninguna regla
  la cubre.

### 33. Respaldo y restauración (octubre 2026)

- Ajustes → "Respaldo y restauración" (admin), `app/webui/backup.py`: un
  .zip con todo lo del usuario de `config/` (perfiles sin las sesiones,
  asistentes, chats, voces clonadas, memoria, recordatorios, listas,
  documentos, rutinas, plugins, MCP). Opcional: adjuntos de los chats y
  claves (red, Spotify, secretos de plugins y MCP; sin ellas van vacíos).
  Nunca el certificado.
- En `backups/` (junto a `config/`): uno automático por día al arrancar (se
  guardan 7) y otro antes de cada restauración. Restaurar valida el
  manifiesto, solo escribe dentro de `config/`, conserva las sesiones
  abiertas y recarga plugins, MCP y voces.

### 34. Home Assistant (octubre 2026)

- Plugin `plugins/home_assistant` (apagado de fábrica, rol mínimo "user"):
  `home_control` (encender/apagar, brillo, color, temperatura, persianas,
  cerraduras, multimedia, escenas, scripts) y `home_find` (buscar y leer
  sensores). Lo que se puede manejar va en el prompt; los nombres se buscan
  por parecido; las entidades excluidas nunca se tocan.
- Los plugins ahora pueden pedir ajustes ("settings" en el manifiesto:
  texto, secreto, número): se llenan en Ajustes → Plugins → Configurar, con
  "Probar conexión" (`check(settings)` en plugin.py). Los secretos no se
  vuelven a mostrar.

### 35. Control de la PC (octubre 2026)

- Plugin `plugins/pc_control` (solo administradores, lo exige el propio
  plugin): volumen, teclas multimedia (play/pausa, siguiente, anterior),
  abrir programas del menú Inicio o una página, bloquear la pantalla. Con
  ctypes, sin librerías. `AURAVOX_PC_DRYRUN=1` solo anota lo que haría
  (para probar).

### 36. Interrumpir hablando (barge-in) (octubre 2026)

- En la conversación por voz con el micrófono de la página, si empiezas a
  hablar mientras el asistente habla, se calla y te escucha (`waitTurn` en
  app.js). Para no confundir su voz (que entra por el micrófono) con la
  tuya, mide primero cuánto eco llega y solo cuenta algo bastante más fuerte
  durante ~0,25 s; el navegador además resta el eco.
- El botón redondo ya no es la X: es el único botón y es el micrófono
  (silenciarte / volver a hablar; el mismo dibujo abierto o tachado, y el
  aviso debajo para que no se corra). Para terminar se le pide por voz ("ya
  terminamos, sal de la conversación": usa su herramienta de salir) o se
  sale del modo voz. Tocar el aro mientras habla también lo interrumpe.
- Si lo interrumpes solo para que se calle ("para", "ya, gracias"), no
  responde nada ("🤫 Me callo"): lo decide el modelo con salida JSON
  (`config_ui._only_stop`, ~0,3 s); si dijiste algo más, responde a eso. La conversación abierta con el micrófono de la PC (manos
  libres del servidor) sigue como antes.

- API_VERSION 8.

### 37. Adjuntos, foto y videollamada en el modo voz (octubre 2026)

- En la conversación por voz hay botones a los lados del micrófono: adjuntar
  archivos (o arrastrarlos), sacar una foto y la **videollamada**. Lo
  adjuntado espera en una bandeja y se manda con lo próximo que digas.
- **Videollamada:** abre la cámara (en el celular la de atrás, con botón para
  cambiar a la frontal) en una ventana sobre el escenario y, con cada cosa
  que dices, manda al modelo el cuadro de ese momento (1024 px, JPEG): así
  reconoce los objetos que le muestras, lee etiquetas, cuenta cosas… El botón
  "¿Qué ves?" pregunta sin hablar. Al prenderla se abre la conversación por
  voz; se apaga al salir del modo voz o del asistente. En el celular el aro
  se corre y se achica para que se vean los dos.
- El servidor le avisa al modelo que está en una videollamada (`video_call`
  en `/api/chat`, ver `_chat_request`) para que use la imagen cuando le
  preguntan y no la describa cuando hablan de otra cosa. Solo el último
  cuadro sigue en el contexto (`IMAGE_TURNS`). Hace falta un modelo con
  visión (gemma4 la tiene). Funciona igual en la PC y en el celular (por
  https, que la cámara lo exige).
- Probado en Chrome con una cámara simulada (una imagen con una manzana, un
  plátano, una taza y el texto "OFERTA 2x1"): "Veo una manzana roja, un
  plátano amarillo y una taza de café morada, con el texto «OFERTA 2x1»".
  En tamaño celular, un manual adjunto más la cámara en la misma pregunta:
  respondió las dos cosas.

### 38. Correcciones tras usarlo por voz (octubre 2026)

Vistas en el log de una sesión real con BELLA:
- **"Tell me about…" llegaba como "Bella me about…":** la corrección de
  nombres de lo que transcribe el micrófono tomaba "tell" por "bella" (67 %
  de parecido). Ahora, para nombres cortos (5 letras o menos), como mucho
  una letra de diferencia (`wake_word_utils.match_ratio`); las variantes
  escritas en wake_words.txt siguen valiendo tal cual.
- **"Buenos días" respondido en inglés:** Whisper lo detectó como inglés (51
  % contra 43 %) y se respondía en el idioma detectado. Ahora, si Whisper
  duda del idioma, la página pide "auto" y el idioma de la respuesta lo
  decide el modelo por el texto (`confident` en `/api/chat/transcribe`).
- **"¿Cuánto falta?" respondía la duración original** ("faltan 10 minutos" a
  los 2 minutos): el prompt trae lo que falta calculado con segundos y la
  indicación de usarlo.
- **Un temporizador quedaba dos veces:** tras un empujón del revisor el
  modelo volvía a llamar la herramienta con los mismos datos. Ahora una
  llamada idéntica en el mismo turno no se ejecuta otra vez
  (`ask_with_tools`, sirve para todas las herramientas con efectos: listas,
  Home Assistant, control de la PC…).

### 39. Respuestas en streaming y menos espera por turno (octubre 2026)

- **Streaming y voz frase por frase:** la respuesta al usuario se pide a
  Ollama con `"stream": true` (`assistant_common._stream_chat`). El chat
  escrito muestra el texto mientras llega y, en la conversación por voz
  (PC, celular, manos libres), cada frase completa (corta en `. ! ? : ;` o
  salto de línea, mínimo ~20 letras, sin cortar en "a. C."; la primera,
  si es muy larga, en una coma) se sintetiza y suena enseguida, en cola,
  mientras el modelo sigue escribiendo (`SpeechChunker`). `/api/chat` suma
  los eventos `delta` (texto), `say` (frase para la voz, con su idioma) y
  `reset` (lo mostrado/dicho se descarta porque el servidor pidió otra
  respuesta: la página lo borra y corta la voz). Si Whisper dudó del
  idioma, las frases se dicen al final, cuando el revisor ya dijo en qué
  idioma salió. `run_voice_loop.bat` también habla frase por frase.
- **Barge-in:** interrumpir hablando corta la voz, vacía la cola y además
  corta la petición (`AbortController`): el servidor lo nota al escribir y
  Ollama deja de generar ("la página cortó la respuesta" en el log). Queda
  en la conversación lo que alcanzó a escribir.
- **Revisión previa en paralelo** (`_needs_tool`): con streaming no se
  puede revisar el borrador antes de decirlo, así que la pregunta "¿esto
  necesita una herramienta?" se hace antes, a la vez que la primera ronda
  (Ollama atiende dos peticiones a la vez). Visto en las pruebas: a "¿qué
  tiempo hace hoy?" y a "pon un temporizador de 7 minutos" gemma4
  respondía de memoria ("listo, ya lo puse") sin llamar la herramienta;
  la revisión previa lo ataja antes de que se oiga. Medida con 14 frases
  (saludo, capital de Australia, ideas de cena o de regalo, clima,
  temporizador, último mundial, dólar, noticias, música, farmacia cerca,
  "recuerda que…"): acierta las 14, ~0,3 s cada una.
- **Revisor solo cuando aporta:** si la revisión previa dijo que no hacía
  falta herramienta, no se usó ninguna y el idioma ya está fijado, no hay
  revisión del borrador: una pregunta sin herramientas se resuelve con una
  sola ronda (más la revisión previa, en paralelo). Tras usar una
  herramienta sí se revisa (¿contradice el resultado?); por voz esa
  respuesta espera al revisor antes de sonar (si pide rehacerla, lo dicho
  no se puede desdecir), en el chat escrito se muestra mientras tanto. Ya
  no se marca "contradice el resultado" cuando no hubo herramientas (visto
  con una foto: costaba una ronda y una revisión de más).
- **Caché de Ollama:** lo que cambia en cada turno (hora, memoria
  relevante, recordatorios con los segundos que faltan, "la charla ya
  empezó") pasó del system prompt al final del último mensaje del usuario
  (`turn_context`). Con herramientas, cualquier cambio en el system prompt
  obligaba a Ollama a leer otra vez ~5000 fichas en cada ronda (0,6–0,9 s).
  La revisión previa sale 50 ms después de la ronda para que cada una
  conserve su "ranura" de caché. El log muestra cuándo una ronda tuvo que
  releer el prompt ("0.8s leyendo el prompt").
- **Ollama:** variables del usuario `OLLAMA_FLASH_ATTENTION=1`,
  `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_MAX_LOADED_MODELS=2` y
  `OLLAMA_NUM_PARALLEL=2` (la última, para la revisión en paralelo; con la
  caché en 8 bits ocupa lo mismo que antes). El diagnóstico muestra si el
  Ollama que corre las tomó (lee su `server.log`) y, si no, "Aplicar y
  reiniciar Ollama" las guarda y lo reinicia. `keep_alive` de la interfaz
  y de los embeddings: sin límite (antes 15 y 10 min), configurable con
  `AURAVOX_KEEP_ALIVE` ("30m", "2h"…); gemma4 y nomic-embed-text quedan
  cargados a la vez y solo se descargan a pedido. "Medir memoria" ya no le
  baja a 60 s el keep_alive a un modelo que estaba cargado.
- **Temporizadores que no quedaban:** gemma4 llamaba `set_reminder` sin
  `in_minutes` ni `at` en la mitad de los "pon un temporizador de 7
  minutos" y decía "listo" igual. Ahora, si falta el cuándo, se le pide
  solo eso al modelo con salida JSON (`reminders._when_from_conversation`)
  y, si tampoco sale, el resultado dice "NOT SET" claramente. El aviso de
  llamada repetida ya no dice "ya está hecho" (también se usaba cuando la
  primera vez había fallado).
- **Medido** (instancia de prueba, gemma4:E4B, RTX 4080 SUPER, voz F4;
  mediana; "primera voz" = primera frase lista + sintetizarla):

  | Frase (modo voz) | Primera voz antes | Primera voz ahora | Total antes | Total ahora | Llamadas antes → ahora (seguidas) |
  |---|---|---|---|---|---|
  | "Hola Bella, ¿cómo estás?" | 1,0 s (una vez 6,1 s) | 0,75 s | 0,8 s | 0,5 s | 2 → 2 (1) |
  | "Explícame por qué el cielo es azul" | 1,3 s | 0,74 s | 1,1 s | 0,75 s | 2 → 2 (1) |
  | "¿Qué tiempo hace hoy?" | 3,0 s | 2,1 s | 2,9 s | 1,9 s | 4 → 4 (3) |
  | "Pon un temporizador de 7 minutos" | 1,7 s (la mitad no quedaba puesto) | 2,8 s (siempre queda) | 1,5 s | 2,6 s | 3 → 4–5 (3–4) |
  | Chat escrito, "¿por qué el cielo es azul?" | 3,5 s (texto completo) | 1,2 s (primer texto) | 3,5 s | 2,2 s | 2 → 2 (1) |

  En una charla de varios turnos la primera frase sale en ~0,6 s. El
  temporizador tarda más porque ahora se corrige al modelo cuando dice
  "listo" sin haberlo puesto (antes quedaba sin temporizador).
- **Pendiente / dudas que quedaron:** la decisión "solo pidió que se
  calle" del barge-in (`_only_stop`) sigue antes de responder (~0,3 s, solo
  en interrupciones); el resumen de chats largos sigue antes de la
  respuesta del turno en que se resume. A veces Ollama igual cruza las
  ranuras y una ronda relee el prompt (~1 s en vez de ~0,6 s).
- API_VERSION 9.

### 40. Barge-in que no saltaba, interfaz más pareja y carpeta AuraVox (octubre 2026)

- **Interrumpir hablando no funcionaba en ningún lado:** el bucle de la
  conversación por voz (`convLoop`) esperaba la respuesta entera, voz
  incluida, antes de volver a `waitTurn`, que es quien mira si hablas
  mientras responde: solo miraba cuando ya había terminado. Ahora el turno
  sigue en paralelo y `waitTurn` escucha mientras habla. Además, mientras
  suena el altavoz el cancelador de eco del navegador atenúa mucho tu voz
  (medido en Chrome: 0,01–0,1 en vez de 0,1–0,3): el umbral parte en 0,012
  (antes 0,035) y basta con voz en ~6 de las últimas 16 mediciones de 30 ms,
  aunque venga a ráfagas (`BARGE` en app.js). Probado en Chrome con un
  micrófono simulado: corta la voz y la respuesta y atiende lo nuevo.
- **Reiniciar un chat borra sus archivos:** los adjuntos y los archivos
  convertidos de esa conversación se borran al reiniciarla, salvo que otra
  conversación guardada los use (`file_store.forget`). Las del invitado
  (están en su navegador) se piden borrar con `POST /api/files/forget`.
- **Interfaz:** mismo margen lateral de 16 px en el celular en todas las
  páginas; las tarjetas del diagnóstico y de las listas se separan igual que
  en "Ajustes compartidos" (cada sección de listas es una tarjeta y la fila
  "nueva lista" ya no salta de línea en el celular); campos de las grillas
  con el mismo espacio (en el panel lateral la etiqueta "Color" quedaba
  pegada a la ayuda de arriba); el chat desvanece lo que sube por debajo de
  la cabecera en vez de cortarlo pegado a ella.
- **Revisión previa:** ya no fuerza una herramienta que hace otra cosa (a
  "cierra Chrome" llamaba `pc_open` y lo abría): si ninguna hace lo pedido,
  "none". `pc_open` aclara que no cierra programas. 17 de 17 frases de
  prueba.
- **Carpeta:** el proyecto pasó de `F:\AI\Assistant` a `F:\AI\AuraVox`. En
  la raíz quedan `AuraVox.bat` (antes `run_config_ui.bat`), README y
  CONTEXTO; los otros `.bat` están en `extras\`.

### 41. ComfyUI: crear y editar imágenes y hacer videos (octubre 2026)

- **Qué es:** un plugin opcional (`plugins\comfyui`, desactivado por
  defecto) que usa el ComfyUI que ya tengas instalado y abierto, con sus
  modelos y tus flujos. No agrega dependencias (solo `requests`, que ya
  estaba, y la API HTTP de ComfyUI; sin websocket ni torch). Si ComfyUI no
  responde, las herramientas no aparecen, el panel dice "No conectado" y
  AuraVox sigue igual.
- **¿Plugin o MCP?** Plugin: tiene que descargar y recargar gemma4 en
  Ollama (la VRAM), esperar a que termine la voz antes de empezar, mandar
  una tarjeta con progreso al chat, guardar el resultado como archivo del
  chat y tener un panel de ajustes. Un servidor MCP solo devuelve texto al
  modelo y no ve nada de eso.
- **Herramientas del modelo:** `generate_image(prompt, negative?, width?,
  height?, workflow?)`, `edit_image(instruction, image?, workflow?)` (la
  última imagen del chat o la que se nombre, propia o adjunta) y
  `generate_video(prompt, duration?, image?, workflow?)`. El prompt va en
  inglés y el modelo responde corto: "La estoy creando, tarda ~25 s".
- **Flujos** (`cu_workflows.py`):
  - Los guardados en ComfyUI (`/api/userdata?dir=workflows`) están en
    formato de la interfaz: se **convierten a formato API** con
    `/object_info` (widgets por nombre o por posición, semillas con
    "randomize", nodos puenteados/silenciados, Reroute, PrimitiveNode,
    Get/Set de KJNodes, Power Lora Loader y **subgrafos** anidados). Probado
    con los 21 de esta PC: se convierten todos los que guardan algo.
  - Los que se dejen en `plugins\comfyui\workflows\` (exportados con
    "Export (API)" o normales) o se importen desde el panel.
  - Los de AuraVox, armados con los modelos que haya: checkpoint SD/SDXL
    (imagen e img2img), **Flux.2 Klein** (imagen y edición con
    ReferenceLatent) y **Wan 2.1/2.2** texto→video (con el LoRA lightx2v si
    está). Qwen-Image-Edit o Flux Kontext se usan importando su flujo.
  - **Detección de entradas:** desde el sampler hacia atrás se encuentran
    el prompt positivo y el negativo (respeta interruptores y
    concatenaciones), y además semilla(s), ancho/alto de los latentes
    vacíos (o del selector de resolución que los alimenta), duración y
    fps de video, LoadImage, el cargador del modelo, pasos, CFG y denoise.
    Avisa si al flujo le faltan nodos o modelos (un archivo que no está en
    la lista de su nodo).
- **Ajustes → Plugins → ComfyUI:** dirección, "Probar", memoria de la GPU
  (intercambio / convivir), segundos de espera antes de recargar el
  asistente (90) y liberar también Whisper y la voz. En "Modelos y flujos":
  flujo y modelo por defecto de cada tarea (la lista de modelos sale del
  cargador del flujo), ancho/alto/duración/pasos, asignar cada flujo a una
  tarea, corregir el mapeo de entradas e importar flujos. Los de ComfyUI se
  usan solo si se les asigna una tarea (si una tarea no tiene ninguno, se
  prueban hasta tres que parezcan servir).
- **Ejecución y VRAM** (`cu_jobs.py`): un hilo corre los trabajos en
  orden: `POST /prompt`, sondeo de `/queue` y `/history/{id}`, `/view` para
  bajar el resultado, `/upload/image` para la imagen de origen e
  `/interrupt` para cancelar. El progreso es estimado (lo que tardó ese
  flujo las veces anteriores; sin websocket ComfyUI no lo informa). En
  modo **intercambio**: antes del primero descarga lo que haya en Ollama
  (keep_alive 0, también los embeddings) y, si se pidió, Whisper, la voz y
  Qwen3-TTS (aparte, para no esperar si se está preparando); al terminar
  la cola espera los segundos configurados y entonces `POST /free` y
  vuelve a cargar lo que había. Si mientras tanto alguien chatea, ComfyUI
  solo pasa sus modelos a la RAM (`/free` sin vaciar caché) para que
  responda el asistente, y la próxima edición no relee el disco.
  Trabajos recientes en `config\comfyui\jobs.json`, tiempos aprendidos en
  `stats.json` y lo elegido en el panel en `config.json`.
- **En el chat:** tarjeta con barra, "Empieza cuando termine de hablar…",
  "Preparando la GPU…", tiempo restante y Cancelar; al terminar, la imagen
  o el video (archivo del chat, `file_store`) con **Editar** (escribe
  "Edita «imagen_….png»: " en la caja), Abrir y Descargar. El archivo se
  suma a la respuesta de ese turno, así el modelo lo ve en el historial
  ("ahora ponle una luna"). El trabajo arranca recién cuando terminó la
  respuesta y su voz (la página manda `go`; si no, a los 45 s). Mientras
  dibuja una imagen en modo intercambio, lo que escribas o digas queda en
  cola y se manda al terminar. El video corre de fondo (se puede seguir
  charlando) y avisa con notificación al terminar, también si estás en
  otro chat (avisos de `notify.py`). Plugin con rol mínimo "Perfiles": el
  invitado no lo usa; el panel es solo para administradores.
- **Núcleo:** los plugins pueden tener rutas propias
  (`/api/plugin/<id>/<acción>`, `plugins.http`) y ajustes `select`/`bool`;
  el contexto de las habilidades trae los archivos de la conversación
  (`ctx.files`); la página tiene `FEATURE_ROLES` (mensajes propios de un
  plugin en el chat) y `featureHoldSend` (retener lo que mandas).
- **Probado de verdad** (instancia de prueba en el puerto 8766, ComfyUI
  0.36 de `F:\AI\ComfyUI-Easy-Install`, RTX 4080 SUPER 16 GB, 32 GB RAM):
  chat "Dibújame…" → Flux.2 Klein 9B GGUF 1024×1024 en 14 s; "ahora ponle
  una luna llena" → edición con el flujo "Klein I2I" del usuario (con
  subgrafo) en 23–27 s; video Wan 2.2 14B 832×480, 17 cuadros, en 59 s;
  cancelar a mitad; lo escrito durante la imagen se mandó al terminar;
  gemma4 se recargó sola tras la espera (2–9 s). **Ojo con la VRAM:** con
  dos Qwen3-TTS abiertos (instancia normal + la de prueba) ComfyUI cargó
  el modelo a medias y tardó 40 s por paso: en 16 GB conviene activar
  "liberar también Whisper y la voz".
- API_VERSION 10.
- **Después (mismo día):** visor de imágenes dentro de la app
  (`openImageViewer` en features.js): pantalla completa con zoom (rueda o
  pellizco hacia donde apuntas, doble clic, + / − / ajustar) y arrastrar;
  lo usan las imágenes de ComfyUI, los archivos convertidos y los adjuntos.
  La tarjeta dice con qué flujo se hizo. Los flujos que asignas a mano a
  una tarea van antes que los de AuraVox y elegir el flujo o modelo de una
  tarea se guarda al instante. Las LoRAs del Power Lora Loader se respetan
  tal como están **guardadas** en el flujo de ComfyUI (lo no guardado de la
  pestaña abierta no se ve desde fuera).
- **Más tarde (mismo día):**
  - **Arreglo:** el flujo elegido en "Tareas" (p. ej. "Klein I2I" para
    editar) se ignoraba si en la lista de flujos no tenía asignada esa
    tarea, y se usaba el de AuraVox. Ahora el elegido va primero siempre.
  - **Regenerar y versiones:** "Regenerar" pide otra versión (otra
    semilla, mismo flujo y pedido, `POST /api/plugin/comfyui/regen`). La
    tarjeta guarda todas y muestra una a la vez, con ‹ 2/3 › para pasar de
    una a otra (como ChatGPT); cada versión se suma a los archivos de la
    respuesta.
  - **Lienzo mientras se crea:** un recuadro del tamaño de lo que se
    genera (el pedido, el de la imagen de origen o el del flujo; el
    servidor lo manda como `size`) con manchas de color difuminadas en
    movimiento y un brillo que lo recorre, más la barra de progreso; al
    terminar, la imagen aparece desenfocándose.
  - **Iconos:** `static/icons.js`, un pack propio delineado de un solo
    color (trazo 1,75, `currentColor`). Lo usa el chat: botones (hablar,
    reintentar, editar, adjuntar, cámara, enviar, cerrar), la tarjeta de
    ComfyUI y los avisos ("Buscando en internet…", "Lo recordaré…": cada
    herramienta con su icono en vez de un emoji).
  - **Carrera de VRAM:** si llegaba un pedido justo mientras el asistente
    se volvía a cargar, los dos peleaban por la GPU (una imagen tardó más
    de 150 s). Ahora descargar y recargar no se pisan: el pedido espera la
    recarga y vuelve a descargar (probado: 29 s).
  - **Flujo elegido, de verdad:** el modelo también podía elegir un flujo
    por su cuenta (`edit_image(..., workflow="AuraVox · …")`), y tras
    reiniciar un chat lo hacía. Si en "Tareas" hay un flujo elegido, la
    herramienta ya no ofrece el parámetro `workflow` y el servidor lo
    ignora: manda siempre el elegido.
  - **Imágenes de referencia al editar:** `edit_image(instruction, image,
    references[])`: la imagen a cambiar más hasta 3 del chat (adjuntas o
    creadas) de las que tomar algo ("ponle la bufanda de la otra foto").
    Se suman al grafo en memoria, sin tocar el flujo guardado
    (`cu_workflows.add_references`): en las entradas mapeadas como
    "Referencia 1/2" (otro LoadImage del flujo, se corrige en el panel), en
    las entradas libres de los codificadores tipo Qwen-Image-Edit-Plus o,
    en flujos con ReferenceLatent (Flux.2 Klein, Kontext), con un
    ReferenceLatent más por referencia en el positivo y el negativo. Si el
    flujo no admite referencias, la tarjeta lo avisa y el asistente lo dice.
    Probado con el "Klein I2I" del usuario: zorro + foto de una bufanda →
    el zorro con esa bufanda (18 s).
