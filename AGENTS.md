# HostInclusion

<!-- What this is, in one or two lines. Replace this. -->

## Running and testing

<!-- The exact commands. An agent that cannot run the tests cannot verify its
     own work, and will confidently tell you it is done. -->

```bash
# install:
# test:
# run:
```

## Decisions that must not change silently

<!-- Language, framework, datastore, anything with a reason behind it.
     If it is not written here, an agent will treat it as negotiable. -->

## Knowledge pointers

Read `~/knowledge/index.md` first — it is the map. Follow links to what the task
needs; do not preload. These are pointers, not content.

- `~/knowledge/concepts/` — cross-domain concepts, interlinked
- `~/knowledge/domains/ai-engineering/index.md` — agent and context patterns

This section is here because it is not inherited. `~/dev/AGENTS.md` does not load
inside a project repo — discovery stops at this repo's git root — so every project
carries its own copy of these pointers.

## Model tier

Default is Tier 2 (Gemini Flash). Escalate to Tier 3 (Claude) only for
architecture decisions, multi-document synthesis, or debugging that has already
failed once at Tier 2. Never run background or bulk work at Tier 3.

## Conventions

- Tests accompany features. A change that cannot be demonstrated is not done.
- Smallest change that solves the problem. No speculative abstraction.
- Secrets live in an ignored env file, never in source.
- Match the surrounding style over any personal preference.
