from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

def _positive_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default

@dataclass(frozen=True)
class Settings:
    provider: str = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    ollama_base_url: str = os.getenv(
        "OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"
    ).rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "")
    max_parallel_sections: int = _positive_int("MAX_PARALLEL_SECTIONS", 1)
    max_section_words: int = _positive_int("MAX_SECTION_WORDS", 600, 300)
    max_report_sections: int = _positive_int("MAX_REPORT_SECTIONS", 8, 3)
    max_chart_count: int = _positive_int("MAX_CHART_COUNT", 8, 1)
    chart_dpi: int = _positive_int("CHART_DPI", 160, 80)

settings = Settings()
