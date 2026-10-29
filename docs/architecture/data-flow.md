# Data flow

How data moves through the pilot platform. Sources: `docs/product/pilot-spec.md`, the decision log (D1 to D37) and ADR 0001. The structure is in `architecture.md`. Almost everything here is **planned**; only the job queue, the port registry with fakes, and the health and home pages exist on `main`.

Where the spec does not fix a detail, the diagram says "assumption" and names the ticket that settles it.

## 1. Level 0: the system and the outside world

```mermaid
flowchart LR
  client(["Client owner and staff"])
  firm(["Firm accountant"])
  lhdn(["LHDN MyInvois"])
  ai(["AI provider"])
  mail(["Email service"])
  buyer(["Client's customer<br/>the buyer"])
  sqlacc(["SQL Account"])

  sys["Pilot platform"]

  client -->|"invoice drafts, approvals, customer details, uploaded documents, tax and currency choices"| sys
  sys -->|"invoice status, document status, requests and reminders"| client

  firm -->|"corrections, verification, checklists, requests"| sys
  sys -->|"documents per client and month, extracted fields, monthly export file"| firm
  firm -.->|"imports the file by hand"| sqlacc

  sys -->|"signed invoice, status polls, cancellations"| lhdn
  lhdn -->|"validation result, buyer rejection requests"| sys

  sys -->|"document images or text, minimum customer data"| ai
  ai -->|"structured fields, function requests"| sys

  sys -->|"validated invoice PDF, reminders"| mail
  mail -->|"delivered to"| buyer
  buyer -.->|"may ask LHDN to reject"| lhdn
```

## 2. Level 1: processes and data stores

Numbered processes (P), data stores (D). Every process runs inside one company's context; every store holds a company id and sits under row-level security, except the job table until ticket 02 gives it a company id (ADR 0001).

```mermaid
flowchart TB
  client(["Client owner and staff"])
  firm(["Firm accountant"])
  lhdn(["LHDN MyInvois"])
  ai(["AI provider"])

  p1["P1 Maintain customers"]
  p2["P2 Draft, approve and submit invoices"]
  p3["P3 Receive and check uploads"]
  p4["P4 Classify and extract"]
  p5["P5 Review and verify"]
  p6["P6 Chase missing documents"]
  p7["P7 Build monthly export"]
  p8["P8 Assistant"]

  d1[("D1 Customers")]
  d2[("D2 Invoices and numbering")]
  d3[("D3 Documents and extracted fields")]
  d4[("D4 Checklists and requests")]
  d5[("D5 Audit trail")]
  d6[("D6 Files<br/>object storage")]
  d7[("D7 Job queue")]

  client --> p1
  p1 <--> d1
  client --> p2
  p2 <--> d2
  d1 -->|"buyer details copied at approval"| p2
  p2 --> d7
  d7 -->|"submit and poll"| lhdn
  lhdn -->|"result"| d7
  d7 --> d2

  client --> p3
  p3 --> d6
  p3 --> d3
  p3 --> d7
  d7 --> p4
  p4 <--> ai
  p4 --> d3

  firm --> p5
  d3 --> p5
  d6 --> p5
  p5 --> d3

  firm --> p6
  p6 <--> d4
  p6 --> d7
  d7 -->|"reminder emails"| client

  d2 --> p7
  d3 -->|"verified only"| p7
  p7 --> firm
  p7 -->|"marks exported, locks"| d3
  p7 -->|"marks exported, locks"| d2

  client --> p8
  p8 <--> ai
  p8 -->|"find customer"| d1
  p8 -->|"save draft"| d2
  p8 -->|"proposal, after human confirmation"| d1

  p1 --> d5
  p2 --> d5
  p5 --> d5
  p7 --> d5
  p8 --> d5

  classDef planned fill:#f4f4f4,stroke:#888,stroke-dasharray:5 3,color:#333
  classDef built fill:#d4edda,stroke:#2e7d32,color:#000
  class p1,p2,p3,p4,p5,p6,p7,p8,d1,d2,d3,d4,d5,d6 planned
  class d7 built
```

