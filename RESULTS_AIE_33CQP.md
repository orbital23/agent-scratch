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
