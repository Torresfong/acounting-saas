"""Operations that create accounts and companies outside a web request: operator commands, onboarding, tests.

They run with the database owner's rights and are not reachable from the web role.
"""

from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Company, CompanyAccess


class EmailInUse(Exception):
    """The address already has an account. One login holds one kind of membership for now (D40 (1))."""


def _require_new_address(email):
    if get_user_model().objects.filter(email__iexact=email.strip()).exists():
        raise EmailInUse


def _accountants():
    return get_user_model().objects.filter(company_access__role=CompanyAccess.ACCOUNTANT).distinct()


@transaction.atomic
def create_company_with_owner(name, owner_email, owner_password):
    """A company with its single owner. Every firm accountant gets access to it, as to every pilot company."""
    _require_new_address(owner_email)
    company = Company.objects.create(name=name)
    owner = get_user_model().objects.create_user(owner_email, password=owner_password)
    CompanyAccess.objects.create(user=owner, company=company, role=CompanyAccess.OWNER)
    CompanyAccess.objects.bulk_create(
        CompanyAccess(user=accountant, company=company, role=CompanyAccess.ACCOUNTANT)
        for accountant in _accountants()
    )
    return company


@transaction.atomic
def create_accountant(email):
    """A firm accountant with access to every pilot company and no usable password until they choose one."""
    _require_new_address(email)
    accountant = get_user_model().objects.create_user(email, password=None)
    CompanyAccess.objects.bulk_create(
        CompanyAccess(user=accountant, company=company, role=CompanyAccess.ACCOUNTANT)
        for company in Company.objects.all()
    )
    return accountant
