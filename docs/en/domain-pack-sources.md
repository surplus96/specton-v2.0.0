# Pack sources and policy rationale

[![한국어](../assets/lang-ko.svg)](../ko/domain-pack-sources.md) [![English](../assets/lang-en.svg)](../en/domain-pack-sources.md)

This document describes included material and implementation policy. It does not claim standards certification or complete implementations of external products. [sources.yaml](../../domain_packs/sources/sources.yaml) records editions, provenance, and hashes of common CSVs; [lexicon_sources.yaml](../../domain_packs/inventory/lexicon_sources.yaml) records inventory extensions.

## Shared dictionary

The eighth Korean public-data common-standard release supplies frozen word, domain, and term CSV inputs. Original copies and attribution are retained. The builder handles quoted commas and encodings; it does not invent official words or abbreviations from evaluation text.

| Example | Dictionary distinction |
|---|---|
| Date `YMD`, timestamp `DT` | Different classifiers |
| Code `CD`, name `NM`, number `NO` | Terminal classifiers |
| Status `STTS`, classification `SE` | Modifiers combined with a classifier |
| Quantity `QTY`, amount `AMT` | Numeric domains with precision/range |

Word/classifier composition derives from the data, while lowercase snake_case, identifier limits, collision handling, and PK/FK conventions are project policies. Official evidence and local choices are kept distinct.

`strict` retains standard-style character dates, Y/N flags, and numeric representations. `pg_native` selects database-native types through explicit mappings. Shared YAML and the compiler define accepted types, precision, and rules. Official synonyms must have unambiguous provenance; original logical names and diagnostic evidence are retained.

## Inventory and maintenance knowledge

Public inventory CSVs are offline lexical evidence with inclusion/exclusion rationale and hashes. Preserve original bytes. A public dictionary does not establish customer business policy.

The maintenance pack models CMMS concepts such as asset hierarchies, plans, requests, work, history, and inventory links. Prior research used EN 13306 maintenance distinctions and ISO 14224 failure-mode/cause distinctions, but paid standards text is not redistributed. This repository does not claim verified compliance with their latest editions.

Development-example approval covers schema, provenance, and design knowledge. Evaluation inputs/answers do not belong in packs. Results from material already seen by the same author or AI are not independent evaluation. Customer schedules, workflow policy, and row access require separate executable-spec decisions.

## Redistribution and updates

Project code uses [MIT](../../LICENSE); bundled fonts retain [SIL OFL](../../frontend/public/fonts/OFL.txt). Preserve each dataset's attribution and source manifest. An edition change requires provenance, hashes, rationale, a new pack version, regeneration, and regression checks. Never replace historical version hashes with new content.

---

[Documentation](README.md) · [Project](../../README.en.md)
