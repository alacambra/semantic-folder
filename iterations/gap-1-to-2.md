---
document_id: GAP-1-TO-2
version: 1.0.0
last_updated: 2026-02-22
purpose: Document commits between IT-1 tag (v0.1.0) and IT-2 start
---

# Gap: IT-1 → IT-2

## Untracked Commits

| Commit    | Date       | Author    | Message                                                   |
| --------- | ---------- | --------- | --------------------------------------------------------- |
| `16ad9c1` | 2026-02-22 | alacambra | fix: tighten .funcignore and add make requirements target |

## Change Details

### 16ad9c1 — fix: tighten .funcignore and add make requirements target

**Files changed:** `.funcignore`, `Makefile`

**Changes:**

- Added `*.docx`, `.venv/`, `local.settings.json`, `.coverage`, `.env.local` to `.funcignore` — prevents accidental inclusion of local-only files in Azure deployment package
- Added `make requirements` target (`poetry export --without-hashes --only main -o requirements.txt`) — ensures `requirements.txt` stays in sync with `poetry.lock` before deployment
- Made `make deploy` depend on `make requirements` — enforces correct build order

**Classification:** Post-iteration fix — addresses deployment hygiene issues discovered after IT-1 validation. These changes are extensions of IT-1 deliverables D1 (project structure) and D5 (local development workflow) rather than new functionality.

**Traceability:** Covered retroactively by IT-1 OUT document (it-1.out.md) which already describes both `.funcignore` and `make requirements` as part of the delivered workflow. The tag `v0.1.0` was created before this fix commit.

**Action required:** None — changes are self-contained and do not affect IT-2 scope or design.
