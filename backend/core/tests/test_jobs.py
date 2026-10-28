import pytest

from core import jobs
from core.models import Job


@pytest.fixture
def registry():
    saved = dict(jobs.HANDLERS)
    yield jobs.HANDLERS
    jobs.HANDLERS.clear()
    jobs.HANDLERS.update(saved)


@pytest.mark.django_db
def test_queued_job_runs_in_process_with_its_payload(registry):
    seen = []
    jobs.register("record")(lambda **payload: seen.append(payload))

    jobs.enqueue("record", value=7)
    assert seen == []  # nothing runs until the runner is called

    assert jobs.run_pending() == 1
    assert seen == [{"value": 7}]
    assert Job.objects.get().status == Job.DONE


@pytest.mark.django_db
def test_a_failing_job_is_recorded_and_does_not_block_the_next_one(registry):
    seen = []

    def boom(**payload):
        raise ValueError("bad input")

    jobs.register("boom")(boom)
    jobs.register("ok")(lambda **payload: seen.append("ok"))

    jobs.enqueue("boom")
    jobs.enqueue("ok")
    jobs.run_pending()

    failed = Job.objects.get(name="boom")
    assert failed.status == Job.FAILED
    assert failed.error == "ValueError"
    assert seen == ["ok"]


@pytest.mark.django_db
def test_a_failed_job_never_stores_or_logs_the_content_that_made_it_fail(registry, caplog):
    secret = "Supplier ACME Sdn Bhd, TIN C2345678901, total RM 18,450.00"

    def echo_content(document_text):
        raise ValueError(f"cannot parse total in: {document_text}")

    jobs.register("extract")(echo_content)
    jobs.enqueue("extract", document_text=secret)

    with caplog.at_level("DEBUG"):
        jobs.run_pending()

    failed = Job.objects.get()
    assert failed.status == Job.FAILED
    assert "ACME" not in failed.error and "C2345678901" not in failed.error
    assert "ACME" not in caplog.text and "C2345678901" not in caplog.text
    assert "ValueError" in caplog.text  # still enough to debug from: which job, which error class


@pytest.mark.django_db
def test_a_job_with_no_registered_handler_fails_instead_of_vanishing(registry):
    jobs.enqueue("unknown")
    jobs.run_pending()

    assert Job.objects.get().status == Job.FAILED
