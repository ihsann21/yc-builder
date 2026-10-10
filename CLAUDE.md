# yc-builder

Freya × YC "Build the Builder" hackathon (10–11 Oct 2026). Design: `build_the_builder_final_plan.md`. Organizer kit: `build-the-builder-v3/build-the-builder/`.

## Progress log (always)

- Keep `PROGRESS.md` up to date. After every notable step (a measurement, a decision, a new file or module, a fix, a lesson, an answer from the organizers), add a short dated paragraph at the end, in Turkish, in the existing style. Update its "Kararlar", "Açık sorular" and "Sıradaki" sections when they change.
- Record numbers exactly as measured (score, reps, duration, cost) and say when something was not measured.
- Before ending a work session, check that `PROGRESS.md` reflects what was done.

## Hard rules

- Never read, print or log `env.sh` or any API key. Traces and logs must not contain secrets; scan for `fak_` and the team key before committing.
- Never write a value, rule or name taken from a specific brief into builder code, prompts or skills. Fixes go to mechanisms, not to a brief.
- One simulation runs at a time per workspace: do not start a second `run_cases.py` while one is running.
