from __future__ import annotations

import json
import time
from typing import Any

from google import genai

from . import settings
from .tools import APPROVED_TOOLS, TOOL_DECLARATIONS


MAX_TOOL_CALLS_PER_TURN = 8
MAX_TOOL_ROUNDS = 4

SYSTEM_INSTRUCTION = """
You are the constrained assistant for the San Diego Youth Opportunity
Index dashboard.

Rules:
1. Use only the approved tools for YOI numbers, rankings, comparisons,
   indicator definitions, methodology, and map links.
2. Never invent a missing value, source, geography, or interpretation.
3. State that scores are relative to San Diego County when relevant.
4. Do not claim that correlation proves causation.
5. Use respectful, non-stigmatizing language.
6. Include only limitations that are relevant to the specific answer:
   - Mention survey uncertainty for estimated values, rankings, or
     comparisons.
   - Mention census-tract boundaries for tract-level results.
   - Mention aggregation for county-region results.
   - Mention military, institutional, or special-use areas only when the
     question or geography specifically concerns one, or when a tool
     explicitly marks that limitation as relevant.
   - Do not attach a generic military-area caveat to every answer.
7. For regional results, say: "Regional scores aggregate multiple census
   tracts. County-region assignments use the project's tract-to-PUMA
   regional crosswalk." Do not describe census tracts as PUMAs.
8. Round youth population estimates to whole people and describe them as
   approximate.
9. Cite only the friendly `source_label` supplied by a tool. Never display
   local filesystem paths, `source_file`, `expected_path`, or a user's
   computer username.
10. Do not make funding or policy decisions for the user.
11. Keep answers concise and explain technical results in plain language.
12. When a tool returns an error or no match, explain the limitation rather
    than guessing.
13. Preserve the exact metric and geography requested by the user. Never
    substitute a related metric simply because an available tool supports it.
14. For multi-step analytical questions, continue using approved tools until
    the information needed to answer the question has been retrieved.
15. Prefer calculations returned by approved tools over doing arithmetic,
    sorting, averaging, set intersections, correlations, or weighting yourself.
16. If the user asks for a ranking using an undefined concept such as "most
    concerning", "highest priority", or "best", do not invent an objective
    formula. Explain the criterion being used or ask for clarification.
17. When only part of a compound question can be answered, clearly separate
    what can be answered from what cannot. Never answer a different question
    in place of the requested one.
18. Never substitute an average for a median, percentile, rate, count, or
    other statistic explicitly requested by the user. Use an approved tool
    that explicitly calculates the requested statistic.
19. Dashboard UI context is read-only. Use it only to understand the current
    view; never claim that you changed the map, layers, filters, or zoom.
20. Format responses for a narrow dashboard sidebar. Prefer short paragraphs,
    descriptive headings, and bullet lists. Avoid Markdown tables unless the
    user explicitly asks for a table. Use bold text only for short labels or
    key values, not entire paragraphs.
""".strip()


def _empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "thought_tokens": 0,
        "tool_tokens": 0,
        "total_tokens": 0,
    }


def _usage_values(interaction: Any) -> dict[str, int]:
    usage = getattr(interaction, "usage", None)
    if usage is None:
        return _empty_usage()

    def value(name: str) -> int:
        return int(getattr(usage, name, 0) or 0)

    return {
        "input_tokens": value("total_input_tokens"),
        "output_tokens": value("total_output_tokens"),
        "thought_tokens": value("total_thought_tokens"),
        "tool_tokens": value("total_tool_use_tokens"),
        "total_tokens": value("total_tokens"),
    }


def _combine_usage(*items: dict[str, int]) -> dict[str, int]:
    keys = {
        "input_tokens",
        "output_tokens",
        "thought_tokens",
        "tool_tokens",
        "total_tokens",
    }
    return {
        key: sum(item.get(key, 0) for item in items)
        for key in keys
    }


