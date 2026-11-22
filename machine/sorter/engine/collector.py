"""The collector line ("R 0381 DSK • EN", "147/269 R ELD EN", "©1995 Wizards of the Coast 128/350"):
a copy of src/CardScanner.Core/Recognition/CollectorLine.cs (same regular expressions)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace


def upper_invariant(s: str) -> str:
    """Like .NET ToUpperInvariant: one character in, one character out (Python's upper() turns ß into SS)."""
    return "".join(u if len(u := c.upper()) == 1 else c for c in s)


def _digits(s: str) -> str:
    return "".join(c for c in s if c.isdecimal())


_COPYRIGHT_TEXT = re.compile(r"WIZARD|RIGHTS\s?RESERV|ALL\s?RIGHTS")
_FUZZY_YEAR = re.compile(r"(?<![A-Z0-9])[A-Z1|©]?[9GQ][9GQ]([0-9])(?![0-9])")
_AFTER_COAST_ANCHOR = re.compile(r"C[O0][A-Z]{1,3}[TRS](?![A-Z])|INC\b|LLC|L1C|LT[O0]")
_AFTER_COAST = re.compile(r"C[O0][A-Z]{1,3}T[^0-9]{0,12}?([0-9O]{1,4})(?:\s*/\s*[0-9O]{1,4})?")
_NUMBER = re.compile(r"(?<![A-Z0-9])[A-Z]{0,2}[.,\-]?\s?([0-9O]*[0-9][0-9O]*)(?:\s*/\s*[0-9O]{1,4})?\s?[CURMLSTPB]?(?![0-9])")
_SET_AND_LANGUAGE = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{3,5}?)\s*[\-–]?\s*([·•★*.|]|[IT1L](?=EN|JP)|)\s*[\-–]?\s*(EN|JP)(?![A-Z0-9]*[·•★])")
_FOREIGN = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{3,5})\s*([·•★*])\s*(KL|PH|DE|FR|IT|ES|SP|PT|RU|KO|CS|CT|JA|LA|QY)(?![A-Z])")
_TOTAL = re.compile(r"(?<![0-9])[0-9O]{1,4}\s*/\s*([0-9O]{2,4})(?![0-9])")
_YEAR = re.compile(r"(?<![0-9])(19|20)[0-9]{2}(?![0-9])")


def _fuzzy_year(up: str) -> int | None:
    if not _COPYRIGHT_TEXT.search(up):
        return None
    year = None
    for m in _FUZZY_YEAR.finditer(up):
        y = 1990 + (ord(m.group(1)[0]) - ord("0"))
        if 1993 <= y <= 1999:
            year = max(year or 0, y)
    return year


def _all_digits(s: str) -> bool:
    return all(c.isdecimal() for c in s)


@dataclass(frozen=True)
class CollectorLine:
    raw: str = ""
    numbers: frozenset = frozenset()
    set_codes: frozenset = frozenset()
    foil: bool | None = None
    copyright_year: int | None = None
    language: str | None = None
    set_totals: frozenset = field(default_factory=frozenset)

    @property
    def foreign_language(self) -> bool:
        return self.language is not None and self.language != "EN"

    @property
    def has_copyright_text(self) -> bool:
        return bool(_COPYRIGHT_TEXT.search(upper_invariant(self.raw)))

    @staticmethod
    def _copyright_digits_one(raw: str) -> str:
        up = upper_invariant(raw)
        ms = list(_AFTER_COAST_ANCHOR.finditer(up))
        if not ms:
            return ""
        return _digits(up[ms[-1].end():].replace("O", "0"))

    def copyright_digits_contain(self, number: str) -> bool:
        d = _digits(number).lstrip("0")
        if len(d) < 2 or len(d) != len(number.lstrip("0").rstrip("★sab")):
            return False
        return d in "|".join(self._copyright_digits_one(part) for part in self.raw.split("|"))

    @staticmethod
    def parse(raw: str) -> "CollectorLine":
        up = upper_invariant(raw)
        numbers = set()
        for m in _NUMBER.finditer(up):
            n = m.group(1).replace("O", "0").lstrip("0")
            if n:
                numbers.add(n)
        sets, foil = set(), None
        for m in _SET_AND_LANGUAGE.finditer(up):
            s = m.group(1)
            if len(s) >= 3 and not _all_digits(s):
                sets.add(s.lower())
            mark = m.group(2) or ""
            if mark in ("★", "*"):
                foil = True
            elif mark in ("·", "•", ".") and foil is None:
                foil = False
            if mark in ("I", "T", "1", "L", "|"):
                if len(s) + 1 <= 5:
                    sets.add((s + mark).lower())
                if foil is None:
                    foil = False
        year = None
        for m in _YEAR.finditer(up):
            y = int(m.group(0))
            if 1993 <= y <= 2030:
                year = max(year or 0, y)
        if year is None:
            year = _fuzzy_year(up)
        lang = None
        for m in _SET_AND_LANGUAGE.finditer(up):
            if lang is None:
                lang = m.group(3)
        for m in _FOREIGN.finditer(up):
            if lang is None:
                lang = m.group(3)
            s = m.group(1)
            if not _all_digits(s):
                sets.add(s.lower())
            if m.group(2) in ("★", "*"):
                foil = True
            elif foil is None:
                foil = False
        if lang == "JA":
            lang = "JP"
        totals = set()
        for m in _TOTAL.finditer(up):
            t = int(m.group(1).replace("O", "0"))
            if 20 <= t <= 999:
                totals.add(t)
        return CollectorLine(raw, frozenset(numbers), frozenset(sets), foil, year, lang, frozenset(totals))

    def merged(self, again: "CollectorLine") -> "CollectorLine":
        """A second, sharper read of the same small print added to this one."""
        return replace(self, raw=self.raw + " | " + again.raw, numbers=self.numbers | again.numbers,
                       set_codes=self.set_codes | again.set_codes, foil=self.foil if self.foil is not None else again.foil)

    def with_copyright_numbers(self, line: str) -> "CollectorLine":
        nums = set(self.numbers)
        up = upper_invariant(line)
        for m in _AFTER_COAST.finditer(up):
            n = m.group(1).replace("O", "0").lstrip("0")
            if n:
                nums.add(n)
            ln = 2
            while ln < len(n) and ln <= 3:
                nums.add(n[:ln])
                ln += 1
        year = self.copyright_year
        for m in _YEAR.finditer(line):
            y = int(m.group(0))
            if 1993 <= y <= 2030:
                year = max(year or 0, y)
        if year is None:
            year = _fuzzy_year(up)
        totals = set(self.set_totals)
        for m in _TOTAL.finditer(up):
            t = int(m.group(1).replace("O", "0"))
            if 20 <= t <= 999:
                totals.add(t)
        return replace(self, raw=(self.raw + " | " + line).strip(" |"), numbers=frozenset(nums),
                       copyright_year=year, set_totals=frozenset(totals))


EMPTY = CollectorLine()
