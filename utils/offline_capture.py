"""See what would leave the process, without a key and without a network (Module 7).

Everything here answers locally. No helper in this file sends a request to LangSmith, a model
provider or the LLM Gateway, and none of them needs an API key.

- `offline_client()` returns a LangSmith client whose HTTP layer records every request and
  answers it locally. Trace an agent into it, then read exactly what would have been uploaded.
  Its masking and sampling settings are fixed, so `LANGSMITH_HIDE_INPUTS` and similar
  variables in your environment do not change what it records. It refuses the two settings
  that would take uploads past the recorder (an OpenTelemetry tracing mode, and batching).
- `count_payloads_containing()` counts the uploaded run payloads that contain a string, for
  example a customer's email address.
- `scripted_model()` is a chat model that returns replies you give it, so an agent can run
  with no model call.
- `gateway_replay()` is a `ChatOpenAI` whose HTTP layer returns one of the saved LLM Gateway
  policy blocks, so you can see which exception LangChain raises for each. Calling it
  directly is never traced, whatever `LANGSMITH_TRACING` says.
- `hide_inputs_in_subprocess()` shows what `LANGSMITH_HIDE_INPUTS=<value>` does to an upload.

One thing here follows your tracing settings: `scripted_model()` is an ordinary LangChain chat
model. Like any LangChain runnable it is traced when tracing is on, and so is an agent built
on it. Inside `tracing_context(enabled=True, client=client)` with a client from
`offline_client()`, the trace goes to the recorder. With `LANGSMITH_TRACING=true` and no such
block, it goes to the LangSmith project your environment names, exactly as for a real model.

Typical use in a notebook:

    from langsmith import tracing_context
    from utils.offline_capture import count_payloads_containing, offline_client, uploaded_payloads

    client, capture = offline_client()
    with tracing_context(enabled=True, client=client):
        agent.invoke({"messages": [{"role": "user", "content": "My email is jordan.lee@example.com"}]})
    client.flush()
    print(count_payloads_containing(capture, "jordan.lee@example.com"), "of", len(uploaded_payloads(capture)))

The two fixture files this module reads (`gateway_blocked_responses.json` and
`alert_webhook_payload.json` in `workshop_modules/module_7/data/`) are written by hand from
the public documentation. They show the documented shape; they are not captured output.
"""

import functools
import itertools
import json
import os
import re
import socket
import subprocess
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import requests
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langsmith import Client
from requests.adapters import BaseAdapter

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "workshop_modules" / "module_7" / "data"

# `.invalid` is a reserved top-level domain that never resolves (RFC 6761), so a request that
# slipped past the capture could not reach a real server either.
OFFLINE_API_URL = "http://offline.invalid"
GATEWAY_REPLAY_BASE_URL = "http://offline.invalid/openai/v1"
OFFLINE_KEY = "offline-dummy"  # a placeholder, not a credential

# Reply to one captured request: (status code, JSON-serialisable body), or None for `200 {}`.
Responder = Callable[[str, str, str | None], tuple[int, Any] | None]


# --- 1. A LangSmith client that uploads to a recorder ---------------------------------------


class Capture(BaseAdapter):
    """Record outgoing requests and answer them locally. Nothing leaves the machine.

    `calls` holds one `(method, url, body)` tuple per request, in the order they were sent.
    Every request is answered `200 {}` unless `responder(method, url, body)` returns a
    `(status, json_body)` pair for it; tests of keyed code use that to play the server.
    """

    def __init__(self, responder: Responder | None = None):
        super().__init__()
        self.calls: list[tuple[str, str, str | None]] = []
        self.responder = responder

    def _record(self, method: str, url: str, body) -> tuple[int, bytes]:
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        self.calls.append((method, url, body or None))
        reply = self.responder(method, url, body or None) if self.responder else None
        status, payload = reply if reply is not None else (200, {})
        return status, json.dumps(payload).encode()

    def send(self, request, **kwargs):
        """The `requests` transport hook: the classic client methods and all trace uploads."""
        status, content = self._record(request.method, request.url, request.body)
        response = requests.Response()
        response.status_code = status
        response._content = content
        response.headers["Content-Type"] = "application/json"
        response.request = request
        response.url = request.url
        return response

    def close(self):
        pass


