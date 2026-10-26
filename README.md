# CGTEL: Confidence-Gated Tool Execution Layer

CGTEL intercepts proposed tool calls, calculates a weighted heuristic risk score, routes the call through policy thresholds, and logs execution outcomes. The LLM proposes calls; CGTEL controls whether the simulated tool executes.

## Setup

Requires Python 3.9 or newer. From the repository directory:

```bash
python -m venv .venv
```

Activate the environment (`.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` in Bash), then install:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

The Gemini API key is read only from the environment. Never put it in source code.

```powershell
$env:GEMINI_API_KEY = "your-key"
```

```bash
export GEMINI_API_KEY="your-key"
```

The model defaults to `gemini-flash-latest`; override with `CGTEL_GEMINI_MODEL`.

## Execution flow

```text
Natural language request
    -> LLMAgent proposes tool + arguments
    -> validate tool name and arguments
    -> @gated_tool captures request
    -> confidence + reversibility + historical failure rate
    -> R = w1*V + w2*(1-C) + w3*F
    -> DecisionRouter (approval prompt on HUMAN_REVIEW)
    -> execute only after route allows
    -> OutcomeLogger records result
    -> executed success/failure updates shared failure-rate store
```

`C` on the live path is three-sample self-consistency agreement, passed directly into scoring. Approval occurs in `DecisionRouter`; a denial leaves the function body uncalled. Failure feedback is recorded only for calls that actually execute.

## Commands

```bash
python -m pytest -q
python demo.py
python demo_llm.py --offline
python demo_llm.py
python run_benchmark.py
```

`demo_llm.py` with no argument is live mode and exits nonzero when no key is configured. Live high-risk calls use the interactive router prompt. `--offline` runs the deterministic rule-based proposal flow and labels its scripted reviewer.

Expected excerpts (the actual score/output can include timestamps and elapsed times):

```text
43 passed
OFFLINE FALLBACK - NOT A LIVE LLM RUN
SCRIPTED REVIEWER (demo only): y
Run totals: {'executed': 3, 'denied': 1, 'rejected': 0, 'errors': 0}
```

The benchmark uses synthetic scenarios, a scoring engine, and auto-approval for its routing metric; it does not invoke tools or use live confidence.

## Current limitations

- Self-consistency agreement is a heuristic, not calibrated confidence.
- `R` is a weighted heuristic score, not Bayesian inference or a posterior probability.
- Reversibility classification is keyword based.
- The included tools are simulated fakes; they do not read, delete, or transfer real data.
- The live API path is only verified to the extent of local mocked tests unless the live demo has been run with a configured key and network access.
- Benchmark evaluation uses auto-approval and does not execute tools or use live confidence.
