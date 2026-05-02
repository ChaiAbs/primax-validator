import json
import re


def parse_json_response(raw: str) -> dict:
    """
    Robustly parses a JSON response from Claude.
    Handles markdown code fences, leading text, and truncated responses.
    """
    text = raw.strip()

    # Strip markdown code fences
    if "```" in text:
        blocks = text.split("```")
        for block in blocks:
            cleaned = block.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                text = cleaned
                break

    # Find the first { and last } to extract just the JSON object
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")

    # Walk backwards from end to find closing brace
    end = text.rfind("}")
    if end == -1 or end < start:
        raise ValueError("No closing brace found — response likely truncated")

    candidate = text[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        # Last resort: truncation repair — remove last incomplete entry and close arrays/objects
        repaired = _repair_truncated_json(candidate)
        if repaired:
            return repaired
        raise ValueError(f"Could not parse JSON: {e}") from e


def _repair_truncated_json(text: str) -> dict | None:
    """
    Attempts to close an unterminated JSON object by counting open braces/brackets.
    """
    try:
        # Count unclosed structures and close them
        stack = []
        in_string = False
        escape_next = False

        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()

        if not stack:
            return None

        # Trim to last complete value before truncation
        closing = ""
        for ch in reversed(stack):
            closing += "}" if ch == "{" else "]"

        repaired = text.rstrip().rstrip(",") + closing
        return json.loads(repaired)
    except Exception:
        return None