def _capture_generated_clients(client: Client, capture: Capture) -> None:
    """Send the SDK's newer resources (`client.runs`, `client.agents`, ...) to the capture too.

    Those resources do not use `client.session`: the SDK builds a second, httpx-style client
    for them the first time one is used. This builds that client here, the way the SDK does,
    with a mock transport, once for the async resources (`client.runs`) and once for the sync
    ones (`client.agents`). It relies on private names of langsmith 0.14;
    `tests/test_offline_capture.py` calls one resource of each kind and fails if a package
    update changes them.
    """
    import langsmith.client as sdk

    hx = sdk._httpx
    base_url = sdk._get_openapi_base_url(client.api_url)

    def handle(request):
        status, content = capture._record(request.method, str(request.url), request.content)
        return hx.Response(status, content=content, headers={"Content-Type": "application/json"})

    shared = {"api_key": client.api_key, "base_url": base_url, "timeout": client._openapi_timeout()}
    client._langsmith_api = sdk.LangsmithOpenAPIClient(
        header_provider=client._aget_openapi_headers,
        http_client=sdk._AsyncHttpxClientWrapper(base_url=base_url, transport=hx.MockTransport(handle), trust_env=False),
        **shared,
    )
    client._langsmith_api_sync = sdk.SyncLangsmithOpenAPIClient(
        header_provider=client._current_openapi_headers,
        http_client=sdk._SyncHttpxClientWrapper(base_url=base_url, transport=hx.MockTransport(handle), trust_env=False),
        **shared,
    )


def _offline_client_defaults() -> dict:
    """What `offline_client()` passes to `Client` unless the caller passes the same argument.

    `Client` reads an environment variable for a setting only when the argument is `None`
    (langsmith 0.14). Passing a value here is what keeps the recorder independent of the
    shell and of `.env`. The caller cannot change `auto_batch_tracing` and `tracing_mode`:
    see `_refuse_uncapturable_arguments`.
    """
    return {
        "api_url": OFFLINE_API_URL,
        "api_key": OFFLINE_KEY,
        "auto_batch_tracing": False,
        "info": {"batch_ingest_config": {}},  # supplied here so the client never asks the server for it
        # Not read from LANGSMITH_HIDE_INPUTS, LANGSMITH_HIDE_OUTPUTS, LANGSMITH_HIDE_METADATA:
        "hide_inputs": False,
        "hide_outputs": False,
        "hide_metadata": False,
        # Not read from LANGSMITH_TRACING_SAMPLING_RATE: every trace is recorded.
        "tracing_sampling_rate": 1.0,
        # Not read from LANGSMITH_TRACING_MODE or LANGSMITH_OTEL_ENABLED: no OpenTelemetry exporter is set up.
        "tracing_mode": "langsmith",
    }


def _refuse_uncapturable_arguments(client_kwargs: dict) -> None:
    """Raise `ValueError` for a `Client` argument that would take uploads past the recorder.

    Two settings do that (langsmith 0.14):

    - An OpenTelemetry tracing mode. The SDK's OpenTelemetry exporter has its own HTTP client,
      which the recorder is not attached to, and it takes its address and API key from the
      environment (`LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, `OTEL_EXPORTER_OTLP_*`), not from
      this client's `api_url` and `api_key`. With a real key in the environment the trace
      would be sent to LangSmith, unmasked, while the recorder stayed empty.
      `tracing_mode=None` is refused as well, because it lets `LANGSMITH_TRACING_MODE` decide.
    - Automatic batching. Runs are then uploaded as `POST /runs/multipart`. The request is
      recorded, but `uploaded_payloads()` cannot read that format.
    """
    if "tracing_mode" in client_kwargs and str(client_kwargs["tracing_mode"]).lower() != "langsmith":
        raise ValueError(
            f"offline_client: tracing_mode={client_kwargs['tracing_mode']!r} is not supported. The recorder is not "
            "attached to the SDK's OpenTelemetry exporter, which sends traces to the address and API key in the "
            "environment. offline_client() always uses tracing_mode='langsmith'; leave the argument out."
        )
    for name in ("otel_enabled", "otel_tracer_provider"):
        if client_kwargs.get(name) is not None:
            raise ValueError(
                f"offline_client: {name} is not supported. The recorder is not attached to the SDK's OpenTelemetry "
                "exporter, so offline_client() never sets one up; leave the argument out."
            )
    if client_kwargs.get("auto_batch_tracing"):
        raise ValueError(
            "offline_client: auto_batch_tracing=True is not supported. Batched runs are uploaded as "
            "POST /runs/multipart, which uploaded_payloads() and count_payloads_containing() cannot read. "
            "offline_client() always sends one request per run; leave the argument out."
        )


