"""Draft data/sections.yaml: assign every printed book to a section by title. Edit the YAML by hand afterwards."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECTIONS = {
    "Science Fiction & Fantasy": ["Dispossessed", "Dungeon Crawler", "Definitely Maybe", "Ancillary Justice", "Children of Time",
        "Hard to Be a God", "VALIS", "Use of Weapons", "Blindsight", "Annihilation", "Good Omens", "Great Work Of Time",
        "Time War", "Mountain in the Sea", "Old Man's War", "Toynbee", "End of Eternity", "Ministry for the Future",
        "Psalm for the Wild", "Consider Phlebas", "Dune", "Quicksilver", "Shadow of the Torturer", "Philip K. Dick",
        "Smoke and Mirrors", "Name of the Wind", "Diamond Age", "Hyperion", "Fifth Season", "Three Body", "Unsong",
        "Player of Games", "Truth of Fact", "Stories of Your Life", "Wind's Twelve", "Futurological", "On Venus",
        "Canticle for Leibowitz", "Gateway", "Rainbow's End", "Piranesi", "Infinite Planets"],
    "Fiction": ["Troy", "Monkey", "Maldon", "The Maniac", "When We Cease", "Forever Flowing", "Parables", "Arcadia",
        "Never Let Me Go", "The Road", "Red Plenty", "The Circle", "Invisible Cities", "Darkness at Noon", "Anthem",
        "Great Gatsby", "Oscar Wao", "Gantenbein", "Odyssey", "Sophie's World", "My Russian Grandmother"],
    "History": ["Peace to End All Peace", "John Dee", "Russian Revolutions", "Medieval Robots", "Bloodlands",
        "Collapse of Complex", "Medieval Technology", "Thirteenth Tribe", "Lost Enlightenment", "Debt:", "Night",
        "Building a Bridge", "War and Peace and War", "Fourth Turning", "Coffee-House", "Nothing is True",
        "Benjamin Franklin", "Lessons of History", "Must Mankind", "Boyd", "History of Future Cities", "Asimov's Chronology"],
    "Society & Economics": ["Incorruptible", "Moral Ambition", "Secret of our Success", "Abundance", "Technofeudalism",
        "End of the World", "Grand Transitions", "Protestant Ethic", "Why Information Grows", "Story of Us",
        "Rewiring America", "Palaces for the People", "Radical Markets", "Seeing Like a State", "Tribe", "Bowling Alone",
        "Shape of Tomorrow", "Skin in the Game", "Scale", "Whole Earth Discipline", "On Tyranny", "Homo Deus", "Sapiens",
        "Don't Think of an Elephant", "Righteous Mind", "Persuaders", "Profiles of the Future"],
    "Science & Nature": ["Immense Journey", "Breath", "Livewired", "Neurobiology of We", "Entangled Life",
        "Sand County", "Every Life is on Fire", "Tales from the Ant", "Timefulness", "Book of Why", "Blue Mind",
        "Man Who Loved Only Numbers", "Strange Loop", "Lucid Dreaming", "Hands"],
    "Thinking & Rationality": ["The Score", "Scout Mindset", "Why Greatness", "Thinking in Systems", "Where Good Ideas",
        "Range", "Reason in Human Affairs", "Superforecasters", "Why Teach Thinking", "Future Babble",
        "Actually Change Your Mind", "Psychology of Curiosity", "Thinking Fast", "Creativity", "Finite and Infinite"],
    "Philosophy & Religion": ["Courage to Be", "Way of Man", "Crisis of Narration", "Disappearance of Ritual", "Mystery Teachings",
        "David:", "Burnout Society", "Letters to my Palestinian", "Sabbath", "Power of Ritual", "Wild Problems",
        "Genesis", "Tao of Philosophy", "You Belong to the Universe", "12 Rules", "Shortness of Life", "Hedgehog and the Fox",
        "Moral Landscape", "In Praise of Idleness", "Science and Human Values"],
    "Work & Craft": ["Inventor Appeared", "Empowered", "Timeless Way of Building", "The Goal", "Smart Notes", "Sid Meier",
        "Revenge of Analog", "The Right It", "Real Estate", "Bad Blood", "Impro", "Deep Work", "One Minute Manager",
        "How to Fail", "Art of Tidying", "Bird by Bird", "Practical Doomsday", "Frank Herbert —", "Frank Herbert"],
    "Learning & Parenting": ["Good Inside", "Math from Three", "Blessing of a Skinned Knee", "Understanding How We Learn",
        "ABC", "Gardener", "Emotional Life of the Toddler", "Tools for Conviviality", "Fatherhood", "Yes Brain",
        "Deschooling", "New Father", "Mindstorms"],
    "Language, Music & Travel": ["In Patagonia", "Absolutely On Music", "Impossible Owls", "Secret Life of Groceries",
        "Fiddler is a Good Woman", "Is That a Fish"],
}
ex = set(json.loads((HERE / "data/exclude.json").read_text())["slugs"])
books = [b for b in json.loads((HERE / "data/books.json").read_text()) if b["slug"] not in ex]
assigned, unassigned = {k: [] for k in SECTIONS}, []
for b in books:
    full = b["title"] + (" — " + b["author"] if b["author"] else "")
    hit = None
    for sec, keys in SECTIONS.items():
        for k in keys:
            if (full.lower().startswith(k.lower()) if k in ("Night", "Range", "Tribe", "Scale", "Dune", "Hands", "ABC", "The Road", "Troy", "Monkey") else k.lower() in full.lower()):
                hit = sec; break
        if hit: break
    (assigned[hit] if hit else unassigned).append(b["slug"]) if hit else unassigned.append(b["slug"])
lines = ["# Sections, in shelf order. Move a slug to another section to re-shelve it; reorder sections freely.",
         "# The label is what's written on the sticky note.", ""]
for sec, slugs in assigned.items():
    lines.append(f"- label: {sec}")
    lines.append("  books:")
    lines += [f"    - {s}" for s in slugs]
if unassigned:
    lines.append("- label: Unsorted")
    lines.append("  books:")
    lines += [f"    - {s}" for s in unassigned]
(HERE / "data/sections.yaml").write_text("\n".join(lines) + "\n")
for sec, slugs in assigned.items(): print(f"{len(slugs):3}  {sec}")
print(f"{len(unassigned):3}  Unsorted:", unassigned)
