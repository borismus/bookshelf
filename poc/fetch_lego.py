"""Box art for the classic Lego Space sets on the low Billy (images: Brickset; box art (c) The LEGO Group).
Writes preview/props/lego/<set>.jpg (front, ~600 px) and preview/props/lego/manifest.json with each box's aspect
ratio (sides are classic-Space black)."""
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "preview/props/lego"
# set number, name, real box width in mm (approximate; boxes are scaled to fit the compartments)
SETS = [("6980", "Galaxy Commander", 470), ("6970", "Beta-1 Command Base", 440), ("928", "Galaxy Explorer", 480),
        ("6951", "Robot Command Center", 380), ("6880", "Surface Explorer", 240), ("6842", "Shuttle Craft", 220),
        ("6950", "Mobile Rocket Transport", 250)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for num, name, w in SETS:
        req = urllib.request.Request(f"https://images.brickset.com/sets/images/{num}-1.jpg", headers={"User-Agent": "bookshelf/1.0"})
        im = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
        im.thumbnail((640, 640), Image.LANCZOS)
        im.save(OUT / f"{num}.jpg", quality=84, optimize=True)
        manifest.append({"set": num, "name": name, "file": f"props/lego/{num}.jpg", "aspect": round(im.width / im.height, 3),
                         "w": w, "side": "#17171c"})
        print(num, name, im.size, manifest[-1]["side"])
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
