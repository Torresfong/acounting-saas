# Tenancy and row-level security

Implements D11 and D40 (1) to (4). Built in ticket 02a (#31). Job-queue tenancy (D36) arrives in 02d (#34), and users and sign-in in 02b (#32).

## How isolation works

- **Company** is the tenant. **CompanyAccess(user, company, role)** says who may act in which company. Owners and staff have one row; accountants have one row per company they are authorised for. There is no bypass role.
- Every business table has a `company_id` and the same policy: a row is visible and writable only when its company is among the signed-in user's `CompanyAccess` rows. The policy applies to reads, inserts, updates and deletes, with a check so a row cannot be inserted for, or moved to, another company.
- Requests run as the database role `web`: not a superuser, no `BYPASSRLS`, and it owns no tables. Tables use `FORCE ROW LEVEL SECURITY`.
- The signed-in user reaches the database as the transaction-local setting `app.user_id`. `core.middleware.TenantContextMiddleware` wraps each request in a transaction and sets the role and the setting with `SET LOCAL`. A missing or empty setting matches nobody, so an anonymous request sees no company.
- The membership tables are read-only to the web role (a user sees only their own `CompanyAccess` rows). Writes to them come with the firm and invitation flows.
- Company-level authorization is this layer. Action-level permission (who may approve, who may change a TIN) is the Django permission service in 02b (D40 (4)).

## Adding a tenant table

1. Subclass `core.models.TenantModel` (it adds the `company` foreign key).
2. In the migration that creates the table, add `core.rls.enable_tenant_rls("app_table")` straight after the `CreateModel`. It grants the web role access to that table and applies the policy.
3. Use `GENERATED ... AS IDENTITY` ids, which Django's `BigAutoField` already does. A separate sequence would need its own grant to the web role.

There are deliberately no default privileges: a table added without step 2 is unreachable by the web role, so forgetting the policy fails closed. A schema test also fails if the web role can use a table that is neither under row-level security nor on a short reviewed list.

## Roles and deployment

- Migrations create the `web` role without a login. They must run as the table owner, never as `web`.
- For production, the application should connect with a login role that is a member of `web` and owns nothing (`CREATE ROLE app LOGIN PASSWORD ... IN ROLE web`), while migrations run with the owner's credentials. The middleware also drops to `web` on every request, so a connection made with the owner's credentials (as in development and tests) still cannot skip row-level security while handling a request.
- The user and session lookup that happens before the middleware runs as the connection's own role. Ticket 02b gives the user table its own policy and a narrow pre-authentication lookup function.
- The job queue and the Django user tables are not yet under tenant policies; 02d and 02b address them.

## Threat model and limits

- **The identity is a mutable session setting.** Any code running as `web` can execute `SELECT set_config('app.user_id', ...)` or `RESET ROLE`. Row-level security therefore protects against mistakes (a missing filter, a wrong query) and not against an attacker who can run arbitrary SQL as `web`.
- **SQL injection is the main threat to this design.** An injected statement could impersonate another user. Defences: parameterized queries and the ORM only, no string-built SQL, no raw SQL that includes request data, review of any `.raw()` or `cursor.execute()` use. Row-level security backs these up; it does not replace them.
- **Transaction-local only.** The setting and role are applied with `SET LOCAL` inside the request's transaction and reset explicitly at the end, so they cannot leak to the next request on a pooled connection. Code must not start work on the connection outside that transaction and expect the identity to apply.
- **Superusers bypass row-level security.** Nothing on a request path may connect as one. Development and test connections use a superuser but switch to `web` before touching tenant data.
- **Per-request cost.** The policy runs a subquery on `CompanyAccess` for each tenant table. This is acceptable at pilot size and the lookup is indexed through the unique constraint on `(user, company)`.
