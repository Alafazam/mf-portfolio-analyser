---
description: Analyse your mutual fund portfolio from a CAS statement, INDmoney or a CSV and build the report
argument-hint: "[path to CAS PDF, INDmoney JSON or CSV]"
---

Use the `mf-portfolio-analyser` skill to analyse the user's mutual fund portfolio. Input, if given: $ARGUMENTS

Follow the skill's workflow: run `python3 -m mfpa doctor` from `${CLAUDE_PLUGIN_ROOT}`, ask the four setup questions, get the input (never read the CAS PDF or its text yourself; never take the PDF password in chat), run the pipeline in the background, report warnings, summarise the strongest candidate moves with the disclaimer, and offer the HTML report.
