import os
import re
import sys
import requests
from difflib import SequenceMatcher

# --------------------------------------------
# CONFIG
# --------------------------------------------
GITHUB_TOKEN = "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"  # or os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# --------------------------------------------
# 1. READ CODE FROM FILE
# --------------------------------------------
def read_code_from_file():
    if len(sys.argv) < 2:
        print("Usage: python script.py <filepath>")
        sys.exit(1)
    filepath = sys.argv[1]
    if not os.path.isfile(filepath):
        print("Error: File does not exist.")
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# --------------------------------------------
# 2. TOKENIZE AND SIMILARITY
# --------------------------------------------
def tokenize(code):
    return re.findall(r"[A-Za-z_]\w+|\S", code)

def similarity(code1, code2):
    # Better similarity than token overlap
    return SequenceMatcher(None, code1, code2).ratio()

# --------------------------------------------
# 3. SEARCH GITHUB CODE
# --------------------------------------------
def github_code_search(code_snippet, language="python", top_tokens=10, per_page=50):
    tokens = [w for w in tokenize(code_snippet) if len(w) > 3]
    if not tokens:
        tokens = tokenize(code_snippet)
    query_tokens = tokens[:top_tokens]
    query = "+".join(query_tokens)
    query += f"+in:file+language:{language}"
    url = f"https://api.github.com/search/code?q={query}&per_page={per_page}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print("GitHub API Error:", res.text)
        return []
    return res.json().get("items", [])

# --------------------------------------------
# 4. FETCH RAW CODE FROM MATCH
# --------------------------------------------
def fetch_raw_file(item):
    raw_url = item["html_url"].replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    res = requests.get(raw_url, headers=HEADERS)
    return res.text if res.status_code == 200 else ""

# --------------------------------------------
# 5. GET LICENSE OF REPO
# --------------------------------------------
def get_repo_license(repo_fullname):
    url = f"https://api.github.com/repos/{repo_fullname}/license"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return "Unknown"
    data = res.json()
    return data.get("license", {}).get("name", "Unknown")

# --------------------------------------------
# MAIN FUNCTION
# --------------------------------------------
def main():
    print("🔍 Reading file...")
    code = read_code_from_file()

    print("🔍 Searching GitHub for similar code...")
    items = github_code_search(code)

    if not items:
        print("✅ No similar code found on GitHub.")
        return

    best_match = None
    best_similarity = 0.0

    for item in items:
        raw_code = fetch_raw_file(item)
        sim = similarity(code, raw_code)
        if sim > best_similarity:
            best_similarity = sim
            best_match = item

    if not best_match:
        print("❌ No meaningful match found.")
        return

    repo_name = best_match["repository"]["full_name"]
    license_name = get_repo_license(repo_name)

    print("\n===========================")
    print("🔎 DUPLICATION CHECK RESULT")
    print("===========================")
    print(f"📄 File match: {best_match['html_url']}")
    print(f"📁 Repository: {repo_name}")
    print(f"📜 License: {license_name}")
    print(f"📊 Similarity: {best_similarity*100:.2f}%")

    if best_similarity > 0.5:  # threshold: 50%
        print("\n⚠️ POSSIBLE DUPLICATION DETECTED!")
    else:
        print("\n✅ No significant duplication detected.")

if __name__ == "__main__":
    main()
