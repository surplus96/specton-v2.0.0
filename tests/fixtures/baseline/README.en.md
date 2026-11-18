# Deterministic baseline input v1

[![한국어](../../../docs/assets/lang-ko.svg)](README.md) [![English](../../../docs/assets/lang-en.svg)](README.en.md)

`inventory-v1.json` is synthetic and contains no customer documents. Three warehouse/item/receipt statements repeat with SYN source IDs to produce 20, 200, or 1,000 CSV blocks. The model stays fixed at four tables and three foreign keys.

The measured path runs the real CSV parser, constructs fixed design data, normalizes with real packs, and generates function specifications, ERDs, DDL, and RTM CSV/XLSX. It excludes LLM interpretation, DB execution, PDF, API load, browsers, and generated business apps. A 1,000-block input is not a 1,000-entity benchmark.

`expected-v1.json` preserves initial artifact bytes/hashes, model/pack hashes, and trace counts. Independent structural assertions check four tables, three FKs, and complete source linkage. CI compares these expectations rather than rewriting them. Intentional output-contract changes need a new fixture version and independent rationale.

```bash
uv run python -m specton.evaluation.baseline --repeats 30
uv run python -m specton.evaluation.baseline --repeats 1 --sizes 20
```

After one warmup, results in ignored `var/baseline/report.json` include p50/p95/max duration, process-wide peak RSS, and input/code/lock hashes. Peak RSS is not per-case incremental memory. Execution errors or hash mismatches return exit code 1; expectations are not updated automatically. Run from the repository root.
