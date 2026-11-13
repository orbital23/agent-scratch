# Resultados AIE-31SC

## Sesión 5 — Comparar los dos jueces

Mismo golden set (31 casos), mismo agente (`gpt-5-mini`), dos jueces.

- Juez local (G-Eval): `data/eval/cards-20261113-101356.json`
- Juez azure_evaluation (decision-1): `data/eval/cards-20261113-100526.json`

| Métrica | G-Eval (`JUDGE=local`) | decision-1 (`azure_evaluation`) |
|---|---|---|
| Apoyo (1–5) | 5.00 | 4.99 |
| Relevancia (1–5) | 5.00 | 4.95 |
| Cita correcta (0–1) | 1.00 | 0.999 |
| Tokens (entrada / salida) | 30 891 / 12 720 | 30 886 / 13 500 |
| Tiempo de la corrida | 6 min 14 s | _(anotar)_ |

### ¿Las notas de apoyo y de cita correcta van en la misma dirección?

Sí. G-Eval puso 5/5/1.0 en todos los casos juzgados. decision-1 puso prácticamente lo mismo, con
probabilidades un poco por debajo del tope (por ejemplo 4.88 de apoyo en `cards-20` y 4.95 en `cards-30`).
Ningún caso queda en direcciones opuestas.

### ¿Cuánto tardó cada corrida?

- Local (G-Eval): 6 min 14 s. Es lento porque los casos se recorren en serie (agente y juez, una llamada
  tras otra) y el juez es un modelo de razonamiento (`gpt-5-mini`) que genera `reasoning` antes de las notas.
  Cada llamada del juez tardó unos 4 s.
- azure_evaluation (decision-1): _(anotar)_.

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
