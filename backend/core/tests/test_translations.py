import pytest

from core.models import CompanyAccess

from .factories import PASSWORD, make_company, make_member

CHINESE = {"accept-language": "zh-hans"}


@pytest.fixture
def acme_owner(db):
    return make_member("owner@acme.example", make_company(), CompanyAccess.OWNER)


def test_the_sign_in_page_is_in_english_by_default_and_in_chinese_on_request(client, db):
    english = client.get("/login/").content.decode()
    chinese = client.get("/login/", headers=CHINESE).content.decode()

    assert "Sign in" in english and "登录" not in english
    assert "登录" in chinese and "电子邮件地址" in chinese and "密码" in chinese


def test_a_failed_sign_in_explains_itself_in_chinese(client, acme_owner, as_production_connection):
    with as_production_connection():
        wrong = client.post("/login/", {"email": "owner@acme.example", "password": "wrong"}, headers=CHINESE)

    assert "电子邮件地址或密码不正确" in wrong.content.decode()


def test_the_lock_message_is_in_chinese(client, acme_owner, as_production_connection):
    with as_production_connection():
        for _ in range(5):
            client.post("/login/", {"email": "owner@acme.example", "password": "wrong"})
        locked = client.post("/login/", {"email": "owner@acme.example", "password": PASSWORD}, headers=CHINESE)

    assert locked.status_code == 429 and "失败次数过多" in locked.content.decode()


def test_the_reset_and_invalid_link_pages_are_in_chinese(client, db):
    assert "重置密码" in client.get("/password-reset/", headers=CHINESE).content.decode()
    assert "此链接已失效" in client.get("/reset/not-a-token/", headers=CHINESE).content.decode()
    assert "此链接已失效" in client.get("/accept/not-a-token/", headers=CHINESE).content.decode()


def test_the_company_pages_and_role_names_are_in_chinese(client, acme_owner, as_production_connection):
    company_id = acme_owner.company_access.get().company_id
    with as_production_connection():
        client.post("/login/", {"email": "owner@acme.example", "password": PASSWORD})
        listing = client.get("/companies/", headers=CHINESE).content.decode()
        detail = client.get(f"/companies/{company_id}/", headers=CHINESE).content.decode()

    assert "公司" in listing and "客户所有者" in listing
    assert "邀请同事" in detail and "发送邀请" in detail


def test_the_emails_are_written_in_the_language_of_the_request(client, acme_owner, fake_ports, as_production_connection):
    with as_production_connection():
        client.post("/password-reset/", {"email": "owner@acme.example"}, headers=CHINESE)

    mail = fake_ports.email.sent[0]
    assert "重置密码" in mail["subject"] and "设置新密码" in mail["body"]
