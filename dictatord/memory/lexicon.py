"""Adaptive memory: the words Whisper does not know that you use anyway.

Two mechanisms, deliberately separate. Terms are injected as the decoder's
initial prompt, which biases recognition. Substitutions are applied after
decoding, which is deterministic and catches what biasing misses.

Both are plain text and inspectable, because a memory you cannot audit is a
liability (v2.md §4.6).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..logging import get_logger

log = get_logger(__name__)

#: How many times a correction must be observed before it is trusted.
PROMOTION_THRESHOLD = 3


@dataclass
class Term:
    text: str
    weight: int = 1
    added_at: float = field(default_factory=time.time)
    source: str = "manual"


@dataclass
class Substitution:
    wrong: str
    right: str
    observations: int = 1
    active: bool = True
    source: str = "manual"


class Lexicon:
    """Vocabulary and corrections, persisted as readable JSON."""

    def __init__(self, path: Path, max_prompt_terms: int = 40) -> None:
        self.path = Path(path)
        self.max_prompt_terms = int(max_prompt_terms)
        self.terms: dict[str, Term] = {}
        self.substitutions: dict[str, Substitution] = {}
        self._pending: dict[str, int] = {}

    # -- persistence -----------------------------------------------------

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError) as exc:
            log.warning("the lexicon is unreadable; starting empty", error=str(exc))
            return
        for raw in data.get("terms", []):
            term = Term(**raw)
            self.terms[term.text.lower()] = term
        for raw in data.get("substitutions", []):
            sub = Substitution(**raw)
            self.substitutions[sub.wrong.lower()] = sub
        self._pending = dict(data.get("pending", {}))
        log.debug("lexicon loaded", terms=len(self.terms), substitutions=len(self.substitutions))

    def save(self) -> None:
        payload = {
            "terms": [vars(t) for t in self.terms.values()],
            "substitutions": [vars(s) for s in self.substitutions.values()],
            "pending": self._pending,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            tmp.replace(self.path)
            self.path.chmod(0o600)
        except OSError as exc:  # pragma: no cover - disk dependent
            log.warning("could not save the lexicon", error=str(exc))

    # -- terms -----------------------------------------------------------

    def add_term(self, text: str, source: str = "manual") -> bool:
        text = text.strip()
        if not text:
            return False
        key = text.lower()
        if key in self.terms:
            self.terms[key].weight += 1
            return False
        self.terms[key] = Term(text=text, source=source)
        return True

    def remove_term(self, text: str) -> bool:
        return self.terms.pop(text.strip().lower(), None) is not None

    def list_terms(self) -> list[Term]:
        return sorted(self.terms.values(), key=lambda t: (-t.weight, t.text.lower()))

    def prompt(self) -> str:
        """The decoder's initial prompt.

        Whisper treats this as preceding context, so a comma-separated list of
        proper nouns biases it toward them without asserting sentence
        structure. Capped, because an over-long prompt degrades decoding.
        """
        if not self.terms or self.max_prompt_terms <= 0:
            return ""
        chosen = [t.text for t in self.list_terms()[: self.max_prompt_terms]]
        return ", ".join(chosen)

    # -- substitutions ---------------------------------------------------

    def add_substitution(self, wrong: str, right: str, source: str = "manual") -> None:
        wrong, right = wrong.strip(), right.strip()
        if not wrong or not right or wrong.lower() == right.lower():
            return
        self.substitutions[wrong.lower()] = Substitution(
            wrong=wrong, right=right, observations=PROMOTION_THRESHOLD, source=source
        )
        self.add_term(right, source="substitution")

    def remove_substitution(self, wrong: str) -> bool:
        return self.substitutions.pop(wrong.strip().lower(), None) is not None

    def apply(self, text: str) -> str:
        """Apply active substitutions, respecting word boundaries and case."""
        if not text or not self.substitutions:
            return text
        result = text
        for sub in self.substitutions.values():
            if not sub.active:
                continue
            pattern = re.compile(rf"\b{re.escape(sub.wrong)}\b", re.IGNORECASE)
            result = pattern.sub(lambda m: _match_case(m.group(0), sub.right), result)
        return result

    # -- learning --------------------------------------------------------

    def observe_correction(self, before: str, after: str) -> list[str]:
        """Record a user correction; promote it once repeatedly seen.

        Requiring repetition is what stops an unrelated edit from poisoning the
        lexicon (v2.md K-6). Learning is opt-in and every entry is reversible.
        """
        promoted: list[str] = []
        for wrong, right in _diff_words(before, after):
            key = f"{wrong.lower()}\x00{right.lower()}"
            count = self._pending.get(key, 0) + 1
            self._pending[key] = count
            if count >= PROMOTION_THRESHOLD:
                self.substitutions[wrong.lower()] = Substitution(
                    wrong=wrong, right=right, observations=count, source="learned"
                )
                self.add_term(right, source="learned")
                self._pending.pop(key, None)
                promoted.append(f"{wrong} -> {right}")
                log.info("lexicon learned a correction", wrong=wrong, right=right,
                         observations=count)
        return promoted


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _diff_words(before: str, after: str) -> list[tuple[str, str]]:
    """Word-level substitutions between two versions of the same utterance.

    Only equal-length one-for-one replacements are considered. Insertions and
    deletions are ordinary editing, not recognition errors, and inferring
    vocabulary from them produces noise.
    """
    import difflib

    old = re.findall(r"\w+", before)
    new = re.findall(r"\w+", after)
    pairs: list[tuple[str, str]] = []
    matcher = difflib.SequenceMatcher(None, [w.lower() for w in old], [w.lower() for w in new])
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace" or (i2 - i1) != (j2 - j1):
            continue
        for offset in range(i2 - i1):
            wrong, right = old[i1 + offset], new[j1 + offset]
            if wrong.lower() != right.lower() and len(right) > 1:
                pairs.append((wrong, right))
    return pairs
