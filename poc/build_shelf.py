"""Write preview/shelf.json: shelves of books with dims, textures and poses.

Shelf 1 is the hand-arranged 15-book sample. Further books (batch*.txt, in order) are laid out
automatically: mostly upright, an occasional horizontal stack of 2-3 shorter books, and a leaning
book at the end of a shelf when there's room. The real layout will come from a subject layout file.
"""
import json
import random

import build_atlases
from pathlib import Path

HERE = Path(__file__).resolve().parent
INNER = 762          # mm: IKEA Billy 80 cm unit, inner width (must match preview)
LEAN_DEG = 11

books = {b["slug"]: b for b in json.loads((HERE / "data/enriched.json").read_text())}
picks = json.loads((HERE / "data/spine_picks.json").read_text())
jackets = {k for k in json.loads((HERE / "data/jackets.json").read_text()) if not k.startswith("_")}
reviews = json.loads((HERE / "data/reviews.json").read_text()) if (HERE / "data/reviews.json").exists() else {}
hidden = set(json.loads((HERE / "data/exclude.json").read_text()).get("hidden", []))

SAMPLE_LAYOUT = [
    # stack on the left, so most upright books sit right of centre and show their back covers when pulled out
    ("math-from-three-to-seven-by-a-k-zvonkin", "lying"), ("the-crisis-of-narration-by-byung-chul-han", "lying"),
    ("dune-by-frank-herbert", "upright"), ("the-dispossessed-by-u-k-le-guin", "upright"),
    ("piranesi-by-susanne-clark", "upright"), ("the-road-by-cormac-mccarthy", "upright"),
    ("invisible-cities-by-italo-calvino", "upright"), ("troy-by-stephen-fry", "upright"),
    ("red-plenty-by-francis-spufford", "upright"), ("seeing-like-a-state-by-james-scott", "upright"),
    ("thinking-fast-and-slow-by-kahnemann-tversky", "upright"), ("the-timeless-way-of-building", "upright"),
    ("mindstorms-by-seymour-papert", "upright"), ("bird-by-bird-by-anne-lamott", "upright"),
    ("finite-and-infinite-games-by-james-carse", "lean-left"),
]


def author_name(b):
    """Display author: hand-set name, else Open Library's if in Latin script, else smus.com/Goodreads's."""
    latin = lambda x: bool(x) and all(ord(c) < 0x250 for c in x if c.isalpha())
    if b.get("display_author"):
        return b["display_author"]
    if latin(b.get("ol_author")):
        return b["ol_author"]
    return b.get("author") or b.get("ol_author") or ""


def author_sort_key(b):
    """Surname of the first author, then title. 'Homer, tr. Emily Wilson' -> homer; 'Wu Cheng-en' stays as given."""
    import unicodedata
    SURNAME_FIRST = {"liu cixin": "liu", "wu cheng-en": "wu", "wu chêng-ên": "wu"}   # East Asian name order
    full = author_name(b).split(",")[0].strip()
    if full.lower() in SURNAME_FIRST:
        return (SURNAME_FIRST[full.lower()], (b.get("display_title") or b["title"]).lower())
    first = full.split("&")[0].split(" and ")[0].strip()
    name = full if len(first.split()) == 1 else first     # "Arkady & Boris Strugatsky" -> Strugatsky
    words = [w for w in name.replace(".", ". ").split() if w.lower().strip(".") not in ("jr", "sr", "ii", "iii", "tr")]
    surname = words[-1] if words else "~"
    fold = lambda x: unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return (fold(surname), fold(b.get("display_title") or b["title"]))


def split_title(t):
    """'A Pattern Language: Towns, Buildings, Construction (Center for ... Series)' ->
    title 'A Pattern Language', subtitle 'Towns, Buildings, Construction'. Short titles stay whole."""
    import re
    t = re.sub(r"\s*\([^)]*(?:Series|Edition|Volumes?|#)[^)]*\)\s*$", "", t).strip()
    if ":" in t and len(t) > 34:
        main, sub = t.split(":", 1)
        return {"title": main.strip(), "subtitle": sub.strip()}
    return {"title": t}


