from app import analyze_with_llm

TEST_TEXTS = [
    (
        "AI-like sample",
        "Artificial intelligence represents a transformative paradigm shift in "
        "modern society. It is important to note that stakeholders must collaborate "
        "to ensure responsible and ethical deployment.",
    ),
    (
        "Human-like sample",
        "ok so i finally tried that ramen place and honestly? kinda mid. broth was "
        "fine but i was thirsty for hours after lol",
    ),
]

for name, text in TEST_TEXTS:
    print(f"\n{name}")
    print(analyze_with_llm(text))
