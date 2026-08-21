"""Layered, schema-validated configuration.

Precedence, lowest to highest::

    built-in defaults
    /etc/dictator/config.toml          (site)
    $XDG_CONFIG_HOME/dictator/config.toml   (user)
    DICTATOR_* environment variables
    command-line overrides

The schema is declared once, in :data:`SCHEMA`, and drives validation, the
``dictator config`` command, documentation, and the sample file. Adding a
setting means adding one :class:`Field` and nothing else.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on 3.10
    import tomli as tomllib

import tomli_w
from platformdirs import site_config_dir, user_config_dir, user_data_dir, user_state_dir

from .errors import Fault, FaultCode

APP = "dictator"

#: Bumped whenever a setting is renamed, removed, or changes meaning. The
#: first migration is always the one nobody planned for, so the machinery
#: exists from version one even though there is nothing to migrate yet.
SCHEMA_VERSION = 1

#: old path -> new path, applied in order on load and on save.
RENAMES: dict[str, str] = {}

#: Settings that no longer exist, and what to tell someone still setting them.
RETIRED: dict[str, str] = {
    "ui.transparency": "the floating window was removed in v2",
    "ui.always_on_top": "the floating window was removed in v2",
    "ui.font_size": "the floating window was removed in v2",
    "ui.theme": "the floating window was removed in v2",
    "hotkey.combination": "renamed to shortcuts.dictate",
    "whisper.model_size": "renamed to model.name",
    "whisper.device": "renamed to model.device",
}

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------


def user_config_path() -> Path:
    return Path(user_config_dir(APP)) / "config.toml"


def site_config_path() -> Path:
    return Path(site_config_dir(APP)) / "config.toml"


def data_dir() -> Path:
    return Path(os.environ.get("DICTATOR_DATA_DIR") or user_data_dir(APP))


def state_dir() -> Path:
    return Path(os.environ.get("DICTATOR_STATE_DIR") or user_state_dir(APP))


def models_dir() -> Path:
    return data_dir() / "models"


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    """One configuration setting."""

    path: str
    default: Any
    type: type
    help: str
    choices: tuple[Any, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    coerce: Callable[[Any], Any] | None = None

    @property
    def section(self) -> str:
        return self.path.rsplit(".", 1)[0] if "." in self.path else ""

    @property
    def key(self) -> str:
        return self.path.rsplit(".", 1)[-1]

    def validate(self, value: Any) -> Any:
        if self.coerce is not None:
            try:
                value = self.coerce(value)
            except Exception as exc:
                raise ValidationError(f"{self.path}: {exc}") from exc
        if self.type is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if self.type is not Any and not isinstance(value, self.type):
            raise ValidationError(
                f"{self.path}: expected {self.type.__name__}, got "
                f"{type(value).__name__} ({value!r})"
            )
        if self.choices is not None and value not in self.choices:
            allowed = ", ".join(str(c) for c in self.choices)
            raise ValidationError(f"{self.path}: must be one of [{allowed}], got {value!r}")
        if self.minimum is not None and value < self.minimum:
            raise ValidationError(f"{self.path}: must be >= {self.minimum}, got {value!r}")
        if self.maximum is not None and value > self.maximum:
            raise ValidationError(f"{self.path}: must be <= {self.maximum}, got {value!r}")
        return value


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    raise ValueError("expected a list of strings")


#: The single source of truth for every setting the product has.
SCHEMA: tuple[Field, ...] = (
    # ---- shortcuts ------------------------------------------------------
    Field(
        "shortcuts.dictate",
        "Super+d",
        str,
        "Primary chord. Tap to toggle dictation; hold to dictate only while held.",
    ),
    Field(
        "shortcuts.dictate_terminal",
        "",
        str,
        "Optional chord that delivers using the terminal paste profile. "
        "Empty means unbound. Useful on Wayland, where the focused application "
        "cannot be detected automatically.",
    ),
    Field("shortcuts.cancel", "Super+Escape", str, "Discard the utterance in flight, delivering nothing."),
    Field(
        "shortcuts.hold_threshold_ms",
        250,
        int,
        "A press shorter than this counts as a tap (toggle). Longer is a hold "
        "(push-to-talk, stops on release).",
        minimum=0,
        maximum=2000,
    ),
    Field(
        "shortcuts.backend",
        "auto",
        str,
        "Shortcut backend. 'auto' probes the session.",
        choices=("auto", "evdev", "portal", "x11", "none"),
    ),
    # ---- audio ----------------------------------------------------------
    Field("audio.device", "", str, "Input device by stable name. Empty means the system default."),
    Field("audio.sample_rate", 16000, int, "Capture rate in Hz. Whisper wants 16000.", choices=(8000, 16000, 22050, 44100, 48000)),
    Field("audio.preroll_ms", 300, int, "Audio retained before the chord registered, so the first word is not clipped.", minimum=0, maximum=5000),
    Field("audio.max_utterance_s", 300, int, "Hard ceiling on a single utterance.", minimum=5, maximum=3600),
    Field(
        "audio.on_device_lost",
        "fallback",
        str,
        "What to do when the active device disappears mid-session.",
        choices=("fallback", "fail"),
    ),
    # ---- vad ------------------------------------------------------------
    Field("vad.enabled", True, bool, "Segment speech so trailing silence is not decoded."),
    Field("vad.silence_ms", 700, int, "Silence that closes a speech segment.", minimum=100, maximum=5000),
    Field("vad.threshold", 0.02, float, "Energy threshold, 0-1, relative to full scale.", minimum=0.0, maximum=1.0),
    Field("vad.min_speech_ms", 150, int, "Speech shorter than this is treated as noise.", minimum=0, maximum=2000),
    # ---- model ----------------------------------------------------------
    Field(
        "model.name",
        "auto",
        str,
        "Whisper model. 'auto' picks large-v3-turbo on CUDA, base on CPU.",
    ),
    Field("model.device", "auto", str, "Compute device.", choices=("auto", "cuda", "cpu")),
    Field(
        "model.compute_type",
        "auto",
        str,
        "Quantisation. 'auto' picks int8_float16 on CUDA, int8 on CPU.",
        choices=("auto", "int8", "int8_float16", "float16", "float32"),
    ),
    Field("model.language", "auto", str, "Force a language code, or 'auto' to detect."),
    Field("model.beam_size", 5, int, "Decoder beam width. Higher is slower and slightly better.", minimum=1, maximum=10),
    Field("model.keep_resident", True, bool, "Hold the model in memory between utterances."),
    Field("model.idle_unload_s", 0, int, "Unload after this many idle seconds. 0 disables.", minimum=0, maximum=86400),
    Field("model.verify_digest", True, bool, "Refuse to load model weights whose digest is not the pinned one."),
    # ---- streaming ------------------------------------------------------
    Field("streaming.enabled", True, bool, "Emit Partial results while the user is still speaking."),
    Field("streaming.interval_ms", 400, int, "Cadence of partial decodes.", minimum=100, maximum=5000),
    Field("streaming.min_audio_ms", 700, int, "Do not attempt a partial until this much audio exists.", minimum=100, maximum=10000),
    # ---- delivery -------------------------------------------------------
    Field(
        "delivery.mode",
        "paste",
        str,
        "How text reaches the focused field. 'paste' is fastest and layout-safe; "
        "'type' synthesises each character; 'clipboard' never synthesises input.",
        choices=("paste", "type", "clipboard"),
    ),
    Field("delivery.clipboard", True, bool, "Always place the transcript on the clipboard as well."),
    Field("delivery.restore_clipboard", True, bool, "Restore the previous clipboard contents after pasting."),
    Field("delivery.restore_delay_ms", 400, int, "How long to wait before restoring the clipboard.", minimum=0, maximum=10000),
    Field("delivery.default_profile", "standard", str, "Paste profile used when the focused application cannot be identified."),
    Field("delivery.trailing_space", False, bool, "Append a space to every delivered transcript."),
    Field("delivery.clipboard_only_apps", [], list, "Applications that must never receive synthesised input.", coerce=_str_list),
    # ---- memory ---------------------------------------------------------
    Field("memory.enabled", True, bool, "Persist transcripts to a searchable local store."),
    Field("memory.retain_days", 365, int, "Delete transcripts older than this. 0 keeps them forever.", minimum=0, maximum=36500),
    Field("memory.store_audio", False, bool, "Also retain the audio. Off by default: it makes the store far more sensitive."),
    Field("memory.audio_retain_days", 7, int, "Retention for stored audio, when enabled.", minimum=0, maximum=3650),
    Field("memory.redact_patterns", [], list, "Regexes whose matches are delivered but never stored.", coerce=_str_list),
    # ---- lexicon --------------------------------------------------------
    Field("lexicon.enabled", True, bool, "Bias the decoder toward known vocabulary."),
    Field("lexicon.learn", False, bool, "Grow the lexicon from observed corrections."),
    Field("lexicon.max_prompt_terms", 40, int, "Cap on terms injected as the decoder prompt.", minimum=0, maximum=200),
    # ---- ui -------------------------------------------------------------
    Field("ui.tray", True, bool, "Show the ambient tray indicator when a tray host exists."),
    Field("ui.overlay", False, bool, "Show live partial text in a small non-focusable overlay."),
    Field("ui.notifications", True, bool, "Send desktop notifications for faults and state changes."),
    Field("ui.sounds", True, bool, "Play a short cue when dictation starts and stops."),
    # ---- logging --------------------------------------------------------
    Field("log.level", "info", str, "Log verbosity.", choices=("debug", "info", "warning", "error")),
    Field("log.json", False, bool, "Force JSON log output even on a terminal."),
)

BY_PATH: dict[str, Field] = {f.path: f for f in SCHEMA}
SECTIONS: tuple[str, ...] = tuple(dict.fromkeys(f.section for f in SCHEMA))


# --------------------------------------------------------------------------
# config object
# --------------------------------------------------------------------------


@dataclass
class Config:
    """A validated configuration, plus the provenance of every setting."""

    values: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    loaded_files: list[Path] = field(default_factory=list)
    #: Settings that were renamed or retired while loading, for reporting.
    migrations: list[str] = field(default_factory=list)

    def __getitem__(self, path: str) -> Any:
        try:
            return self.values[path]
        except KeyError:
            raise KeyError(f"unknown setting: {path}") from None

    def get(self, path: str, default: Any = None) -> Any:
        return self.values.get(path, default)

    def source(self, path: str) -> str:
        return self.sources.get(path, "default")

    def section(self, name: str) -> dict[str, Any]:
        prefix = name + "."
        return {
            k[len(prefix) :]: v for k, v in self.values.items() if k.startswith(prefix)
        }

    def as_nested(self, only_non_default: bool = False) -> dict:
        out: dict[str, Any] = {}
        for path, value in self.values.items():
            if only_non_default and value == BY_PATH[path].default:
                continue
            section, _, key = path.rpartition(".")
            target = out.setdefault(section, {}) if section else out
            target[key] = value
        return out


def defaults() -> Config:
    return Config(values={f.path: f.default for f in SCHEMA})


def migrate(flat: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply renames and drop retired settings.

    Returns the migrated mapping and a list of notes worth showing the user.
    A stale config must never be a hard failure: someone upgrading should get
    a working daemon and an explanation, not a refusal to start.
    """
    notes: list[str] = []
    out: dict[str, Any] = {}
    for key, value in flat.items():
        if key in RETIRED:
            notes.append(f"{key} is no longer used ({RETIRED[key]})")
            continue
        if key in RENAMES:
            notes.append(f"{key} is now {RENAMES[key]}")
            out[RENAMES[key]] = value
            continue
        out[key] = value
    return out, notes


