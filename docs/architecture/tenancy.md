# Tenancy and row-level security

Implements D11 and D40 (1), (2) for `CompanyAccess`, (3) and (4). Built in ticket 02a (#31). Still to come: the policy on user records and the pre-authentication lookup function (D40 (2)) in 02b (#32), and job-queue tenancy (D36) in 02d (#34).

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

The web role starts with access to nothing and there are no default privileges, so a table added without step 2 is unreachable by it and forgetting the policy fails closed. Users, jobs, sessions and Django's own tables are closed to the web role for now; the ticket that puts each under a policy opens it (02b for users, 02d for jobs). A schema test fails if the web role can use any table that is not under forced row-level security.

## Roles and deployment

- Migrations create the `web` role without a login. If it already exists (roles are cluster-wide), they reset it to `NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS` and stop with an error unless those attributes hold. They must run as the table owner, never as `web`.
- For production, the application should connect with a login role that is a member of `web` and owns nothing (`CREATE ROLE app LOGIN PASSWORD ... IN ROLE web`), while migrations run with the owner's credentials. The middleware also drops to `web` on every request, so a connection made with the owner's credentials (as in development and tests) still cannot skip row-level security while handling a request.
- The user and session lookup that happens before the middleware runs as the connection's own role. Ticket 02b gives the user table its own policy and a narrow pre-authentication lookup function.
- The web role reads only its own row of the user table and uses the session table (see the 02b section below); it still cannot reach jobs until 02d (#34).
- A streaming response is read after the middleware returns, outside the web role and its transaction. Do not query tenant data lazily inside a streamed response.

## Threat model and limits

- **The identity is a mutable session setting, and the role switch can be undone.** Any code running as `web` can execute `SELECT set_config('app.user_id', ...)` and so impersonate another user. It can also run `RESET ROLE`, which returns the session to the role the connection was made with, and what that role can do depends on what it is:
  - A **superuser** or a role with `BYPASSRLS` ignores row-level security entirely, `FORCE` or not. If the application connected as one, injected SQL could simply `RESET ROLE` and read every tenant's data.
  - An ordinary **table owner** is subject to `FORCE ROW LEVEL SECURITY` like anyone else, so it does not see other companies' rows by default. It does keep DDL rights, so it can alter or drop the policies and disable row-level security, or grant itself access, and then read everything.
  - A login role that is only a member of `web` has nothing stronger to go back to, so `RESET ROLE` gains nothing. That is the production setup.
  In development and tests the connection is the owner's (and a superuser's in the Docker stack) and only the per-request switch protects tenant data. Row-level security protects against mistakes (a missing filter, a wrong query) and not against an attacker who can run arbitrary SQL as `web`.
- **SQL injection is the main threat to this design.** An injected statement could impersonate another user. Defences: parameterized queries and the ORM only, no string-built SQL, no raw SQL that includes request data, review of any `.raw()` or `cursor.execute()` use. Row-level security backs these up; it does not replace them.
- **Transaction-local only.** The setting and role are applied with `SET LOCAL` inside the request's transaction and reset explicitly at the end, so they cannot leak to the next request on a pooled connection. Code must not start work on the connection outside that transaction and expect the identity to apply.
- **Superusers bypass row-level security.** Nothing on a request path may connect as one. Development and test connections use a superuser but switch to `web` before touching tenant data.
- **Per-request cost.** The policy runs a subquery on `CompanyAccess` for each tenant table. This is acceptable at pilot size and the lookup is indexed through the unique constraint on `(user, company)`.

## Go-live prerequisite: production database login role

This is not built in ticket 02a and is mandatory before any real client data is stored. Provisioning must create a login role for the application that is a member of `web` and nothing else (no superuser, no `BYPASSRLS`, no ownership of tables or schemas, no other role memberships), keep its credentials in the secrets service and out of the repository, and run migrations with a separate owner role. A check at deployment should confirm the application's connection is not a superuser, does not bypass row-level security and owns no tables. Until then the repository's development and test connections, which use the owner, must not be treated as production-safe.

## Sign-in, invitations and the functions that run before anyone is identified (02b, #32)

Implements D40 (2), (4), (5), (7) and D48 for staff and accountants. Owner self-registration is #67.

**Users and roles.** `core.User` signs in with an email address (stored lowercase, unique ignoring case) and an Argon2 password. The role is on the `CompanyAccess` row, and a partial unique index allows one `owner` row per company. Owners and staff have one row; a firm accountant has one row per pilot company, added when the company is created (`core.services.create_company_with_owner`) or when the accountant is created (`manage.py create_accountant`). Accountants are never created or invited by a client (D48).

**Who may do what.** `core.permissions` holds the action-level rules (D40 (4)): `ACTIONS` maps an action to the roles that may perform it, `require` raises 403 in a view, and `{% can "action" company as allowed %}` offers the same check in templates. Register a new protected action in `ACTIONS`. A company the user cannot reach is a 404, so its existence is not revealed.

**Why functions.** Before anyone is signed in the web role has no identity, so row-level security shows it nothing. Sign-in, password reset and invitation acceptance therefore go through narrow `SECURITY DEFINER` functions owned by the table owner, each with a pinned `search_path`, executable by `web` only:

| Function | Returns | Notes |
|---|---|---|
| `auth_lookup(email)` | id, password hash, active flag | exact match, case-insensitive; nothing else about the user |
| `login_failures_in_window`, `record_login_failure`, `clear_login_failures` | count / nothing | only a SHA-256 of the email is stored |
| `create_password_reset`, `token_is_valid`, `complete_password_reset` | bool / user id | at most three links an hour per account |
| `create_invitation` | nothing | checks inside the database that the signed-in user owns the company; the role is fixed to staff |
| `accept_invitation` | user id | creates the user and the membership in one transaction |

The web role has no direct access to `core_authtoken` or `core_loginfailure`, and may read only its own row of `core_user` (it needs the password hash to validate the session). It cannot create, change or delete users.

**Forced row-level security and the owner.** `FORCE ROW LEVEL SECURITY` also hides rows from the table owner, and the functions run as the owner, so each table the functions touch has a `definer_functions` policy naming the migrating role (`core.rls.owner_policy_sql`). It opens nothing to `web` or to a login role that is a member of it. Verified against a non-superuser owner: the migrations run, and every function works under forced row-level security.

**Identity and sessions.** The middleware takes the user id from the session, not from loading the user, because loading the user is itself a query that row-level security restricts and must run as the signed-in user. Sessions are stored in `django_session`, which the web role can use; it holds a session key and a signed blob naming a user id, no tenant data, and is the one listed exception to the rule that every table the web role can use is under row-level security. Django's `last_login` update is turned off, because the web role cannot write the user table and nobody is identified yet at sign-in; sign-ins belong in the audit trail (#33).

**Throttling.** Five failed sign-ins for an address lock that address for fifteen minutes (also for addresses with no account, so the lock does not reveal which exist). A successful sign-in resets the count.

**Links.** Reset links last an hour and invitations a week. Tokens are random, stored only as a SHA-256 hash, single use, and indistinguishable when unknown, expired or used. A password change ends the account's other sessions, because Django ties a session to a hash of the password.

**Two-factor authentication** is a go-live blocker (D40 (7)) and is not built here. Sign-in ends in one function, `core.signin.complete_sign_in`, which is where it plugs in.
