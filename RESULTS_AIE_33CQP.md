# Resultados — AIE-33CQP (Equipo 02 · Dominio: cards)

## Sesión 7 — Runtime `react` vs `agent_framework`

### 1. Corrida con `AGENT_RUNTIME=react`

| Turno | Mensaje | Tools invocadas | Primer texto (ms) | Respuesta completa (ms) | Tokens (entrada / salida) | Observación |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| 1 | Soy CUS-1001, ¿qué tarjetas tengo y cuál es mi línea de crédito? | `get_cards`, `get_credit_line` | 16166 | 16469 | 5369 / 944 | Consultó tarjeta `CRD-2001` y línea (S/ 3,000, máx. elegible S/ 4,500). |
| 2 | Sí, solicita un aumento de línea a 4500 para esa tarjeta | `request_credit_line_increase` | 21524 | 21701 | 4439 / 1802 | No repitió consultas; acción sensible quedó pendiente de aprobación (HITL) con citas RAG. |
| 3 | ¿Cuál era la línea máxima de mi tarjeta? | Ninguna | 13317 | 13449 | 2799 / 1181 | Respondió correctamente S/ 4,500.00 desde la memoria de trabajo sin invocar tools. |
| 4 | Devuélveme la comisión FEE-4002 | *(Pendiente / opcional)* | — | — | — | — |

### 2. Corrida con `AGENT_RUNTIME=agent_framework`

| Turno | Mensaje | Tools invocadas | Primer texto (ms) | Respuesta completa (ms) | Tokens (entrada / salida) | Observación |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| 1 | Soy CUS-1001, ¿qué tarjetas tengo y cuál es mi línea de crédito? | `get_cards`, `get_credit_line` | 16449 | 16625 | 5369 / 712 | Consultó tarjeta `CRD-2001` y línea correctamente. |
| 2 | Sí, solicita un aumento de línea a 4500 para esa tarjeta | `request_credit_line_increase` | 25862 | 26003 | 4518 / 2493 | No repitió consultas; acción sensible quedó pendiente de aprobación (HITL) con cita RAG. |
| 3 | ¿Cuál era la línea máxima de mi tarjeta? | Ninguna | 19708 | 19828 | 2862 / 2011 | Clasificó como `product_question` y buscó el dato en fragmentos RAG en lugar de recuperarlo de la memoria de sesión. |
| 4 | Devuélveme la comisión FEE-4002 | Ninguna | 13209 | 13406 | 2937 / 1179 | Clasificó como `out_of_scope` y respetó el límite de la skill sin llamar tools. |

### 3. Análisis comparativo y trade-offs

* **Latencia y consumo de tokens:** En los turnos 1 a 3, `react` fue más rápido y económico en tokens de salida (especialmente en el turno 2: 21.7 s y 1,802 tokens vs. 26.0 s y 2,493 tokens en `agent_framework`; y en el turno 3: 13.4 s vs. 19.8 s).
* **Uso de memoria de trabajo:** En el turno 3, `react` recuperó correctamente el valor `S/ 4,500.00` del historial sin reconsultar tools. En cambio, `agent_framework` clasificó la pregunta como `product_question` y respondió basándose solo en los fragmentos RAG, ofreciendo reconsultar la cuenta.
* **Control de acciones sensibles y límites de skill:** Ambos runtimes aplicaron correctamente el flujo HITL (`pendiente_aprobacion`) en `request_credit_line_increase` sin repetir consultas previas, y `agent_framework` respetó el límite de dominio en el turno 4 (`out_of_scope`).
* **Decisión técnica:** Para este dominio (`cards`), el bucle propio (`react`) ofrece menor latencia, menos tokens de salida y mejor aprovechamiento del contexto conversacional, mientras que `agent_framework` aporta estandarización a costa de mayor sobrecarga en razonamiento y latencia.

## Sesión 8 — Aprobación humana, validación y reintentos

Dominio: `cards` (paso 6).

