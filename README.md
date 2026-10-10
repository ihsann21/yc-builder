# yc-builder

Builder for the Freya × YC "Build the Builder" hackathon: reads a bank collections brief and its tool API
file and builds a Freya phone-agent workflow (Claude Agent SDK + `builder/skill/SKILL.md` + the tested
helper library `builder/lib/`).

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt    # Python 3.10 or later
export FREYA_API_KEY=...            # Freya API key (fak_...); FREYA_API_URL optional
export ANTHROPIC_API_KEY=...        # or a logged-in Claude Code on this machine
.venv/bin/python builder/build.py <brief.md> <tool_api.openapi.json>
```

The run takes a few minutes (hard cap 25 minutes, `BUILD_DEADLINE_S`). It prints the trace and writes it
to `traces/<slot>-<time>.log`, saves and publishes the workflow on Freya (updated in place on later runs,
state in `builder/work/.freya-agents.json`) and exports it to `submission/<slot>.workflow.json`, where the
slot is the brief's file name. Exit code 0 only when this run saved and exported a workflow.

## Tests

```bash
.venv/bin/python -m pytest -q        # offline, a few seconds
```

Design and decisions: `PROGRESS.md` and `build_the_builder_final_plan.md`.
