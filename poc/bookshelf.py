#!/usr/bin/env python3
"""bookshelf: put newly read books on the shelf.

  poc/bookshelf.py build [--publish] [--no-gen]
      1. Builds smus.com into poc/.cache/smus-www (lightning), so new reviews show up without a preview build.
      2. Re-reads the book list: smus.com + the newest goodreads/goodreads_library_export_*.csv
         (export from Goodreads and drop the CSV in goodreads/ to pick up Goodreads-only books).
      3. New books: Open Library lookup + data/overrides.json, dimensions (Open Library, Google Books, cover ratio),
         front cover (smus.com post image, else Open Library).
      4. Spine and back cover with Gemini for every book that has a cover but no spine (a few cents per book;
         --no-gen skips this and leaves those books off the shelf).
      5. Books in no section: Gemini picks one of the labels in data/sections.yaml and the slug is appended there
         (look for "# added ... by bookshelf.py"; move the line to re-shelve).
      6. Rebuilds review excerpts, the shelf layout and atlases; writes data/audit/sheet_NN.jpg for the new books and
         runs the viewer's fit check in headless Chrome.
      7. --publish: deploys to gh-pages (only if the fit check passed).

  poc/bookshelf.py redo <slug> [...] [--backs]   regenerate these spines (and back covers), then rebuild
  poc/bookshelf.py candidates [slug ...]          gather candidate covers for books with none -> preview/covers_review.html
  poc/bookshelf.py covers '<json>' | file.json    apply picks from covers_review.html ({slug: n | "https://…" | 0})
  poc/bookshelf.py status                         what's missing: no cover, no spine, no section
"""
import datetime
import functools
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SMUS = Path.home() / "Projects/smus.com"
LIGHTNING = Path.home() / "Projects/lightning/lightning"
CACHE = HERE / ".cache/smus-www"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SECTIONS = HERE / "data/sections.yaml"
TEXT_MODEL = "gemini-flash-latest"


# ---------- helpers ----------

def say(msg):
    print(f"\033[1m▸ {msg}\033[0m", flush=True)


def run(script, *args, numpy=False, check=True, quiet=False):
    """Run a pipeline script, streaming its output."""
    # The spine/back generators need numpy (run under uv); everything else uses this interpreter, whose TLS stack
    # Open Library accepts (uv's Python 3.13 gets connection resets from openlibrary.org).
    cmd = (["uv", "run", "-q", "--with", "pillow", "--with", "numpy", "python"] if numpy else [sys.executable]) + [script, *args]
    env = dict(os.environ, SMUS_WWW=str(CACHE))
    r = subprocess.run(cmd, cwd=HERE, env=env, text=True, capture_output=quiet)
    if check and r.returncode:
        if quiet:
            print(r.stdout[-2000:], r.stderr[-2000:], file=sys.stderr)
        sys.exit(f"{script} failed (exit {r.returncode})")
    return r


def load_env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def jload(rel, default=None):
    p = HERE / rel
    return json.loads(p.read_text()) if p.exists() else default


def excluded():
    ex = jload("data/exclude.json", {})
    return set(ex.get("slugs", [])) | set(ex.get("hidden", []))


def all_books():
    """slug -> book from the smus.com list and Goodreads-only list (what *should* be on the shelf)."""
    books = {b["slug"]: b for b in jload("data/books.json", [])}
    books.update({b["slug"]: b for b in jload("data/goodreads_books.json", [])})
    return {s: b for s, b in books.items() if s not in excluded()}


def shelved_in_yaml():
    return set(re.findall(r"^\s+- (?!label:|case:)(\S+)\s*$", SECTIONS.read_text(), re.M))


def has(kind, slug):
    return (HERE / f"data/{kind}/{slug}.jpg").exists()


# ---------- steps ----------

def build_site():
    say("Building smus.com into poc/.cache/smus-www")
    if not LIGHTNING.exists():
        sys.exit(f"lightning not found at {LIGHTNING}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["uv", "run", "-q", str(LIGHTNING), "-o", str(CACHE)], cwd=SMUS, capture_output=True, text=True)
    if r.returncode or not (CACHE / "books/index.html").exists():
        print(r.stderr[-2000:], file=sys.stderr)
        sys.exit("smus.com build failed")


def read_lists():
    say("Reading the book lists (smus.com + newest Goodreads export)")
    run("build_books.py", quiet=True)
    run("import_goodreads.py")


def enrich(new):
    say(f"Looking up {len(new)} new book(s): Open Library, overrides, dimensions")
    run("enrich.py", *new)
    ov = jload("data/overrides.json", {})
    hinted = [s for s in new if s in ov]
    if hinted:
        run("fix_matches.py", *hinted)
    run("refine_dims.py", *new, quiet=True)
    if os.environ.get("GOOGLE_BOOKS_API_KEY"):
        run("gbooks_dims.py", *new, check=False)


def covers(slugs):
    todo = [s for s in slugs if not has("covers", s)]
    if todo:
        say(f"Fetching covers for {len(todo)} book(s)")
        run("fetch_covers.py", *todo)


def generate(slugs, backs=True):
    if not slugs:
        return
    say(f"Generating {len(slugs)} spine(s) with Gemini")
    run("gen_spines.py", *slugs, numpy=True, check=False)
    if backs:
        need = [s for s in slugs if has("covers", s) and not has("backs", s)]
        if need:
            say(f"Generating {len(need)} back cover(s)")
            run("gen_backs.py", *need, numpy=True, check=False)


def gemini_text(prompt):
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{TEXT_MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    resp = json.load(urllib.request.urlopen(req, timeout=120))
    return json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])


