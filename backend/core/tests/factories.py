from django.contrib.auth import get_user_model

from core.models import Company, CompanyAccess

PASSWORD = "correct horse battery"


def make_user(email, password=PASSWORD):
    return get_user_model().objects.create_user(email, password=password)


def make_member(email, company, role, password=PASSWORD):
    """A new user with a membership row in `company`."""
    user = make_user(email, password)
    CompanyAccess.objects.create(user=user, company=company, role=role)
    return user


def make_company(name="Acme Sdn Bhd"):
    return Company.objects.create(name=name)
