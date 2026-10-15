"""Report drafting with bounded concurrency and stable section ordering."""
import asyncio
from app.config import settings
from app.services.llm import chat

PLANNER_SYSTEM = (
    "You are a careful report planner. Return only section titles, one per line. "
    "Do not invent data, sources, or facts."
)
SECTION_SYSTEM = (
    "You write clear, accurate business and analytical reports. Never fabricate "
    "measurements, citations, or historical data. Explicitly label assumptions and "
    "illustrative data. Use Markdown tables only when useful; tables do not replace "
    "requested charts."
)
FINAL_SYSTEM = (
    "You are a meticulous report editor. Preserve supplied facts, units, dates, "
    "table values, caveats, and citations. Do not invent data or sources. Return Markdown."
)

def _clean_title(line: str) -> str:
    s = line.strip()
    for prefix in ("- ", "* ", "• ", "# "):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    if len(s) > 3 and s[0].isdigit() and s[1:3] in (". ", ") "):
        s = s[3:].strip()
    return s.strip("`*_ \t")

def plan_sections(query: str, section_count: int, provider: str, model: str) -> list:
    prompt = (
        f"Create exactly {section_count} distinct sections for this report. "
        "Include context, analysis, limitations, and recommendations where relevant. "
        "Return one title per line and no commentary.\n\nREQUEST:\n" + query
    )
    raw = chat(PLANNER_SYSTEM, prompt, provider, model, temperature=0.1, max_tokens=500)
    titles, seen = [], set()
    for line in raw.splitlines():
        title = _clean_title(line)
        if len(title) > 2 and title.casefold() not in seen:
            seen.add(title.casefold())
            titles.append(title)
    titles = titles[:section_count]
    fallback = [
        "Introduction and context", "Main analysis and findings",
        "Data limitations and interpretation", "Recommendations and conclusion",
        "Implementation plan", "Risks and next steps", "Appendix and assumptions",
        "Summary of evidence",
    ]
    return titles if len(titles) >= 3 else fallback[:section_count]

async def _write_section(semaphore, query, title, index, total, provider, model):
    async with semaphore:
        prompt = (
            f"Write section {index + 1} of {total} in a larger report.\n\n"
            f"Request:\n{query}\n\nSection title:\n{title}\n\n"
            f"Target length: about {settings.max_section_words} words.\n"
            "Start with a level-2 Markdown heading. Do not create a separate overall "
            "introduction/conclusion unless appropriate to this section. For numerical "
            "analysis, show the available data and units. Never make up missing data. "
            "If the request asks for charts, describe which supplied data fields can "
            "support them, but do not substitute a table for a chart."
        )
        result = await asyncio.to_thread(
            chat, SECTION_SYSTEM, prompt, provider, model, 0.2, 1800
        )
        if not result.strip():
            raise RuntimeError(f"Empty generated section: {title}")
        return index, result.strip()

async def generate_report_async(query: str, provider: str, model: str, section_count: int) -> str:
    titles = await asyncio.to_thread(plan_sections, query, section_count, provider, model)
    if not titles:
        raise RuntimeError("The report planner returned no sections.")
    sem = asyncio.Semaphore(settings.max_parallel_sections)
    tasks = [
        _write_section(sem, query, title, i, len(titles), provider, model)
        for i, title in enumerate(titles)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful, errors = [], []
    for i, item in enumerate(results):
        if isinstance(item, Exception):
            errors.append(f"- {titles[i]}: {item}")
        else:
            successful.append(item)
    if not successful:
        raise RuntimeError("All report sections failed. " + " | ".join(errors))
    successful.sort(key=lambda x: x[0])
    draft = "\n\n".join(text for _, text in successful)
    if errors:
        draft += "\n\n## Generation notes\n\nSome sections failed:\n" + "\n".join(errors)
    final_prompt = (
        f"User request:\n{query}\n\nDraft sections (preserve facts and order):\n{draft}\n\n"
        "Create a self-contained Markdown report. Add a concise title and executive "
        "summary. Preserve all tables, units, dates, caveats and source references. "
        "Do not invent missing data. Return Markdown only."
    )
    final = await asyncio.to_thread(
        chat, FINAL_SYSTEM, final_prompt, provider, model, 0.1, 5000
    )
    if not final.strip():
        raise RuntimeError("Final report editor returned empty Markdown.")
    return final.strip()

def generate_report(query: str, provider: str, model: str, section_count: int = 5) -> str:
    if not query or not query.strip():
        raise ValueError("Please enter a report question or topic.")
    section_count = max(3, min(section_count, settings.max_report_sections))
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(generate_report_async(query.strip(), provider, model, section_count))
    # Safe for callers already inside an event loop.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            asyncio.run, generate_report_async(query.strip(), provider, model, section_count)
        ).result()
