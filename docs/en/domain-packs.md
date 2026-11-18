# Domain packs and document I/O

[![한국어](../assets/lang-ko.svg)](../ko/domain-packs.md) [![English](../assets/lang-en.svg)](../en/domain-packs.md)

## Purpose

Packs provide naming dictionaries, standard domains, business terminology, design patterns, and agent examples prepared before execution. They are not application code or implementations of every business rule. Different domains use their packs and customer designs through the same analysis/specification/generation pipeline.

| Pack | Repository version | Purpose |
|---|---|---|
| `common` | 0.1.8 | Standard words, classifiers, domains, naming and storage policies |
| `inventory` | 0.1.23 | Inventory, materials, and stock transaction terminology/patterns |
| `maintenance` | 0.1.9 | Equipment, maintenance, work, and measurement terminology/patterns |

Each `manifest.yaml` and `pack.lock` is authoritative. `GET /api/v1/packs` checks pack/common schemas, provenance, approval, and hashes. Draft or corrupted packs are rejected during selection and run creation. Display names and descriptions live in `catalog.yaml`.

## Files and updates

| Input file | Purpose |
|---|---|
| `manifest.yaml` | Name, version, provenance, approval |
| `term_specs.yaml`, `words.yaml` | Business term composition and additional words |
| `patterns.yaml`, `examples/A01.yaml`, etc. | Patterns and structured development examples |
| `naming.yaml`, `rules.yaml` | Shared naming/review policy |
| `standard_selection.yaml` | Rationale for selected official synonyms/prohibited terms |
| `lexicon_sources.yaml`, `sources/` | Public dictionary copies, editions, hashes, selection evidence |

The builder owns files marked `GENERATED` and lock records. Check file headers: the same filename may be an input in one pack and generated in another.

1. Increment the affected manifest version; approval-status changes also change content.
2. Edit input YAML and review provenance.
3. Generate and check with the commands below.
4. Review generated terms, shared words/domains, and locks together.

```bash
uv run python -m specton.packs.build
uv run python -m specton.packs.build --check
```

A version cannot identify different content hashes. Preserve encodings and newlines of common-standard CSVs and inventory public sources. The builder validates length, classifiers, domains, and duplicate physical names. See [source rationale](domain-pack-sources.md) for provenance and licensing information.

## Naming and types

Logical and physical names are distinct. Pack policy controls lowercase names, separators, and PostgreSQL identifier length. Generation and verification must use the same `strict` or `pg_native` storage profile. Preserve numeric precision, nullability, composite keys, and relationship provenance. Distinguish official vocabulary, observed practice, and project decisions.

Adding terminology alone does not complete support for a domain. Validate extraction, requirement/function/storage links, supported execution contracts, and normal/boundary/failure cases. Do not copy evaluation answers into few-shot examples.

## Document contracts

Excel/CSV extraction preserves requirement IDs, names, detail columns, sheets, and rows. Supported HWP/HWPX requirement tables preserve section, paragraph, table, and cell locations. Damaged, encrypted, or unextractable inputs are rejected explicitly; extraction failures are not empty successes.

Final artifacts are function specifications (Markdown/optional PDF), ERDs (Mermaid/optional PDF), DDL (SQL), and RTMs (CSV/XLSX). Revision, model, and file hashes identify the same approved version. PDF input/OCR and unrestricted narrative-document interpretation are outside the supported table-input scope.

---

[Documentation](README.md) · [Project](../../README.en.md)
