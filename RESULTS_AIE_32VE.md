# Resultados AIE-32VE

## Sesión 5 — Comparar los dos jueces

Mismo golden set (31 casos), mismo agente (`gpt-5-mini`), dos jueces.

- Juez local (G-Eval): 
- Juez azure_evaluation (decision-1):

| Métrica | G-Eval (`JUDGE=local`) | decision-1 (`azure_evaluation`) |
|---|---|---|
| Apoyo (1–5) | 5.00 | 5.00 |
| Relevancia (1–5) | 5.00 | 4.9 |
| Cita correcta (0–1) | 1.00 | 1.00 |
| Tokens (entrada / salida) | 29 781 / 12 573 | 30 655 / 13 290 |
| Tiempo de la corrida | 6 min 36 s | 5 min 40 s |

### ¿Las notas de apoyo y de cita correcta van en la misma dirección?

Sí. G-Eval puso 5/5/1.0 en todos los casos juzgados. decision-1 puso prácticamente lo mismo, con
probabilidades un poco por debajo del tope. Ningún caso queda en direcciones opuestas.

### ¿Cuánto tardó cada corrida?

- Local (G-Eval): 6 min 36 s. 
- azure_evaluation (decision-1): 5 min 40 s.

### Casos donde no coinciden

No hay casos con desacuerdo real entre los jueces: las diferencias son de centésimas, así que no hay un `reasoning` de G-Eval que explique una divergencia.

### Diferencias de la corrida local que no vienen del juez

El agente respondió distinto entre corridas (el modelo no es determinista):

- `cards-11`: la intención salió como `sensitive_action` en vez de `product_question`, así que bajó
  `intent_accuracy` a 0.97.
- `cards-25` (ruido): el agente respondió con un comunicado interno y citó `internal-notice-anniversary.html`,
  una fuente prohibida (`forbidden_citations` = 1, `sources_ok` = 0.97).

### Conclusión

decision-1 no explica, pero es rápido y da probabilidades: sirve para frenar un despliegue (sesión 11).
G-Eval es más lento pero deja el `reasoning`, que sirve para entender por qué falló un caso.


## Sesión 6 — Tools del MCP en el chat

Dominio: `cards`. MCP: el mock (`http://127.0.0.1:8200/mcp`) y, si ya tienes `MCP_URL`, el compartido (`bank-mcp`).

### Tools de tu dominio

| MCP | Tools que lista `dev/mcp/mcp_tools.py` |
|---|---|
| Mock | get_cards, get_credit_line, request_credit_line_increase |
| Compartido | get_cards, get_credit_line, request_credit_line_increase |

### Conversación en `dev/chat.py` (paso 12)

| Prueba | Mensaje | Tool pedida (`→`) | Qué pasó | Primer texto / respuesta completa (ms) |
|---|---|---|---|---|
| Consulta de tu dominio | Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000? | request_credit_line_increase | Pidio una aprobacion y tambien respondio a la pregunta | 32034/32341 |
| Acción confirmada | Soy CUS-1001, ¿cuales son mis tarjetas? | get_cards | Encontro 1 tarjeta, Visa Clásica (CRD-2001), últimos 4 dígitos 4417 | 14273/14468 |
| Sin tool que la resuelva | ¿Quiero obtener la tarjeta clasica que requisito tengo? | product_question | Respondio que para la Tarjeta Clásica: ser persona de 21 a 75 años,  ingreso mínimo mensual desde S/ 1 200 | 13201/13341 |
| Tool de otro dominio | Soy CUS-1001, me cobraron dos veces en el supermercado | No puedo tramitar reclamos ni ver movimientos desde aquí | out_of_scope | 25282/25554 |

### ¿El modelo inventó algún dato cuando ninguna tool lo resolvía?

No invento ningun dato, toda la informacion me lo trajo de los documentos.

### Conclusión

Se comprobó que con un servidor MCP compartido te permite consumir las distintas herramientas para cada domino que se tiene asignado.


## Sesión 7 — Skills, memoria de trabajo y Agent Framework

Dominio: `cards`. La misma conversación con los dos runtimes (paso 7).

| | `react` | `agent_framework` |
|---|---|---|
| Tools pedidas en la consulta | get_cards, get_credit_line | get_cards, get_credit_line |
| La acción sensible quedó **NO SE EJECUTA** | SI | SI |
| Pregunta de memoria respondida sin `→` | ¿Cuál era la línea máxima de mi tarjeta? | ¿Cuál era la línea máxima de mi tarjeta? |
| Primer texto (ms) | 20052 | 26324 |
| Respuesta completa (ms) | 20350 | 26588 |
| Tokens (entrada / salida) | 5284/1699 | 3433/2333 |

### ¿La skill frenó la tool de otro dominio?

Mensaje:¿Qué movimientos estaban duplicados?. Respuesta: Agente [out_of_scope]: Eso está fuera de mi alcance: no puedo ver ni investigar movimientos...

### Diferencias entre los dos runtimes

React es mucho mas rapido que Agent-framework, ya que react es un custom a diferencia de agent-framework.

### Conclusión

El agent_framework tiene menos consumo de tokens segun lo explorado en las pruebas realizadas

## Sesión 8 — Aprobación humana, validación y reintentos

Dominio: `cards` (paso 6).

