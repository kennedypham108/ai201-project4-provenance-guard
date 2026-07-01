from app import classify_attribution, generate_label

TEST_SCORES = [0.20, 0.60, 0.90]

for score in TEST_SCORES:
    attribution = classify_attribution(score)
    label = generate_label(attribution)

    print("\nScore:", score)
    print("Attribution:", attribution)
    print("Label:", label)