## 3. E-invoice: from draft to delivered

Only the owner approves and submits (D17). Approval locks a copy of the buyer details on the invoice (D19). The signing key is read only by the signing code (D13).

```mermaid
sequenceDiagram
  autonumber
  actor Staff as Client staff
  actor Owner as Client owner
  participant App as Web app
  participant DB as Postgres
  participant Q as Job queue and worker
  participant GW as MyInvois gateway port
  participant KV as Key vault
  participant L as LHDN MyInvois
  participant EM as Email port

  Staff->>App: draft invoice from customer master
  App->>DB: save draft, audit entry
  Owner->>App: review and approve
  App->>DB: allocate number, copy buyer details, lock invoice, audit entry
  Note over App,DB: assumption: the number is allocated at approval so a discarded draft leaves no gap. Settled in ticket 07 (#8).
  App->>Q: queue "submit" with ids only
  Q->>DB: claim job, set company context
  Q->>GW: submit invoice
  GW->>KV: read signing key
  GW->>L: signed document
  Note over GW,L: every signing is logged
  L-->>GW: accepted for validation
  loop until a final status
    Q->>GW: poll status
    GW->>L: status request
    L-->>GW: validated or invalid
  end
  alt validated
    Q->>DB: status validated, keep QR identifiers
    Q->>EM: send English PDF with QR code to the buyer
  else invalid
    Q->>DB: status invalid with LHDN's reasons
    App-->>Owner: show reasons, owner corrects and resubmits
  end
  Owner->>App: view live status
```

If LHDN is unavailable, the submit job waits in the queue and the owner sees a status banner (D16). Retries must not create a second invoice at LHDN; the lease and idempotency work for that is ticket #27.

### Invoice states

```mermaid
stateDiagram-v2
  [*] --> Draft
  Draft --> Waiting: staff finishes draft
  Waiting --> Submitted: owner approves
  Draft --> Submitted: owner approves
  Submitted --> Validated: LHDN accepts
  Submitted --> Invalid: LHDN rejects
  Invalid --> Submitted: corrected and resubmitted
  Validated --> Cancelled: supplier cancels inside LHDN's window
  Validated --> RejectedByBuyer: buyer's rejection request
  Cancelled --> [*]
  RejectedByBuyer --> [*]

  state "Waiting approval" as Waiting
  state "Rejected by buyer" as RejectedByBuyer
```

