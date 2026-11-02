"""Generate a back cover per book from its front cover with Gemini (only a sliver shows on hover).

Usage: uv run --with pillow --with numpy gen_backs.py [slug ...]
Reads data/covers/<slug>.jpg, writes data/backs/<slug>.jpg resized to the front cover's aspect.
"""
import base64, io, json, os, sys, urllib.request
from pathlib import Path
from PIL import Image
from gen_spines import MODEL, load_env

HERE = Path(__file__).resolve().parent

PROMPT = """The attached image is the front cover of a book. Create the BACK cover of this exact edition,
as a flat, straight-on scan that fills the whole image edge to edge (no background, no shadow, no 3D).
- Continue the front cover's background, illustration, colours and textures across the back,
  the way a wraparound jacket would.
- NO words at all: no title, no author, no blurb, no quotes, no publisher name, no lettering of any kind.
- The only graphic element besides the artwork is a small ISBN barcode in the lower right corner."""


def gen(img_bytes):
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img_bytes).decode()}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "2:3"}},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]},
    )
    resp = json.load(urllib.request.urlopen(req, timeout=180))
    for part in resp["candidates"][0]["content"]["parts"]:
        data = part.get("inlineData") or part.get("inline_data")
        if data:
            return Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")
    raise RuntimeError("no image in response")


def main():
    load_env()
    out = HERE / "data/backs"; out.mkdir(exist_ok=True)
    slugs = sys.argv[1:] or [p.stem for p in sorted((HERE / "data/covers").glob("*.jpg"))]
    for s in slugs:
        front = HERE / f"data/covers/{s}.jpg"
        if (out / f"{s}.jpg").exists() and not sys.argv[1:]:
            continue
        try:
            back = gen(front.read_bytes())
        except Exception as e:
            print(f"{s}: FAILED {e!r}"); continue
        back = back.resize(Image.open(front).size, Image.LANCZOS)  # match the front's aspect exactly
        back.save(out / f"{s}.jpg", quality=90)
        print(f"{s}: {back.size}")


if __name__ == "__main__":
    main()
