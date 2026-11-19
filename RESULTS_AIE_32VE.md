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
probabilidades un poco por debajo del tope (por ejemplo 4.88 de apoyo en `cards-20` y 4.95 en `cards-30`).
Ningún caso queda en direcciones opuestas.

### ¿Cuánto tardó cada corrida?

- Local (G-Eval): 6 min 36 s. Es lento porque los casos se recorren en serie (agente y juez, una llamada
  tras otra) y el juez es un modelo de razonamiento (`gpt-5-mini`) que genera `reasoning` antes de las notas.
  Cada llamada del juez tardó unos 4 s.
- azure_evaluation (decision-1): 3 s.

### Casos donde no coinciden

No hay casos con desacuerdo real entre los jueces: las diferencias son de centésimas, así que no hay un `reasoning` de G-Eval que explique una divergencia. Los dos casos con apoyo más bajo en decision-1
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
| Consulta de tu dominio | Soy CUS-1001, ¿puedo subir la línea de mi tarjeta CRD-2001 a 4000? | request_credit_line_increase | Pidio una aprobacion y tambien respondio a la pregunta | 32034/32341 |
| Acción confirmada | Soy CUS-1001, ¿cuales son mis tarjetas? | get_cards | Encontro 1 tarjeta, Visa Clásica (CRD-2001), últimos 4 dígitos 4417 | 14273/14468 |
| Sin tool que la resuelva | ¿Quiero obtener la tarjeta clasica que requisito tengo? | product_question | Respondio que para la Tarjeta Clásica: ser persona de 21 a 75 años,  ingreso mínimo mensual desde S/ 1 200 | 13201/13341 |
| Tool de otro dominio | Soy CUS-1001, me cobraron dos veces en el supermercado | No puedo tramitar reclamos ni ver movimientos desde aquí | out_of_scope | 25282/25554 |

### ¿El modelo inventó algún dato cuando ninguna tool lo resolvía?

No invento ningun dato.

### Conclusión

Se comprobó que con un servidor MCP compartido te permite consumir las distintas herramientas para cada domino que se tiene asignado.


## Sesión 7 — Skills, memoria de trabajo y Agent Framework

Dominio: `cards`. La misma conversación con los dos runtimes (paso 7).

| | `react` | `agent_framework` |
|---|---|---|
| Tools pedidas en la consulta | get_cards, get_credit_line | get_cards, get_credit_line |
| La acción sensible quedó **NO SE EJECUTA** | - | - |
| Pregunta de memoria respondida sin `→` | ¿Cuál era la línea máxima de mi tarjeta? | ¿Cuál era la línea máxima de mi tarjeta? |
| Primer texto (ms) | 20052 | 26324 |
| Respuesta completa (ms) | 20350 | 26588 |
| Tokens (entrada / salida) | 5284/1699 | 3433/2333 |

### ¿La skill frenó la tool de otro dominio?

Mensaje:¿Qué movimientos estaban duplicados?. Respuesta: Agente [out_of_scope]: Eso está fuera de mi alcance: no puedo ver ni investigar movimientos...

### Diferencias entre los dos runtimes

Agent-framework demora mucho mas que la react

### Conclusión

El agent_framework tiene menos consumo de tokens