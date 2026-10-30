import pytest

from core.models import CompanyAccess

from .factories import PASSWORD, make_company, make_member


@pytest.fixture
def world(db):
    """Two client companies, an owner and a staff member at Acme, an owner at Beta, and a firm accountant on both."""
    acme, beta = make_company("Acme Sdn Bhd"), make_company("Beta Trading")
    people = {
        "acme_owner": make_member("owner@acme.example", acme, CompanyAccess.OWNER),
        "acme_staff": make_member("staff@acme.example", acme, CompanyAccess.STAFF),
        "beta_owner": make_member("owner@beta.example", beta, CompanyAccess.OWNER),
    }
    accountant = make_member("accountant@firm.example", acme, CompanyAccess.ACCOUNTANT)
    CompanyAccess.objects.create(user=accountant, company=beta, role=CompanyAccess.ACCOUNTANT)
    people["accountant"] = accountant
    return {"acme": acme, "beta": beta, **people}


def sign_in(client, user):
    assert client.post("/login/", {"email": user.email, "password": PASSWORD}).status_code == 302


def test_an_owner_sees_only_their_own_company_in_the_list(client, world, as_production_connection):
    with as_production_connection():
        sign_in(client, world["acme_owner"])
        page = client.get("/companies/").content.decode()

    assert "Acme Sdn Bhd" in page and "Beta Trading" not in page


def test_staff_see_only_their_own_company_in_the_list(client, world, as_production_connection):
    with as_production_connection():
        sign_in(client, world["acme_staff"])
        page = client.get("/companies/").content.decode()

    assert "Acme Sdn Bhd" in page and "Beta Trading" not in page


def test_an_accountant_sees_every_pilot_company_in_the_list(client, world, as_production_connection):
    with as_production_connection():
        sign_in(client, world["accountant"])
        page = client.get("/companies/").content.decode()

    assert "Acme Sdn Bhd" in page and "Beta Trading" in page


def test_the_list_names_the_role_the_user_has_in_each_company(client, world, as_production_connection):
    with as_production_connection():
        sign_in(client, world["acme_staff"])
        assert "Client staff" in client.get("/companies/").content.decode()
        client.post("/logout/")
        sign_in(client, world["accountant"])
        assert "Firm accountant" in client.get("/companies/").content.decode()


@pytest.mark.parametrize("who", ["acme_owner", "acme_staff", "accountant"])
def test_a_user_can_open_a_company_they_have_access_to(client, world, who, as_production_connection):
    with as_production_connection():
        sign_in(client, world[who])
        response = client.get(f"/companies/{world['acme'].pk}/")

    assert response.status_code == 200 and "Acme Sdn Bhd" in response.content.decode()


@pytest.mark.parametrize("who", ["acme_owner", "acme_staff"])
def test_a_client_user_cannot_open_another_company(client, world, who, as_production_connection):
    with as_production_connection():
        sign_in(client, world[who])
        response = client.get(f"/companies/{world['beta'].pk}/")

    assert response.status_code == 404 and "Beta Trading" not in response.content.decode()


def test_an_anonymous_visitor_cannot_see_companies(client, world, as_production_connection):
    with as_production_connection():
        assert client.get("/companies/").status_code == 401
        assert client.get(f"/companies/{world['acme'].pk}/").status_code == 401


def test_only_the_owner_is_offered_the_invite_form(client, world, as_production_connection):
    url = f"/companies/{world['acme'].pk}/"
    with as_production_connection():
        sign_in(client, world["acme_owner"])
        owner_page = client.get(url).content.decode()
        client.post("/logout/")
        sign_in(client, world["acme_staff"])
        staff_page = client.get(url).content.decode()
        client.post("/logout/")
        sign_in(client, world["accountant"])
        accountant_page = client.get(url).content.decode()

    assert "Invite a colleague" in owner_page
    assert "Invite a colleague" not in staff_page and "Invite a colleague" not in accountant_page
