---
description: Build a family money plan (budget by phase, emergency fund, children's goals, home loan, independence age) from a short interview
argument-hint: "[plan name, or path to an existing plan.json]"
---

Use the `mf-portfolio-analyser` skill's **family plan** workflow (see `references/plan.md`). Input, if given: $ARGUMENTS

Run the scripts from `${CLAUDE_PLUGIN_ROOT}`. In short:
1. If `$ARGUMENTS` is an existing `plan.json`, read it and go to step 4. Otherwise run `python3 -m mfpa plan --init <name>` (default name `family`).
2. Ask the 10 core questions from `references/plan.md`, in two or three short messages, multiple choice where possible. Offer `--from-run` if a fund analyser run exists.
3. Write the answers into the plan file. Leave everything else at its default; defaulted fields are tagged as guesses on the page.
4. Run `python3 -m mfpa plan --file <plan.json>` (add `--from-run <run dir>` if chosen).
5. Summarise: base and stress independence ages with the disclaimer beside them, the emergency fund and term-cover gap, the two levers that move the age most, and the guesses that matter most. Then offer the refine pass and the page.

Never publish the page. If the user wants to share it, build `--share`, show them what it contains, and publish only on their yes.
