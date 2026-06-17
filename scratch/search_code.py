import glob

def main():
    for filepath in glob.glob("**/*.py", recursive=True):
        if ".venv" in filepath or "scratch" in filepath:
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f, 1):
                    if "generate_equipment_by_ai" in line:
                        print(f"{filepath}:{idx} - {line.strip()}")
        except Exception as e:
            pass

if __name__ == "__main__":
    main()