def _flatten(data: dict, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, path + "."))
        else:
            flat[path] = value
    return flat


def _env_overrides(environ: dict[str, str]) -> dict[str, Any]:
    """``DICTATOR_MODEL_NAME`` -> ``model.name``.

    Section and key names contain no underscores by construction, except for a
    handful of multiword keys; we resolve against the schema rather than
    guessing where the separator falls.
    """
    out: dict[str, Any] = {}
    lookup = {f.path.replace(".", "_").replace("-", "_").upper(): f.path for f in SCHEMA}
    for name, raw in environ.items():
        if not name.startswith("DICTATOR_"):
            continue
        path = lookup.get(name[len("DICTATOR_") :])
        if path is None:
            continue
        out[path] = _parse_scalar(raw, BY_PATH[path])
    return out


def _parse_scalar(raw: str, spec: Field) -> Any:
    """Turn a string into the field's type, reporting failures uniformly.

    Everything that can go wrong here is user input, so it must surface as a
    ValidationError with the setting named — never a bare ValueError from the
    conversion, which tells the user nothing about which setting was wrong.
    """
    if not isinstance(raw, str):
        return raw
    if spec.type is bool:
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ValidationError(
            f"{spec.path}: expected true or false, got {raw!r}"
        )
    if spec.type is int:
        try:
            return int(raw.strip())
        except ValueError:
            raise ValidationError(
                f"{spec.path}: expected a whole number, got {raw!r}"
            ) from None
    if spec.type is float:
        try:
            return float(raw.strip())
        except ValueError:
            raise ValidationError(
                f"{spec.path}: expected a number, got {raw!r}"
            ) from None
    if spec.type is list:
        return _str_list(raw)
    return raw


