"""Transcript store and adaptive lexicon."""
import pytest

from dictatord.memory.lexicon import PROMOTION_THRESHOLD, Lexicon
from dictatord.memory.store import TranscriptStore


@pytest.fixture
def store(tmp_path):
    store = TranscriptStore(tmp_path / "t.db")
    store.open()
    yield store
    store.close()


def test_add_and_recall(store):
    entry = store.add("the quarterly forecast", model="base", confidence=0.9)
    assert entry.id > 0
    assert store.count() == 1
    assert store.last().text == "the quarterly forecast"


def test_full_text_search(store):
    store.add("the quarterly forecast looks strong")
    store.add("remember to email chris about the rebuild")
    assert len(store.search("quarterly")) == 1
    assert len(store.search("rebuild")) == 1
    assert store.search("nonexistentword") == []


def test_search_is_injection_safe(store):
    """FTS5 syntax in user input must not become a query operator."""
    store.add("hello world")
    for hostile in ['AND OR "((', 'NEAR/', '*', 'a OR b']:
        store.search(hostile)  # must not raise


def test_empty_query_returns_recent(store):
    store.add("one")
    store.add("two")
    assert len(store.search("")) == 2


def test_redaction_stores_but_does_not_alter_delivery(tmp_path):
    store = TranscriptStore(tmp_path / "r.db", redact_patterns=[r"\b\d{4}-\d{4}\b"])
    store.open()
    entry = store.add("my pin is 1234-5678 ok")
    assert "1234-5678" not in entry.text
    assert entry.redacted is True
    store.close()


def test_redaction_leaves_clean_text_alone(tmp_path):
    store = TranscriptStore(tmp_path / "r.db", redact_patterns=[r"\d{4}-\d{4}"])
    store.open()
    entry = store.add("nothing sensitive here")
    assert entry.redacted is False
    store.close()


def test_retention_deletes(store):
    import time
    store.add("old", created_at=time.time() - 40 * 86400)
    store.add("new")
    assert store.prune(30) == 1
    assert store.count() == 1


def test_retention_zero_keeps_everything(store):
    store.add("keep me")
    assert store.prune(0) == 0
    assert store.count() == 1


def test_mark_delivered(store):
    entry = store.add("hello")
    store.mark_delivered(entry.id, "paste", "firefox", True)
    assert store.get(entry.id).delivered is True
    assert store.get(entry.id).app_id == "firefox"


# -- lexicon ---------------------------------------------------------------


def test_lexicon_terms_round_trip(tmp_path):
    path = tmp_path / "lex.json"
    lexicon = Lexicon(path)
    lexicon.add_term("ctranslate2")
    lexicon.add_term("Kubernetes")
    lexicon.save()

    reloaded = Lexicon(path)
    reloaded.load()
    assert len(reloaded.terms) == 2
    assert "ctranslate2" in reloaded.prompt()


def test_prompt_is_capped(tmp_path):
    lexicon = Lexicon(tmp_path / "lex.json", max_prompt_terms=3)
    for i in range(10):
        lexicon.add_term(f"term{i}")
    assert len(lexicon.prompt().split(", ")) == 3


def test_substitution_respects_word_boundaries(tmp_path):
    lexicon = Lexicon(tmp_path / "lex.json")
    lexicon.add_substitution("cat", "cot")
    assert lexicon.apply("the cat sat") == "the cot sat"
    assert lexicon.apply("catalogue") == "catalogue"


def test_substitution_preserves_case(tmp_path):
    lexicon = Lexicon(tmp_path / "lex.json")
    lexicon.add_substitution("kubernetes", "Kubernetes")
    assert lexicon.apply("Kubernetes is") == "Kubernetes is"
    assert lexicon.apply("KUBERNETES") == "KUBERNETES"


def test_learning_requires_repetition(tmp_path):
    """One stray edit must not poison the lexicon (v2.md K-6)."""
    lexicon = Lexicon(tmp_path / "lex.json")
    for _ in range(PROMOTION_THRESHOLD - 1):
        assert lexicon.observe_correction("deploy to cubernetes", "deploy to kubernetes") == []
    assert not lexicon.substitutions

    promoted = lexicon.observe_correction("deploy to cubernetes", "deploy to kubernetes")
    assert promoted
    assert lexicon.apply("cubernetes") == "kubernetes"


def test_learning_ignores_insertions(tmp_path):
    """Ordinary editing is not a recognition error."""
    lexicon = Lexicon(tmp_path / "lex.json")
    for _ in range(PROMOTION_THRESHOLD + 1):
        lexicon.observe_correction("hello", "hello there friend")
    assert not lexicon.substitutions


def test_missing_lexicon_file_is_not_an_error(tmp_path):
    lexicon = Lexicon(tmp_path / "absent.json")
    lexicon.load()
    assert lexicon.terms == {}


def test_corrupt_lexicon_file_is_survivable(tmp_path):
    path = tmp_path / "lex.json"
    path.write_text("{not json")
    lexicon = Lexicon(path)
    lexicon.load()
    assert lexicon.terms == {}