def _never_resolves(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "invalid" or host.endswith(".invalid")


def offline_client(*, responder: Responder | None = None, **client_kwargs) -> tuple[Client, Capture]:
    """A LangSmith `Client` that records its requests instead of sending them.

    Returns `(client, capture)`. Pass masking options as you would to `Client`, for example
    `offline_client(anonymizer=...)` or `offline_client(hide_inputs=True)`.

    Runs are sent one request each (`auto_batch_tracing=False`): a `POST /runs` when a run
    starts and a `PATCH /runs/<id>` when it ends, so `capture.calls` is easy to read.

    What it records does not depend on your environment. Unless you pass the argument
    yourself, inputs, outputs and metadata are not hidden and every trace is recorded
    (sampling rate 1.0), whatever `LANGSMITH_HIDE_INPUTS`, `LANGSMITH_HIDE_OUTPUTS`,
    `LANGSMITH_HIDE_METADATA` and `LANGSMITH_TRACING_SAMPLING_RATE` say. To let one of those
    variables decide, pass `None` for that argument, for example
    `offline_client(hide_inputs=None)`.

    Two settings are fixed, because changing them would take uploads past the recorder.
    Passing any of these arguments raises `ValueError`:

    - `tracing_mode` other than `"langsmith"` (so `"otel"`, `"hybrid"` and `None`),
      `otel_enabled` and `otel_tracer_provider`. No OpenTelemetry exporter is ever set up,
      whatever `LANGSMITH_TRACING_MODE` says. The SDK's exporter does not go through the
      recorder: it sends traces to the address and API key in your environment.
    - `auto_batch_tracing=True`. Batched runs are uploaded as `POST /runs/multipart`, which
      `uploaded_payloads()` cannot read.

    Every other `Client` argument can be passed, including `api_url` and `api_key`. Use
    `offline_client(api_url="https://eu.api.smith.langchain.com")` to see the URLs the client
    would build for that endpoint: the recorder answers every `http://` and `https://` request
    for every host, so that address is recorded and never contacted. Pass `api_url` here; do
    not assign `client.api_url` afterwards, because `client.runs`, `client.agents` and the
    other newer resources keep the address they were built with.
    """
    _refuse_uncapturable_arguments(client_kwargs)
    capture = Capture(responder)
    client = Client(**{**_offline_client_defaults(), **client_kwargs})
    # Mount after the client exists: Client.__init__ mounts its own adapters on the session.
    client.session.mount("http://", capture)
    client.session.mount("https://", capture)
    try:
        _capture_generated_clients(client, capture)
    except Exception as exc:  # noqa: BLE001 - the upload path above does not depend on this
        problem = (
            f"offline_client: could not attach the capture to client.runs and the other newer resources "
            f"({type(exc).__name__}: {exc})."
        )
        if not _never_resolves(client.api_url):
            # Those resources would contact this address for real. Refuse to hand out the client.
            raise RuntimeError(
                f"{problem} With api_url={client.api_url!r} they would send real requests, so no client is returned."
            ) from exc
        warnings.warn(f"{problem} Trace uploads are still captured.", RuntimeWarning, stacklevel=2)
    return client, capture


# The routes the SDK uploads runs to (langsmith 0.14): one run, a JSON batch, a multipart batch, one run's end.
_RUN_UPLOAD_PATH = re.compile(r"/runs(/batch|/multipart|/[0-9a-fA-F-]{36})?/?$")


def uploaded_payloads(capture: Capture) -> list[dict]:
    """The run payloads in `capture`, decoded from JSON, in the order they were sent.

    One payload per `POST /runs` (run started) and per `PATCH /runs/<id>` (run ended), so a
    run usually appears twice. A `POST /runs/batch` body (what `Client.batch_ingest_runs`
    sends) counts as one payload per run in it.

    Raises `ValueError` if the capture holds a run upload that is not a JSON object. That is
    the case for `POST /runs/multipart`, which a `Client` with `auto_batch_tracing=True`
    sends. Leaving such an upload out would make the count too low, and "0 payloads contain
    the address" would then be wrong. A client from `offline_client()` never sends one.
    """
    payloads = []
    for method, url, body in capture.calls:
        if method not in ("POST", "PATCH") or not body or not _RUN_UPLOAD_PATH.search(urlsplit(url).path):
            continue
        try:
            data = json.loads(body)
        except (TypeError, ValueError):
            data = None
        if not isinstance(data, dict):
            raise ValueError(
                f"uploaded_payloads: cannot read the run upload {method} {url}: its body is not a JSON object. "
                "Its runs would be missing from the count, so no count is returned. A client with "
                "auto_batch_tracing=True uploads runs as POST /runs/multipart; trace into a client from "
                "offline_client(), which sends one JSON request per run."
            )
        if isinstance(data.get("post"), list) or isinstance(data.get("patch"), list):
            payloads += [*(data.get("post") or []), *(data.get("patch") or [])]
        else:
            payloads.append(data)
    return payloads


def _contains(value, text: str) -> bool:
    if isinstance(value, str):
        return text in value
    if isinstance(value, dict):
        return any(_contains(k, text) or _contains(v, text) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains(item, text) for item in value)
    return False


def count_payloads_containing(capture: Capture, text: str) -> int:
    """How many uploaded run payloads contain `text` anywhere (inputs, outputs, metadata, error, ...).

    Compare with `len(uploaded_payloads(capture))` for the "N of M" line. Raises `ValueError`
    when `uploaded_payloads(capture)` does: it never answers 0 for an upload it cannot read.
    """
    return sum(_contains(payload, text) for payload in uploaded_payloads(capture))


# --- 2. A chat model that needs no provider ---------------------------------------------------

# The replies live here, not on the model object: an agent harness copies and re-binds the model
# it is given, and replies held in a field of the model (an iterator) do not survive that.
_SCRIPTS: dict[str, list[AIMessage]] = {}
_script_ids = itertools.count(1)


class ScriptedChatModel(BaseChatModel):
    """A chat model that returns prepared replies in order and calls nothing."""

    script_id: str

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        remaining = _SCRIPTS.get(self.script_id)
        if not remaining:
            raise RuntimeError(
                "scripted_model: no replies left. The model was called more often than the number of replies "
                "it was given; build a new one with scripted_model([...])."
            )
        return ChatResult(generations=[ChatGeneration(message=remaining.pop(0))])

    def bind_tools(self, tools, **kwargs):
        # Replies are fixed, so the tool list changes nothing. Returning self keeps the script.
        return self


def scripted_model(replies: list[str | AIMessage]) -> ScriptedChatModel:
    """A chat model that answers with `replies`, one per call, and makes no network call.

    Each reply is a string or an `AIMessage` (use an `AIMessage` with `tool_calls` to script a
    tool call). Calling the model more often than there are replies raises `RuntimeError`.

    It is traced like any other chat model. To keep a run on this machine, call it (or the
    agent built on it) inside `tracing_context(enabled=True, client=client)` with a client from
    `offline_client()`, or inside `tracing_context(enabled=False)`.
    """
    script_id = f"script-{next(_script_ids)}"
    _SCRIPTS[script_id] = [reply if isinstance(reply, AIMessage) else AIMessage(content=reply) for reply in replies]
    return ScriptedChatModel(script_id=script_id)


# --- 3. Saved LLM Gateway policy blocks, replayed ---------------------------------------------


def blocked_responses() -> dict:
    """The three documented LLM Gateway policy blocks: `spend`, `rate` and `model_access`.

    Each entry has `status`, `headers`, `body`, `policy_type`, the documentation page it was
    written from (`_source_url`) and a `_note`. Hand-written from the docs, not captured output.

    `policy_type` is `spend_limit`, `rate_limit` or `model_access`: an identifier this module
    chose, spelled as in the Module 7 answer key (`s4_blocks` in `answers.json`), so an answer
    built from this file passes the check. The response itself carries no such field.
    """
    return json.loads((DATA / "gateway_blocked_responses.json").read_text())


@functools.cache
def _replay_model_class():
    """`ChatOpenAI` with tracing switched off around each direct call (built once, on first use)."""
    from langchain_openai import ChatOpenAI
    from langsmith import tracing_context

    class GatewayReplayChatOpenAI(ChatOpenAI):
        """A `ChatOpenAI` for `gateway_replay()`: a direct call to it is never traced.

        Every call to this model ends in an exception. With `LANGSMITH_TRACING=true` an
        ordinary `ChatOpenAI` would upload each of them as a failed run, with its traceback,
        to the learner's LangSmith project. `generate` and `agenerate` are behind `invoke`,
        `ainvoke`, `batch` and `abatch`; `stream` and `astream` start their own run.
        """

        def generate(self, *args, **kwargs):
            with tracing_context(enabled=False):
                return super().generate(*args, **kwargs)

        async def agenerate(self, *args, **kwargs):
            with tracing_context(enabled=False):
                return await super().agenerate(*args, **kwargs)

        def stream(self, *args, **kwargs):
            with tracing_context(enabled=False):
                yield from super().stream(*args, **kwargs)

        async def astream(self, *args, **kwargs):
            with tracing_context(enabled=False):
                async for chunk in super().astream(*args, **kwargs):
                    yield chunk

    return GatewayReplayChatOpenAI


def gateway_replay(kind: str, model: str = "gpt-5.4"):
    """A `ChatOpenAI` that receives the saved Gateway block `kind` instead of calling anything.

    `kind` is `"spend"` (HTTP 402), `"rate"` (429 with a `Retry-After` header) or
    `"model_access"` (403). `gateway_replay(kind).invoke("ping")` raises the exception LangChain
    raises for that status. The exception has `.status_code`, `.body` and `.response`
    (`.response.headers`, `.response.text`).

    This replays the documented response through the installed OpenAI SDK. It shows how the
    SDK maps the status code; it is not a recording of a live Gateway call.

    A direct call (`invoke`, `ainvoke`, `batch`, `abatch`, `stream`, `astream`) is never
    traced, with or without `LANGSMITH_TRACING=true` and even inside
    `tracing_context(enabled=True)`: the failed call does not appear in your LangSmith project
    and does not count as an error there. No wrapper is needed around the call. If you put the
    model inside a chain or an agent that is traced, the chain's and the agent's own runs are
    recorded as usual, with the error text; only the model call's run is left out.
    """
    import httpx

    replay_class = _replay_model_class()  # a ChatOpenAI subclass, see above

    saved = blocked_responses()
    if kind not in saved:
        raise ValueError(f"gateway_replay: unknown kind {kind!r}. Use one of: {', '.join(saved)}.")
    entry = saved[kind]
    # Compact separators reproduce the body text exactly as the documentation prints it.
    body = json.dumps(entry["body"], separators=(",", ":"))

    def blocked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(entry["status"], headers=entry["headers"], content=body)

    return replay_class(
        model=model,
        api_key=OFFLINE_KEY,
        base_url=GATEWAY_REPLAY_BASE_URL,
        max_retries=0,  # the OpenAI SDK would otherwise retry a 429 itself before raising
        http_socket_options=(),  # both HTTP clients are supplied below; this also avoids a proxy warning
        # trust_env=False: a proxy variable in the environment must not reroute the replay.
        http_client=httpx.Client(transport=httpx.MockTransport(blocked), trust_env=False),
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(blocked), trust_env=False),
    )


