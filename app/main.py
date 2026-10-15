from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app.config import settings
from app.services.generator import generate_report
from app.services.exporters import export_docx, export_pdf, export_pptx, markdown_to_html
from app.services.chart_generator import generate_chart_specs

app = FastAPI(title="AI Report Generator API", version="2.0.0")

class GenerateRequest(BaseModel):
    query: str = Field(min_length=5, max_length=20000)
    provider: str = settings.provider
    model: Optional[str] = None
    sections: int = Field(default=5, ge=3, le=8)

class ExportRequest(BaseModel):
    markdown: str = Field(min_length=1)
    charts: list[dict] = Field(default_factory=list)
    query: str = ""

@app.get("/health")
def health():
    return {
        "status": "ok",
        "default_provider": settings.provider,
        "default_model": settings.ollama_model,
        "max_chart_count": settings.max_chart_count,
    }

@app.post("/generate")
def generate(req: GenerateRequest):
    try:
        markdown_text = generate_report(req.query, req.provider, req.model, req.sections)
        chart_warning = None
        try:
            charts = generate_chart_specs(req.query, markdown_text, req.provider, req.model)
        except Exception as exc:
            charts = []
            chart_warning = f"Report generated, but chart specification failed: {exc}"
        result = {
            "markdown": markdown_text,
            "html": markdown_to_html(markdown_text),
            "charts": charts,
            "provider": req.provider,
            "model": req.model or (
                settings.ollama_model if req.provider == "ollama" else None
            ),
        }
        if chart_warning:
            result["chart_warning"] = chart_warning
        if not charts and any(word in req.query.lower() for word in
                              ("chart", "graph", "histogram", "pie", "scatter", "timeline")):
            result["chart_warning"] = (
                result.get("chart_warning", "") +
                " No valid chart data was available. Charts are not fabricated; "
                "provide numeric observations or a table with numeric columns."
            ).strip()
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.post("/export/{fmt}")
def export(fmt: str, payload: ExportRequest):
    exporters = {
        "pptx": (export_pptx,
                 "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                 "report.pptx"),
        "docx": (export_docx,
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                 "report.docx"),
        "pdf": (export_pdf, "application/pdf", "report.pdf"),
    }
    if fmt not in exporters:
        raise HTTPException(status_code=400, detail="Format must be pptx, docx, or pdf")
    func, media_type, filename = exporters[fmt]
    try:
        content = func(payload.markdown, payload.charts, payload.query)
        return Response(content=content, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
