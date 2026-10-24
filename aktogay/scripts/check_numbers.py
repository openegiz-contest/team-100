"""Check of the headline numbers of the documents against the registry web/static/claims.json.

Every number of the form «+N,NN т» (a signed number followed by a mass unit), every signed number inside a bracket pair
«[a; b]» (an interval) and every signed number in a table cell of the presentation must be in the registry, and every claim
of the registry that points to a computation or a stored result is recomputed here:

  source.file  JSON file (relative to aktogay/) and source.path: dotted path to a number (or to a node with `mean` and `ci95`)
  verify.json  scenario results computed beforehand (sim/verify.py): path `runs[<id>@<kip>].…`
  check        'auto' (recomputed), 'history' (a run of an earlier code that is not repeated, kept as a record),
               'literature' (a number of another work), 'manual' (stated with the reason)

  python -I aktogay/scripts/check_numbers.py            # exit 1 when a number is unmarked or an automatic claim fails
  python -I aktogay/scripts/check_numbers.py --list     # all numbers found with the claim that holds them

Files scanned: final_docs/SUBMISSION.md (outside the «Concept» section, which is the participant's text: it is read, its numbers are
compared with the registry and mismatches are reported, nothing is edited), final_docs/README_aktogay.md and the presentation
index.html (path in the environment variable AKT_PRES, or pres/index.html inside or next to the repository when present; a checkout
without the presentation source skips it).

Stop-list (FORBIDDEN): statements the evidence of 24.10.2026 does not carry, kept as regular expressions. The same files and
final_docs/VALIDATION.md are scanned sentence by sentence (a table row is one sentence); a sentence that negates the statement
(«нельзя», «не пишем», «не значит», «неверно») or marks it as history of an earlier base is skipped. A hit in the files outside the
Concept gives exit code 1; a hit in the Concept is only reported to the owner of the text.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                  # aktogay/
STAGE = os.path.dirname(ROOT)
CLAIMS = os.path.join(ROOT, "web", "static", "claims.json")
def _doc(name: str) -> str:
    """final_docs/<name> in the working tree of the team, or the repository root (README_aktogay.md is README.md there)."""
    p = os.path.join(STAGE, "final_docs", name)
    return p if os.path.exists(p) else os.path.join(STAGE, "README.md" if name == "README_aktogay.md" else name)


DOCS = {"SUBMISSION": _doc("SUBMISSION.md"), "README": _doc("README_aktogay.md")}
STOP_DOCS = dict(DOCS, VALIDATION=_doc("VALIDATION.md"))
PRES_DEFAULTS = (os.path.join(STAGE, "pres", "index.html"), os.path.join(os.path.dirname(STAGE), "pres", "index.html"))
CONCEPT = ("## Concept", "## Почему это важно")

UNIT = r"(?=\s*(?:т\b|т\s*Cu|кг\b|кВт))"
RE_UNIT = re.compile(r"(?<![\w.,])([+−]\d+(?:,\d+)?)" + UNIT)
RE_BRACKET = re.compile(r"\[([^\[\]]{1,60})\]")
RE_SIGNED = re.compile(r"(?<![\w.,])([+−]\d+(?:,\d+)?)")
RE_CELL = re.compile(r'<td class="n">\s*([+−]\d+(?:,\d+)?)\s*</td>')


# ---------------------------------------------------------------------------------------------------------------------
# Stop-list. (id, regular expression, words that make the sentence acceptable). Sentences with a global skip word are never reported.
# ---------------------------------------------------------------------------------------------------------------------
SKIP_WORDS = ("нельзя", "не пишем", "не значит", "неверно")
HIST = ("22.10", "историч", "прежн", "8.8", "none", "несимметрич", "старая", "раньше стояло", "опубликован")
FORBIDDEN: list[tuple[str, str, tuple[str, ...]]] = [
    ("twin_gives_1_07", r"двойник\s+(?:даёт|даст)\s+\+1,07|\+1,07\s+т(?:\s+Cu)?\s+за\s+смену[^.]{0,20}на\s+фабрике", HIST),
    ("annual_money", r"(?:экономия|выигрыш|доход|польза)[^.|]{0,40}\s+в\s+год\b", ("не пересчитываем", "неизвестно", "нельзя")),
    ("1_07_as_current", r"\+1,07", HIST + ("history", "прежн", "смены хуже", "reported", "для связи", "контроль")),
    ("no_more_model_vs_model", r"снят\w*\s+упрёк|полностью\s+источников", ()),
    ("worse_as_proof", r"хуже\s+(?:людей|«как сейчас»|опытного)[^.|]{0,30}\b0\s*[–-]\s*1\s*%", ("следствие", "min", "добавк", "не доказ")),
    ("twin_sees_loud_earlier", r"двойник\s+раньше\s+людей\s+видит\s+громк|раньше\s+видны\s+громкие\s+беды", HIST + ("основан",)),
    ("find_roping_75", r"(?:канатирован\w+|дрейф\w*\s+pH|перекос\w*\s+ВВД)[^.|]{0,80}\b(?:за|через)\s+75\s*мин", ("допущен", "вход", "не измер", "прежн", "8.8", "none")),
    ("hard_ore_at_sag_2h", r"твёрд\w+\s+руд\w+[^.|]{0,100}(?:дошла\s+до\s+SAG|на\s+SAG|на\s+мельнице)[^.|]{0,60}(?:через\s+2\s*ч|2\s*ч\b)", ("4 ч", "244", "выемк", "край", "верхн", "dig", "sag")),
    ("4_7_minutes", r"\b4,7\s*мин", ("эквивалент", "разложен", "прежн")),
    ("maintenance_downtime_as_proof", r"reduced\s+maintenance\s+downtime[^.|]{0,200}(?:подтвержд|эффект\w*\s+двойник|даёт\s+двойник)", ("контекст", "не эффект")),
    ("kio_hours", r"КИО\s+0,78[^.|]{0,40}78\s*%\s*(?:часов|времени)", ("не часов", "суток", "доля суток")),
    ("crusher_nameplate", r"паспорт\w*\s+дробилки[^.|]{0,40}4\s?386", ("не паспорт", "нет", "не найден", "темп участка")),
    ("crusher_bottleneck", r"дробилк\w+\s+—\s+узкое\s+место|доступность\s+(?:дробилки|измельчения)\s+подтвержд", ()),
    ("line_hour_price_checked", r"цена\s+часа\s+линии[^.|]{0,40}сверена\s+с\s+отчётами", ()),
    ("reline_reproduced", r"перефутеровк\w+\s+воспроизведен\w*|84\s*ч\s+подтвержден\w*", ()),
    ("reline_hours_claims", r"85\s*[–-]\s*127\s*ч|\b109\s*ч\b|17,8\s*т\s*Cu|90\s*[–-]\s*103\s*ч|3,0\s*%\s*против\s*RME", ("перевод", "не пишем")),
    ("artifact_of_comparison", r"артефакт\w*\s+способа\s+сравнения|−5,55\s+против\s+−?5,47", ()),
    ("formula_beats_constant", r"лучше\s+константы[^.|]{0,60}(?:полугоди|годах)[^.|]{0,30}4\s+из\s+4|формула\s+извлечения\s+прогнозирует", ()),
    ("zigzag_is_noise", r"зигзаг[^.|]{0,60}шум\w*\s+отчётности", ()),
    ("pelambres", r"Актогай\s+похож\w*\s+на\s+Los\s+Pelambres", ()),
    ("q1_2020_cause_unnamed", r"I\s+кв\.\s+2020[^.|]{0,60}причина\s+не\s+назван", ()),
    ("rec_2026_075", r"±\s?0,75\s*п\.п|\b128\s+независим", ()),
    ("only_18_assumptions", r"только\s+(?:18|17|16|15)\s+(?:допущен|чисел|строк)", ("первом", "прежн", "скрининг 24.10", "до нового")),
    ("sourced_do_not_matter", r"(?:факты|вендор\w*|числа\s+из\s+источников)[^.|]{0,40}не\s+влияют", ("не сдвигал", "скрининг брал", "прежн", "первом")),
    ("sensors_realistic", r"датчики\s+реалистичн|несут\s+погрешность\s+по\s+паспорт\w*|структур\w+\s+ошибки\s+(?:взята\s+)?от\s+вендора", ()),
    ("no_sensor_bias", r"нет\s+никаких\s+смещений|уровень\s+склада[^.|]{0,60}считается\s+по\s+весам", ("не интеграл", "значение модели")),
    ("sag_energy_pinned", r"зажата\s+фактами|6,6\s*[–-]\s*7,27", ()),
    ("bozshakol_identical", r"(?:Бозшаколь|лент\w|дробилк\w)[^.|]{0,60}идентичн", ()),
    ("twin_cuts_emissions", r"двойник\s+сокращает\s+выбросы|двойник\s+убирает\s+лавину|0,95\s*[–-]\s*1\s+ложн", ("не воспроизвод",)),
    ("grid_cut_aktogay", r"сеть\s+14\.08\.2026\s+урезала\s+Актогай", ()),
    ("people_reaction_measured", r"реакци\w+\s+людей\s+Актогая\s+измерен|время\s+реакции\s+людей\s+Актогая\s+измерено", ()),
    ("stock_independent", r"не\s+зависит\s+от\s+трактовк\w+\s+склада", ()),
    ("first_in_world", r"\bвпервые\s+в\s+мире", ("не «впервые", "не \"впервые", "не 'впервые")),
]
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[А-ЯA-Z«\[(\-—])")


def plain(text: str) -> str:
    """Text for the stop-list: no markdown emphasis or code marks, tags and entities of the presentation removed, one space between words."""
    t = re.sub(r"<[^>]+>", " ", text)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&laquo;", "«").replace("&raquo;", "»")
    t = t.replace("*", "").replace("`", "").replace("\xa0", " ").replace("\u202f", " ")
    return t


def sentences(text: str) -> list[str]:
    out: list[str] = []
    for line in plain(text).split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            continue
        out.extend(x.strip() for x in _SENT_SPLIT.split(line) if x.strip())
    return out


def forbidden_hits(text: str) -> list[tuple[str, str]]:
    """[(id, sentence)] of the stop-list statements in a text that neither negate them nor mark them as an earlier base."""
    hits = []
    for sent in sentences(text):
        low = sent.lower()
        if any(w in low for w in SKIP_WORDS):
            continue
        for fid, rx, ok in FORBIDDEN:
            if re.search(rx, sent, re.I) and not any(w.lower() in low for w in ok):
                hits.append((fid, sent[:240]))
    return hits


def pres_path() -> str | None:
    for p in (os.environ.get("AKT_PRES"),) + PRES_DEFAULTS:
        if p and os.path.exists(p):
            return p
    return None


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def tokens_in(text: str, html: bool = False) -> list[tuple[str, str]]:
    """[(token, context)] of the numbers that must be registered."""
    out: list[tuple[str, str]] = []
    for m in RE_UNIT.finditer(text):
        out.append((m.group(1), text[max(0, m.start() - 30):m.end() + 12].replace("\n", " ")))
    for b in RE_BRACKET.finditer(text):
        body = b.group(1)
        if not re.match(r"^\s*(?:95\s*%\s*ДИ\s*)?[+−]\d", body) or (";" not in body and "…" not in body):
            continue
        for m in RE_SIGNED.finditer(body):
            out.append((m.group(1), text[max(0, b.start() - 24):b.end()].replace("\n", " ")))
    if html:
        for m in RE_CELL.finditer(text):
            out.append((m.group(1), text[max(0, m.start() - 40):m.end()].replace("\n", " ")))
    seen = set()
    uniq = []
    for t, c in out:
        if (t, c) not in seen:
            seen.add((t, c))
            uniq.append((t, c))
    return uniq


def split_concept(text: str) -> tuple[str, str]:
    i, j = text.index(CONCEPT[0]), text.index(CONCEPT[1])
    return text[:i] + text[j:], text[i:j]


def fmt(v: float, dec: int) -> str:
    r = round(v + (1e-12 if v >= 0 else -1e-12), dec)
    s = f"{abs(r):.{dec}f}".replace(".", ",")
    return ("+" if r > 0 else "−" if (r < 0 or v < 0) else "") + s


def dec_of(token: str) -> int:
    return len(token.split(",")[1]) if "," in token else 0


def _get(obj, path: str):
    cur = obj
    for part in re.findall(r'\["[^"]+"\]|[^.\[\]]+|\[\d+\]', path):
        if part.startswith('["'):
            cur = cur[part[2:-2]]
        elif part.startswith("["):
            cur = cur[int(part[1:-1])]
        elif isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


_FILES: dict = {}


def load_json(rel: str):
    if rel not in _FILES:
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
            _FILES[rel] = json.load(f)
    return _FILES[rel]


def verify_index() -> dict:
    d = load_json("web/static/verify.json")
    return {"%s@%d" % (r["id"], r["kip"]): r for r in d["runs"]}


def resolve(claim: dict):
    """The computed number(s) of an automatic claim: (value, ci or None, scale) from its source."""
    src = claim["source"]
    scale = float(src.get("scale", 1.0))
    if src["file"] == "web/static/verify.json":
        node = _get(verify_index(), src["path"])
    else:
        node = _get(load_json(src["file"]), src["path"])
    if isinstance(node, dict):
        ci = node.get("ci95") or node.get("ci95_mean_bca") or ([node["min"], node["max"]] if "min" in node and "max" in node else None)
        return float(node["mean"]) * scale, ([float(ci[0]) * scale, float(ci[1]) * scale] if ci else None)
    return float(node) * scale, None


def tokens_of(claim: dict) -> list[str]:
    out = [claim["text"]] if claim.get("text") else []
    out += list(claim.get("ci_text") or [])
    out += list(claim.get("also") or [])
    return out


def check_claims(reg: dict) -> tuple[list[str], list[str]]:
    """Claims recomputed from their source: (failures of automatic claims, warnings of history claims that differ)."""
    bad: list[str] = []
    warn: list[str] = []
    for c in reg["claims"]:
        if c.get("check") not in ("auto", "history") or not c.get("source"):
            continue
        out = warn if c["check"] == "history" else bad
        try:
            value, ci = resolve(c)
        except (KeyError, IndexError, TypeError) as e:
            out.append(f"{c['id']}: source not found ({e!r})")
            continue
        sign = -1.0 if "negated" in (c.get("note") or "") or c.get("negate") else 1.0
        if sign < 0:
            value = -value
            ci = [-ci[1], -ci[0]] if ci else None
        if c.get("text") and fmt(value, dec_of(c["text"])) != c["text"]:
            out.append(f"{c['id']}: document {c['text']}, computed {fmt(value, dec_of(c['text']))} ({value:.4f})")
        if c.get("ci_text"):
            if ci is None:
                out.append(f"{c['id']}: source has no interval")
            else:
                for t, v in zip(c["ci_text"], ci):
                    if fmt(v, dec_of(t)) != t:
                        out.append(f"{c['id']}: interval {t}, computed {fmt(v, dec_of(t))}")
    return bad, warn


def scan(reg: dict, with_pres: bool = True):
    """(unmarked, listing, concept_report): unmarked tokens of the checked files, all found tokens with claim ids,
    and what the Concept section holds against the registry (read only)."""
    held: dict[str, list[str]] = {}
    for c in reg["claims"]:
        for t in tokens_of(c):
            held.setdefault(t, []).append(c["id"])
    unmarked, listing = [], []
    texts = {name: read(p) for name, p in DOCS.items()}
    concept_text = ""
    texts["SUBMISSION"], concept_text = split_concept(texts["SUBMISSION"])
    pp = pres_path() if with_pres else None
    if pp:
        texts["presentation"] = read(pp)
    for name, text in texts.items():
        for tok, ctx in tokens_in(text, html=(name == "presentation")):
            ids = held.get(tok)
            listing.append((name, tok, ids, ctx))
            if not ids:
                unmarked.append((name, tok, ctx))
    concept = []
    for tok, ctx in tokens_in(concept_text):
        ids = held.get(tok)
        concept.append((tok, ids, ctx))
    return unmarked, listing, concept


def scan_forbidden(with_pres: bool = True) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """(hits outside the Concept as (file, id, sentence), hits inside the Concept as (id, sentence))."""
    hits: list[tuple[str, str, str]] = []
    concept_hits: list[tuple[str, str]] = []
    for name, path in STOP_DOCS.items():
        text = read(path)
        if name == "SUBMISSION":
            text, concept = split_concept(text)
            concept_hits = forbidden_hits(concept)
        hits += [(name, fid, sent) for fid, sent in forbidden_hits(text)]
    pp = pres_path() if with_pres else None
    if pp:
        hits += [("presentation", fid, sent) for fid, sent in forbidden_hits(read(pp))]
    return hits, concept_hits


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reg = json.loads(read(CLAIMS))
    bad, warn = check_claims(reg)
    unmarked, listing, concept = scan(reg)
    stop_hits, stop_concept = scan_forbidden()
    if "--list" in argv:
        for name, tok, ids, ctx in listing:
            print(f"{name:12} {tok:8} {','.join(ids) if ids else 'НЕТ В РЕЕСТРЕ':28} {ctx}")
    for msg in bad:
        print("FAIL", msg)
    for msg in warn:
        print("warning (history, differs from the stored re-run):", msg)
    for name, tok, ctx in unmarked:
        print(f"UNMARKED {name}: {tok}  …{ctx}")
    for tok, ids, ctx in concept:
        if not ids:
            print(f"CONCEPT (read only): {tok} is not in the registry  …{ctx}")
    for name, fid, sent in stop_hits:
        print(f"FORBIDDEN {name}: {fid}  …{sent}")
    for fid, sent in stop_concept:
        print(f"CONCEPT (read only): stop-list {fid}  …{sent}")
    kinds: dict[str, int] = {}
    for c in reg["claims"]:
        kinds[c.get("check", "?")] = kinds.get(c.get("check", "?"), 0) + 1
    print(f"claims {len(reg['claims'])} ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}); numbers found {len(listing)}; "
          f"unmarked {len(unmarked)}; failed {len(bad)}; forbidden {len(stop_hits)}; Concept numbers not in registry {sum(1 for _t, i, _c in concept if not i)}; "
          f"Concept stop-list {len(stop_concept)}")
    return 1 if (bad or unmarked or stop_hits) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
