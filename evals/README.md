# Evaluations

- **Golden use cases** (BUILD_SPEC 8.3): one per Domain Pack in `adef/engine/scenarios.py`
  (sources, target model, business rules, quality rules and governed metrics with known answers).
  `tests/test_lifecycle.py` runs each through all nine agents and every gate and asserts zero failing
  test cases and full requirement traceability.
- **Guardrail scenarios** GT-01..GT-14: `adef/guardrails/gt_suite.py`, runnable with
  `python -m adef suite`, from the console (Guardrails page), and in `tests/test_guardrails.py`.
- **Live-LLM path**: `tests/test_llm_path.py` drives the structured-output contracts with a scripted
  provider, including rejection and repair of a technology-leaking requirement.
