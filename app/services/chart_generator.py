"""Convert a report/request into validated, renderer-friendly chart specifications."""
import json
import re
from typing import Any
from app.config import settings
from app.services.llm import chat

ALLOWED_TYPES = {"bar", "line", "pie", "histogram", "scatter", "timeline"}
DEFAULT_COLORS = ["#2563EB", "#14B8A6", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4"]

def _json_from_text(raw: str) -> Any:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)

def _requested_types(query: str) -> list:
    q = query.casefold()
    found = []
    patterns = [
        ("histogram", r"\bhistogram(s)?\b"),
        ("line", r"\b(line chart|line graph|trend line)\b"),
        ("timeline", r"\b(timeline|time line|time-series|time series)\b"),
        ("pie", r"\b(pie chart|pie graph|donut chart)\b"),
        ("scatter", r"\b(scatter plot|scatter graph|scatter chart)\b"),
        ("bar", r"\b(bar chart|bar graph|column chart)\b"),
    ]
    for kind, pattern in patterns:
        if re.search(pattern, q) and kind not in found:
            found.append(kind)
    return found

def _normalise_chart(item: dict, index: int) -> dict:
    kind = str(item.get("type", "bar")).lower().strip()
    if kind not in ALLOWED_TYPES:
        raise ValueError(f"Unsupported chart type: {kind}")
    title = str(item.get("title") or f"Chart {index + 1}").strip()[:160]
    labels = item.get("labels", [])
    values = item.get("values", [])
    data = item.get("data", [])
    if kind == "scatter":
        xs = item.get("x_values", [])
        ys = item.get("y_values", [])
        if not xs or not ys or len(xs) != len(ys):
            raise ValueError("Scatter chart needs equal-length x_values and y_values.")
        clean = []
        for x, y in zip(xs, ys):
            try:
                clean.append([float(x), float(y)])
            except (TypeError, ValueError):
                continue
        if len(clean) < 2:
            raise ValueError("Scatter chart needs at least two numeric points.")
        item["x_values"], item["y_values"] = [p[0] for p in clean], [p[1] for p in clean]
    elif kind == "histogram":
        source = item.get("values", [])
        nums = []
        for x in source:
            try: nums.append(float(x))
            except (TypeError, ValueError): pass
        if len(nums) < 2:
            raise ValueError("Histogram needs at least two numeric observations.")
        item["values"] = nums
    else:
        if not isinstance(labels, list) or not isinstance(values, list) or len(labels) != len(values):
            raise ValueError("Chart labels and values must be equal-length lists.")
        clean_labels, clean_values = [], []
        for label, value in zip(labels, values):
            try:
                number = float(value)
                if number != number or abs(number) == float("inf"):
                    continue
                clean_labels.append(str(label)[:100])
                clean_values.append(number)
            except (TypeError, ValueError):
                continue
        if len(clean_values) < (2 if kind != "pie" else 1):
            raise ValueError(f"{kind} chart has insufficient numeric data.")
        if kind == "pie" and any(v < 0 for v in clean_values):
            raise ValueError("Pie chart values cannot be negative.")
        item["labels"], item["values"] = clean_labels, clean_values
    item["type"], item["title"] = kind, title
    item["x_label"] = str(item.get("x_label") or "")[:80]
    item["y_label"] = str(item.get("y_label") or "")[:80]
    item["colors"] = item.get("colors") if isinstance(item.get("colors"), list) else DEFAULT_COLORS
    item["notes"] = str(item.get("notes") or "")[:500]
    return item

def _table_fallback(query: str, markdown: str) -> list:
    """Parse simple Markdown tables into chartable series when LLM chart JSON fails."""
    lines = markdown.splitlines()
    charts = []
    i = 0
    while i < len(lines):
        if "|" not in lines[i] or i + 1 >= len(lines) or not re.search(r"\|?\s*:?-{3,}", lines[i + 1]):
            i += 1
            continue
        headers = [x.strip() for x in lines[i].strip().strip("|").split("|")]
        rows, j = [], i + 2
        while j < len(lines) and "|" in lines[j]:
            cells = [x.strip() for x in lines[j].strip().strip("|").split("|")]
            if len(cells) == len(headers):
                rows.append(cells)
            j += 1
        if len(rows) >= 2 and len(headers) >= 2:
            for col in range(1, len(headers)):
                labels, values = [], []
                for row in rows:
                    cleaned = re.sub(r"[$,%£€,]", "", row[col]).replace(" ", "")
                    try:
                        val = float(cleaned)
                        labels.append(row[0])
                        values.append(val)
                    except ValueError:
                        pass
                if len(values) >= 2:
                    qtypes = _requested_types(query)
                    kind = next((t for t in qtypes if t in {"bar", "line", "timeline", "pie"}), "bar")
                    charts.append({
                        "type": kind, "title": f"{headers[col]} by {headers[0]}",
                        "labels": labels, "values": values,
                        "x_label": headers[0], "y_label": headers[col],
                        "notes": "Derived from a numeric Markdown table; verify units.",
                    })
                    if len(charts) >= settings.max_chart_count:
                        return charts
        i = max(j, i + 1)
    return charts

def generate_chart_specs(query: str, report_markdown: str, provider: str, model: str) -> list:
    requested = _requested_types(query)
    prompt = f"""
Return ONLY valid JSON in this exact structure:
{{"charts":[{{"type":"bar|line|timeline|pie|histogram|scatter","title":"...","labels":["..."],"values":[1,2],"x_values":[1,2],"y_values":[3,4],"x_label":"...","y_label":"...","colors":["#2563EB","#14B8A6"],"notes":"..."}}]}}
Rules:
- Requested chart types: {requested or ["choose appropriate charts"]}.
- Use ONLY numerical data explicitly present in the report or request. Do not invent data.
- For bar/line/timeline/pie, use labels and values of equal length.
- For histogram, values must be the actual numeric observations, not category totals.
- For scatter, provide x_values and y_values of equal length, at least two points.
- Pie values must be non-negative and represent parts of a whole.
- If a requested chart cannot be supported by the available data, omit it; do not fabricate data.
- Include separate chart objects for separate requested charts. Keep chart titles descriptive.
USER REQUEST:
{query}

REPORT MARKDOWN:
{report_markdown[:18000]}
"""
    raw = chat(
        "You convert report data into strict machine-readable chart specifications. "
        "Never invent values. Return JSON only.",
        prompt, provider, model, temperature=0.0, max_tokens=2500
    )
    try:
        parsed = _json_from_text(raw)
        candidates = parsed.get("charts", []) if isinstance(parsed, dict) else []
        valid = []
        for i, item in enumerate(candidates[:settings.max_chart_count]):
            if isinstance(item, dict):
                try: valid.append(_normalise_chart(dict(item), i))
                except (ValueError, TypeError): continue
        # A requested type should not silently disappear if it can be built from a table.
        if requested and not all(any(c["type"] == t for c in valid) for t in requested):
            fallback = _table_fallback(query, report_markdown)
            present = {c["type"] for c in valid}
            for c in fallback:
                if c["type"] not in present and len(valid) < settings.max_chart_count:
                    try: valid.append(_normalise_chart(c, len(valid))); present.add(c["type"])
                    except ValueError: pass
        return valid
    except Exception:
        fallback = _table_fallback(query, report_markdown)
        return [_normalise_chart(c, i) for i, c in enumerate(fallback[:settings.max_chart_count])]
