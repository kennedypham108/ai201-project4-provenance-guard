from app import (
    analyze_stylometrics,
    analyze_with_llm,
    classify_attribution,
    combine_scores,
)

TEST_CASES = [
    (
        "Clearly AI-generated",
        """Artificial intelligence represents a transformative paradigm shift in modern society.
It is important to note that while the benefits of AI are numerous, it is equally
essential to consider the ethical implications. Furthermore, stakeholders across
various sectors must collaborate to ensure responsible deployment.""",
    ),
    (
        "Clearly human-written",
        """ok so i finally tried that new ramen place downtown and honestly?
underwhelming. the broth was fine but they put WAY too much sodium in it and
i was thirsty for like three hours after. my friend got the spicy version and
said it was better. probably won't go back unless someone drags me there""",
    ),
    (
        "Borderline formal human writing",
        """The relationship between monetary policy and asset price inflation has been
extensively studied in the literature. Central banks face a fundamental tension
between their mandate for price stability and the unintended consequences of
prolonged low interest rates on equity and real estate valuations.""",
    ),
    (
        "Borderline edited AI writing",
        """I've been thinking a lot about remote work lately. There are genuine tradeoffs —
flexibility and no commute on one side, isolation and blurred work-life boundaries
on the other. Studies show productivity varies widely by individual and role type.""",
    ),
]

for name, text in TEST_CASES:
    llm = analyze_with_llm(text)
    style = analyze_stylometrics(text)
    combined = combine_scores(llm["llm_score"], style["stylometric_score"])
    attribution = classify_attribution(combined)

    print("\n" + "=" * 60)
    print(name)
    print(f"LLM score:          {llm['llm_score']}")
    print(f"Stylometric score: {style['stylometric_score']}")
    print(f"Combined score:    {combined}")
    print(f"Attribution:       {attribution}")
    print(f"Metrics:           {style['metrics']}")
    print(f"LLM reasoning:     {llm['reasoning']}")
