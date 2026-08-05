from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.assistant import ask_assistant  # noqa: E402


QUESTIONS_PATH = Path(__file__).with_name("questions.json")
RESULTS_PATH = Path(__file__).with_name("results.csv")


def _contains_private_path(answer: str) -> bool:
    normalized = answer.replace("\\", "/")
    return any(
        marker in normalized
        for marker in [
            "/Users/",
            "/home/",
            "Documents/Github/",
            "assistant_backend/",
        ]
    )


def main() -> None:
    questions = json.loads(
        QUESTIONS_PATH.read_text(encoding="utf-8")
    )

    results = []

    for item in questions:
        print(f"Running: {item['id']}")
        try:
            response = ask_assistant(item["question"])
            selected_tools = [
                call["name"]
                for call in response.get("tool_trace", [])
            ]
            expected_tool = item["expected_tool"]
            answer = response.get("answer", "") or ""

            results.append(
                {
                    "id": item["id"],
                    "persona": item["persona"],
                    "question": item["question"],
                    "expected_tool": expected_tool,
                    "selected_tools": "|".join(selected_tools),
                    "tool_selection_pass": (
                        expected_tool in selected_tools
                    ),
                    "answer_present": bool(answer.strip()),
                    "private_path_exposed": _contains_private_path(answer),
                    "response_time_ms": response.get(
                        "response_time_ms"
                    ),
                    "input_tokens": response.get(
                        "usage", {}
                    ).get("input_tokens"),
                    "output_tokens": response.get(
                        "usage", {}
                    ).get("output_tokens"),
                    "thought_tokens": response.get(
                        "usage", {}
                    ).get("thought_tokens"),
                    "estimated_paid_cost_usd": response.get(
                        "estimated_paid_cost_usd"
                    ),
                    "answer": answer,
                    "manual_accuracy_pass": "",
                    "manual_source_label_pass": "",
                    "manual_caveat_pass": "",
                    "review_notes": "",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": item["id"],
                    "persona": item["persona"],
                    "question": item["question"],
                    "expected_tool": item["expected_tool"],
                    "selected_tools": "",
                    "tool_selection_pass": False,
                    "answer_present": False,
                    "private_path_exposed": False,
                    "response_time_ms": "",
                    "input_tokens": "",
                    "output_tokens": "",
                    "thought_tokens": "",
                    "estimated_paid_cost_usd": "",
                    "answer": "",
                    "manual_accuracy_pass": "",
                    "manual_source_label_pass": "",
                    "manual_caveat_pass": "",
                    "review_notes": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }
            )

    with RESULTS_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(results[0].keys()),
        )
        writer.writeheader()
        writer.writerows(results)

    tool_passes = sum(
        bool(row["tool_selection_pass"])
        for row in results
    )
    answers_present = sum(
        bool(row["answer_present"])
        for row in results
    )
    exposed_paths = sum(
        bool(row["private_path_exposed"])
        for row in results
    )

    print(f"Saved evaluation results to: {RESULTS_PATH}")
    print(f"Tool selection: {tool_passes}/{len(results)}")
    print(f"Nonblank answers: {answers_present}/{len(results)}")
    print(f"Private paths exposed: {exposed_paths}")


if __name__ == "__main__":
    main()
