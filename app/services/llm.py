"""OpenAI-compatible adapter for Ollama and optional hosted providers."""
from typing import Optional
from openai import OpenAI
from app.config import settings

PROVIDERS = {
    "ollama": {
        "base_url": settings.ollama_base_url,
        "key": "ollama-local",
        "model": settings.ollama_model,
        "timeout": 600.0,
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key": settings.groq_api_key,
        "model": settings.groq_model,
        "timeout": 120.0,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "key": settings.deepseek_api_key,
        "model": settings.deepseek_model,
        "timeout": 120.0,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key": settings.openrouter_api_key,
        "model": settings.openrouter_model,
        "timeout": 120.0,
    },
}

def get_provider(provider: Optional[str] = None, model_override: Optional[str] = None):
    name = (provider or settings.provider).strip().lower()
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Choose: {', '.join(PROVIDERS)}.")
    cfg = PROVIDERS[name]
    if name != "ollama" and not cfg["key"]:
        env = {"groq":"GROQ_API_KEY", "deepseek":"DEEPSEEK_API_KEY",
               "openrouter":"OPENROUTER_API_KEY"}[name]
        raise ValueError(f"Missing API key. Add {env} to your .env file.")
    model = (model_override or cfg["model"] or "").strip()
    if not model:
        raise ValueError(f"No model ID configured for provider '{name}'.")
    return OpenAI(api_key=cfg["key"], base_url=cfg["base_url"],
                  timeout=cfg["timeout"], max_retries=2), model, name

def chat(system_prompt: str, user_prompt: str, provider: Optional[str] = None,
         model_override: Optional[str] = None, temperature: Optional[float] = 0.2,
         max_tokens: Optional[int] = None) -> str:
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("system_prompt must not be empty.")
    if not isinstance(user_prompt, str) or not user_prompt.strip():
        raise ValueError("user_prompt must not be empty.")
    if temperature is not None and not 0.0 <= temperature <= 2.0:
        raise ValueError("temperature must be between 0.0 and 2.0.")
    if max_tokens is not None and (not isinstance(max_tokens, int) or max_tokens < 1):
        raise ValueError("max_tokens must be a positive integer.")
    client, model, name = get_provider(provider, model_override)
    args = {"model": model, "messages": [
        {"role":"system", "content":system_prompt},
        {"role":"user", "content":user_prompt},
    ]}
    if temperature is not None:
        args["temperature"] = temperature
    if max_tokens is not None:
        args["max_tokens"] = max_tokens
    try:
        response = client.chat.completions.create(**args)
    except Exception as exc:
        if name == "ollama":
            raise RuntimeError(
                "Could not call Ollama. Check that the Ollama service is running, "
                f"the model exists ('ollama list'), and the API URL is correct: "
                f"{settings.ollama_base_url}. Original error: {exc}"
            ) from exc
        raise RuntimeError(f"Request to provider '{name}' failed: {exc}") from exc
    if not response.choices:
        raise RuntimeError(f"The {name} provider returned no completion choices.")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"The {name} provider returned an empty response.")
    return content.strip()
