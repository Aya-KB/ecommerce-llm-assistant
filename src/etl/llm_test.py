import time
import subprocess

# ======================
# CHEMIN OLLAMA (IMPORTANT)
# ======================
OLLAMA_PATH = r"C:\Users\hp\AppData\Local\Programs\Ollama\ollama.exe"


# ======================
# OLLAMA TEST FUNCTION
# ======================
def test_ollama(model, prompt):
    start = time.time()

    result = subprocess.run(
        [OLLAMA_PATH, "run", model],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    return {
        "model": model,
        "response": result.stdout.strip(),
        "time": round(time.time() - start, 2)
    }


# ======================
# PROMPTS TEST
# ======================
prompts = [
    "Analyse les ventes e-commerce.",

    """Tu es un data analyst expert e-commerce.
    Analyse ces données :
    - 1200 commandes
    - 300 retards
    - délai moyen 5 jours

    Donne 3 insights business.""",

    """En tant que consultant business, explique pourquoi
    les livraisons sont en retard et propose des solutions."""
]


# ======================
# RUN BENCHMARK
# ======================
if __name__ == "__main__":

    results = []

    llms = ["llama3", "mistral"]

    for model in llms:
        for p in prompts:
            print(f"\n Test {model}...")
            results.append(test_ollama(model, p))

    # ======================
    # RESULTS
    # ======================
    print("\n\n======= RESULTS =======")

    for r in results:
        print("\n----------------------")
        print("MODEL:", r["model"])
        print("TIME:", r["time"], "sec")
        print("RESPONSE:\n", r["response"])


# ======================
# SIMPLE SCORING
# ======================
def score_response(text):
    return len(text.split())