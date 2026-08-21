"""``dictator lexicon`` — words the recogniser should know."""
from __future__ import annotations

import argparse

from dictatord import config as cfg
from dictatord.memory.lexicon import Lexicon

from .. import format as fmt


def _open() -> Lexicon:
    config = cfg.load()
    lexicon = Lexicon(cfg.data_dir() / "lexicon.json",
                      max_prompt_terms=config["lexicon.max_prompt_terms"])
    lexicon.load()
    return lexicon


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator lexicon",
        description="Proper nouns and jargon the recogniser should expect.",
    )
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("list", help="Everything the lexicon knows.")

    add = sub.add_parser("add", help="Add one or more terms.")
    add.add_argument("terms", nargs="+")

    remove = sub.add_parser("remove", help="Remove a term.")
    remove.add_argument("terms", nargs="+")

    fix = sub.add_parser("fix", help="Always rewrite one word as another.")
    fix.add_argument("wrong")
    fix.add_argument("right")

    unfix = sub.add_parser("unfix", help="Remove a rewrite rule.")
    unfix.add_argument("wrong")

    imp = sub.add_parser("import", help="Add every word from a file, one per line.")
    imp.add_argument("path")

    sub.add_parser("prompt", help="Show the prompt sent to the recogniser.")

    args = parser.parse_args(argv)
    action = args.action or "list"
    lexicon = _open()

    if action == "list":
        return _list(lexicon)
    if action == "add":
        added = sum(lexicon.add_term(t) for t in args.terms)
        lexicon.save()
        print(f"{fmt.OK} added {added} term(s); the lexicon holds {len(lexicon.terms)}")
        return 0
    if action == "remove":
        removed = sum(lexicon.remove_term(t) for t in args.terms)
        lexicon.save()
        print(f"{fmt.OK} removed {removed} term(s)")
        return 0
    if action == "fix":
        lexicon.add_substitution(args.wrong, args.right)
        lexicon.save()
        print(f"{fmt.OK} {args.wrong} will be rewritten as {fmt.bold(args.right)}")
        return 0
    if action == "unfix":
        ok = lexicon.remove_substitution(args.wrong)
        lexicon.save()
        print(f"{fmt.OK} removed" if ok else "no such rewrite rule")
        return 0
    if action == "import":
        return _import(lexicon, args.path)
    if action == "prompt":
        prompt = lexicon.prompt()
        print(prompt if prompt else fmt.dim("(empty — add terms with 'dictator lexicon add')"))
        return 0
    parser.print_help()
    return 2


def _list(lexicon: Lexicon) -> int:
    terms = lexicon.list_terms()
    if terms:
        rows = [[t.text, str(t.weight), fmt.dim(t.source)] for t in terms]
        print(fmt.table(rows, headers=("term", "seen", "source")))
    else:
        print(fmt.dim("no terms yet"))
    if lexicon.substitutions:
        print()
        rows = [
            [s.wrong, "→", fmt.bold(s.right), fmt.dim(s.source)]
            for s in lexicon.substitutions.values()
        ]
        print(fmt.table(rows, headers=("heard", "", "written", "source")))
    print()
    print(fmt.dim(f"  stored in {lexicon.path}"))
    return 0


def _import(lexicon: Lexicon, path: str) -> int:
    from pathlib import Path

    source = Path(path)
    if not source.is_file():
        print(f"{fmt.BAD} no such file: {path}")
        return 1
    added = 0
    for line in source.read_text().splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            added += lexicon.add_term(term, source="import")
    lexicon.save()
    print(f"{fmt.OK} imported {added} new term(s); the lexicon holds {len(lexicon.terms)}")
    return 0