| Caso | Runtime | Mensaje | Qué pasó | Resultado o ID |
|---|---|---|---|---|
| Aprobar | `agent_framework` | `Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000?` / `Sí, solicítalo, el motivo es mayor gasto familiar` | Consultó `get_credit_line`, pidió confirmación, dejó `request_credit_line_increase` en `pendiente_aprobacion` (`NO SE EJECUTA`), y al aprobar (`s`) se ejecutó una sola vez en el MCP y el agente confirmó el registro sin tools. | `CLI-9001` (`"status": "registered"`, `action_id`: `call-441c926d`) |
| Rechazar | `react` | `Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000?` | Consultó `get_cards` y `get_credit_line`, dejó `request_credit_line_increase` en `pendiente_aprobacion`, y al rechazar (`n`) no llamó al MCP (`rejected`) y explicó al cliente que la solicitud fue rechazada y no se ejecutó. | `rejected` (`action_id`: `call_cZRIiz5OjGR8tlmoWQo54yOi`, sin ejecución) |
| Error de negocio (`CUS-9999`) | `agent_framework` | `Soy CUS-9999, ¿qué tarjetas tengo?` | `get_cards` devolvió error de negocio sin reintentos ni HTTP 502; el modelo explicó el problema al cliente y pidió confirmar el código. | `error`: `"El cliente CUS-9999 no existe"` |
| Input inválido | `agent_framework` | `Mi número de cliente es 1001, ¿qué tarjetas tengo?` | El modelo leyó el patrón `^CUS-[0-9]{4}$` del schema de `get_cards`, normalizó a `CUS-1001` y consultó la tarjeta; la red de seguridad con `jsonschema` en `_run` bloquea argumentos inválidos antes del MCP (`test_invalid_arguments_never_reach_the_mcp`). | `ok` (`CRD-2001`, Visa Clásica `4417`) |

### La trayectoria en el log

```text
INFO agent.application.chat_service: trayectoria 1c1074ab-fd4f-484a-b5e0-7f798e928978: get_cards error → get_credit_line ok → respuesta sensitive_action
INFO agent.application.chat_service: trayectoria 1c1074ab-fd4f-484a-b5e0-7f798e928978: request_credit_line_increase pending_approval → respuesta sensitive_action
INFO agent.application.chat_service: trayectoria 1c1074ab-fd4f-484a-b5e0-7f798e928978: decisión del asesor → request_credit_line_increase ok
INFO agent.application.chat_service: trayectoria 52d92f50-bcdb-41bc-9099-2dd20e2fa7c8: get_cards error → respuesta data_query
INFO agent.application.chat_service: trayectoria a2140d5c-1c81-49aa-b54e-ab9b797a6a03: get_cards ok → respuesta data_query
INFO agent.application.chat_service: trayectoria a495fb85-7a7a-4950-b14d-e42769c360c0: get_cards ok → get_credit_line ok → request_credit_line_increase pending_approval → respuesta sensitive_action
INFO agent.application.chat_service: trayectoria a495fb85-7a7a-4950-b14d-e42769c360c0: decisión del asesor → request_credit_line_increase rejected
```

### ¿Algo se ejecutó sin que lo aprobaras?

No. En ambos runtimes (`agent_framework` y `react`), `request_credit_line_increase` quedó detenida en `pending_approval` (`pendiente_aprobacion`) en `_run` sin invocar al MCP. Con `agent_framework` solo se ejecutó cuando se envió la aprobación a `POST /chat/actions`, y con `react` al rechazar no hubo llamada al MCP.

### Conclusión

El control humano (HITL), la validación de argumentos por JSON Schema y el manejo de errores/reintentos viven en `ChatService` (`_run`, `_call` y `resolve`), por lo que funcionan de forma idéntica con `agent_framework` y `react`. Una acción sensible nunca se reintenta al aprobarse para evitar duplicados, los fallos transitorios de consulta se reintentan una vez sin tumbar el turno con 502, y la línea `trayectoria` deja trazabilidad clara de cada turno en el log.

## Sesión 9 — Despliegue en Azure

