import argparse
from pathlib import Path

from app.evaluation.runner import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run INVARIANT safety evaluation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_evaluation()
    payload = report.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
