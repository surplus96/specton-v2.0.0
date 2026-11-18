# Frontend development

[![한국어](../assets/lang-ko.svg)](../ko/frontend.md) [![English](../assets/lang-en.svg)](../en/frontend.md)

The platform uses React 19, TypeScript, Vite, custom CSS, React Flow, and Mermaid. It calls APIs rather than running PostgreSQL or LangGraph directly. Styling tokens live in `frontend/src/index.css`, shared elements in `frontend/src/ui/`, and pages in `frontend/src/pages/`.

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
npm --prefix frontend run dev:mock
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run check:api
npm --prefix frontend run build
```

`dev:mock` supplies synthetic UI responses and is not evidence of real design generation, Gmail access, or app verification. `dev` proxies the API on port 8000 by default; `VITE_DEV_API_ORIGIN` overrides the development target.

## Implemented screens

| Route | Capability | Implementation |
|---|---|---|
| `/projects` | Projects and approved-design links | [Page](../../frontend/src/pages/ProjectsPage.tsx) |
| `/specifications/:specId` | Specs, contracts, acceptance, source, verification, preview | [Page](../../frontend/src/pages/SpecificationPage.tsx) |
| `/projects/:projectId/candidates` | Candidate comparison and adoption | [Page](../../frontend/src/pages/CandidatesPage.tsx) |
| `/feedback` | Gmail connection, sync, messages, changes | [Page](../../frontend/src/pages/FeedbackPage.tsx) |
| `/changes/:changeId` | Impact analysis, review, contract edits, approval, retests | [Page](../../frontend/src/pages/ChangePage.tsx) |

The customer app UI is built from approved screen/API/role contracts. Platform specification/change pages and customer business screens are separate frontends. Customer UI provides record creation/listing/editing/transitions, relationship selection, multi-record commands, calculation results, and separate login. Visual-spec interpretation is outside the [supported scope](roadmap.md).

## Pages and state

The flow connects projects, document analysis/review, approved designs, executable specs, verification/previews, and candidate adoption. Customer mail connects to change requests. Keep ready, queued, running, failed, unverified, and passed states distinct. API failures must remain visible. Preserve run revisions/spec versions and avoid mixing evidence from different versions.

`src/api/client.ts` handles cookies, CSRF, and errors. OpenAPI types are generated into `src/api/schema.d.ts`; update the root schema and run `gen:api` instead of editing generated types. HTTP and SSE assume same-origin deployment. Cross-origin hosting requires additional server CORS and cookie policy.

Generated customer apps use separate code in `specton/implementation/templates/frontend/`. Platform UI changes do not modify existing customer ZIPs. Template changes require new packages, real browser verification, and compatibility checks.

Pretendard is served locally with its [OFL notice](../../frontend/public/fonts/OFL.txt). Korean/English documentation buttons are Markdown links, not a complete product UI localization feature.

---

[Documentation](README.md) · [Project](../../README.en.md)
