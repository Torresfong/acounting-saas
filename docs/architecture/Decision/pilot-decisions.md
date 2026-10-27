# Pilot decision log

Decisions settled in the grilling session of 2026-10-27, on the MVP pilot proposal of 2026-10-09. The product spec is in `docs/product/pilot-spec.md`. Each entry gives the decision and the reason.

## Company and legal

| # | Decision | Why |
|---|---|---|
| D1 | Our company acts as the MyInvois intermediary, not the firm's. | The platform is our product, and holding the intermediary role keeps the client relationship and the commercial position with us. |
| D2 | A Malaysian lawyer reviews the service agreement, the AI and cross-border consent text and the AI data processing agreement by week 12. No client signs before that review. | The pilot sends client documents to an AI provider, possibly abroad, and signs invoices on clients' behalf. |
| D3 | AI processing in Malaysia is preferred, not mandatory. Client consent plus a no-training data processing agreement is the baseline, and the cross-border transfer is named in the consent text and the service agreement. | A mandatory in-region rule would rule out most capable providers. It becomes a hard filter only if the firm or a client requires it. |
| D4 | Records are kept at least 7 years under a written retention agreement. Each client gets a full data export if the pilot ends. | LHDN expects tax records to be kept; clients must never be locked in. |

## Schedule and scope

| # | Decision | Why |
|---|---|---|
| D5 | Week 1 starts 2026-10-27. Target gates: 2026-11-09, 2027-01-25 and 2027-02-22. | Dates follow the 17-week plan. |
| D6 | The schedule may slip, with a hard outer limit of about 2027-04-27 (6 months). If Gate 2 slips past week 18, stop and review before hardening. | Lateness is acceptable, but unlimited slip turns the gates into decoration. |
| D7 | Gate 3 moves day for day with the signing certificate and intermediary approval. It is never declared on sandbox results. | The certificate lead time is outside the team's control. |
| D8 | Nothing is cut from scope, including the AI assistant. No cut order is defined. | Decided by the product owner: the whole proposal ships, and time gives instead. |
| D9 | Build in vertical slices, MyInvois first, demoed to the firm by week 6. The assistant comes last. | MyInvois is the riskiest part and everything else depends on it. |

## Stack and operations

| # | Decision | Why |
|---|---|---|
| D10 | Django with server-rendered pages, HTMX and Alpine.js, on Postgres 16, with a Postgres-backed job queue and no broker. Replaces the scaffolded FastAPI and Nuxt. | Both developers know basic Python and Postgres, and neither knows Vue or Nuxt. Django adds auth, migrations, forms and translation, and the scaffold was empty so switching was free. |
| D11 | Company isolation uses Postgres row-level security from the first migration. | The proposal promises separate data per company, so the database itself must enforce it. |
| D12 | Hosting is a Malaysian-region public cloud with managed Postgres, probably AWS Malaysia. Daily backups are copied to a second Malaysian zone. | Keeps the residency promise. Service availability in the region is to be confirmed in week 1. |
| D13 | The signing key lives in a key vault, never in the repository, the environment file or a laptop. Sandbox and production use different certificates. Every signing is logged. | One leaked key would compromise every client's invoices. |
| D14 | All MyInvois calls sit behind one module. A two-week sandbox spike comes first. If there is no accepted sandbox submission by week 3, it becomes the top risk. A paid review session with someone who has integrated MyInvois comes before Gate 1. | Nobody on the team has built a government API integration. |
| D15 | Extraction uses a vision-capable model with structured output and no separate OCR engine at first. The provider is chosen in the weeks 1 to 2 sample test. | Fewer parts for two developers. The AI port stays swappable. |
| D16 | Support is business hours, with a one-working-day response target and a weekly developer rotation. If MyInvois is down, submissions queue and the owner sees a status banner. | Real clients and real invoices need a named response path, and silent failure is risky with LHDN's validity window. |

## Product rules