def pack_sections(secs, stack_gap, lean_p, reserve, allow_wrap):
    """Shelve whole sections: no section wraps onto the next shelf unless it is bigger than a shelf on its own.
    Sections are packed best-fit-decreasing into as few shelves as possible (so the order can shift a little), then
    shelves are ordered by where their sections come in sections.yaml. Within a shelf, stacks and leaning books are
    used only while everything still fits on that one shelf.
    allow_wrap=True is the fallback: plain greedy filling across sections."""
    if allow_wrap:
        return auto_shelves([s for _, _, ss in secs for s in ss], random.Random(42), stack_gap, lean_p, reserve)
    cap = INNER - 4
    width = lambda ss: sum(books[s]["dims_mm"]["t"] + 2.4 for s in ss)
    big = [(i, sec) for i, sec in enumerate(secs) if width(sec[2]) > cap]
    small = sorted([(i, sec) for i, sec in enumerate(secs) if width(sec[2]) <= cap], key=lambda x: -width(x[1][2]))
    bins = []                                       # [order key, used, [(i, sec)]]
    for i, sec in small:
        w = width(sec[2])
        fits = [bn for bn in bins if bn[1] + w + 8 <= cap - reserve * 0.5]
        if fits:
            bn = min(fits, key=lambda bn: cap - bn[1] - w)          # best fit
            bn[1] += w + 8; bn[2].append((i, sec)); bn[0] = min(bn[0], i)
        else:
            bins.append([i, w, [(i, sec)]])
    units = [(i, [(i, sec)]) for i, sec in big] + [(bn[0], sorted(bn[2], key=lambda x: x[0])) for bn in bins]
    # spare shelves (the case has MAX_SHELVES) go to the big sections, so they can afford stacks and leaning books
    mins = [len(auto_shelves([s for _, sec in m for s in sec[2]], random.Random(42), 10**9, 0.0, 0)) for _, m in units]
    spare = max(0, MAX_SHELVES - sum(mins))
    layout = []
    for _, members in sorted(units, key=lambda u: u[0]):
        ss = [s for _, sec in members for s in sec[2]]
        if len(members) == 1 and width(ss) > cap:
            # a section bigger than a shelf: as many stacks/leans as still fit in the minimum number of shelves
            need = len(auto_shelves(ss, random.Random(42), 10**9, 0.0, 0))
            if spare:
                need += 1; spare -= 1
            for g, lp, res in [(stack_gap, lean_p, reserve), (16, 0.5, reserve), (24, 0.4, reserve // 2),
                               (40, 0.3, 0), (80, 0.2, 0), (10**9, 0.0, 0)]:
                part = auto_shelves(ss, random.Random(42), g, lp, res)
                if len(part) <= need:
                    break
            layout += part
            continue
        for g, lp, res in [(stack_gap, lean_p, reserve), (40, 0.3, reserve // 2), (10**9, 0.0, 0)]:
            part = auto_shelves(ss, random.Random(42), g, lp, res)
            if len(part) == 1:
                break
        layout += part
    return layout


def add_lean_runs(layout, rng):
    """Use each shelf's slack: a few runs of 2-4 narrow upright books lean left on their neighbour, the way thin
    books slump when there's room. Pose becomes ('lean-run', degrees); the extra width is budgeted against the slack."""
    import math
    out = []
    for shelf in layout:
        used, stack = 0.0, 0.0
        for s, pose in shelf + [(None, "end")]:
            if pose != "lying" and stack:
                used += stack + 14; stack = 0.0           # a flat stack is as wide as its widest book
            if pose == "end":
                break
            d = books[s]["dims_mm"]
            if pose == "lying":
                stack = max(stack, d["h"])
            else:
                used += d["t"] + 2.2 + (0.2 * d["h"] + 30 if pose == "lean-left" else 0)
        slack = (INNER - 4) - used
        shelf = [list(x) + [None] for x in shelf]
        tries = 0
        while slack > 18 and tries < 30:
            tries += 1
            i = rng.randrange(1, max(2, len(shelf) - 1))
            run = []
            for j in range(i, min(i + rng.choice([2, 3, 3, 4]), len(shelf))):
                s, pose, _ = shelf[j]
                if pose != "upright" or books[s]["dims_mm"]["t"] > 24 or shelf[j - 1][1] not in ("upright", "lean-run"):
                    break
                run.append(j)
            if len(run) < 2 or any(shelf[j][1] == "lean-run" for j in run) or (run[-1] + 1 < len(shelf) and shelf[run[-1] + 1][1] == "lean-run"):
                continue
            h = max(books[shelf[j][0]]["dims_mm"]["h"] for j in run)
            deg = min(rng.uniform(4, 13), math.degrees(math.atan((slack - 6) / h)))
            if deg < 3:
                break
            for j in run:
                shelf[j][1], shelf[j][2] = "lean-run", round(deg, 1)
            slack -= h * math.tan(math.radians(deg)) + 4
        out.append([tuple(x) for x in shelf])
    return out


def record(slug, pose):
    b = books[slug]
    tex = HERE / f"data/textures/{slug}.jpg"
    if not tex.exists():
        return None
    return {
        "slug": slug, "link": b.get("link") or f"https://smus.com/books/{slug}", **split_title(b.get("display_title") or b["title"]), "author": author_name(b),
        "beloved": b["beloved"] or (reviews.get(slug, {}).get("rating") or 0) >= 4,   # smus ☆, or 4-5★ on Goodreads
        "dims": b["dims_mm"], "pose": pose,
        "texture": f"../data/textures/{slug}.jpg",
        "cover": f"../data/covers/{slug}.jpg" if (HERE / f"data/covers/{slug}.jpg").exists() else None,
        "back": f"../data/backs/{slug}.jpg" if (HERE / f"data/backs/{slug}.jpg").exists() else None,
        "spine_source": "jacket" if slug in jackets else "photo" if slug in picks else "ai",
        # dust-jacket scans are hardcovers; otherwise trust Open Library's format, defaulting to paperback
        "binding": "hardcover" if slug in jackets or b.get("binding_class") == "hardcover" else "paperback",
        "review": reviews.get(slug, {}),
        "atlas": build_atlases.build(slug, str(tex), *(str(HERE / f"data/{d}/{slug}.jpg") if (HERE / f"data/{d}/{slug}.jpg").exists() else None for d in ("covers", "backs"))),
        "publisher": b.get("publisher"), "pages": b.get("pages"), "year": b.get("year") or b.get("first_publish_year"),
    }


MAX_SHELVES = 6   # per bookcase (a real Billy)


def auto_shelves(slugs, rng, stack_gap=10, lean_p=0.6, reserve=0):
    cap = INNER - 4 - reserve          # leave `reserve` mm per shelf for leaning runs
    """Greedy fill. Widths: upright = t + ~1 mm gap; stack = tallest book's height + 14; lean ~ t + 0.2 h + 30."""
    shelves, cur, used = [], [], 0.0
    i = 0
    since_stack = 0
    while i < len(slugs):
        b = books[slugs[i]]
        d = b["dims_mm"]
        # occasionally lay 2-3 consecutive shorter books flat
        run = [s for s in slugs[i:i + 3] if books[s]["dims_mm"]["h"] <= 230]
        if since_stack > stack_gap and len(run) >= 2 and run == slugs[i:i + len(run)] and rng.random() < 0.5:
            width = max(books[s]["dims_mm"]["h"] for s in run) + 14
            if used + width <= cap:            # only lay them flat if the stack fits; else they stand upright
                cur += [(s, "lying") for s in run]
                used += width; i += len(run); since_stack = 0
                continue
        width = d["t"] + 2.2
        if used + width > cap:
            shelves.append(cur); cur, used = [], 0.0
        # lean the last book that fits on a shelf if there's room for the tilt
        lean_w = d["t"] + 0.2 * d["h"] + 30
        nxt = books[slugs[i + 1]]["dims_mm"]["t"] + 2.2 if i + 1 < len(slugs) else 0
        if cur and used + nxt > cap - lean_w and used + lean_w <= cap and cur[-1][1] == "upright" and rng.random() < lean_p:
            cur.append((slugs[i], "lean-left")); shelves.append(cur); cur, used = [], 0.0
            i += 1; since_stack += 1
            continue
        cur.append((slugs[i], "upright")); used += width; i += 1; since_stack += 1
    if cur:
        shelves.append(cur)
    return shelves


def load_sections():
    """Minimal reader for data/sections.yaml: [{case, sections: [{label, books: [slug]}]}]."""
    cases, case, sec = [], None, None
    for line in (HERE / "data/sections.yaml").read_text().splitlines():
        t = line.strip()
        if t.startswith("- case:"):
            case = {"name": t.split(":", 1)[1].strip(), "sections": []}; cases.append(case)
        elif t.startswith("- label:"):
            sec = {"label": t.split(":", 1)[1].strip(), "books": []}; case["sections"].append(sec)
        elif t.startswith("- ") and sec is not None:
            sec["books"].append(t[2:].strip())
    return cases


CAPACITY = MAX_SHELVES * (INNER - 4)


def main():
    """Two bookcases, Fiction first. If one case's books can't fit in MAX_SHELVES, its last sections overflow to
    the end of the other case (they keep their own group in the section bar)."""
    cases = load_sections()
    cases.sort(key=lambda c: c["name"] != "Fiction")
    plan = []                                   # per case: list of (group, label, [slugs])
    for case in cases:
        secs = []
        for sec in case["sections"]:
            have = [s for s in sec["books"] if s in books and s not in hidden and (HERE / f"data/textures/{s}.jpg").exists()]
            have.sort(key=lambda s: author_sort_key(books[s]))
            if have:
                secs.append((case["name"], sec["label"], have))
        plan.append(secs)
    width = lambda secs: sum(books[s]["dims_mm"]["t"] + 2.2 for _, _, ss in secs for s in ss)
    for i, secs in enumerate(plan):
        other = plan[1 - i]
        while width(secs) > CAPACITY * 0.92 and len(secs) > 1 and width(other) + width(secs[-1:]) <= CAPACITY * 0.92:
            other.append(secs.pop())
            print(f"  overflow: {other[-1][1]} ({other[-1][0]}) moves to the end of the {cases[1 - i]['name']} bookcase")
    out = []
    for case, secs in zip(cases, plan):
        ordered = [s for _, _, ss in secs for s in ss]
        starts = {ss[0]: (label, group) for group, label, ss in secs}
        fill = lambda shelf: sum(books[s]["dims_mm"]["t"] for s, _ in shelf)
        tries = [pack_sections(secs, g, lp, res, wrap)
                 for wrap in (False, True)
                 for res in (45, 25, 0)
                 for g, lp in [(10, 0.6), (16, 0.5), (24, 0.4), (40, 0.3), (80, 0.2), (10**9, 0.0)]]
        layout = next((t for t in tries if len(t) <= MAX_SHELVES and fill(t[-1]) > 80), None) \
            or min(tries, key=lambda t: (len(t) > MAX_SHELVES, len(t)))
        if len(layout) > MAX_SHELVES:
            print(f"  warning: {case['name']} needs {len(layout)} shelves even fully packed")
        rows = []
        for shelf in add_lean_runs(layout, random.Random(sum(map(ord, case["name"])))):
            row = []
            for s, pose, lean in shelf:
                r = record(s, pose)
                if lean:
                    r["lean"] = lean
                if r:
                    if s in starts:
                        r["section"], r["group"] = starts[s]
                    row.append(r)
            rows.append(row)
        out.append({"name": case["name"], "shelves": rows})
        print(f"{case['name']}: {len(ordered)} books on {len(rows)} shelves, {len(starts)} sections")
    (HERE / "preview/shelf.json").write_text(json.dumps({"inner": INNER, "cases": out}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
