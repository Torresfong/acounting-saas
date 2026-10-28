# 0001: The job queue is a global table, outside row-level security

Status: proposed, pending independent review. Relates to D10 (Postgres-backed queue) and D11 (row-level security).

## Context

D11 says every business table carries a company id and Postgres row-level security enforces isolation. Background work (extraction, MyInvois polling, reminders, exports) is queued in a `Job` table (D10), and jobs will refer to tenant records. A worker polls for pending jobs across all companies.

## Decision

`Job` is a **global system table**: it has no row-level security policy and is exempt from D11. This exemption is narrow and carries these rules:

1. **Identifiers only.** A payload holds a company id and record ids, never document content, names, TINs, amounts or other personal or financial data. Handlers load the data themselves.
2. **No content in errors.** A failed job stores only the exception class name, and the log line carries the job id, job name and class name. Exception messages and tracebacks are not stored or logged, because they often echo tenant content.
3. **Tenant context in handlers.** Once row-level security exists (ticket 02), a job that touches tenant data carries a `company_id` and the handler runs under that company's context, so it cannot read another company's rows even if its payload is wrong.
4. **No exposure.** The job table is not shown in any admin screen, API or report.

## Why not put row-level security on the queue

A single worker must see every tenant's pending jobs to run them with `SKIP LOCKED`. Row-level security on the queue would either hide jobs from the worker or force it to run with a bypass role, which is the same exemption with more machinery. Isolation is enforced where the data lives: in the handler's tenant context.

## Consequences

- A person with direct database access can read job ids and job names, but no tenant content, as long as rule 1 holds. Rule 1 is a convention; review must check every new job's payload.
- Debugging a failed job means reproducing it from the ids, not reading the stored message.
- Ticket 02 must provide the tenant context and prove with a test that a job for one company cannot read another's rows.

## Verified

A test (`test_a_failed_job_never_stores_or_logs_the_content_that_made_it_fail`) enqueues a job whose exception echoes document text and asserts the text appears in neither the stored error nor the logs.