# --- 4. The documented alert webhook body -----------------------------------------------------


def alert_webhook_payload() -> dict:
    """The top-level keys LangSmith adds to an alert webhook body, with illustrative values.

    The key names are the documented ones. The values are examples: the documentation does not
    show a sample body, so value formats are UNVERIFIED (see `_note` in the file).
    """
    data = json.loads((DATA / "alert_webhook_payload.json").read_text())
    return {key: value for key, value in data.items() if not key.startswith("_")}


# --- 5. Proving that no network is used -------------------------------------------------------


def _is_local(address) -> bool:
    if isinstance(address, (str, bytes)):  # a Unix socket path
        return True
    host = str(address[0]) if isinstance(address, tuple) and address else ""
    return host in ("localhost", "::1") or host.startswith("127.")


@contextmanager
def refuse_non_local_connects():
    """Refuse every socket connection and name lookup that is not local, and list the attempts.

    Yields a list that receives each refused address. Loopback addresses and Unix sockets
    pass, because Jupyter kernels and subprocess pipes use them. Use it to prove that a block
    of code is offline: the list is still empty afterwards.
    """
    attempts: list = []
    real_connect, real_connect_ex, real_getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def connect(self, address):
        if _is_local(address):
            return real_connect(self, address)
        attempts.append(address)
        raise ConnectionRefusedError(f"refused by refuse_non_local_connects: {address}")

    def connect_ex(self, address):
        if _is_local(address):
            return real_connect_ex(self, address)
        attempts.append(address)
        raise ConnectionRefusedError(f"refused by refuse_non_local_connects: {address}")

    def getaddrinfo(host, *args, **kwargs):
        if host is None or _is_local((host,)):
            return real_getaddrinfo(host, *args, **kwargs)
        attempts.append(("name lookup", host))
        raise socket.gaierror(f"refused by refuse_non_local_connects: name lookup of {host}")

    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
    try:
        yield attempts
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = real_connect, real_connect_ex, real_getaddrinfo


