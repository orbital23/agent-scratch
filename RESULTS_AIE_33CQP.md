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
