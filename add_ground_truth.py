import json
import os
from pathlib import Path

DATA_DIR = Path("sca_llm_eval_data")   # folder where records are stored

def find_record_file(record_id: str):
    """
    record_id can be:
      - the filename, e.g., record_1713892345.json
      - OR the code_hash value
    """
    for file in DATA_DIR.glob("record_*.json"):
        # match filename
        if file.name == record_id or file.name.replace(".json", "") == record_id:
            return file

        # match code_hash
        with open(file, "r", encoding="utf8") as fp:
            data = json.load(fp)
            if data.get("code_hash") == record_id:
                return file

    return None


def main():
    print("=== Ground Truth Annotation Script ===\n")

    record_id = input("Enter record ID (filename or code_hash): ").strip()

    file_path = find_record_file(record_id)
    if not file_path:
        print("\n❌ ERROR: No matching record found.")
        return

    print(f"\n✔ Found file: {file_path}\n")

    with open(file_path, "r", encoding="utf8") as fp:
        record = json.load(fp)

    print("Existing data:")
    print("  Verdict (Judge):", record.get("verdict"))
    print("  Path:", record.get("file_path"))
    print("  Language:", record.get("language"))
    print("\nEnter ground truth values:")

    gt_verdict = input("Ground truth verdict (safe/low_risk/medium_risk/high_risk/violation): ").strip()
    gt_basis = input("Infringement basis (independent/inspired/derivative/copied): ").strip()
    gt_license = input("License risk (none/attribution_required/weak_copyleft_obligations/strong_copyleft_violation): ").strip()
    gt_conf = input("Confidence (high/medium/low): ").strip()
    gt_notes = input("Notes (optional): ").strip()

    # Attach ground truth into the JSON
    record["ground_truth"] = {
        "verdict": gt_verdict or None,
        "infringement_basis": gt_basis or None,
        "license_risk": gt_license or None,
        "confidence": gt_conf or "high",
        "notes": gt_notes or ""
    }

    # Save back
    with open(file_path, "w", encoding="utf8") as fp:
        json.dump(record, fp, indent=2)

    print("\n✔ Ground truth added successfully!")
    print(f"Updated file: {file_path}")


if __name__ == "__main__":
    main()