def parse_value(path: str, raw: str) -> Any:
    """Parse and validate a single setting from its string form (``config set``)."""
    spec = BY_PATH.get(path)
    if spec is None:
        raise ValidationError(f"unknown setting: {path}")
    return spec.validate(_parse_scalar(raw, spec))


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise Fault(
            code=FaultCode.CONFIG_INVALID,
            message=f"{path} is not valid TOML: {exc}",
            remedy=f"Fix the syntax in {path}, or delete it to fall back to defaults.",
        ) from exc


def load(
    *,
    extra_files: Iterable[Path] = (),
    overrides: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    use_site: bool = True,
    use_user: bool = True,
) -> Config:
    """Assemble a validated configuration from every layer."""
    config = defaults()

    layers: list[tuple[str, dict[str, Any]]] = []
    if use_site:
        site = site_config_path()
        if site.is_file():
            layers.append((f"site:{site}", _flatten(_read_toml(site))))
            config.loaded_files.append(site)
    if use_user:
        user = user_config_path()
        if user.is_file():
            layers.append((f"user:{user}", _flatten(_read_toml(user))))
            config.loaded_files.append(user)
    for path in extra_files:
        path = Path(path)
        if path.is_file():
            layers.append((f"file:{path}", _flatten(_read_toml(path))))
            config.loaded_files.append(path)

    layers.append(("env", _env_overrides(environ if environ is not None else dict(os.environ))))
    if overrides:
        layers.append(("cli", dict(overrides)))

    problems: list[str] = []
    for origin, flat in layers:
        flat, notes = migrate(flat)
        for note in notes:
            config.migrations.append(f"{origin}: {note}")
        for path, value in flat.items():
            spec = BY_PATH.get(path)
            if spec is None:
                problems.append(f"{origin}: unknown setting {path!r}")
                continue
            try:
                config.values[path] = spec.validate(value)
            except ValidationError as exc:
                problems.append(f"{origin}: {exc}")
                continue
            config.sources[path] = origin

    if problems:
        raise Fault(
            code=FaultCode.CONFIG_INVALID,
            message="; ".join(problems),
            remedy="Correct the listed settings, or run: dictator config reset <setting>",
        )
    return config


