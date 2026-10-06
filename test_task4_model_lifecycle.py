"""Task 4 — Model Lifecycle tests (fully offline / deterministic).

No real Ollama is required: all HTTP goes through a scripted fake
transport installed via monkeypatch-style attribute swap on
OllamaProvider._request. Tests assert real behavior: error codes,
keep_alive payloads, resident-model switching protocol, invariants.
"""
import inspect
import json
import re
import sys
import urllib.error
from socket import timeout as SocketTimeout

sys.path.insert(0, ".")

from mia.ai.provider import (
    AIProvider,
    MALFORMED_RESPONSE,
    MODEL_UNAVAILABLE,
    OLLAMA_UNAVAILABLE,
    PROVIDER_ERROR,
    PROVIDER_TIMEOUT,
    ModelResponse,
)
from mia.ai.lifecycle import (
    DEFAULT_KEEP_ALIVE,
    HEALTH_TIMEOUT_SECONDS,
    UNLOAD_KEEP_ALIVE,
    AvailabilityResult,
    HealthResult,
)
from mia.ai.ollama_provider import OllamaConfig, OllamaProvider
from mia.ai.model_router import ModelRouter

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------

TAGS_OK = {"models": [{"name": "qwen3:4b"}, {"name": "qwen2.5-coder:7b"}, {"name": "qwen2.5:7b"}]}
GEN_OK = {"response": "hello world", "eval_count": 42}


