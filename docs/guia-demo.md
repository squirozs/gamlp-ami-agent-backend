# Guia de demo / MVP

Esta guia describe como levantar AMI Copiloto de punta a punta para una demo
convincente **sin** depender de credenciales reales de e-SITRAM/iGOB (que llegaran
mas adelante) ni, si se quiere, de un numero de WhatsApp real de Twilio.

## 1. Que es indispensable y que es opcional

| Componente | Estado para la demo | Que hacer |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Indispensable** | No hay modo mock para el LLM/vision: sin esta key el agente no responde ni valida documentos. Conseguir una key en https://console.anthropic.com/ |
| `ESITRAM_MODE` / `IGOB_MODE` | Ya en `mock` por defecto | No requiere accion. Los mocks generan codigos de tramite y estados deterministicos (`app/integrations/esitram_mock.py`, `igob_mock.py`) |
| Docker Desktop (o Docker Engine + Compose) | **Indispensable** para el flujo con un solo comando | Instalar si no esta disponible. Levanta Postgres, Redis, ChromaDB, la API y el worker |
| `TWILIO_*` | **Opcional para la demo** | Si no tienes un sandbox de WhatsApp de Twilio a mano, se puede demostrar todo el flujo pegandole directo a la API REST (seccion 4) sin pasar por WhatsApp. Si quieres el flujo real por WhatsApp, usa el sandbox gratuito de Twilio (`https://www.twilio.com/docs/whatsapp/sandbox`) y pon `TWILIO_WEBHOOK_VALIDATE=false` solo en ese entorno de pruebas si necesitas simular peticiones sin firma valida |
| `JWT_SECRET_KEY`, `APP_SECRET_KEY` | Indispensable (cualquier valor) | Genera algo random, ej. `openssl rand -hex 32`. El usuario admin del dashboard usa `APP_SECRET_KEY` como contrasena (ver ADR-007 en `decisiones-tecnicas.md`) |

## 2. Levantar el stack

```bash
cp .env.example .env
# Edita .env y completa como minimo:
#   ANTHROPIC_API_KEY=sk-ant-...
#   APP_SECRET_KEY=<valor random>
#   JWT_SECRET_KEY=<valor random>
# Deja ESITRAM_MODE=mock e IGOB_MODE=mock (default) para la demo.

./scripts/demo_reset.sh
```

`demo_reset.sh` hace, en orden: baja contenedores previos, reconstruye imagenes,
levanta Postgres/Redis/ChromaDB, aplica las migraciones de Alembic, siembra datos
ficticios (`scripts/seed_data.py`: un ciudadano, un tramite en curso, un
recordatorio pendiente) e **ingesta un documento de normativa de ejemplo al RAG**
(`docs/normativa/ejemplo_licencia_funcionamiento.txt`) para que
`buscar_normativa` tenga contexto real que citar desde el primer momento. Al
terminar, la API queda arriba en `http://localhost:8000/api/v1/health`.

Documentacion interactiva de la API: `http://localhost:8000/docs`.

## 3. Verificar que todo esta arriba

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","service":"ami-copiloto-backend"}
```

## 4. Flujo demostrativo sin WhatsApp (recomendado si no hay sandbox de Twilio a mano)

El webhook de WhatsApp exige firma valida de Twilio por seguridad (ver ADR y
`app/core/security.py`), asi que para una demo rapida sin Twilio configurado, el
camino mas simple es mostrar cada capacidad directamente contra la API REST — el
orquestador y las tools son los mismos que usaria el flujo de WhatsApp, solo cambia
el canal de entrada.

**a) Busqueda de normativa (RAG, con fuente citada):**
```bash
curl "http://localhost:8000/api/v1/normativa/buscar?consulta=requisitos+licencia+de+funcionamiento"
```
Devuelve el fragmento ingestado en el paso 2, con `fuente.titulo` y
`fuente.fecha_vigencia` — asi se demuestra la regla de "nunca inventar" (compara
con una consulta fuera de tema, ver seccion 5).

**b) Iniciar un tramite (contra e-SITRAM en modo mock):**
```bash
curl -X POST http://localhost:8000/api/v1/tramites \
  -H "Content-Type: application/json" \
  -d '{"ciudadano_id":"<uuid-del-seed>","tipo_tramite":"licencia_funcionamiento","sistema_origen":"esitram","metadata_tramite":{}}'
