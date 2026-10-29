# Architecture

How the pilot platform is put together. Sources: `docs/product/pilot-spec.md`, the decision log (`docs/architecture/Decision/pilot-decisions.md`, D1 to D37) and ADR 0001 (`docs/adr/0001-job-queue-and-tenancy.md`). Data flows are in `data-flow.md`.

**Legend.** Solid green boxes exist on `main` today. Dashed grey boxes are planned and tracked in the GitHub issues named in the status table at the end. Nothing here is built that the table does not say is built.

## 1. System overview

Two portals in one Django application. Everything the application knows about the outside world goes through four ports, each a single module with a fake used in tests. Each client company's data is isolated inside Postgres.

```mermaid
flowchart TB
  subgraph users["People"]
    owner["Client owner<br/>approves and submits invoices"]
    staff["Client staff<br/>drafts and uploads"]
    acct["Firm accountant<br/>reviews, corrects, exports"]
  end

  subgraph platform["Platform, hosted in a Malaysian region"]
    web["Django web app<br/>server-rendered pages, HTMX, Alpine.js<br/>client portal in English and Chinese, firm portal in English"]

    subgraph modules["Application modules"]
      ten["Tenancy, roles, audit trail"]
      inv["Invoicing<br/>customers, numbering, approval, PDF"]
      docs["Documents<br/>upload, classify, extract, review"]
      exp["Checklist, reminders, SQL Account export"]
      asst["Assistant<br/>four backend functions"]
    end

    jobs["Job queue and worker<br/>Postgres-backed, no broker"]

    subgraph ports["Ports: the only way out"]
      pgw["MyInvois gateway"]
      pai["AI provider"]
      pem["Email"]
      pst["Object storage"]
    end

    db[("Postgres 16<br/>row-level security per company")]
    store[("Object storage<br/>S3-compatible, Malaysia")]
    vault["Key vault<br/>signing key"]
  end

  lhdn["LHDN MyInvois"]
  aiext["AI provider service"]
  mail["Email service"]
  sqlacc["SQL Account<br/>on the firm's side"]

  owner --> web
  staff --> web
  acct --> web

  web --> ten
  web --> inv
  web --> docs
  web --> exp
  web --> asst

  ten --> db
  inv --> db
  docs --> db
  exp --> db
  asst --> db

  inv --> jobs
  docs --> jobs
  exp --> jobs
  jobs --> db

  jobs --> pgw
  jobs --> pai
  jobs --> pem
  inv --> pst
  docs --> pst
  asst --> pai

  vault --> pgw
  pgw --> lhdn
  pai --> aiext
  pem --> mail
  pst --> store
  acct -. "imports the monthly file by hand" .-> sqlacc

  classDef built fill:#d4edda,stroke:#2e7d32,color:#000
  classDef planned fill:#f4f4f4,stroke:#888,stroke-dasharray:5 3,color:#333
  class web,jobs,db built
  class ten,inv,docs,exp,asst,pgw,pai,pem,pst,store,vault planned
```

What "built" means above: the Django app with a health page and a sign-in-only home page, the job queue, Postgres, and the port registry with fakes. The four real adapters and every business module are still to do.

## 2. Rules the shape depends on

| Rule | Where it comes from | What it forces |
|---|---|---|
| External services only through the four ports | Hard rule in `CLAUDE.md`, from the spec's "External ports" decision | Swapping the AI provider or MyInvois library never touches callers; tests use fakes |
| Every business table has a company id and row-level security | D11 | Isolation is enforced by the database, not only by queries in code |
| Jobs carry a company id and run under that company's context | D36, ADR 0001 | A worker role claims jobs across companies but sets the tenant context from the job's column, never its payload |
| Only the owner approves and submits | D17 | Staff and the assistant can only draft |
| The model never touches the database | D26 | The backend runs four functions on the model's behalf with the user's permissions |
| Signing key lives in a key vault | D13 | Only the signing code can read it, and every signing is logged |
| Database and files in Malaysia | D12 | Hosting region is a fixed choice; AI processing in-region is preferred, not required (D3) |

## 3. Database roles and trust boundary

The job table is the one place where the web side and the worker side meet (ADR 0001, D36). Two roles keep that safe.

```mermaid
flowchart LR
  req["Web request<br/>signed-in user, one company"]
  web["Web role<br/>subject to row-level security"]
  jobs[("Job table<br/>company id column, identifiers only")]
  worker["Worker role<br/>claims across companies<br/>not owner, not superuser"]
  ctx["Set company context<br/>from the job's company id column"]
  handler["Handler<br/>reads and writes under that company's policy"]
  tenant[("Business tables<br/>company id, row-level security")]

  req --> web
  web -->|"queues and sees only its own company's jobs"| jobs
  worker -->|"claims with SKIP LOCKED"| jobs
  worker --> ctx
  ctx --> handler
  handler --> tenant

  classDef planned fill:#f4f4f4,stroke:#888,stroke-dasharray:5 3,color:#333
  class req,web,jobs,worker,ctx,handler,tenant planned
```

Today the job table has no company id and no row-level security. That is acceptable only because no tenant data exists yet; the column, policy and roles arrive with ticket 02 (#3), and no handler may touch tenant data before then.

## 4. Deployment view (planned)

```mermaid
flowchart LR
  dev["Developers<br/>Docker Compose locally"]
  gh["GitHub<br/>main is protected: pull request,<br/>backend and image checks required"]
  ci["GitHub Actions<br/>check, migration drift, pytest,<br/>image build"]

  subgraph region["Malaysian cloud region"]
    subgraph staging["Staging, uses MyInvois sandbox"]
      sweb["Web and worker containers"]
      sdb[("Managed Postgres 16")]
      sstore[("Object storage")]
      svault["Key vault<br/>sandbox certificate"]
    end
    subgraph prod["Production, uses MyInvois production"]
      pweb["Web and worker containers"]
      pdb[("Managed Postgres 16<br/>backup copied to a second zone")]
      pstore[("Object storage")]
      pvault["Key vault<br/>production certificate"]
    end
  end

  dev -->|"branch and pull request"| gh
  gh --> ci
  ci -->|"deploy from main"| sweb
  sweb --> sdb
  sweb --> sstore
  svault --> sweb
  pweb --> pdb
  pweb --> pstore
  pvault --> pweb

  classDef planned fill:#f4f4f4,stroke:#888,stroke-dasharray:5 3,color:#333
  classDef built fill:#d4edda,stroke:#2e7d32,color:#000
  class dev,gh,ci built
  class sweb,sdb,sstore,svault,pweb,pdb,pstore,pvault planned
```

Sandbox and production use different signing certificates (D13). Staging and production both live in the Malaysian region (D12); the cloud provider is not yet chosen, AWS Malaysia being the working assumption.

## 5. Status

| Part | State | Tracked in |
|---|---|---|
| Django app, health page, translation, CI, image build | Built, on `main` | #2 (closed) |
| Port registry and fakes; Postgres-backed job queue with identifier-only payloads | Built, on `main` | #2 |
| Companies, roles, audit, row-level security, job company id and role split | Planned | #3 |
| MyInvois gateway and sandbox spike | Planned | #4 |
| Malaysian hosting, staging, key vault, backups, email domain | Planned | #5 |
| AI port and extraction harness | Planned | #6 |
| Invoicing, documents, review, export, checklist, assistant, onboarding | Planned | #7 to #24 |
| Job leases, retries, idempotent external calls | Planned | #27 |
