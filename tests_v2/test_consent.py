"""Consent memory: ask once, never nag."""
import pytest

from dictatord.consent import ConsentLedger, Decision


@pytest.fixture
def ledger(tmp_path):
    return ConsentLedger(tmp_path / "consent.json").load()


def test_an_unasked_permission_should_be_asked(ledger):
    assert ledger.should_ask("shortcuts") is True


@pytest.mark.parametrize("decision", [Decision.DECLINED, Decision.IGNORED])
def test_a_settled_answer_is_never_re_asked(ledger, decision):
    """Re-asking on every start turns a restart into a stream of dialogs."""
    ledger.record("shortcuts", decision)
    assert ledger.should_ask("shortcuts") is False
    assert ledger.why_not_asking("shortcuts")


def test_granted_is_not_re_asked(ledger):
    ledger.record("injection", Decision.GRANTED)
    assert ledger.should_ask("injection") is False


def test_unavailable_is_retried(ledger):
    """The portal being down is not the user's answer."""
    ledger.record("shortcuts", Decision.UNAVAILABLE)
    assert ledger.should_ask("shortcuts") is True


def test_decisions_persist(tmp_path):
    path = tmp_path / "consent.json"
    ConsentLedger(path).load().record("shortcuts", Decision.DECLINED)
    assert ConsentLedger(path).load().should_ask("shortcuts") is False


def test_attempts_accumulate(ledger):
    ledger.record("shortcuts", Decision.DECLINED)
    ledger.record("shortcuts", Decision.DECLINED)
    assert ledger.get("shortcuts").attempts == 2


def test_reset_reopens_one_permission(ledger):
    ledger.record("shortcuts", Decision.DECLINED)
    ledger.record("injection", Decision.DECLINED)
    ledger.reset("shortcuts")
    assert ledger.should_ask("shortcuts") is True
    assert ledger.should_ask("injection") is False


def test_reset_all_reopens_everything(ledger):
    ledger.record("shortcuts", Decision.DECLINED)
    ledger.record("injection", Decision.DECLINED)
    ledger.reset()
    assert all(ledger.should_ask(k) for k in ConsentLedger.KEYS)


def test_a_corrupt_ledger_is_survivable(tmp_path):
    path = tmp_path / "consent.json"
    path.write_text("{not json")
    assert ConsentLedger(path).load().should_ask("shortcuts") is True


def test_the_file_is_private(tmp_path):
    path = tmp_path / "consent.json"
    ConsentLedger(path).load().record("shortcuts", Decision.GRANTED)
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_summary_covers_every_permission(ledger):
    assert set(ledger.summary()) == set(ConsentLedger.KEYS)
