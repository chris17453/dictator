"""Model catalogue, selection, download, and integrity.

Two things the old system got wrong and this fixes: the model actually
configured is the model loaded (G-12), and weights are checked against a
recorded digest before they are trusted (G-17).

TLS verification is never disabled. The certificate problem that motivated
that bypass is a host trust-store issue, diagnosed by ``dictator doctor``
with a real remedy (G-15).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..errors import Fault, FaultCode
from ..logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    """One selectable Whisper model."""

    name: str
    repo: str
    parameters: str
    approx_mb: int
    multilingual: bool
    note: str

    @property
    def is_english_only(self) -> bool:
        return not self.multilingual


#: Everything the user may choose between. Ordered smallest to largest, with
#: the turbo variants last because they are the recommended default.
CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec("tiny", "Systran/faster-whisper-tiny", "39M", 75, True,
              "Fastest, least accurate. Useful on constrained hardware."),
    ModelSpec("tiny.en", "Systran/faster-whisper-tiny.en", "39M", 75, False,
              "English-only tiny; slightly better than tiny for English."),
    ModelSpec("base", "Systran/faster-whisper-base", "74M", 145, True,
              "Reasonable CPU default."),
    ModelSpec("base.en", "Systran/faster-whisper-base.en", "74M", 145, False,
              "English-only base."),
    ModelSpec("small", "Systran/faster-whisper-small", "244M", 484, True,
              "Good accuracy, still comfortable on CPU."),
    ModelSpec("small.en", "Systran/faster-whisper-small.en", "244M", 484, False,
              "English-only small."),
    ModelSpec("medium", "Systran/faster-whisper-medium", "769M", 1530, True,
              "Strong accuracy; wants a GPU."),
    ModelSpec("medium.en", "Systran/faster-whisper-medium.en", "769M", 1530, False,
              "English-only medium."),
    ModelSpec("large-v2", "Systran/faster-whisper-large-v2", "1550M", 3090, True,
              "Previous generation large."),
    ModelSpec("large-v3", "Systran/faster-whisper-large-v3", "1550M", 3090, True,
              "Most accurate; slowest."),
    ModelSpec("large-v3-turbo", "deepdml/faster-whisper-large-v3-turbo-ct2", "809M", 1620, True,
              "Near large-v3 accuracy at a fraction of the cost. Recommended on a GPU."),
    ModelSpec("distil-large-v3", "Systran/faster-distil-whisper-large-v3", "756M", 1510, False,
              "English-only, very fast, close to large-v3 on English."),
)

BY_NAME = {spec.name: spec for spec in CATALOG}


def known(name: str) -> bool:
    return name in BY_NAME


def spec_for(name: str) -> ModelSpec:
    try:
        return BY_NAME[name]
    except KeyError:
        available = ", ".join(BY_NAME)
        raise Fault(
            code=FaultCode.MODEL_NOT_FOUND,
            message=f"unknown model {name!r}",
            remedy=f"Choose one of: {available}",
        ) from None


# --------------------------------------------------------------------------
# capability-driven defaults
# --------------------------------------------------------------------------


def cuda_available() -> tuple[bool, str]:
    """Whether ctranslate2 can actually use a GPU, not merely whether one exists."""
    try:
        import ctranslate2

        count = ctranslate2.get_cuda_device_count()
        if count > 0:
            return True, f"{count} CUDA device(s)"
        return False, "no CUDA devices visible to ctranslate2"
    except Exception as exc:
        return False, f"ctranslate2 cannot report CUDA support: {exc}"


def resolve_device(requested: str) -> tuple[str, str]:
    """(device, why). ``auto`` probes rather than assumes."""
    if requested == "cuda":
        ok, why = cuda_available()
        if not ok:
            raise Fault(
                code=FaultCode.MODEL_LOAD_FAILED,
                message=f"model.device is 'cuda' but CUDA is unusable: {why}",
                remedy="Set model.device to 'auto' or 'cpu': dictator config set model.device auto",
            )
        return "cuda", why
    if requested == "cpu":
        return "cpu", "configured explicitly"
    ok, why = cuda_available()
    return ("cuda", why) if ok else ("cpu", why)


def resolve_compute_type(requested: str, device: str) -> str:
    if requested != "auto":
        return requested
    return "int8_float16" if device == "cuda" else "int8"


def resolve_model_name(requested: str, device: str) -> str:
    """``auto`` picks by hardware: turbo on a GPU, base on CPU."""
    if requested != "auto":
        spec_for(requested)
        return requested
    return "large-v3-turbo" if device == "cuda" else "base"


@dataclass(frozen=True)
class Resolution:
    model: str
    device: str
    compute_type: str
    reason: str


def resolve(model: str, device: str, compute_type: str) -> Resolution:
    chosen_device, why = resolve_device(device)
    return Resolution(
        model=resolve_model_name(model, chosen_device),
        device=chosen_device,
        compute_type=resolve_compute_type(compute_type, chosen_device),
        reason=why,
    )


# --------------------------------------------------------------------------
# on-disk state and integrity
# --------------------------------------------------------------------------


def model_dir(root: Path, name: str) -> Path:
    return Path(root) / name.replace("/", "_")


def is_downloaded(root: Path, name: str) -> bool:
    directory = model_dir(root, name)
    if not directory.is_dir():
        return False
    return any(directory.rglob("model.bin")) or any(directory.rglob("*.bin"))


def installed(root: Path) -> list[str]:
    return sorted(spec.name for spec in CATALOG if is_downloaded(root, spec.name))


def disk_usage(root: Path, name: str) -> int:
    directory = model_dir(root, name)
    if not directory.is_dir():
        return 0
    return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())


def _manifest_path(root: Path) -> Path:
    return Path(root) / "digests.json"


def _load_manifest(root: Path) -> dict:
    path = _manifest_path(root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        log.warning("the model digest manifest is unreadable; it will be rebuilt")
        return {}


def _save_manifest(root: Path, manifest: dict) -> None:
    path = _manifest_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    except OSError as exc:  # pragma: no cover - disk dependent
        log.warning("could not write the model digest manifest", error=str(exc))


def compute_digest(root: Path, name: str) -> str:
    """SHA-256 over every weight file, in a stable order."""
    directory = model_dir(root, name)
    digest = hashlib.sha256()
    for file in sorted(p for p in directory.rglob("*") if p.is_file()):
        if file.name == "digests.json":
            continue
        digest.update(file.relative_to(directory).as_posix().encode())
        with file.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def verify(root: Path, name: str, *, enforce: bool = True) -> tuple[bool, str]:
    """Check the model against its recorded digest.

    Where no digest has been recorded, this is trust-on-first-use: the digest
    is recorded now and enforced from the next load onward. That is weaker
    than a shipped pin and is described as such rather than dressed up.
    """
    manifest = _load_manifest(root)
    actual = compute_digest(root, name)
    expected = manifest.get(name)

    if expected is None:
        manifest[name] = actual
        _save_manifest(root, manifest)
        return True, f"digest recorded on first use ({actual[:16]}…)"

    if expected == actual:
        return True, f"digest verified ({actual[:16]}…)"

    message = (
        f"the weights for {name} do not match the recorded digest "
        f"(expected {expected[:16]}…, found {actual[:16]}…)"
    )
    if not enforce:
        log.warning(message)
        return False, message
    raise Fault(
        code=FaultCode.MODEL_DIGEST_MISMATCH,
        message=message,
        remedy=(
            f"If you changed the model deliberately, re-record it: "
            f"dictator models trust {name}. Otherwise remove and re-download it: "
            f"dictator models remove {name} && dictator models download {name}"
        ),
    )


def trust(root: Path, name: str) -> str:
    """Record the current on-disk digest as the expected one."""
    manifest = _load_manifest(root)
    actual = compute_digest(root, name)
    manifest[name] = actual
    _save_manifest(root, manifest)
    return actual


def forget(root: Path, name: str) -> None:
    manifest = _load_manifest(root)
    if manifest.pop(name, None) is not None:
        _save_manifest(root, manifest)


def remove(root: Path, name: str) -> None:
    import shutil

    directory = model_dir(root, name)
    if directory.is_dir():
        shutil.rmtree(directory)
    forget(root, name)


def download(root: Path, name: str) -> Path:
    """Fetch weights, with certificate verification left firmly on."""
    spec = spec_for(name)
    directory = model_dir(root, name)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=spec.repo,
            local_dir=str(directory),
            allow_patterns=["*.bin", "*.json", "*.txt", "*.model"],
        )
    except Exception as exc:
        raise Fault(
            code=FaultCode.MODEL_DOWNLOAD_FAILED,
            message=f"could not download {name} from {spec.repo}: {exc}",
            remedy=(
                "Check network access. If this is a certificate error, fix the host "
                "trust store (dnf install ca-certificates) — do not disable "
                "verification."
            ),
        ) from exc
    trust(root, name)
    return directory
