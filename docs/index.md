# Documentation

The hub for cite-citadel's docs. Start with the [README](../README.md) for the pitch and
quickstart; come here when you know what you want to do.

## I want to…

| I want to… | Read |
|------------|------|
| Install it and build my first wiki | [README — Quickstart](../README.md#quickstart) |
| Configure the knobs / run a local model | [configuration.md](configuration.md) |
| Hook up an AI client (Claude Desktop, Claude Code, …) over MCP | [mcp.md](mcp.md) |
| Fix something that's broken | [troubleshooting.md](troubleshooting.md) |
| Understand the OKF page format | [okf-reference.md](okf-reference.md) |
| Read the founding idea | [karpathy-llm-wiki.md](karpathy-llm-wiki.md) |
| Contribute | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Understand how it works inside (the contributor/agent bible) | [CLAUDE.md](../CLAUDE.md) |

## What's here

```
docs/
├── index.md               ← you are here
├── configuration.md       every CITADEL_* env var + local-model (Ollama) recipes
├── mcp.md                 wire the MCP server into an AI client
├── troubleshooting.md     symptom → cause → fix; leads with `citadel doctor`
├── okf-reference.md       the Open Knowledge Format the wiki pages use
└── karpathy-llm-wiki.md   the LLM-Wiki pattern this implements
```

The rules the ingest agent actually follows live in
[`citadel/rules/`](../citadel/rules/README.md) (packaged with the wheel), not here.
</content>