Equipo: `team-02`. Dominio: `cards`.

| Comprobación | Resultado |
|---|---|
| Tests en el contenedor (paso 3) | `139 passed, 5 skipped in 9.02s` (`agent:test`) |
| Acción aprobada después de reiniciar `uvicorn` (paso 2, Cosmos DB) | `CLI-9001` (`status: "registered"`, sesión `a543105a-c802-40ed-b283-cf0d1f10b95f`, `action_id`: `call-b74d61e9`; `Cosmos doc`: `messages: 8`, `pending: None`) |
| Imagen desplegada (`team-NN/agent:<sha>`) | `team-02/agent:1bf5cd2d959c54a1d6d87b785a140d9c954bf1c7` |
| Revisión activa y duración del job `deploy` | `ca-agent-chat-02--0000002` (`RunningAtMaxScale`; confirmar duración exacta en GitHub Actions) |
| `/health` del agente desplegado | `Agente en ca-agent-chat-02: ok` (HTTP 401 sin token Entra ID; `ok` con token de `az login`) |
| Respuesta con `Fuentes:` contra Azure (y su tiempo en ms) | `7873 ms` (primer texto en `7742 ms`, `1413` in / `625` out); fuentes: `[1] credit-line-increase.md · Aumento de línea de crédito > Requisitos`, `[2] credit-line-increase.md · Aumento de línea de crédito > Cómo se solicita` |
| Acción aprobada contra Azure, con su `resultado:` | `CLI-9001` (`"status": "registered"`, `action_id`: `call-4fe1c4f1`, `request_credit_line_increase(card_id=CRD-2001, requested_limit=4000)`) |

### Comprobación imagen runtime local (paso 4)

- `agent:local` (`DOMAIN=cards`) arrancó con `FOUNDRY_AUTH_PROVIDER=entra_id` (copiando `AZURE_OPENAI_ENDPOINT` a `FOUNDRY_ENDPOINT`) y se detuvo en el fail-fast esperado: `RuntimeError: KNOWLEDGE_BASE=azure_search requiere SEARCH_ENDPOINT y SEARCH_INDEX en .env.`

### Qué pone Azure y qué pone la imagen

- **La imagen (`Dockerfile`):** `DOMAIN`, `FOUNDRY_AUTH_PROVIDER=entra_id`, `KNOWLEDGE_BASE=azure_search`, `AGENT_RUNTIME=agent_framework`.
- **Azure (Container App `ca-agent-chat-02`):** `APPLICATIONINSIGHTS_CONNECTION_STRING`, `AZURE_CLIENT_ID`, `AZURE_OPENAI_ENDPOINT`, `COSMOS_CONTAINER`, `COSMOS_DATABASE`, `COSMOS_ENDPOINT`, `FOUNDRY_PROJECT_ENDPOINT`, `KEY_VAULT_URI`, `MCP_SCOPE`, `MCP_URL`, `SEARCH_ENDPOINT`, `SEARCH_INDEX`, `TEAM_ID`.

### Problemas que encontraste y cómo los resolviste

- El primer intento del job `deploy` falló en `azure/login@v2` con `AADSTS700213` (*No matching federated identity record*) por discrepancia en el *subject claim* de OIDC; plataforma actualizó la credencial federada del repo y el re-run completó el despliegue.
- `az containerapp auth show` devolvió `{}` por permisos sobre `authConfigs`, por lo que se consultó el `appId` de `app-workshop-agent-chat` en Entra ID para armar `AGENT_SCOPE` y autenticar `/health`, `/chat/stream` y `/chat/actions`.

### Conclusión

El agente del equipo (`team-02`, dominio `cards`) quedó desplegado en Azure Container Apps (`ca-agent-chat-02--0000002`) usando identidad administrada (`id-team-02`) sin secretos en el repositorio ni API keys. Tanto la consulta RAG sobre `idx-team-02` como el flujo HITL con `request_credit_line_increase` en el MCP compartido y la persistencia en Cosmos DB (`workshop/team-02`) funcionaron de extremo a extremo.