def save_user(updates: dict[str, Any], *, path: Path | None = None) -> Path:
    """Merge ``updates`` into the user config file, writing atomically.

    A value equal to its default is removed rather than written, so the file
    stays a record of deliberate choices instead of a snapshot of everything.
    """
    target = path or user_config_path()
    existing = _flatten(_read_toml(target)) if target.is_file() else {}

    for key, value in updates.items():
        spec = BY_PATH.get(key)
        if spec is None:
            raise ValidationError(f"unknown setting: {key}")
        validated = spec.validate(value)
        if validated == spec.default:
            existing.pop(key, None)
        else:
            existing[key] = validated

    nested: dict[str, Any] = {}
    for flat_key in sorted(existing):
        section, _, leaf = flat_key.rpartition(".")
        target_section = nested.setdefault(section, {}) if section else nested
        target_section[leaf] = existing[flat_key]
    nested = {k: v for k, v in nested.items() if v}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".toml.tmp")
        with tmp.open("wb") as handle:
            tomli_w.dump(nested, handle)
        os.replace(tmp, target)
        target.chmod(0o600)
    except OSError as exc:
        raise Fault(
            code=FaultCode.CONFIG_UNWRITABLE,
            message=f"could not write {target}: {exc}",
            remedy=f"Check permissions on {target.parent}.",
        ) from exc
    return target


def sample_toml() -> str:
    """A fully commented configuration file showing every setting at default."""
    lines = [
        "# dictator configuration",
        f"# {user_config_path()}",
        "#",
        "# Every setting below is shown at its built-in default and commented out.",
        "# Uncomment only what you change. Run 'dictator config list' to see the",
        "# effective values and where each one came from.",
    ]
    for section in SECTIONS:
        lines.append("")
        lines.append(f"[{section}]")
        for spec in SCHEMA:
            if spec.section != section:
                continue
            for note in _wrap(spec.help, 74):
                lines.append(f"# {note}")
            constraints = []
            if spec.choices:
                constraints.append("one of: " + ", ".join(str(c) for c in spec.choices))
            if spec.minimum is not None or spec.maximum is not None:
                constraints.append(f"range: {spec.minimum}..{spec.maximum}")
            if constraints:
                lines.append(f"#   ({'; '.join(constraints)})")
            rendered = tomli_w.dumps({spec.key: spec.default}).strip()
            lines.append(f"# {rendered}")
            lines.append("")
        if lines[-1] == "":
            lines.pop()
    return "\n".join(lines) + "\n"


def _wrap(text: str, width: int) -> list[str]:
    words, out, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            out.append(current)
            current = word
        else:
            current = candidate
    if current:
        out.append(current)
    return out
