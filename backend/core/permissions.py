"""Action-level permissions (D40 (4)).

Row-level security decides which companies a user can reach at all. This module decides what the user's
role in that company lets them do. The role comes from the `CompanyAccess` row for the company in play,
never from the user, so one login can hold different roles in different companies later.

To protect a new action, register it in ACTIONS and call `require` in the view or `can` where a choice is
shown. There is no delegation (D17): an action is allowed for a role or it is not.
"""

from django.core.exceptions import PermissionDenied

from .models import CompanyAccess

OWNER, STAFF, ACCOUNTANT = CompanyAccess.OWNER, CompanyAccess.STAFF, CompanyAccess.ACCOUNTANT

ACTIONS = {
    "view_company": {OWNER, STAFF, ACCOUNTANT},
    "invite_staff": {OWNER},
}


def role_in(user, company):
    """The user's role in the company, or None when they have no membership there."""
    if not user.is_authenticated:
        return None
    return CompanyAccess.objects.filter(user=user, company=company).values_list("role", flat=True).first()


def can(user, action, company):
    return role_in(user, company) in ACTIONS[action]


def require(user, action, company):
    if not can(user, action, company):
        raise PermissionDenied
