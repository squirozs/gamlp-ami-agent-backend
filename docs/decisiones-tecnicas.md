# Decisiones Tecnicas (ADRs)

Formato: contexto / decision / consecuencias. Cada ADR queda numerado y no se edita
retroactivamente; si una decision cambia, se agrega un ADR nuevo que la reemplaza.

---

## ADR-001: Interfaz abstracta para integraciones municipales (mock/real intercambiable)

**Contexto:** durante la hackathon no hay credenciales reales de e-SITRAM/iGOB/Gestion
Documental, pero el sistema debe demostrar el flujo completo end-to-end y estar listo
para conectar credenciales reales despues sin reescribir logica de negocio.

**Decision:** `MunicipalAPIClient` es una interfaz abstracta (`app/integrations/base.py`)
con dos implementaciones por integracion (`*_client.py` real, `*_mock.py` mock),
seleccionadas por variable de entorno (`ESITRAM_MODE=mock|real`). La capa de
`services` y `agents/tools` solo dependen de la interfaz.

**Consecuencias:** cambiar de mock a real es un cambio de configuracion, no de codigo.
El costo es mantener el mock sincronizado en forma (misma estructura de respuesta) con
la API real cuando esta se defina.

---

## ADR-002: Nunca se persiste la foto de un documento

**Contexto:** los documentos de identidad/propiedad son datos sensibles. Guardarlos en
disco o en el vector store crearia una superficie de riesgo innecesaria (fuga de PII,
requisitos de retencion legal) sin aportar valor al producto: solo se necesita el
*resultado* de la validacion.

**Decision:** la foto llega como bytes en memoria (`UploadFile` en el endpoint REST, o
media descargado del webhook de WhatsApp), se envia directo a la API de vision de
Anthropic, y los bytes se descartan explicitamente apenas se obtiene el resultado
(ver `app/services/documento_service.py` y `app/agents/tools/validate_document.py`).
Nunca se escribe a disco, nunca se indexa en ChromaDB, nunca se guarda en una columna
BLOB de Postgres. Solo se persiste `resultado` + `observaciones` (metadatos) en
`documentos_validados`.

**Consecuencias:** si se necesita auditoria visual retroactiva, no existe. Se acepta
ese trade-off por privacidad; si el negocio lo requiere en el futuro, deberia ser un
ADR nuevo con retencion explicita y consentimiento.

---

## ADR-003: Logging estructurado sin PII

**Contexto:** los logs de produccion suelen terminar en sistemas de menor confianza
(agregadores, dashboards de terceros) que la base transaccional. Loguear contenido de
mensajes o numeros de documento seria una fuga de datos personales de facto.

**Decision:** `app/core/logging.py` usa `structlog` con salida JSON. Las tools y
servicios loguean solo identificadores (`tramite_id`, `recordatorio_id`), resultados
(`estado`, `resultado`) y timestamps. Numeros de telefono se enmascaran
(`_mask_phone` en `whatsapp_client.py`) antes de loguearse.

**Consecuencias:** debuggear un caso especifico requiere correlacionar por
`tramite_id`/`conversacion_id` en la base de datos, no leyendo el log directamente.

---

## ADR-004: Tool registry en vez de if/elif en el orquestador

**Contexto:** el numero de tools va a crecer con cada nuevo tipo de tramite que se
soporte. Un `if/elif` gigante en el orquestador se vuelve inmanejable y acopla al
orquestador con el conocimiento de cada tramite especifico.

**Decision:** cada tool se define en su propio modulo bajo `app/agents/tools/` y se
auto-registra en un `ToolRegistry` singleton via decorador (`@tool_registry.register`).
El orquestador solo conoce `tool_registry.anthropic_tool_specs()` y
`tool_registry.ejecutar(name, input)`.

**Consecuencias:** agregar una tool nueva es agregar un archivo nuevo e importarlo en
`app/agents/tools/__init__.py`; cero cambios en `orchestrator.py`.

---

