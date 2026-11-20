
## Sesión 5 — Comparar los dos jueces

Mismo golden set (31 casos), mismo agente (`gpt-5-mini`), dos jueces.

- Juez local (G-Eval): 
- Juez azure_evaluation (decision-1):

| Métrica | G-Eval (`JUDGE=local`) | decision-1 (`azure_evaluation`) |
|---|---|---|
| Apoyo (1–5) | 5.00 | 4.99 |
| Relevancia (1–5) | 5.00 | 4.95 |
| Cita correcta (0–1) | 1.00 | 0.999 |
| Tokens (entrada / salida) | 30 891 / 12 720 | 30 886 / 13 500 |
| Tiempo de la corrida | 6 min 14 s | 5 min 19 s |

### ¿Las notas de apoyo y de cita correcta van en la misma dirección?

Sí. G-Eval puso 5/5/1.0 en todos los casos juzgados. decision-1 puso prácticamente lo mismo, con
probabilidades un poco por debajo del tope (por ejemplo 4.88 de apoyo en `cards-20` y 4.95 en `cards-30`).
Ningún caso queda en direcciones opuestas.

### ¿Cuánto tardó cada corrida?

- Local (G-Eval): 6 min 14 s. Es lento porque los casos se recorren en serie (agente y juez, una llamada
  tras otra) y el juez es un modelo de razonamiento (`gpt-5-mini`) que genera `reasoning` antes de las notas.
  Cada llamada del juez tardó unos 4 s.
- azure_evaluation (decision-1): 3 s.

### Casos donde no coinciden

No hay casos con desacuerdo real entre los jueces: las diferencias son de centésimas, así que no hay un
`reasoning` de G-Eval que explique una divergencia. Los dos casos con apoyo más bajo en decision-1
(`cards-20` 4.88, `cards-30` 4.95) G-Eval los calificó con 5.

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
| Consulta de tu dominio | Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000? | Soy CUS-1001, ¿cuales son mis tarjetas? | request_credit_line_increase | Pidio una aprobacion y tambien respondio a la pregunta | 32034/32341
| Acción confirmada | Soy CUS-1001, ¿cuales son mis tarjetas? | get_cards | Encontro 1 tarjeta, Visa Clásica (CRD-2001), últimos 4 dígitos 4417 | 14273/14468 |
| Sin tool que la resuelva | ¿Quiero obtener la tarjeta clasica que requisito tengo? |product_question | Respondio que para la Tarjeta Clásica: ser persona de 21 a 75 años, ingreso mínimo mensual desde S/ 1 200 | 13201/13341 |
| Tool de otro dominio | Soy CUS-1001, me cobraron dos veces en el supermercado | No puedo tramitar reclamos ni ver movimientos desde aquí | out_of_scope | 25282/25554 |

### ¿El modelo inventó algún dato cuando ninguna tool lo resolvía?

No invento ningun dato.

### Conclusión

Se comprobó que con un servidor MCP compartido te permite consumir las distintas herramientas para cada domino que se tiene asignado.



## Sesión 7 — Skills, memoria de trabajo y Agent Framework

Dominio: `cards`. La misma conversación con los dos runtimes (paso 7).

| | `react` | `agent_framework` |
|---|---|---|
| Tools pedidas en la consulta | 3 | 3 |
| La acción sensible quedó **NO SE EJECUTA** | SI | SI  |
| Pregunta de memoria respondida sin `→` | ¿Cuál era la línea máxima de mi tarjeta? | ¿Cuál era la línea máxima de mi tarjeta? |
| Primer texto (ms) | 12197 ms | 23382 ms |
| Respuesta completa (ms) | 12443 ms | 23719 ms |
| Tokens (entrada / salida) | 1728/655 | 1891/2052 |

### ¿La skill frenó la tool de otro dominio?

Mensaje: "Bloquea mi tarjeta CRD-2001" (el bloqueo es una tool de cards) Respuesta: con los dos runtimes el agente no pidió ninguna tool y dijo que no puede bloquear tarjetas desde este canal; derivó al bloqueo en la app (24 horas) o al (01) 555-0200. El modelo no tiene esa tool: el MCP compartido filtra por dominio y la skill de support solo deja pasar find_branches, get_request_status y update_contact_details.

### Diferencias entre los dos runtimes

El agent_framework demora mas vs react
### Conclusión

El agent_framework tiene mas consumo de tokens



## Sesión 8 — Aprobación humana, validación y reintentos

Dominio: `cards` (paso 6).

| Caso | Runtime | Mensaje | Qué pasó | Resultado o ID |
|---|---|---|---|---|
| Aprobar | `agent_framework` | Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000? | Me mostro informacion de mi tarjeta, luego se mando la solicitud con el motivo y se aprobo | La solicitud de aumento a S/4000 para la tarjeta CRD-2001 fue registrada (ID CLI-9001) para que el banco lo procese; no se aplico el aumento.
| Rechazar | `react` | Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000? | Me mostro informacion de mi tarjeta, luego se mando la solicitud con el motivo y se rechazo | Su solicitud de aumento a S/4000 fue rechazada por el asesor; la accion no se ejecuto |
| Error de negocio (`CUS-9999`) | `react` | Soy CUS-9999, ¿que comisiones me cobraron? | _Respondio que el cliente CUS-9999 no existe | No se encuentra el codigo de cliente CUS-9999 en el sistema |
| Input inválido | `agent_framework` | Mi numero de cliente es ABCD, ¿que comisiones me cobraron? | El modelo no llamó a la tool: leyó el patrón ^CUS-\d{4}$ y pidió confirmar "¿Su código de cliente es ABCD?" | Sin →; no salió nada al MCP

### La trayectoria en el log

trayectoria 83c9d031-0d7a-4c8d-ae25-457cd6c04aff: get_cards error → respuesta sensitive_action

trayectoria 83c9d031-0d7a-4c8d-ae25-457cd6c04aff: get_credit_line ok → request_credit_line_increase pending_approval → respuesta sensitive_action

trayectoria 83c9d031-0d7a-4c8d-ae25-457cd6c04aff: decision del asesor → request_credit_line_increase ok

trayectoria 9051b7b9-b20e-4f6d-9551-21364da2f700: get_cards ok → get_credit_line ok → respuesta sensitive_action

trayectoria 9051b7b9-b20e-4f6d-9551-21364da2f700: request_credit_line_increase pending_approval → respuesta sensitive

trayectoria 9051b7b9-b20e-4f6d-9551-21364da2f700: get_cards ok → get_credit_line ok → request_credit_line_increase pending_approval → respuesta sensitive_action

trayectoria 9051b7b9-b20e-4f6d-9551-3rtruftr7500: get_cards error → respuesta data_query

trayectoria 83c9d031-0d7a-4c8d-ae25-3rtruftr400: get_cards ok → respuesta data_query

### ¿Algo se ejecutó sin que lo aprobaras?

No. Con los dos runtimes, get_credit_line siempre apareció primero como NO SE EJECUTA, pendiente de aprobación, y su resultado del MCP salió solo después. Cuando no llego al MCP: quedó rejected en la trayectoria y en la memoria.

### Conclusión

La aprobación humana vive en _run y resolve, no en el framework: funcionó igual con agent_framework y react, se tomo el action_id de cada uno, y esto sirvió para decidir por POST /chat/actions. Después de aprobar, el modelo contó solo lo que dijo el resultado ("quedó para que el banco la procese; no está aplicada aún"), luego el asesor reviso cada caso para aprobar o rechazar segun corresponda.