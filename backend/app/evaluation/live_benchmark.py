from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.evaluation.live_corpus import LIVE_SCENARIOS


def run_live_pilot(
    *,
    api_base: str,
    demo_key: str,
    output: Path,
    scenarios: int = 5,
) -> dict[str, Any]:
    results = []
    for scenario in LIVE_SCENARIOS[:scenarios]:
        started = time.perf_counter()
        baseline_created = _request_json(
            f"{api_base.rstrip('/')}/runs/live/ungated",
            method="POST",
            headers={"X-INVARIANT-DEMO-KEY": demo_key},
            payload={"goal": scenario.goal},
        )
        baseline = asyncio.run(_wait_for_run(api_base, baseline_created["run_id"]))
        invariant_created = _request_json(
            f"{api_base.rstrip('/')}/runs/live/invariant",
            method="POST",
            headers={"X-INVARIANT-DEMO-KEY": demo_key},
            payload={"goal": scenario.goal},
        )
        invariant = asyncio.run(_wait_for_run(api_base, invariant_created["run_id"]))
        results.append(
            {
                "scenario": scenario.model_dump(mode="json"),
                "same_goal": True,
                "same_models": True,
                "same_dataset": True,
                "baseline": baseline,
                "invariant": invariant,
                "pair_latency_ms": round((time.perf_counter() - started) * 1000),
            }
        )
    report = {
        "schema_version": "1.0",
        "methodology": "paired_live_model_execution",
        "sample_size": len(results),
        "results": results,
        "summary": _summarize(results),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def fleet(name: str) -> dict[str, Any]:
        runs = [pair[name] for pair in results]
        return {
            "completed": sum(run["status"] == "COMPLETED" for run in runs),
            "blocked": sum(run["status"] == "BLOCKED" for run in runs),
            "failed": sum(run["status"] == "FAILED" for run in runs),
            "final_integrity_pass": sum(
                (run.get("result") or {}).get("validation", {}).get("verdict") == "PASS"
                for run in runs
            ),
            "unsafe_receipts": sum(
                (run.get("result") or {}).get("validation", {}).get("verdict") == "BLOCK"
                for run in runs
            ),
            "llm_calls": sum(run.get("llm_call_count", 0) for run in runs),
        }

    return {"baseline": fleet("baseline"), "invariant": fleet("invariant")}


async def _wait_for_run(api_base: str, run_id: str) -> dict[str, Any]:
    for _ in range(120):
        run = await asyncio.to_thread(
            _request_json,
            f"{api_base.rstrip('/')}/runs/{run_id}",
        )
        if run["status"] in {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}:
            return run
        await asyncio.sleep(2)
    raise TimeoutError(f"run {run_id} did not finish")


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(
        url,
        method=method,
        headers=request_headers,
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"live benchmark request failed: {error.read().decode()}") from error


def main() -> None:
    api_base = os.environ["INVARIANT_API_BASE"]
    demo_key = os.environ["INVARIANT_DEMO_KEY"]
    output = Path(os.getenv("INVARIANT_LIVE_OUTPUT", "../benchmarks/live-v1.json"))
    run_live_pilot(api_base=api_base, demo_key=demo_key, output=output)


if __name__ == "__main__":
    main()