def estimate_paid_cost_usd(usage: dict[str, int]) -> float:
    input_cost = (
        usage["input_tokens"]
        / 1_000_000
        * settings.FLASH_LITE_INPUT_USD_PER_MILLION
    )
    billable_output = (
        usage["output_tokens"]
        + usage["thought_tokens"]
    )
    output_cost = (
        billable_output
        / 1_000_000
        * settings.FLASH_LITE_OUTPUT_USD_PER_MILLION
    )
    return round(input_cost + output_cost, 8)


def _execute_tool(
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    function = APPROVED_TOOLS.get(name)
    if function is None:
        return {
            "ok": False,
            "error": "UnapprovedTool",
            "message": f"Tool '{name}' is not approved.",
        }

    try:
        result = function(**arguments)
        return {
            "ok": True,
            "data": result,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }


def _append_model_steps(
    history: list[dict[str, Any]],
    interaction: Any,
) -> None:
    # Stateless Interactions API calls must resend all model-generated steps
    # exactly as returned, including thought and function-call steps.
    for step in interaction.steps:
        history.append(
            step.model_dump(
                exclude_none=True,
                mode="json",
            )
        )


def _append_function_result(
    history: list[dict[str, Any]],
    call: Any,
    result: dict[str, Any],
) -> None:
    history.append(
        {
            "type": "function_result",
            "name": call.name,
            "call_id": call.id,
            "result": [
                {
                    "type": "text",
                    "text": json.dumps(
                        result,
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            ],
        }
    )


def _friendly_key(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _deterministic_fallback(
    tool_trace: list[dict[str, Any]],
) -> str:
    """Return a useful nonblank answer if the model fails to emit text."""
    successful = [
        item
        for item in tool_trace
        if item.get("result", {}).get("ok") is True
    ]
    if not successful:
        if tool_trace:
            message = tool_trace[-1].get("result", {}).get(
                "message",
                "The approved tool could not complete the request.",
            )
            return f"I could not complete that request: {message}"
        return "I could not produce a response for that question."

    latest = successful[-1]
    name = latest["name"]
    data = latest["result"].get("data", {})
    source_label = data.get("source_label")

    if name == "get_methodology":
        excerpts = data.get("excerpts") or []
        if excerpts:
            lines = "\n".join(f"- {item}" for item in excerpts[:5])
            source = f"\n\nSource: {source_label}" if source_label else ""
            return f"Relevant YOI methodology:\n\n{lines}{source}"

        message = data.get(
            "message",
            "No matching methodology passage was found.",
        )
        return message

    if name == "get_indicator_definition":
        matches = data.get("matches") or []
        if not matches:
            return data.get(
                "message",
                "No matching indicator definition was found.",
            )

        first = matches[0]
        lines = []
        for key, value in first.items():
            if value in (None, "", "nan"):
                continue
            lines.append(f"- **{_friendly_key(str(key))}:** {value}")
            if len(lines) >= 10:
                break

        source = f"\n\nSource: {source_label}" if source_label else ""
        return "Indicator information:\n\n" + "\n".join(lines) + source

    # This branch should be rare. It still returns a readable answer rather
    # than silently storing an empty CSV cell.
    source = f" Source: {source_label}." if source_label else ""
    return (
        "The approved tool returned data, but the model did not format a "
        f"final answer.{source} Please retry the question."
    )


def _force_text_response(
    client: genai.Client,
    history: list[dict[str, Any]],
) -> tuple[str, dict[str, int]]:
    forced_history = [
        *history,
        {
            "type": "user_input",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Using only the approved tool results already in "
                        "the conversation, answer the original question "
                        "now. Do not request another tool. Return visible "
                        "plain-language text and use only friendly source "
                        "labels."
                    ),
                }
            ],
        },
    ]

    interaction = client.interactions.create(
        model=settings.GEMINI_MODEL,
        input=forced_history,
        system_instruction=SYSTEM_INSTRUCTION,
        store=False,
    )
    return (
        (interaction.output_text or "").strip(),
        _usage_values(interaction),
    )


def _build_response(
    answer: str,
    tool_trace: list[dict[str, Any]],
    usage: dict[str, int],
    started: float,
) -> dict[str, Any]:
    elapsed_ms = round(
        (time.perf_counter() - started) * 1000,
        2,
    )
    estimated_paid_cost = estimate_paid_cost_usd(usage)

    return {
        "answer": answer,
        "model": settings.GEMINI_MODEL,
        "tool_trace": tool_trace,
        "usage": usage,
        "estimated_paid_cost_usd": estimated_paid_cost,
        "estimated_current_cost_usd": (
            0.0
            if settings.BILLING_MODE == "free"
            else estimated_paid_cost
        ),
        "response_time_ms": elapsed_ms,
    }

def ask_assistant(
    question: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to assistant_backend/.env."
        )

    clean_question = question.strip()
    if not clean_question:
        raise ValueError("Question cannot be empty.")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    started = time.perf_counter()

    user_text = clean_question

    if context:
        user_text = (
            "READ-ONLY DASHBOARD_UI_CONTEXT:\n"
            + json.dumps(
                context,
                ensure_ascii=False,
                default=str,
            )
            + "\n\nUSER QUESTION:\n"
            + clean_question
        )

    history: list[dict[str, Any]] = [
        {
            "type": "user_input",
            "content": [
                {
                    "type": "text",
                    "text": user_text,
                }
            ],
        }
    ]

    tool_trace: list[dict[str, Any]] = []
    usage = _empty_usage()

    call_cache: dict[str, dict[str, Any]] = {}
    total_tool_calls = 0

    for _ in range(MAX_TOOL_ROUNDS):
        interaction = client.interactions.create(
            model=settings.GEMINI_MODEL,
            input=history,
            tools=TOOL_DECLARATIONS,
            system_instruction=SYSTEM_INSTRUCTION,
            store=False,
        )

        usage = _combine_usage(
            usage,
            _usage_values(interaction),
        )

        _append_model_steps(history, interaction)

        function_calls = [
            step
            for step in interaction.steps
            if getattr(step, "type", None) == "function_call"
        ]

        # No tool requested -> model has finished answering.
        if not function_calls:
            answer = (interaction.output_text or "").strip()

            if not answer:
                answer = _deterministic_fallback(tool_trace)

            return _build_response(
                answer,
                tool_trace,
                usage,
                started,
            )

        for call in function_calls:
            arguments = dict(call.arguments or {})

            signature = json.dumps(
                {
                    "name": call.name,
                    "arguments": arguments,
                },
                sort_keys=True,
                default=str,
            )

            # Reuse duplicate calls instead of executing them again.
            if signature in call_cache:
                result = call_cache[signature]

            elif total_tool_calls >= MAX_TOOL_CALLS_PER_TURN:
                result = {
                    "ok": False,
                    "error": "ToolLimitExceeded",
                    "message": (
                        "The assistant reached the maximum number "
                        "of approved data lookups for one question."
                    ),
                }

            else:
                result = _execute_tool(
                    call.name,
                    arguments,
                )

                call_cache[signature] = result
                total_tool_calls += 1

            tool_trace.append(
                {
                    "name": call.name,
                    "arguments": arguments,
                    "result": result,
                }
            )

            # IMPORTANT:
            # Every function_call gets a function_result.
            _append_function_result(
                history,
                call,
                result,
            )

    # Safety fallback after too many reasoning/tool rounds.
    answer, final_usage = _force_text_response(
        client,
        history,
    )

    usage = _combine_usage(
        usage,
        final_usage,
    )

    if not answer:
        answer = _deterministic_fallback(tool_trace)

    return _build_response(
        answer,
        tool_trace,
        usage,
        started,
    )