Credit, debit and refund notes follow the same path as separate documents that reference the original (ticket 10, #11).

## 4. Document: from upload to SQL Account

```mermaid
flowchart TB
  up["Client uploads PDF, scan or phone photo"]
  chk{"Quality check<br/>sharp, whole page, readable"}
  bounce["Bounced to the client<br/>with a reason, within seconds"]
  store[("Original stored<br/>object storage")]
  cls["Classify by document type"]
  ext{"Sales invoice,<br/>purchase invoice or receipt?"}
  other["Stored and searchable<br/>accountant keys it as today"]
  ai["Extract fields with the AI provider<br/>schema-validated output"]
  rev["Review queue<br/>fields beside the image"]
  ret["Returned for re-upload<br/>with a reason"]
  ver["Verified"]
  exp["Monthly export per client"]
  lock["Marked exported and locked"]
  imp["Firm imports into SQL Account<br/>and adds account coding"]

  up --> chk
  chk -->|"fails"| bounce
  chk -->|"passes"| store
  store --> cls
  cls --> ext
  ext -->|"no"| other
  ext -->|"yes"| ai
  ai --> rev
  rev -->|"unreadable"| ret
  ret --> up
  rev -->|"correct and verify"| ver
  ver --> exp
  exp --> lock
  exp --> imp

  classDef planned fill:#f4f4f4,stroke:#888,stroke-dasharray:5 3,color:#333
  class up,chk,bounce,store,cls,ext,other,ai,rev,ret,ver,exp,lock,imp planned
```

Only verified documents are exported, never twice (D21). A cancellation or correction after export is exported as a new item in the next batch, flagged "changed after export". Text inside a document is treated as data and never as an instruction to the model (D28).

### Document states

```mermaid
stateDiagram-v2
  [*] --> Uploaded
  Uploaded --> QualityChecked: passes the upload check
  Uploaded --> Returned: blurry, cropped or incomplete
  QualityChecked --> Classified
  Classified --> Extracted: invoice or receipt types
  Extracted --> InReview
  InReview --> Verified: accountant confirms
  InReview --> Returned: unreadable
  InReview --> Rejected
  Returned --> Uploaded: client re-uploads
  Verified --> Exported: included in a monthly batch
  Exported --> [*]
  Rejected --> [*]

  state "Quality-checked" as QualityChecked
  state "In review" as InReview
```

## 5. Assistant: what the model can and cannot do

The model has no database connection (D26). It sees only what the backend puts in the request, and it can only ask the backend to run four functions with the signed-in user's permissions (D27, D28).

```mermaid
sequenceDiagram
  autonumber
  actor U as Client user
  participant App as Web app
  participant AIp as AI provider port
  participant DB as Postgres
  participant GW as MyInvois gateway port

  U->>App: plain-language description of an invoice
  App->>AIp: the description plus the minimum data needed
  AIp-->>App: asks to run "search customers"
  App->>DB: search, scoped to this company and user
  App->>AIp: only the matching few customers
  AIp-->>App: asks to run "save draft"
  App->>DB: save draft, audit entry with the user
  App-->>U: the draft, with missing mandatory fields asked for

  Note over U,GW: new or changed customer
  AIp-->>App: asks to run "propose create" or "propose amend"
  App->>GW: validate the TIN
  App-->>U: before-and-after screen
  U->>App: confirm
  App->>DB: write customer, audit entry
  Note over U,DB: staff may confirm a new customer. Only the owner may confirm a change to TIN, legal name or registration number.
```

Not available to the model, by design: delete a customer, approve or submit an invoice, choose a tax when uncertain.

## 6. Job queue

```mermaid
flowchart LR
  req["Request or schedule"]
  enq["enqueue<br/>accepts ids and short references only"]
  job[("Job table<br/>pending, done, failed")]
  claim["Worker claims the oldest pending job<br/>SKIP LOCKED"]
  run["Handler runs<br/>under the job's company"]
  ok["Done"]
  fail["Failed<br/>only the exception class is kept"]
  log["Log line<br/>job id, name, exception class, no content"]

  req --> enq
  enq -->|"refuses content, floats, lists, objects"| req
  enq --> job
  job --> claim
  claim --> run
  run -->|"returns"| ok
  run -->|"raises"| fail
  fail --> log

  classDef built fill:#d4edda,stroke:#2e7d32,color:#000
  classDef planned fill:#f4f4f4,stroke:#888,stroke-dasharray:5 3,color:#333
  class enq,job,claim,run,ok,fail,log built
  class req planned
```

Built today: the enqueue check, the table, claiming, the identifier-only payload rule and the no-content failure record. Planned: the company id column and policy (ticket 02, #3); leases, retries, backoff, idempotent external calls and a purge of old jobs (#27).

## 7. What leaves the platform

| Data | Goes to | When | Control |
|---|---|---|---|
| Signed invoice | LHDN MyInvois | Owner approves | Signing key from the key vault; separate sandbox and production certificates; every signing logged (D13) |
| Document images or text | AI provider | After upload, for invoices and receipts | Client consent, a no-training data processing agreement, in-region preferred (D3); output schema-checked |
| Minimum customer data and the user's description | AI provider | When the assistant is used | Only matching customers are sent; the model has no database access (D26) |
| Validated invoice PDF | The client's customer, by email | After LHDN validates | Sent from the platform's domain under the client's name, with the client's reply-to (D23) |
| Reminders | The client, by email | Days 3, 7 and 14 after the due date | Stops after three and flags the accountant (D22) |
| Monthly export file | The firm accountant, who imports it by hand | Per client, per month | Verified documents only, never twice (D21) |
| Originals and database | Stay in the Malaysian region | Always | D12; daily backups copied to a second Malaysian zone |