| Caso | Runtime | Mensaje | Qué pasó | Resultado o ID |
|---|---|---|---|---|
| Aprobar | `agent_framework` | Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000? | Me mostro la informacion de mi tarjeta, luego le mande la solicitud con el motivo y al final lo aprobé | La solicitud de aumento a S/4,000 para la tarjeta terminada en 2001 fue registrada (ID CLI-9001) para que el banco la procese; no se aplicó la nueva línea. |
| Rechazar | `react` | Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000? | Me mostro la informacion de mi tarjeta, luego le mande la solicitud con el motivo y al final lo rechaze | Su solicitud de aumento a S/4000 fue rechazada por el asesor; la acción no se ejecutó. |
| Error de negocio (`CUS-9999`) | `react` | Soy CUS-9999, ¿qué comisiones me cobraron? | Respondio que el cliente CUS-9999 no existe | No encuentro el código de cliente CUS-9999 en nuestro sistema. |
| Input inválido | `agent_framework` | Mi número de cliente es ABCD, ¿qué comisiones me cobraron? | No se ejecuto la tool de solo ejecuto un data_query | El código de cliente que enviaste (ACBD) no es válido. |

### La trayectoria en el log

- trayectoria 4cbab062-612d-40df-bb14-578b4420ea07: get_cards error → respuesta sensitive_action |
- trayectoria 4cbab062-612d-40df-bb14-578b4420ea07: get_credit_line ok → request_credit_line_increase pending_approval → respuesta sensitive_action
- trayectoria 4cbab062-612d-40df-bb14-578b4420ea07: decisión del asesor → request_credit_line_increase ok
- trayectoria 8e4f6a79-1766-4c9b-b640-9af481a81152: get_cards ok → get_credit_line ok → respuesta sensitive_action
- trayectoria 8e4f6a79-1766-4c9b-b640-9af481a81152: request_credit_line_increase pending_approval → respuesta sensitive_action
- trayectoria 8e4f6a79-1766-4c9b-b640-9af481a81152: decisión del asesor → request_credit_line_increase rejected
- trayectoria 732862ae-d791-4bac-a07e-c4e56c4452a4: get_cards error → respuesta data_query
- trayectoria ac68dd32-00be-4e56-b7e1-5abfa8f17ce5: sin tools → respuesta data_query

### ¿Algo se ejecutó sin que lo aprobaras?

No, esperaba que el asesor aprobara la solicitud.

### Conclusión

Funciono correctamente con agent_framework y react, funciono de acuerdo a lo planteado en el laboratorio

## Sesión 9 — Despliegue en Azure

Equipo: `team-02`. Dominio: `cards`.

| Comprobación | Resultado |
|---|---|
| Tests en el contenedor (paso 3) | 144 passed in 22.89s |
| Acción aprobada después de reiniciar `uvicorn` (paso 2, Cosmos DB) | {"id": "CLI-9001", "card_id": "CRD-2001", "requested_limit": 4000.0, "status": "registered"} |
| Imagen desplegada (`team-02/agent:<sha>`) | team-02/agent:1bf5cd2d959c54a1d6d87b785a140d9c954bf1c7 |
| Revisión activa y duración del job `deploy` | revision: ca-agent-chat-02--0000002, duración: 2m 35s2.21 min |
| `/health` del agente desplegado | Agente: https://ca-agent-chat-02.icybush-2ea2dfc1.eastus2.azurecontainerapps.io |
| Respuesta con `Fuentes:` contra Azure (y su tiempo en ms) | Fuentes: [1] credit-line-increase.md · Aumento de línea de crédito > Requisitos.  [2] credit-line-increase.md · Aumento de línea de crédito > Cómo se solicita (primer texto en 33000 ms. respuesta completa en 34359 ms, 2930 tokens de entrada, 1696 de salida) |
| Acción aprobada contra Azure, con su `resultado:` | Asesor: ¿apruebas request_credit_line_increase(card_id=CRD-2001, requested_limit=4000)? [s/n]: s. Agente [sensitive_action]: La solicitud de aumento a S/4,000 para la tarjeta terminada en 2001 quedó registrada para que el banco la procese; no se aplicó todavía. |

### Qué pone Azure y qué pone la imagen

- Azure (ca-agent-chat-02): AZURE_OPENAI_ENDPOINT, FOUNDRY_PROJECT_ENDPOINT, AZURE_CLIENT_ID, TEAM_ID, MCP_SCOPE, KEY_VAULT_URI APPLICATIONINSIGHTS_CONNECTION_STRING, COSMOS_ENDPOINT, COSMOS_DATABASE, COSMOS_CONTAINER, SEARCH_ENDPOINT, SEARCH_INDEX, MCP_URL.
- La imagen (ENV del Dokerfile): DOMAIN, FOUNDRY_AUTH_PROVIDER=entra_id, KNOWLEDGE_BASE=azure_search, AGENT_RUNTIME=agent_framework, PATH y PYTHONUNBUFFERED.

### Problemas que encontraste y cómo los resolviste

No puede ejecutar 'git fetch upstream', me ayude con el capitan, luego subio sus cambios y con los que pude trabajar.
El problema recurrente en el que la api falla en los primeros intentos porque no recien se esta levantando la app.

### Conclusión

Se llego a desplegar en Azure Container Apps (ca-agent-chat-02--0000002) se llego a desplegar sin secretos en el repositorio ni API keys, se llego a realizar las pruebas respectivas al agente, preguntas y respuestas ademas con actuar del asesor.