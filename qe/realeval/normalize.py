"""Deterministic text canonicalisation for lexical scoring (no model, no clock).

Maps equivalent surface forms to ONE token so containment/recall comparisons are not defeated by
formatting: number words (seven = 7), thousands separators, trailing zeros (5.0 = 5), percentages
(5 percent = 5%), durations (one week = 7 days = 168 hours; 12 months = twelve months = 1 year) and
dates (2015-03 = March 2015; 2015-03-01 = March 1, 2015).

Canonical tokens (all [a-z0-9], so the generic word tokenizer keeps them whole):
  q<value><unit>  duration; unit d (days; weeks and whole-day hours convert), h (other hours),
                  mo (months; years x 12);   '.' in the value is written 'p'
  pct<value>      percentage
  dt<yyyy><mm>[<dd>] calendar date
Limit (stated): conversions are exact arithmetic only (7 days, not "about a week"; a month is
never converted to days because its length is not fixed).
"""

from __future__ import annotations

import re

_MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december"
    .split())}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())} | {"sept": 9})
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b")
_MDY = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b")
_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\.?,?\s+(\d{{4}})\b")
_MY = re.compile(rf"\b({_MON})\.?,?\s+(\d{{4}})\b")

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
_WORDNUM = re.compile(
    r"\b(?:(?:" + "|".join(_TENS) + r")(?:[ -](?:" + "|".join(list(_UNITS)[1:10]) + r"))?"
    r"|" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")\b")
_UNIT_AFTER = re.compile(r"\s*(?:hours?|hrs?|days?|weeks?|months?|years?|yrs?|percent|per cent|%)")
_ARTICLE = re.compile(r"\b(?:a|an)\s+(?=(?:hours?|days?|weeks?|months?|years?)\b)")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_DECIMAL = re.compile(r"(?<![\w.])(\d+)\.(\d+)(?!\w|\.\d)")
_QTY = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*-?\s*(hours?|hrs?|days?|weeks?|months?|years?|yrs?)\b")
_PCT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|percent\b|per cent\b)")
_NEG_CONTRACTION = re.compile(r"n['’]t\b")


def _fmt(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def _date(y: str, m: int, d: str | None = None) -> str:
    return f"dt{y}{m:02d}" + (f"{int(d):02d}" if d else "")


def _words(m: re.Match[str]) -> str:
    text = m.group(0)
    if text in _UNITS:
        return str(_UNITS[text])
    parts = re.split(r"[ -]", text)
    return str(_TENS[parts[0]] + (_UNITS[parts[1]] if len(parts) > 1 else 0))


def _number_words(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        word = m.group(0)
        if word == "one" and not _UNIT_AFTER.match(text, m.end()):
            return word  # "no one", "one of the": a pronoun, not a quantity
        return _words(m)
    return _WORDNUM.sub(repl, text)


def _quantity(m: re.Match[str]) -> str:
    value, unit = float(m.group(1)), m.group(2)
    if unit.startswith("week"):
        return f"q{_fmt(value * 7)}d"
    if unit.startswith("day"):
        return f"q{_fmt(value)}d"
    if unit.startswith(("hour", "hr")):
        return f"q{_fmt(value / 24)}d" if value % 24 == 0 and value else f"q{_fmt(value)}h"
    if unit.startswith(("year", "yr")):
        return f"q{_fmt(value * 12)}mo"
    return f"q{_fmt(value)}mo"


def canon(text: str) -> str:
    """Lower-cased text with numbers, percentages, durations and dates in canonical tokens."""
    t = text.lower().replace("’", "'")
    t = _NEG_CONTRACTION.sub(" not", t)
    t = _ISO.sub(lambda m: _date(m.group(1), int(m.group(2)), m.group(3)), t)
    t = _MDY.sub(lambda m: _date(m.group(3), _MONTHS[m.group(1)], m.group(2)), t)
    t = _DMY.sub(lambda m: _date(m.group(3), _MONTHS[m.group(2)], m.group(1)), t)
    t = _MY.sub(lambda m: _date(m.group(2), _MONTHS[m.group(1)]), t)
    t = _ARTICLE.sub("1 ", t)
    t = _number_words(t)
    t = _THOUSANDS.sub("", t)
    t = _DECIMAL.sub(lambda m: m.group(1) if set(m.group(2)) == {"0"}
                     else f"{m.group(1)}.{m.group(2).rstrip('0')}", t)
    t = _PCT.sub(lambda m: f"pct{_fmt(float(m.group(1)))}", t)
    return _QTY.sub(_quantity, t)
