import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()


def test_a_user_is_identified_by_email_and_the_password_is_stored_as_argon2(db):
    user = User.objects.create_user("Owner@Example.com", password="correct horse battery")

    assert user.email == "owner@example.com"
    assert user.password.startswith("argon2$")
    assert user.check_password("correct horse battery")


def test_two_users_cannot_share_an_email_address_in_any_letter_case(db):
    User.objects.create_user("owner@example.com", password="correct horse battery")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("OWNER@example.com", password="another long password")


def make_company_with(*memberships):
    from core.models import Company, CompanyAccess

    company = Company.objects.create(name="Acme Sdn Bhd")
    users = []
    for email, role in memberships:
        user = User.objects.create_user(email, password="correct horse battery")
        CompanyAccess.objects.create(user=user, company=company, role=role)
        users.append(user)
    return company, users


def test_the_database_rejects_a_second_owner_for_the_same_company(db):
    from core.models import CompanyAccess

    company, _ = make_company_with(("owner@example.com", CompanyAccess.OWNER))
    other = User.objects.create_user("other@example.com", password="correct horse battery")

    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyAccess.objects.create(user=other, company=company, role=CompanyAccess.OWNER)


def test_a_company_can_have_many_staff_and_the_same_person_can_own_only_once_per_company(db):
    from core.models import CompanyAccess

    company, _ = make_company_with(
        ("owner@example.com", CompanyAccess.OWNER),
        ("staff1@example.com", CompanyAccess.STAFF),
        ("staff2@example.com", CompanyAccess.STAFF),
    )

    assert company.access.count() == 3