def place(slugs):
    """Append books with no section to the section Gemini picks, keeping sections.yaml's hand formatting."""
    if not slugs:
        return {}
    text = SECTIONS.read_text()
    labels, case = [], None
    for line in text.splitlines():
        t = line.strip()
        if t.startswith("- case:"):
            case = t.split(":", 1)[1].strip()
        elif t.startswith("- label:"):
            labels.append((case, t.split(":", 1)[1].strip()))
    hidden_labels = {"Children's"}
    choices = [f"{c} / {l}" for c, l in labels if l not in hidden_labels]
    recs = {r["slug"]: r for r in jload("data/enriched.json", [])}
    books = all_books()
    # a few examples per section, so the model learns how *I* file things (e.g. Illich under Technology)
    examples, cur = {}, None
    for line in text.splitlines():
        t = line.strip()
        if t.startswith("- label:"):
            cur = t.split(":", 1)[1].strip(); examples[cur] = []
        elif cur and t.startswith("- ") and len(examples[cur]) < 6:
            s = t[2:].strip()
            if s in recs:
                examples[cur].append(recs[s].get("display_title") or recs[s]["title"])
    items = [{"slug": s, "title": (recs.get(s) or books[s]).get("display_title") or (recs.get(s) or books[s])["title"],
              "author": (recs.get(s) or books[s]).get("author"), "subjects": (recs.get(s) or {}).get("subjects", [])[:8]}
             for s in slugs]
    say(f"Choosing sections for {len(slugs)} book(s) with {TEXT_MODEL}")
    prompt = ("Shelve each book in exactly one section of my two bookcases. Sections (case / label), with books "
              "already there:\n" + "\n".join(f"- {c}: e.g. {', '.join(examples.get(c.split(' / ')[1], []))}" for c in choices)
              + "\n\nBooks:\n" + json.dumps(items, ensure_ascii=False)
              + '\n\nReply with JSON: {"<slug>": "<case> / <label>", ...} using the section strings exactly.')
    picks = gemini_text(prompt)
    stamp = datetime.date.today().isoformat()
    lines = text.splitlines()
    placed = {}
    for s in slugs:
        choice = picks.get(s)
        if choice not in choices:
            print(f"  {s}: no valid section from the model ({choice!r}); leaving it unplaced")
            continue
        want_case, want_label = choice.split(" / ", 1)
        # find the label line inside the right case, then the end of its book list
        case, at = None, None
        for i, line in enumerate(lines):
            t = line.strip()
            if t.startswith("- case:"):
                case = t.split(":", 1)[1].strip()
            elif t.startswith("- label:") and case == want_case and t.split(":", 1)[1].strip() == want_label:
                at = i
                break
        end = at + 1
        indent = "      "
        while end < len(lines) and not lines[end].strip().startswith(("- label:", "- case:")):
            if re.match(r"^\s+- ", lines[end]):
                indent = re.match(r"^(\s+)", lines[end]).group(1)
            end += 1
        while end > at + 1 and not lines[end - 1].strip():
            end -= 1                                        # keep blank separator lines after the section
        lines[end:end] = [f"{indent}# added {stamp} by bookshelf.py", f"{indent}- {s}"]
        placed[s] = choice
        print(f"  {s} -> {choice}")
    SECTIONS.write_text("\n".join(lines) + "\n")
    return placed


def rebuild():
    say("Rebuilding review excerpts, shelf layout and atlases")
    run("extract_reviews.py")
    run("build_shelf.py")


def fit_check():
    """Load the viewer in headless Chrome with ?fitdebug=1 and read its verdict from the console."""
    say("Fit check in headless Chrome")
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(HERE))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = subprocess.run([CHROME, "--headless=new", "--enable-unsafe-swiftshader", "--window-size=1200,800",
                            "--virtual-time-budget=40000", "--enable-logging=stderr", "--v=0", "--dump-dom",
                            f"http://127.0.0.1:{port}/preview/index.html?fitdebug=1"],
                           capture_output=True, text=True, timeout=240)
    finally:
        srv.shutdown()
    m = re.search(r'"FIT ([^"]*)"', r.stderr)
    errors = re.findall(r'"(Uncaught [^"]*)"', r.stderr)
    if errors:
        print("  page errors:", *errors[:3], sep="\n    ")
    verdict = m.group(1) if m else "no result (page failed to load?)"
    print("  " + verdict)
    return bool(m) and verdict.startswith("all shelves fit") and not errors