| # | Decision | Why |
|---|---|---|
| D17 | Three roles: client owner, client staff, firm accountant. Only the owner approves and submits. No delegation. | Keeps responsibility clear and the audit trail simple. Delegation waits until after the pilot. |
| D18 | The platform is the only invoice issuer for a client after go-live. Numbering is gapless per company and document type, with an owner-set prefix and starting number. | Two issuers would produce duplicate numbers in LHDN and in SQL Account. |
| D19 | Buyer details are copied onto an invoice at approval and locked. | A later customer edit must never change a submitted invoice. |
| D20 | Documents move through fixed states: uploaded, quality-checked, classified, extracted, in review, verified, exported, with returned-for-re-upload and rejected as side states. Only verified documents are exported. The blurry or cropped check runs during the upload. | Bounce within seconds, and no unchecked data in the books. |
| D21 | Exported documents are locked. Later cancellations or corrections appear as new items in the next batch with a "changed after export" flag. No document is exported twice. | Avoids duplicates and silent edits in SQL Account. |
| D22 | Reminders go out on day 3, 7 and 14 after the due date, then stop and flag the accountant. The accountant can pause reminders. | Chasing without nagging the client forever. |
| D23 | The invoice PDF carries the MyInvois QR code and validation link. Email is sent from the platform's domain with the client's name and reply-to. | A validated invoice normally carries both, and using each client's domain is not realistic. |
| D24 | The default exchange-rate source is the Bank Negara Malaysia daily reference rate, unless the firm's SQL Account uses another. | The platform and SQL Account must agree on the rate. To be asked in week 1. |
| D25 | The SQL Account export format is designed only after the firm has hand-built a file that its own SQL Account accepted. The firm names an owner for this by 2026-11-06. | An unverified format would be rework. |

## Assistant

| # | Decision | Why |
|---|---|---|
| D26 | The assistant never touches the database. It has four functions: search customers, propose create customer, propose amend customer, and save draft. The backend runs each with the signed-in user's permissions and row-level security, and sends the model only the minimum data. | Limits the damage from a wrong or manipulated model, and limits what is sent to the provider. |
| D27 | The assistant can create and amend customers only through a human-confirmed before-and-after screen, with the TIN validated with MyInvois first. Staff may confirm creating a customer. Only the owner may change a TIN, legal name or registration number. | Customer records feed the legal buyer details on an LHDN invoice. This reverses the proposal's exclusion of assistant-created customers and is an accepted scope increase. |
| D28 | The assistant cannot delete customers, approve or submit invoices, or choose an uncertain tax. Text in uploaded documents is data, never instructions, and extraction output must pass schema validation. Every assistant action is logged. | Highest-risk actions stay with people, and a crafted document cannot steer the model. |

## Success measures

| # | Decision | Why |
|---|---|---|
| D29 | Targets accepted as defined: every pilot client has an accepted production e-invoice; one full month imported into SQL Account; 95% or more accepted on first submission (real client invoices only); 80% or more needing no correction, per document type on actual uploads including phone photos; accountant time per document at least halved. A miss on one target is a partial result with a stated cause. | Precise definitions make the targets measurable. |
| D30 | The time baseline is at least 40 documents, timed by week 8 and re-timed on the same set after go-live. | A fair before-and-after comparison. |
| D31 | Each pilot owner states a monthly price they would pay at go-live and again at the end. | A cheap commercial signal at no scope cost. |
| D32 | The firm commits a lead accountant and a named backup, with weekly hours in writing. We shortlist 5 clients and aim to sign 3 to 4, each with a named owner contact by 2026-11-09. | One reviewer is a single point of failure, and one dropout should not cost a target. |

## Testing

| # | Decision | Why |
|---|---|---|
| D33 | Three test seams: the web application's HTTP interface with the job runner in-process and four faked ports (seam 1); MyInvois sandbox contract tests (seam 2); an extraction regression harness on the firm-approved sample set (seam 3). CI blocks merges on failures. | Highest-level tests, few seams, and the regression set doubles as evidence for the 80% target. |

## Repository and process

| # | Decision | Why |
|---|---|---|
| D34 | Issues and specs live as GitHub issues in `Torresfong/acounting-saas`, using the `gh` CLI. The pilot spec itself is kept as a file in `docs/product/`. | The remote already exists and Issues are enabled. |
| D35 | The repository is a multi-context monorepo with `backend/` and `frontend/` as the contexts, recorded in `docs/agents/domain.md`. | Stated by the product owner. To be revisited if `frontend/` is dropped under the Django stack. |

## Still open

- The AI provider, decided by the weeks 1 to 2 sample test.
- The SQL Account version, import method and file format.
- The exchange-rate source the firm uses today.
- The price after the pilot.
- Whether our company is a registered Malaysian company LHDN will accept as an intermediary. This is assumed, not confirmed.
- Whether AWS Malaysia offers the managed services we need. This is assumed, not confirmed.
- The ticket breakdown: 22 slices drafted, waiting on answers about granularity, blocking edges and publishing.
