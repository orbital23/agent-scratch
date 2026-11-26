"""Cliente de consola para conversar con el agente, sin pelear con las comillas ni las tildes de PowerShell.

uv run python dev/chat.py            conversación: escribe tus mensajes; "nueva" empieza otra sesión, "salir" termina
uv run python dev/chat.py "Hola"     un solo mensaje y termina

La respuesta aparece mientras el agente la escribe (POST /chat/stream, Server-Sent Events), y antes, cada tool que usa.
Si el agente deja una acción sensible pendiente, la consola te pregunta como asesor si la apruebas (POST /chat/actions).
AGENT_URL cambia la dirección del agente (por defecto http://127.0.0.1:8000).
AGENT_SCOPE, solo para el agente en Azure: el scope de tu ficha. Cada pedido lleva un token de Entra de tu az login.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.client import HTTPResponse

AGENT_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8000").rstrip("/")
AGENT_SCOPE = os.environ.get("AGENT_SCOPE", "")
URL = AGENT_URL + "/chat/stream"
TOOL_STATUS = {"ok": "resultado", "error": "error", "pending_approval": "NO SE EJECUTA, pendiente de aprobación",
               "rejected": "rechazada por el asesor"}
AUTH_HINT = {401: "el agente pide un token: define AGENT_SCOPE con el scope de tu ficha y haz az login",
             403: "tu usuario no está en el grupo de tu equipo: avisa a plataforma"}


def token_provider():
    """El mismo patrón que usa el agente con el MCP: un token de Entra para el scope, renovado solo cuando vence."""
    if not AGENT_SCOPE:
        return None
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider  # solo hace falta contra Azure

    return get_bearer_token_provider(DefaultAzureCredential(), AGENT_SCOPE)


TOKEN = token_provider()


def headers() -> dict[str, str]:
    if not TOKEN:
        return {"Content-Type": "application/json"}
    from azure.core.exceptions import ClientAuthenticationError

    try:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN()}"}
    except ClientAuthenticationError:
        sys.exit(f"No se pudo obtener un token para {AGENT_SCOPE}: haz az login y revisa que AGENT_SCOPE termine en /.default.")


def check_health() -> None:
    """Antes de conversar: si la URL o el token están mal, lo dice en la primera línea y no a mitad de un turno."""
    try:
        with urllib.request.urlopen(urllib.request.Request(AGENT_URL + "/health", headers=headers()), timeout=30) as response:
            status = json.loads(response.read().decode("utf-8"))["status"]
    except urllib.error.HTTPError as error:
        show_error(error.code, read_error(error))
        sys.exit(1)
    except urllib.error.URLError:
        sys.exit(f"No hay agente en {AGENT_URL}. ¿Lo levantaste con uvicorn en otra terminal, o es la URL de tu ficha?")
    print(f"Agente en {AGENT_URL}: {status}")


def read_error(error: urllib.error.HTTPError) -> dict:
    """El agente responde sus errores en JSON; el 401 y el 403 de Azure llegan antes de él, sin cuerpo."""
    try:
        return json.loads(error.read().decode("utf-8"))
    except ValueError:
        return {"detail": AUTH_HINT.get(error.code, error.reason)}


def send(message: str, session_id: str | None) -> str | None:
    """Envía el mensaje, muestra la respuesta mientras llega y devuelve el session_id para el siguiente turno."""
    body = json.dumps({"message": message, "session_id": session_id}).encode("utf-8")
    request = urllib.request.Request(URL, data=body, headers=headers())
    sent_at = time.perf_counter()
    try:
        response = urllib.request.urlopen(request, timeout=120)
    except urllib.error.HTTPError as error:  # falló antes de empezar a responder: llega como HTTP normal
        show_error(error.code, read_error(error))
        return None
    except urllib.error.URLError:
        sys.exit(f"No hay agente en {URL}. ¿Lo levantaste con uvicorn en otra terminal?")

    first_text_ms = None
    with response:
        for name, data in read_events(response):
            match name:
                case "tool_call":
                    arguments = ", ".join(f"{key}={value}" for key, value in data["arguments"].items())
                    print(f"  → {data['name']}({arguments})", flush=True)
                case "tool_result":
                    show_tool(data["status"], data["content"])
                case "intent":
                    print(f"  Agente [{data['intent']}]: ", end="", flush=True)
                case "delta":
                    first_text_ms = first_text_ms or milliseconds_since(sent_at)
                    print(data["text"], end="", flush=True)
                case "end":
                    print()
                    show_end(data, first_text_ms, milliseconds_since(sent_at))
                    if action := data.get("pending_action"):
                        decide(data["session_id"], action)
                    return data["session_id"]
                case "error":
                    print()
                    show_error(200, data)
    return None


def decide(session_id: str, action: dict) -> None:
    """Haces de asesor: apruebas o rechazas la acción sensible, y el agente le cuenta al cliente qué pasó."""
    arguments = ", ".join(f"{key}={value}" for key, value in action["arguments"].items())
    answer = input(f"  Asesor: ¿apruebas {action['name']}({arguments})? [s/n]: ").strip().lower()
    decision = "approve" if answer in ("s", "si", "sí") else "reject"
    body = json.dumps({"session_id": session_id, "action_id": action["id"], "decision": decision}).encode("utf-8")
    request = urllib.request.Request(AGENT_URL + "/chat/actions", data=body, headers=headers())
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            reply = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        show_error(error.code, read_error(error))
        return
    for tool in reply["tools"]:
        show_tool(tool["status"], tool["content"])
    print(f"  Agente [{reply['intent']}]: {reply['answer']}")


def show_tool(status: str, content: str) -> None:
    print(f"    {TOOL_STATUS[status]}: {content[:160]}", flush=True)


def read_events(response: HTTPResponse) -> Iterator[tuple[str, dict]]:
    """Lee los eventos a medida que llegan: cada uno es una línea "event: <nombre>" y una "data: <json>"."""
    name = ""
    for raw_line in response:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            yield name, json.loads(line.removeprefix("data: "))


def show_end(reply: dict, first_text_ms: int | None, total_ms: int) -> None:
    if citations := reply.get("citations"):
        print("  Fuentes:")
        for number, citation in enumerate(citations, start=1):
            print(f"   [{number}] {citation['source']} · {citation['section']}")
    usage = reply["usage"]
    first_text = f"primer texto en {first_text_ms} ms, " if first_text_ms else ""
    print(f"  ({first_text}respuesta completa en {total_ms} ms, "
          f"{usage['prompt_tokens']} tokens de entrada, {usage['completion_tokens']} de salida)")


def show_error(status: int, reply: dict) -> None:
    detail = reply.get("detail")
    if isinstance(detail, list):  # 422: FastAPI explica qué campo no pasó la validación
        detail = "; ".join(problem.get("msg", str(problem)) for problem in detail)
    kind = f" ({reply['error']})" if reply.get("error") else ""
    where = "a mitad de la respuesta" if status == 200 else str(status)
    print(f"  Error {where}{kind}: {detail}")


def milliseconds_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def main() -> None:
    check_health()
    if len(sys.argv) > 1:
        send(" ".join(sys.argv[1:]), None)
        return
    print('Conversación con el agente. Escribe "nueva" para otra sesión o "salir" para terminar.')
    session_id = None
    while True:
        try:
            message = input("Tú: ")
        except (EOFError, KeyboardInterrupt):
            break
        if message.strip().lower() == "salir":
            break
        if message.strip().lower() == "nueva":
            session_id = None
            print("  (sesión nueva)")
            continue
        session_id = send(message, session_id) or session_id


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()