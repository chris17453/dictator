"""Model selection and integrity."""
import pytest

from dictatord.asr import models
from dictatord.asr.engine import confidence_from_logprob
from dictatord.asr.stream import Partial, common_prefix_length
from dictatord.errors import Fault, FaultCode


def test_catalog_is_consistent():
    assert models.CATALOG
    for spec in models.CATALOG:
        assert spec.repo.count("/") == 1
        assert spec.approx_mb > 0
    assert len(models.BY_NAME) == len(models.CATALOG)


def test_unknown_model_names_the_alternatives():
    with pytest.raises(Fault) as excinfo:
        models.spec_for("gpt-9")
    assert excinfo.value.code is FaultCode.MODEL_NOT_FOUND
    assert "tiny" in excinfo.value.remedy


def test_auto_picks_turbo_on_gpu_and_base_on_cpu():
    assert models.resolve_model_name("auto", "cuda") == "large-v3-turbo"
    assert models.resolve_model_name("auto", "cpu") == "base"


def test_explicit_model_is_honoured():
    """The configured model must be the model loaded (G-12)."""
    assert models.resolve_model_name("small", "cuda") == "small"
    assert models.resolve_model_name("tiny", "cpu") == "tiny"


def test_compute_type_follows_the_device():
    assert models.resolve_compute_type("auto", "cuda") == "int8_float16"
    assert models.resolve_compute_type("auto", "cpu") == "int8"
    assert models.resolve_compute_type("float32", "cuda") == "float32"


def test_cpu_is_always_available():
    device, why = models.resolve_device("cpu")
    assert device == "cpu" and why


def test_digest_is_recorded_then_enforced(tmp_path):
    root = tmp_path / "models"
    directory = models.model_dir(root, "tiny")
    directory.mkdir(parents=True)
    (directory / "model.bin").write_bytes(b"weights")

    ok, detail = models.verify(root, "tiny")
    assert ok and "first use" in detail

    ok, detail = models.verify(root, "tiny")
    assert ok and "verified" in detail

    (directory / "model.bin").write_bytes(b"tampered")
    with pytest.raises(Fault) as excinfo:
        models.verify(root, "tiny")
    assert excinfo.value.code is FaultCode.MODEL_DIGEST_MISMATCH
    assert "dictator models" in excinfo.value.remedy


def test_trust_re_records_a_deliberate_change(tmp_path):
    root = tmp_path / "models"
    directory = models.model_dir(root, "tiny")
    directory.mkdir(parents=True)
    (directory / "model.bin").write_bytes(b"a")
    models.verify(root, "tiny")
    (directory / "model.bin").write_bytes(b"b")
    models.trust(root, "tiny")
    assert models.verify(root, "tiny")[0] is True


def test_non_enforcing_verify_reports_without_raising(tmp_path):
    root = tmp_path / "models"
    directory = models.model_dir(root, "tiny")
    directory.mkdir(parents=True)
    (directory / "model.bin").write_bytes(b"a")
    models.verify(root, "tiny")
    (directory / "model.bin").write_bytes(b"b")
    ok, detail = models.verify(root, "tiny", enforce=False)
    assert ok is False and detail


def test_is_downloaded_and_removal(tmp_path):
    root = tmp_path / "models"
    assert models.is_downloaded(root, "tiny") is False
    directory = models.model_dir(root, "tiny")
    directory.mkdir(parents=True)
    (directory / "model.bin").write_bytes(b"x")
    assert models.is_downloaded(root, "tiny") is True
    models.remove(root, "tiny")
    assert models.is_downloaded(root, "tiny") is False


# -- confidence and partials ----------------------------------------------


@pytest.mark.parametrize("logprob,expected", [
    (0.0, 1.0), (-0.3, 0.7), (-1.0, 0.0), (-5.0, 0.0), (2.0, 1.0),
])
def test_confidence_mapping_is_clamped(logprob, expected):
    assert confidence_from_logprob(logprob) == pytest.approx(expected)


def test_stable_prefix_marks_settled_text():
    assert common_prefix_length("hello wor", "hello world") == 9
    assert common_prefix_length("", "abc") == 0
    assert common_prefix_length("abc", "xyz") == 0


def test_partial_splits_settled_from_provisional():
    partial = Partial(session_id=1, text="hello world", stable_chars=5)
    assert partial.stable == "hello"
    assert partial.tail == " world"