## ADR-005: Circuit breaker + timeout en clientes municipales, no reintentos infinitos

**Contexto:** si e-SITRAM/iGOB estan caidos, el agente no debe colgarse esperando
respuesta ni convertir cada mensaje del ciudadano en una cadena de timeouts largos que
degraden la experiencia de todo el sistema (y el costo de tokens del LLM en el loop
de tool use).

**Decision:** cada cliente real tiene timeout configurable
(`ESITRAM_TIMEOUT_SECONDS`, `IGOB_TIMEOUT_SECONDS`) y un circuit breaker en memoria
(`app/integrations/circuit_breaker.py`) que abre el circuito tras N fallos
consecutivos y falla rapido durante una ventana de enfriamiento. Ante fallo, se
lanza `MunicipalAPIUnavailableError`, que las tools capturan para responder con
degradacion elegante en vez de propagar un stack trace al ciudadano.

**Consecuencias:** durante una caida prolongada, el agente sistematicamente responde
"no puedo verificar esto ahora" sin reintentar agresivamente contra el sistema caido.

---

## ADR-006: RAG con umbral de similitud estricto para prevenir alucinaciones

**Contexto:** el requisito de producto es que el agente NUNCA invente requisitos,
montos o plazos. Un RAG que siempre devuelve los top-k resultados (aunque no sean
relevantes) le da al modelo material para "justificar" una alucinacion con una cita
que en realidad no aplica.

**Decision:** `RagService.buscar()` filtra los resultados de ChromaDB por
`RAG_SIMILARITY_THRESHOLD` (default 0.45) y devuelve una lista vacia si ninguno la
supera. La tool `buscar_normativa` traduce eso a `encontrado=false`. El system prompt
(`app/agents/prompts.py`) instruye al modelo a admitir la falta de informacion en ese
caso, en vez de responder con conocimiento general. Existe un test dedicado
(`tests/unit/test_rag_anti_hallucination.py`) que verifica este contrato.

La coleccion de ChromaDB se crea explicitamente con `metadata={"hnsw:space": "cosine"}`
(`app/services/rag_service.py`): sin esto, Chroma usa distancia `l2` por defecto, que
no es directamente convertible a una similitud [0,1] y produce falsos negativos
sistematicos (se detecto este bug corriendo contra un servidor Chroma real, no en los
tests unitarios que mockean `RagService`).

El valor 0.45 se calibro empiricamente contra el modelo de embeddings por defecto de
ChromaDB (`all-MiniLM-L6-v2`, descargado localmente por el propio servidor Chroma, sin
necesidad de una API de embeddings externa) usando el corpus de demo
(`docs/normativa/ejemplo_licencia_funcionamiento.txt`):

| Consulta | Similitud coseno |
|---|---|
| "requisitos licencia de funcionamiento" (relevante) | 0.54 |
| "que necesito para el catastro de mi casa" (relevante) | 0.51 |
| "requisitos para viajar a la luna" (irrelevante) | 0.38 |
| "como cocinar un pastel de chocolate" (irrelevante) | 0.20 |

**Consecuencias:** un umbral muy alto puede hacer que el agente diga "no se" en casos
donde si habia informacion util pero mal fraseada (con 0.55, la primera fila de la
tabla ya caia por debajo y producia un falso negativo). 0.45 separa con margen las
consultas relevantes de las irrelevantes en esta muestra, pero es una calibracion
inicial sobre poco contenido: al ingestar el corpus real de normativa del GAMLP
(`docs/guia-demo.md`, seccion 7) hay que volver a medir y ajustar via
`RAG_SIMILARITY_THRESHOLD` en `.env` — no es un valor universal para cualquier corpus
o modelo de embeddings.

---

## ADR-007: Autenticacion admin del dashboard simplificada para el MVP de hackathon

**Contexto:** el dashboard administrativo necesita JWT con expiracion corta, pero no
hay tiempo en el alcance de la hackathon para construir gestion completa de usuarios
administrativos (altas, bajas, roles).

