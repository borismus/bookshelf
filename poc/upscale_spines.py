"""Re-render low-resolution real spine crops at high resolution with Gemini, staying faithful to the photo.

Usage: uv run --with pillow --with numpy upscale_spines.py [slug ...]   (default: picked crops narrower than MIN_W px)
Reads data/crops/<slug>.jpg, writes data/ai/<slug>/upscale_N.png and data/textures/<slug>.jpg.
"""
import base64, io, json, os, sys, urllib.request
from pathlib import Path
from PIL import Image
from gen_spines import MODEL, load_env, trim

HERE = Path(__file__).resolve().parent
MIN_W = 200

PROMPT = """The attached image is a low-resolution photo of a real book spine, cropped from a larger picture.
Re-create this exact spine as a sharp, high-resolution photograph.
- Keep everything faithful: identical layout, colours, typefaces, artwork, logos and text. Do not redesign, add or remove anything.
- Spell every word exactly as it appears.
- Shot perfectly straight-on (orthographic), upright, centred, filling almost the full image height.
- Background: perfectly flat, uniform mid grey (RGB 128,128,128), no shadow, no other objects.
- Realistic printed card texture and soft even studio light."""


def upscale(img_bytes):
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img_bytes).decode()}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16", "imageSize": "2K"}},
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
    picks = {k: v for k, v in json.loads((HERE / "data/spine_picks.json").read_text()).items() if not k.startswith("_")}
    slugs = [a for a in sys.argv[1:]] or [s for s in picks if Image.open(HERE / f"data/crops/{s}.jpg").width < MIN_W]
    for s in slugs:
        crop = HERE / f"data/crops/{s}.jpg"
        out = HERE / "data/ai" / s
        out.mkdir(parents=True, exist_ok=True)
        raw = upscale(crop.read_bytes())
        n = len(list(out.glob("upscale_*.png")))
        raw.save(out / f"upscale_{n}.png")
        sp = trim(raw)
        sp.save(HERE / "data/textures" / f"{s}.jpg", quality=92)
        print(f"{s}: {Image.open(crop).size} -> {sp.size}")


if __name__ == "__main__":
    main()
