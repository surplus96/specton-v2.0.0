# Dependency security

[![한국어](../assets/lang-ko.svg)](../ko/dependency-security.md) [![English](../assets/lang-en.svg)](../en/dependency-security.md)

## Review scope

The review dated 2026-11-18 separates the platform frontend, API ERD renderer, generated-app frontend build tools, and browser verification worker. Audit package counts include advisories propagated to parent packages; they are not counts of distinct vulnerabilities. This review does not replace OS package scanning or penetration testing.

## Security updates

| Component | Action | Reference |
|---|---|---|
| Platform Python | Pin OpenTelemetry API to 1.45.2 | [OpenTelemetry advisory](https://github.com/advisories/GHSA-mf5v-w3w3-f6cg) |
| TypeScript checks | Use fixed minimatch 11 through the official typescript-eslint 8.73 dependency tree | [minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249) |
| Web/PDF ERD | Lock Mermaid 12.3.0, CLI 12.2.0, and KaTeX 0.18.10 | [KaTeX advisory](https://github.com/advisories/GHSA-238p-pmpm-9mq7) |

Validate the Mermaid major upgrade through frontend type checks, tests, builds, and real PDF/ERD rendering. Update web and PDF versions together without forcing transitive dependency overrides. Use Node.js 22.13.0 or later.

## Remaining picomatch advisory

[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) is a High advisory affecting versions through 4.0.7: attacker-controlled extglob patterns can cause excessive regular-expression processing. No official patched version was available at review time. It remains in platform development tools and generated-app Vite build dependencies, so full npm audits still report findings.

The service does not pass requirement documents, customer email, or executable specifications as glob patterns. The deployed platform serves a static web bundle rather than a Vite development server. Generated apps build a fixed frontend template and include approved design configuration through a fixed `contract.json` import. Verification workers run fixed commands with limited container resources. CI jobs also have time limits.

The review is complete for this boundary; it does not establish that the package is patched or that every attack path is eliminated. Accepting user-supplied globs, Vite configuration, plugins, or arbitrary frontend source invalidates this assessment. Do not run development servers from untrusted repositories on production hosts.

The maintainer must review this advisory again at the next dependency update or by 2026-12-18, whichever comes first. When a fix is available, validate both the platform and generated template. Do not retroactively alter files or hashes in approved delivery ZIPs; manage template changes as new versions.

## Verification

```bash
npm --prefix frontend audit --json
npm --prefix frontend audit --omit=dev --audit-level=low
npm --prefix specton/implementation/templates/frontend audit --package-lock-only --json
npm --prefix docker/browser audit --package-lock-only --json
docker build --target check .
```

To audit the renderer, copy `docker/api/mermaid-package.json` and `mermaid-package-lock.json` into a temporary directory as `package.json` and `package-lock.json`, then run `npm audit --package-lock-only --omit=dev`. CI fails on advisories in platform web and renderer production dependencies. The picomatch exception for development dependencies and generated templates is limited to the scope above and does not accept new advisories by default.

---

[Documentation](README.md) · [Project](../../README.en.md)