```
El `ciudadano_id` del ciudadano sembrado lo puedes obtener conectandote a Postgres
(`docker compose exec postgres psql -U ami -d ami_copiloto -c "select id, telefono_whatsapp from ciudadanos;"`)
o revisando el log de `scripts/seed_data.py` al correr `demo_reset.sh`.

**c) Validar un documento por foto (vision):**
```bash
curl -X POST http://localhost:8000/api/v1/documentos/validar \
  -F "tramite_id=<uuid-del-tramite>" \
  -F "tipo_documento=cedula_identidad" \
  -F "archivo=@/ruta/a/una/foto.jpg"
```
Muestra el resultado (`aprobado`/`observado`/`rechazado`) sin persistir la imagen
(ver ADR-002).

**d) Dashboard administrativo (resumen agregado):**
```bash
curl -X POST http://localhost:8000/api/v1/dashboard/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<valor de APP_SECRET_KEY>"}'
# copiar el access_token de la respuesta
curl http://localhost:8000/api/v1/dashboard/resumen \
  -H "Authorization: Bearer <access_token>"
```

## 5. Demostrar el comportamiento anti-alucinacion

```bash
curl "http://localhost:8000/api/v1/normativa/buscar?consulta=requisitos+para+viajar+a+la+luna"
```
Debe devolver `"encontrado": false` y `fragmentos: []` — es el mismo contrato que
verifica `tests/unit/test_rag_anti_hallucination.py`. Es el punto mas fuerte de la
demo para explicar por que el agente no inventa requisitos.

## 6. Flujo completo por WhatsApp (si hay sandbox de Twilio disponible)

1. Configura un sandbox en https://www.twilio.com/docs/whatsapp/sandbox y copia
   `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_NUMBER` a `.env`.
2. Expone `http://localhost:8000` a internet (ej. `ngrok http 8000`) y configura esa
   URL + `/api/v1/webhooks/whatsapp` como webhook entrante en la consola de Twilio.
3. Escribe al numero del sandbox desde tu WhatsApp. El mensaje llega firmado por
   Twilio, se verifica la firma (`app/core/security.py::verify_twilio_signature`) y
   el orquestador responde usando las mismas tools que en el flujo REST.

## 7. Ingestar normativa real del GAMLP (para ir mas alla del ejemplo de demo)

El indice publico https://lapaz.bo/tramites-y-servicios-gamlp/ confirma las
categorias de tramite reales (licencia de funcionamiento, catastro, RUAT, patentes,
permisos, etc.) pero es un indice de navegacion, no el texto legal en si — no
expone directamente PDFs de ordenanzas por tramite. Para reemplazar el contenido de
ejemplo por normativa oficial:

1. Navega desde esa pagina hasta el tramite especifico que quieras cubrir y ubica el
   enlace a "Normativa" o al reglamento/ordenanza aplicable (usualmente un PDF).
2. Descarga ese PDF localmente.
3. Ingierelo con el numero de norma y fecha de vigencia reales que indique el
   documento:
   ```bash
   docker compose run --rm api python -m app.ingestion.ingest_normativa \
     --archivo /ruta/al/pdf/descargado.pdf \
     --titulo "Titulo exacto de la norma" \
     --numero-norma "OM XXX/AAAA" \
     --fecha-vigencia AAAA-MM-DD \
     --url https://lapaz.bo/... (URL de la fuente)
   ```
4. Repite por cada tramite que quieras que el agente pueda responder con fuente
   verificable. Mientras no se ingeste una norma, `buscar_normativa` seguira
   devolviendo `encontrado: false` para ese tema — es el comportamiento esperado, no
   un bug (ver seccion 5).

**Importante:** no se debe alimentar al RAG con texto redactado por el LLM o
parafraseado sin verificar contra la fuente oficial; eso reintroduciria el riesgo de
alucinacion que el ADR-006 busca evitar. Solo texto extraido literalmente de un PDF
o pagina oficial del GAMLP.

## 8. Conectar e-SITRAM / iGOB reales cuando esten disponibles

Sin tocar codigo de negocio: en `.env`, cambiar `ESITRAM_MODE=real` (o `IGOB_MODE=real`)
y completar `ESITRAM_API_URL` / `ESITRAM_API_KEY` (o los equivalentes de iGOB). Ver
`app/integrations/factory.py` y ADR-001 en `docs/decisiones-tecnicas.md`.
