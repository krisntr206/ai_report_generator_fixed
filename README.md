# AI Report Generator — chart/table export fix

## Included
- `app/config.py`
- `app/services/llm.py`
- `app/services/generator.py`
- `app/services/chart_generator.py`
- `app/services/exporters.py`
- `app/main.py`
- `requirements.txt`

The replacement exporter creates real PDF tables, real PowerPoint tables, and chart images. Each chart is placed on its own page in PDF and its own slide in PPTX. It supports bar, line, timeline, pie, histogram, and scatter charts. User-specified basic colour themes are applied when the query includes a colour/theme instruction.

## Important behavior
- Charts are created only from data present in the request/report. The code must not fabricate numeric observations just to fill a chart.
- A histogram requires multiple raw numeric observations. A pie chart requires non-negative part-to-whole values. A scatter plot requires paired x/y values. A line/timeline chart needs ordered labels and numeric values.
- If the LLM cannot supply a valid chart specification, a fallback tries to extract numeric columns from Markdown tables. This fallback cannot infer raw observations from a summary total.
- The PDF/PPTX chart pages are appended after the report text/tables, not interleaved at exact positions in the Markdown. For the requested example, add explicit chart requirements to the query; charts then appear as separate pages/slides after the report content.
- Your previous `exporters.py` and `chart_generator.py` implementations were not included in the pasted source. These files are full replacement implementations.

## Install/run
From the project root:
```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Test `http://127.0.0.1:8000/docs`.

## Export API
`POST /generate` returns `markdown` and `charts`.
Send both to `POST /export/pdf`, `/export/pptx`, or `/export/docx`:
```json
{
  "markdown": "# Sales report\n\n| Category | Sales |\n|---|---:|\n| A | 120 |\n| B | 90 |",
  "charts": [],
  "query": "Create a blue themed sales report with bar and pie charts"
}
```
The frontend must send the returned `charts` array and original `query` along with the Markdown to the export endpoint. If it sends only Markdown, the exporters cannot recreate the generated charts.