**Decision:** existe un unico usuario `admin` cuya "contrasena" es el valor de
`APP_SECRET_KEY` (ver `app/api/v1/dashboard.py`). Esto es deliberadamente un
placeholder de demo, marcado explicitamente en el codigo y aqui.

**Consecuencias:** **no usar este esquema en produccion.** El siguiente paso fuera del
alcance de la hackathon es una tabla `usuarios_admin` con hash bcrypt por usuario y
roles, reutilizando integramente `app/core/security.py` (que ya genera/valida JWT de
forma generica).

---

## ADR-008: Hallazgos de correr el stack contra Docker/Postgres reales

**Contexto:** el codigo se desarrollo y se probo primero con SQLite en memoria (tests)
y sin Docker disponible en el entorno de build. Al levantar el stack completo contra
Docker real (Postgres, Redis, ChromaDB) aparecieron varios problemas que las pruebas
con mocks no podian detectar. Se documentan aqui para que no se reintroduzcan.

**Decisiones:**

1. **Enums de Postgres se serializan por `.value`, no por `.name`.** SQLAlchemy, por
   defecto, persiste el `.name` del miembro del enum de Python (ej. `"EN_REVISION"`),
   pero el tipo `ENUM` de Postgres en la migracion se creo con los `.value` en
   minuscula (`"en_revision"`). Sin `values_callable=lambda e: [x.value for x in e]`
   en cada `sa.Enum(...)` de `app/db/models/`, cualquier INSERT falla con
   `invalid input value for enum`. Los 4 modelos con enums (`tramite.py`,
   `documento_validado.py`, `recordatorio.py`, `conversacion.py`) ya lo tienen.

2. **El tipo ENUM de Postgres no debe crearse manualmente antes de `op.create_table`.**
   `op.create_table` ya crea el `ENUM` como parte del DDL de la tabla; llamar tambien a
   `enum.create(bind, checkfirst=True)` antes produce `DuplicateObjectError`. La
   migracion inicial (`app/db/migrations/versions/...`) no llama a `.create()`
   manualmente por esta razon.

3. **El puerto host de Postgres en `docker-compose.yml` es `5433`, no `5432`.** Un
   Postgres local (nativo o de otro proyecto en Docker) ocupando el 5432 del host
   rompe `docker compose up` con `port is already allocated`. La comunicacion interna
   entre contenedores (api/worker -> postgres) siempre usa el puerto 5432 del
   contenedor via DNS de compose (`postgres:5432`), asi que este remapeo solo afecta
   herramientas que se conecten desde el host.

4. **La imagen del servidor de ChromaDB debe ir alineada con el SDK de Python.** El
   `pyproject.toml` fija `chromadb>=0.5.5` sin techo, por lo que pip instala la ultima
   release del cliente (1.x); ese cliente no habla el protocolo de un servidor
   `chromadb/chroma:0.5.5` (imagen vieja fijada originalmente en `docker-compose.yml`)
   y falla con `ValueError: {"detail":"Not Found"}` al inicializar `HttpClient`. Se usa
   `chromadb/chroma:latest` para mantener cliente y servidor alineados; en produccion,
   fijar un tag exacto y actualizar ambos (cliente y servidor) juntos.

5. **`docs/` se monta como volumen en el contenedor `api`, no se copia en el
   `Dockerfile`.** `app/ingestion/ingest_normativa.py` lee archivos de
   `docs/normativa/`; como el `Dockerfile` solo copia `app/`, `alembic.ini` y
   `scripts/`, correr la ingesta sin este volumen monta falla con
   `FileNotFoundError`. El volumen tambien evita tener que rebuildear la imagen cada
   vez que se agrega o reemplaza un documento de normativa.

**Consecuencias:** todos estos problemas eran invisibles en la suite de tests (usa
SQLite y mockea RagService), lo que confirma que "los tests pasan" no es sustituto de
correr el stack real al menos una vez por cambio de infraestructura. Ver
`docs/guia-demo.md` para el procedimiento verificado de arranque.