# --- 6. LANGSMITH_HIDE_INPUTS, one fresh process per spelling ---------------------------------

HIDE_INPUTS_PROBE_QUESTION = "Where is order ORD-2025-0050?"

_HIDE_INPUTS_CHILD = """
import json, sys
sys.path.insert(0, sys.argv[1])
from langchain_core.runnables import RunnableLambda
from langsmith import tracing_context
from utils.offline_capture import offline_client, refuse_non_local_connects, uploaded_payloads

with refuse_non_local_connects() as attempts:
    # hide_inputs=None: offline_client() does not hide inputs by default; None lets the variable decide.
    client, capture = offline_client(hide_inputs=None)
    with tracing_context(enabled=True, client=client):
        RunnableLambda(lambda inputs: {"answer": "It shipped."}, name="probe").invoke({"question": sys.argv[2]})
    client.flush()
first = uploaded_payloads(capture)[0]
print(json.dumps({"uploaded_inputs": first.get("inputs"), "non_local_connects": [str(a) for a in attempts]}))
"""


def hide_inputs_in_subprocess(value: str) -> dict:
    """Trace one call in a new Python process with `LANGSMITH_HIDE_INPUTS=<value>`.

    Returns `{"uploaded_inputs": <the inputs in the uploaded run>, "non_local_connects": []}`.
    The uploaded inputs are `{}` when the setting took effect, and
    `{"question": HIDE_INPUTS_PROBE_QUESTION}` when it did not.

    A new process is needed for each value because the SDK caches the first value it reads.
    The child gets only `PATH`, `HOME` and this one variable, uploads to
    `offline_client(hide_inputs=None)` (`None` lets the variable decide; without it the
    recorder never hides inputs), and refuses any non-local connection.
    """
    env = {name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ}
    env["LANGSMITH_HIDE_INPUTS"] = value
    result = subprocess.run(
        [sys.executable, "-c", _HIDE_INPUTS_CHILD, str(REPO_ROOT), HIDE_INPUTS_PROBE_QUESTION],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"hide_inputs_in_subprocess({value!r}) failed:\n{result.stderr.strip()}")
    return json.loads(result.stdout.strip().splitlines()[-1])