def audit(slugs):
    shelved = {b["slug"] for c in jload("preview/shelf.json")["cases"] for s in c["shelves"] for b in s}
    show = [s for s in slugs if s in shelved]
    if show:
        run("audit_sheet.py", *show, quiet=True)
        say(f"Check the new spines: open {HERE / 'data/audit'}")


def status(verbose=True):
    books, recs = all_books(), {r["slug"] for r in jload("data/enriched.json", [])}
    yaml, hidden = shelved_in_yaml(), excluded()
    out = {
        "not looked up": sorted(s for s in books if s not in recs),
        "no cover": sorted(s for s in books if s in recs and not has("covers", s)),
        "no spine": sorted(s for s in books if has("covers", s) and not has("textures", s)),
        "no section": sorted(s for s in books if s in recs and s not in yaml and s not in hidden),
    }
    if verbose:
        for k, v in out.items():
            print(f"{k:14} {len(v):3}  " + ", ".join(v[:8]) + (" …" if len(v) > 8 else ""))
    return out


# ---------- commands ----------

def cmd_build(args):
    load_env()
    build_site()
    known = {r["slug"] for r in jload("data/enriched.json", [])}
    read_lists()
    books = all_books()
    new = [s for s in books if s not in known]
    say(f"{len(new)} new book(s)" + (": " + ", ".join(new[:10]) + (" …" if len(new) > 10 else "") if new else ""))
    if new:
        enrich(new)
        covers(new)
    st = status(verbose=False)
    if "--no-gen" not in args:
        generate(st["no spine"])
    st = status(verbose=False)
    place([s for s in st["no section"] if has("textures", s)])
    rebuild()
    ok = fit_check()
    audit(new + st["no spine"])
    st = status(verbose=False)
    if st["no cover"]:
        print(f"\n{len(st['no cover'])} book(s) still have no cover; run `poc/bookshelf.py candidates` to pick them.")
    if "--publish" in args:
        if not ok:
            sys.exit("Not publishing: the fit check didn't pass.")
        say("Publishing to gh-pages")
        subprocess.run([str(HERE / "publish.sh")], cwd=ROOT, check=True)


def cmd_redo(args):
    load_env()
    slugs = [a for a in args if not a.startswith("-")]
    if not slugs:
        sys.exit("usage: bookshelf.py redo <slug> [...] [--backs]")
    if "--backs" in args:
        for s in slugs:
            (HERE / f"data/backs/{s}.jpg").unlink(missing_ok=True)
    generate(slugs, backs="--backs" in args)
    place([s for s in status(verbose=False)["no section"] if has("textures", s)])
    rebuild()
    fit_check()
    audit(slugs)


def cmd_candidates(args):
    load_env()
    run("cover_candidates.py", *args)
    say(f"Pick covers: open {HERE / 'preview/covers_review.html'} (via a local server, e.g. python3 -m http.server -d poc)")


def cmd_covers(args):
    """Apply picks: n = candidate number, a URL = download it, 0 = leave the book off (adds it to hidden)."""
    if not args:
        sys.exit("usage: bookshelf.py covers '<json>' | picks.json")
    src = Path(args[0])
    picks = json.loads(src.read_text() if src.exists() else args[0])
    manifest = jload("data/cover_candidates/manifest.json", {})
    from PIL import Image
    import io
    done, hide = [], []
    for slug, pick in picks.items():
        dst = HERE / f"data/covers/{slug}.jpg"
        if pick in (0, "0", None, ""):
            hide.append(slug); continue
        if isinstance(pick, str) and pick.startswith("http"):
            data = urllib.request.urlopen(urllib.request.Request(pick, headers={"User-Agent": "bookshelf/1.0"}), timeout=60).read()
            Image.open(io.BytesIO(data)).convert("RGB").save(dst, quality=92)
        else:
            c = next((c for c in manifest.get(slug, {}).get("candidates", []) if c["n"] == int(pick)), None)
            if not c:
                print(f"  {slug}: no candidate {pick}"); continue
            shutil.copy(HERE / "data/cover_candidates" / c["file"], dst)
        done.append(slug)
        print(f"  {slug}: cover set")
    if hide:
        ex = jload("data/exclude.json", {})
        ex.setdefault("hidden", []).extend(s for s in hide if s not in ex.get("hidden", []))
        (HERE / "data/exclude.json").write_text(json.dumps(ex, indent=1, ensure_ascii=False))
        print(f"  hidden (no cover): {', '.join(hide)}")
    if done:
        load_env()
        generate(done)
        place([s for s in done if s not in shelved_in_yaml() and has("textures", s)])
        rebuild()
        fit_check()
        audit(done)


COMMANDS = {"build": cmd_build, "redo": cmd_redo, "candidates": cmd_candidates, "covers": cmd_covers,
            "status": lambda a: status()}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]](sys.argv[2:])
