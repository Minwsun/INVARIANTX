import argparse
import subprocess
from pathlib import Path

from app.evaluation import run_comparative_benchmark, run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run INVARIANT safety evaluation")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--cases-per-category", type=int, default=10)
    args = parser.parse_args()
    report = (
        run_comparative_benchmark(
            args.cases_per_category,
            code_revision=_git_revision(),
        )
        if args.benchmark
        else run_evaluation()
    )
    payload = report.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    main()
