# TechHub Support Agent: Managed Deep Agent (Module 6)

The Module 4 deep agent (`agents/deep_support_agent.py`) as a [Managed Deep Agent](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview). This folder is its own project with its own `pyproject.toml`.

> MDA is in public beta on LangSmith Cloud: GCP US (default), GCP EU, GCP APAC, and AWS US. Set `LANGSMITH_ENDPOINT` before the first deploy to pick a non-default region. BYOC and self-hosted are not supported yet.

## Run it

```bash
uv tool install --prerelease allow managed-deepagents   # once: the `mda` CLI
cd managed_agent
uv sync
cp .env.example .env   # LANGSMITH_API_KEY + ONE credential option:
                       #   A: OPENAI_API_KEY and/or ANTHROPIC_API_KEY
                       #   B: LANGSMITH_GATEWAY_API_KEY (LLM Gateway; workspace provider secrets)
mda dev       # local: compiles, bakes the sandbox snapshot, serves Studio
mda deploy    # hosted: prints the Agent Server URL -> set MDA_DEPLOYMENT_URL in the repo .env
mda delete    # tear down when finished
```

Pass the verified customer as run context, for example `{"customer_id": "CUST-003"}`.

## Layout

| Path | Role |
|---|---|
| `agent.py` | `define_deep_agent(...)`: model, tools, subagents (small model), middleware, refund approval |
| `model.py` | `resolve_model()`: `DEEP_AGENT_MODEL` → OpenAI key (gpt-5.4) → Anthropic key (Claude Sonnet 5.5) → LLM Gateway (`langsmith:openai/gpt-5.4`). `resolve_small_model()` and `resolve_fallback_models()` follow the same route |
| `instructions.md`, `skills/` | System prompt and skills, synced to Context Hub |
| `memory.py` | Agent memory, mounted for `role == "ops"` runs only (`MemoryLayer(allow=ops_only)`) |
| `sandbox/` | Per-thread LangSmith sandbox with a default-deny egress allowlist; `setup.sh` loads public docs and the product catalog |
| `identity.py` | Callers authenticate with a LangSmith API key |
| `tools/support.py` | Parameterized SQL tools over `data/techhub.db` |
| `middleware/customer_scope.py` | Verified-customer prompt and customer-scope guard (sync and async). Identity claims win over run context |
| `middleware/fault_tolerance.py` | Retries, a fallback chain (`resolve_fallback_models()`: Claude Sonnet 5.5, then the small model), and call limits |
| `schedules/_demo/` | Parked weekday digest. Move it to `schedules/` to provision the cron |
| `evals/` | Harbor evals: `harbor-job.json` + 3 tasks (own-order status, cross-customer refusal, return-policy grounding). See `evals/README.md` |

Customer data is deliberately **not** in the sandbox: code execution would bypass the tool-level guard.
