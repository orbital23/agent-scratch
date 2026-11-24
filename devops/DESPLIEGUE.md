# Despliegue en Azure (CI/CD)

Cada equipo despliega su agente desde su fork con GitHub Actions (`.github/workflows/deploy-agent.yaml`). El workflow no usa
secretos: GitHub le da un token OIDC y Azure solo lo acepta si viene de **este repo y de la rama `main`**.

| Evento | Qué corre |
|---|---|
| Pull request, push a `main` o `solution`, tags `t*-v*` | tests en contenedor (stage `test`) |
| Push a `main` (el merge de un PR) | tests, imagen `runtime`, comprobación de arranque (`/health` hasta la sesión 3; desde la 4, que llegue a pedir AI Search), publicación en el ACR (`team-NN/agent:<sha>`) y actualización de la Container App `ca-agent-chat-NN` (solo cambia la imagen) |

Cada integrante trabaja en su rama y abre un pull request; el líder hace el merge. Solo `main` despliega: una rama de trabajo no
obtiene el token de Azure aunque modifique el workflow.

## Configuración (una vez, la hace el líder del equipo)

1. En el fork: **Actions → habilitar workflows** (en un fork vienen desactivados).
2. **Settings → Secrets and variables → Actions → Variables**: las 6 variables que entrega el instructor para tu equipo
   (`ci_handoff`) más `DOMAIN`. Son variables, no secretos.

| Variable | Valor |
|---|---|
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | identidad de CI de tu equipo y su suscripción |
| `ACR_LOGIN_SERVER` | registro de imágenes (`<nombre>.azurecr.io`) |
| `RESOURCE_GROUP` | `rg-team-NN` |
| `CONTAINER_APP` | `ca-agent-chat-NN` (de aquí sale el número de equipo y el repositorio `team-NN/agent`) |
| `DOMAIN` | dominio de tu equipo (tabla de abajo) |

Sin `ACR_LOGIN_SERVER` el workflow solo corre los tests, así que el fork funciona antes de configurar Azure. Si falta o es inválida
otra variable, el despliegue se detiene al inicio con un mensaje que dice cuál.

| `DOMAIN` | Dominio del temario | Equipos |
|---|---|---|
| `fees` | tarifario-comisiones | 01 y 06 |
| `cards` | tarjeta-credito | 02 y 07 |
| `fraud` | fraude-bloqueo-reclamos | 03 y 08 |
| `loans` | prestamos | 04 y 09 |
| `support` | atencion-faq | 05 y 10 |

## Qué pone Azure y qué pone la imagen

El workflow **no** fija variables de entorno: las pone Terraform en la Container App de tu equipo, y un `apply` revertiría las que
añadiera el CI. El agente las recibe con estos nombres:

| Variable | La pone | Uso |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | Terraform | endpoint de Foundry; el `CMD` de la imagen lo copia a `FOUNDRY_ENDPOINT` si esta no está definida |
| `AZURE_CLIENT_ID` | Terraform | identidad administrada del equipo (`DefaultAzureCredential`) |
| `TEAM_ID`, `APPLICATIONINSIGHTS_CONNECTION_STRING` | Terraform | equipo y trazas |
| `COSMOS_*`, `SEARCH_ENDPOINT`, `SEARCH_INDEX`, `MCP_URL`, `MCP_SCOPE`, `KEY_VAULT_URI` | Terraform | los bloques de T2, T3 y T4 (coinciden con el prefijo de su bloque de settings) |
| `DOMAIN` | la imagen (`--build-arg DOMAIN`, variable `DOMAIN` del repo) | prompt del dominio |
| `FOUNDRY_AUTH_PROVIDER=entra_id` | la imagen | sin api key: Managed Identity |
| `KNOWLEDGE_BASE=azure_search` | la imagen | la imagen no lleva `data/`: el índice es el de AI Search (`SEARCH_*`) |
| `AGENT_RUNTIME=agent_framework` | la imagen | el runtime con el que terminan las sesiones 7 y 8 |

El contenedor escucha en el **8000** con un usuario sin privilegios; el ingress de la Container App apunta a ese puerto.

## Qué sale en el ACR

`<ACR_LOGIN_SERVER>/team-NN/agent:<sha del commit>`. El CI de tu equipo solo puede publicar bajo `team-NN/`; publicar en el de otro
equipo está denegado.

## Actualizar tu fork con estos cambios

El pipeline vive en `.github/workflows/deploy-agent.yaml` y `devops/`, archivos que no se editan durante el workshop: no debería
haber conflictos.

```bash
git remote add upstream <url del repo base>    # una sola vez
git fetch upstream
git switch -c actualizar-pipeline
git merge upstream/main
git push -u origin actualizar-pipeline         # y abre un pull request hacia main
```