if __name__ == "__main__":
    class FakeTransport:
        """Scriptable replacement for OllamaProvider._request."""

        def __init__(self, tags=None, generate_responses=None, fail=None):
            self.tags = TAGS_OK if tags is None else tags
            # queue of (resp, err, code) consumed by real generation calls only
            # (residency loads/unloads get default success unless overridden).
            self.generate_responses = list(generate_responses or [])
            self.fail = fail
            self.calls = []   # list of dicts: {path, payload, timeout}

        def _tags_result(self):
            if isinstance(self.tags, urllib.error.URLError):
                reason = getattr(self.tags, "reason", self.tags)
                if isinstance(reason, SocketTimeout) or "timed out" in str(reason).lower():
                    return None, f"timeout contacting host: {reason}", PROVIDER_TIMEOUT
                return None, f"cannot reach host: {reason}", OLLAMA_UNAVAILABLE
            if isinstance(self.tags, SocketTimeout):
                return None, "timeout contacting host", PROVIDER_TIMEOUT
            if isinstance(self.tags, Exception):
                return None, str(self.tags), PROVIDER_ERROR
            if self.tags is MALFORMED_SENTINEL:
                return None, "invalid JSON body", MALFORMED_RESPONSE
            return dict(self.tags) if self.tags is not None else {}, None, None

        def __call__(self, path, payload=None, timeout=None):
            self.calls.append({"path": path, "payload": payload, "timeout": timeout})
            if path == "/api/tags":
                return self._tags_result()
            if path == "/api/generate":
                ka = (payload or {}).get("keep_alive")
                prompt = (payload or {}).get("prompt")
                is_lifecycle = prompt is None or prompt == ""  # unload / residency load
                if (not is_lifecycle) and self.generate_responses:
                    resp, err, code = self.generate_responses.pop(0)
                    if err is None:
                        return (dict(resp) if resp is not None else GEN_OK.copy()), None, None
                    return None, err, code
                return GEN_OK.copy(), None, None
            return None, f"unexpected path {path}", PROVIDER_ERROR


    MALFORMED_SENTINEL = object()


    def make_provider(fake=None, **cfg_kwargs):
        cfg = OllamaConfig(**cfg_kwargs)
        p = OllamaProvider(cfg)
        f = fake if fake is not None else FakeTransport()
        p._request = f  # instance-level monkeypatch
        p.fake = f
        return p


    def gen_calls(fake):
        return [c for c in fake.calls if c["path"] == "/api/generate"]


    def load_calls(fake):
        # residency loads carry prompt "" + keep_alive default
        return [c for c in gen_calls(fake)
                if (c["payload"] or {}).get("prompt") == ""]


    def unload_calls(fake):
        return [c for c in gen_calls(fake)
                if (c["payload"] or {}).get("keep_alive") == UNLOAD_KEEP_ALIVE
                and (c["payload"] or {}).get("prompt") is None]


    def real_gen_calls(fake):
        return [c for c in gen_calls(fake)
                if (c["payload"] or {}).get("prompt") not in ("", None)]


    print("=== 1. Provider abstraction & ModelResponse contract ===")
    try:
        AIProvider().generate("x")
        raised = False
    except NotImplementedError:
        raised = True
    check("AIProvider.generate raises NotImplementedError", raised)
    check("OllamaProvider is an AIProvider", issubclass(OllamaProvider, AIProvider))

    ok = ModelResponse(text="t", model="m", tokens_used=5)
    check("success response: success=True", ok.success is True)
    check("success response: error=None", ok.error is None)
    bad = ModelResponse(text="", model="m", error="boom")
    check("error response: success=False", bad.success is False)
    check("invariant: error set => not success", bad.error is not None and not bad.success)
    check("invariant: no success=True with error", not (bad.success and bad.error))
    empty_err = ModelResponse(text="x", model="m", error="   ")
    check("whitespace-only error normalized to success", empty_err.error is None and empty_err.success is True)
    f = ModelResponse.failure(PROVIDER_TIMEOUT, "slow", model="m")
    check("failure factory sets error_code", f.error_code == PROVIDER_TIMEOUT)
    check("failure factory message prefixed with code", f.error.startswith(PROVIDER_TIMEOUT))
    check("failure factory success=False", f.success is False and f.text == "")
    check("ModelResponse fields present", {"text", "model", "tokens_used", "error"} <=
          set(inspect.signature(ModelResponse).parameters.keys()))

    print("=== 2. Health ===")
    p = make_provider()
    h = p.health()
    check("healthy server => healthy=True", h.healthy is True and h.error is None)
    check("health result is structured HealthResult", isinstance(h, HealthResult))
    check("health probes GET /api/tags", p.fake.calls[-1]["path"] == "/api/tags" and p.fake.calls[-1]["payload"] is None)
    check("health timeout default is 1s", OllamaConfig().health_timeout == HEALTH_TIMEOUT_SECONDS == 1)
    check("health passes short timeout", p.fake.calls[-1]["timeout"] == 1)

    down = make_provider(FakeTransport(tags=urllib.error.URLError("connection refused")))
    h2 = down.health()
    check("unavailable => healthy=False", h2.healthy is False)
    check("unavailable => OLLAMA_UNAVAILABLE code", h2.error.startswith(OLLAMA_UNAVAILABLE))
    to = make_provider(FakeTransport(tags=SocketTimeout("timed out")))
    h3 = to.health()
    check("health timeout does not raise", isinstance(h3, HealthResult))
    check("health timeout => unhealthy with PROVIDER_TIMEOUT", h3.healthy is False and h3.error.startswith(PROVIDER_TIMEOUT))

    print("=== 3. Model availability ===")
    p = make_provider()
    a = p.is_model_available("qwen3:4b")
    check("present model detected (tagged name)", a.available is True and a.model == "qwen3:4b")
    check("availability result structured", isinstance(a, AvailabilityResult))
    m = p.is_model_available("llama3:8b")
    check("missing model => available=False", m.available is False)
    check("missing model => MODEL_UNAVAILABLE", (m.error or "").startswith(MODEL_UNAVAILABLE))
    mal = make_provider(FakeTransport(tags=MALFORMED_SENTINEL))
    mm = mal.is_model_available("qwen3:4b")
    check("malformed tags body => not available", mm.available is False)
    check("malformed tags body => MALFORMED_RESPONSE code", (mm.error or "").startswith(MALFORMED_RESPONSE))
    nonobj = make_provider(FakeTransport())
    nonobj._request = lambda path, payload=None, timeout=None: ([1, 2], "non-object JSON body", MALFORMED_RESPONSE)
    nn = nonobj.is_model_available("x")
    check("non-object JSON treated as malformed", nn.available is False and (nn.error or "").startswith(MALFORMED_RESPONSE))

    print("=== 4. Generation happy path & payload contract ===")
    p = make_provider()
    r = p.generate("hi", system_prompt="sys", max_tokens=64)
    check("generation success", r.success and r.error is None)
    check("generation text parsed", r.text == "hello world")
    check("generation tokens parsed", r.tokens_used == 42)
    check("system prompt prepended", "sys\n\nhi" == real_gen_calls(p.fake)[-1]["payload"]["prompt"])
    check("stream disabled", real_gen_calls(p.fake)[-1]["payload"]["stream"] is False)
    check("num_predict forwarded", real_gen_calls(p.fake)[-1]["payload"]["options"]["num_predict"] == 64)
    check("keep_alive default centralized '5m'", DEFAULT_KEEP_ALIVE == "5m"
          and real_gen_calls(p.fake)[-1]["payload"]["keep_alive"] == "5m")
    check("resident state updated after success", p.current_model == "qwen2.5-coder:7b")
    ck = make_provider()
    cr = ck.generate("hi", keep_alive="30s")
    check("custom keep_alive honored", cr.success and real_gen_calls(ck.fake)[-1]["payload"]["keep_alive"] == "30s")

    print("=== 5. Generation error mapping ===")
    cases = [
        (SocketTimeout("gen timed out"), PROVIDER_TIMEOUT),
        (None, OLLAMA_UNAVAILABLE),  # special marker below
        ({"bad": "json"}, MALFORMED_RESPONSE),
        (urllib.error.HTTPError("u", 500, "server boom", None, None), PROVIDER_ERROR),
    ]
    for idx, (resp, expect) in enumerate(cases):
        if resp is None:  # URLError unavailable
            t = FakeTransport(generate_responses=[(None, "cannot reach host", OLLAMA_UNAVAILABLE)])
        elif isinstance(resp, dict):
            t = FakeTransport(generate_responses=[(None, "invalid JSON body", MALFORMED_RESPONSE)])
        elif isinstance(resp, SocketTimeout):
            t = FakeTransport(generate_responses=[(None, "timeout contacting host", PROVIDER_TIMEOUT)])
        else:
            t = FakeTransport(generate_responses=[(None, "HTTP 500 server boom", PROVIDER_ERROR)])
        pr = make_provider(t)
        res = pr.generate("hi")
        check(f"error case {expect}: success=False", res.success is False)
        check(f"error case {expect}: error_code mapped", res.error_code == expect)
        check(f"error case {expect}: error message set", bool(res.error))

    # missing string 'response' field => structure invalid
    t = FakeTransport(generate_responses=[({"eval_count": 3}, None, None)])
    pr = make_provider(t)
    res = pr.generate("hi")
    check("response field absent => MALFORMED_RESPONSE", res.error_code == MALFORMED_RESPONSE and not res.success)
    t = FakeTransport(generate_responses=[({"response": {"nested": 1}}, None, None)])
    pr = make_provider(t)
    res = pr.generate("hi")
    check("response field non-string => MALFORMED_RESPONSE", res.error_code == MALFORMED_RESPONSE)

    print("=== 6. Single resident model lifecycle ===")
    # first launch: becomes resident with keep_alive=5m, no unload before it
    p = make_provider()
    r = p.generate("hi", model="qwen3:4b")
    check("first model generation succeeds", r.success and r.model == "qwen3:4b")
    check("first launch has no unload step", len(unload_calls(p.fake)) == 0)
    lc = load_calls(p.fake)
    check("first launch loads qwen3:4b with keep_alive=5m",
          len(lc) == 1 and lc[0]["payload"]["model"] == "qwen3:4b" and lc[0]["payload"]["keep_alive"] == "5m")
    check("current_model == qwen3:4b after first run", p.current_model == "qwen3:4b")

    # same model again: NO extra load/unload traffic
    before = len(p.fake.calls)
    r2 = p.generate("again", model="qwen3:4b")
    new_calls = p.fake.calls[before:]
    check("same-model reuse succeeds", r2.success)
    check("same-model reuse performs no switching traffic",
          not [c for c in new_calls if c["path"] == "/api/generate" and (c["payload"] or {}).get("prompt") == ""]
          and not [c for c in new_calls if (c["payload"] or {}).get("keep_alive") == UNLOAD_KEEP_ALIVE])

    # switch A -> B: protocol order A keep_alive=0 then B keep_alive=5m then B resident
    start = len(p.fake.calls)
    r3 = p.generate("switch", model="qwen2.5-coder:7b")
    switch_calls = p.fake.calls[start:]
    unload_idx = next((i for i, c in enumerate(switch_calls)
                       if (c["payload"] or {}).get("keep_alive") == UNLOAD_KEEP_ALIVE), None)
    load_b_idx = next((i for i, c in enumerate(switch_calls)
                       if c["path"] == "/api/generate" and (c["payload"] or {}).get("prompt") == ""
                       and c["payload"]["model"] == "qwen2.5-coder:7b"), None)
    gen_idx = next((i for i, c in enumerate(switch_calls)
                    if c["path"] == "/api/generate" and (c["payload"] or {}).get("prompt") not in ("", None)), None)
    check("switch succeeds", r3.success and r3.model == "qwen2.5-coder:7b")
    check("A unloaded with keep_alive=0", unload_idx is not None
          and switch_calls[unload_idx]["payload"]["model"] == "qwen3:4b")
    check("B loaded with keep_alive=5m after A unload",
          load_b_idx is not None and load_b_idx > unload_idx
          and switch_calls[load_b_idx]["payload"]["keep_alive"] == "5m")
    check("generation happens after B load", gen_idx is not None and gen_idx > load_b_idx)
    check("resident now B", p.current_model == "qwen2.5-coder:7b")

    # repeated A -> B -> A works and unloads the right side each time
    start = len(p.fake.calls)
    p.generate("back", model="qwen3:4b")
    sw = p.fake.calls[start:]
    u = [c for c in sw if (c["payload"] or {}).get("keep_alive") == UNLOAD_KEEP_ALIVE]
    l = [c for c in sw if c["path"] == "/api/generate" and (c["payload"] or {}).get("prompt") == ""]
    check("B->A reverse switch unloads B", len(u) == 1 and u[0]["payload"]["model"] == "qwen2.5-coder:7b")
    check("B->A loads A resident", len(l) == 1 and l[0]["payload"]["model"] == "qwen3:4b" and p.current_model == "qwen3:4b")

    # failed switch does NOT corrupt resident state
    p = make_provider()
    p.generate("prime", model="qwen3:4b")
    assert p.current_model == "qwen3:4b"
    # target missing from tags
    t_missing = FakeTransport(tags={"models": [{"name": "qwen3:4b"}]},
                              generate_responses=[])
    p2 = make_provider(t_missing)
    p2.current_model = "qwen3:4b"
    res = p2.generate("hi", model="ghost:1b")
    check("switch to missing model fails MODEL_UNAVAILABLE",
          res.error_code == MODEL_UNAVAILABLE and not res.success)
    check("failed switch clears stale residency", p2.current_model != "ghost:1b")
    check("failed switch never claims B resident", "ghost:1b" not in json.dumps([c["payload"] for c in real_gen_calls(t_missing) if c["payload"]]))

    # load request itself fails => B not resident
    p3 = make_provider()
    p3.current_model = "qwen3:4b"


    class FailLoad(FakeTransport):
        """tags include coder-x:7b; unload OK; residency LOAD of coder-x:7b fails."""

        def _tags_result(self):
            return {"models": [{"name": "qwen3:4b"}, {"name": "coder-x:7b"}]}, None, None

        def __call__(self, path, payload=None, timeout=None):
            self.calls.append({"path": path, "payload": payload, "timeout": timeout})
            if path == "/api/tags":
                return self._tags_result()
            ka = (payload or {}).get("keep_alive")
            mdl = (payload or {}).get("model")
            prompt = (payload or {}).get("prompt")
            if prompt == "" and ka != UNLOAD_KEEP_ALIVE and mdl == "coder-x:7b":
                return None, "load refused", PROVIDER_ERROR
            return GEN_OK.copy(), None, None


    p3._request = FailLoad()
    res = p3.generate("hi", model="coder-x:7b")
    check("failed B-load => structured failure", res.error_code == PROVIDER_ERROR and not res.success)
    check("failed B-load => B NOT resident", p3.current_model != "coder-x:7b")
    check("failed B-load => residency unknown (not stale A)", p3.current_model is None)

    # Ollama dies mid-lifecycle => residency unknown, structured error
    p4 = make_provider()
    p4.generate("prime", model="qwen3:4b")
    p4._request = lambda path, payload=None, timeout=None: (
        None, "cannot reach host", OLLAMA_UNAVAILABLE)
    res = p4.generate("hi")
    check("unavailable during generate => OLLAMA_UNAVAILABLE", res.error_code == OLLAMA_UNAVAILABLE)
    check("unavailable clears residency", p4.current_model is None)

    print("=== 7. Provider reuse ===")
    p = make_provider()
    r1 = p.generate("one")
    r2 = p.generate("two")
    r3 = p.generate("three")
    check("same provider handles repeated generations", all(x.success for x in (r1, r2, r3)))
    check("reuse does not re-load resident model", len(load_calls(p.fake)) == 1)

    print("=== 8. ModelRouter purity (role -> model only) ===")
    calls_seen = []


    class SpyProvider(AIProvider):
        def __init__(self, name):
            self.name = name

        def generate(self, prompt, system_prompt=None, max_tokens=512):
            calls_seen.append((self.name, prompt))
            return ModelResponse(text=f"{self.name}:{prompt}", model=self.name)


    chat, coder = SpyProvider("chat-model"), SpyProvider("coder-model")
    router = ModelRouter(chat_provider=chat, coder_provider=coder)
    rr = router.generate("hi", preferred="chat")
    check("router routes chat role to chat provider", rr.text == "chat-model:hi")
    rr2 = router.generate("code", preferred="coder")
    check("router routes coder role to coder provider", rr2.text == "coder-model:code")
    rr3 = router.generate("weird", preferred="unknown-role")
    check("unknown role falls back to chat", rr3.text == "chat-model:weird")
    check("router returns provider ModelResponse unchanged", rr2.success and rr2.error is None)

    src = inspect.getsource(sys.modules["mia.ai.model_router"])
    # Strict purity: the ENTIRE module source (code, comments and docstrings
    # alike) must contain no transport/lifecycle vocabulary at all.
    check("no HTTP/transport vocabulary anywhere in ModelRouter module",
          "urllib" not in src and "requests" not in src
          and "http" not in src.lower())
    check("no keep_alive/lifecycle vocabulary anywhere in ModelRouter module",
          "keep_alive" not in src and "current_model" not in src
          and "health" not in src.lower())
    check("ModelRouter has no hard dependency on OllamaProvider at module top",
          "from .ollama_provider import OllamaProvider, OllamaConfig" not in src.split("class ModelRouter")[0].split('"""')[0])
    check("router reusable across many requests", len(calls_seen) == 3)

    default_router = ModelRouter()
    check("default router maps chat->qwen2.5:7b", default_router.default_chat_model == "qwen2.5:7b")
    check("default router maps coder->qwen2.5-coder:7b", default_router.coder_model == "qwen2.5-coder:7b")
    check("default router providers are AIProviders",
          isinstance(default_router.chat_provider, AIProvider) and isinstance(default_router.coder_provider, AIProvider))

    print("=== 9. Centralization of defaults ===")
    check("UNLOAD_KEEP_ALIVE is '0'", UNLOAD_KEEP_ALIVE == "0")
    def _code_only(path):
        s = open(path).read()
        s = re.sub(r'"""(?:.*?)"""', "", s, flags=re.S)
        s = re.sub(r"#.*", "", s)
        return s


    check("'5m' default literal lives only in lifecycle.py (code, not prose)",
          _code_only("mia/ai/lifecycle.py").count('"5m"') == 1
          and '"5m"' not in _code_only("mia/ai/model_router.py")
          and '"5m"' not in _code_only("mia/ai/provider.py")
          and '"5m"' not in _code_only("mia/ai/ollama_provider.py"))

    print("=== 10. No-exception guarantee (smoke fuzz over broken transports) ===")
    def _exploding(path, payload=None, timeout=None):
        raise RuntimeError("kaboom")


    p = make_provider()
    p._request = _exploding
    try:
        res = p.generate("hi")
        check("even catastrophic transport bug yields structured failure", res.success is False and res.error is not None)
    except Exception as e:
        check("provider must not raise outward", False)

    print()
    print(f"TOTAL: {PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)
