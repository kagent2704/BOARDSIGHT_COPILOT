from __future__ import annotations

import json
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

from boardsight_ai.config import AppConfig
from boardsight_ai.providers.runtime import optional_import


def _extract_text_from_gemini_payload(payload: dict[str, Any]) -> str | None:
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        text_parts = [str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("text")]
        combined = "".join(text_parts).strip()
        if combined:
            return combined
    return None


def _gemini_generate_text(prompt: str, config: AppConfig, *, response_mime_type: str = "text/plain") -> tuple[str, str] | None:
    api_key = (config.gemini_api_key or "").strip()
    if config.llm_provider != "gemini" or not api_key:
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.gemini_model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt[:12000]}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": response_mime_type,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None

    text = _extract_text_from_gemini_payload(payload)
    if not text:
        return None
    return text.strip(), f"gemini:{config.gemini_model}"


@lru_cache(maxsize=1)
def _summarizer() -> tuple[Any, Any, Any, str, str] | None:
    transformers = optional_import("transformers")
    torch = optional_import("torch")
    if transformers is None:
        return None
    try:
        model_name = "google/flan-t5-small"
        tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
        model = transformers.AutoModelForSeq2SeqLM.from_pretrained(model_name)
        device = "cpu"
        if torch is not None and getattr(torch.cuda, "is_available", lambda: False)():
            device = "cuda"
            model = model.to(device)
        return tokenizer, model, torch, device, model_name
    except Exception:
        return None


def _transformer_summary(text: str) -> tuple[str, str] | None:
    summarizer = _summarizer()
    if summarizer is None:
        return None
    try:
        tokenizer, model, torch, device, model_name = summarizer
        normalized_text = " ".join(str(text or "").split())
        prompt = (
            "You are summarizing slide evidence and nearby meeting transcript. "
            "Write exactly 2 concise sentences with no numbering or labels. "
            "State the main topic of the presentation, then mention one or two concrete takeaways mentioned in the slide evidence or transcript. "
            "Prefer specific subject words that appear in the evidence.\n\n"
            f"{normalized_text}"
        )
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        if torch is not None and device != "cpu":
            inputs = {key: value.to(device) for key, value in inputs.items()}
        generated = model.generate(
            **inputs,
            max_new_tokens=72,
            min_new_tokens=12,
            do_sample=False,
            num_beams=4,
            no_repeat_ngram_size=3,
        )
        summary = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        if summary:
            return summary, f"transformers:{model_name}"
    except Exception:
        return None
    return None


def summarize(text: str, config: AppConfig) -> tuple[str, str]:
    gemini_response = _gemini_generate_text(
        (
            "You are summarizing meeting evidence. "
            "Write exactly 2 concise sentences with no bullets or labels. "
            "State the main topic of the discussion, then mention one or two concrete takeaways.\n\n"
            f"{' '.join(str(text or '').split())[:5000]}"
        ),
        config,
    )
    if gemini_response is not None and gemini_response[0]:
        return gemini_response

    transformer_response = _transformer_summary(text)
    if transformer_response is not None:
        return transformer_response

    return "Summary unavailable because no summarization model is available.", "model-unavailable"


def generate_structured_json(prompt: str, config: AppConfig) -> tuple[dict[str, Any] | None, str]:
    response = _gemini_generate_text(prompt, config, response_mime_type="application/json")
    if response is None:
        return None, "model-unavailable"
    text, source = response
    try:
        return json.loads(text), source
    except json.JSONDecodeError:
        return None, f"{source}:invalid-json"


def answer_question(prompt: str, config: AppConfig) -> tuple[str, str]:
    gemini_response = _gemini_generate_text(
        (
            "Answer the user's question only from the supplied meeting context. "
            "Do not invent facts. Keep the reply concise and grounded.\n\n"
            f"{prompt[:12000]}"
        ),
        config,
    )
    if gemini_response is not None and gemini_response[0]:
        return gemini_response

    transformer_response = _transformer_summary(prompt)
    if transformer_response is not None:
        return transformer_response

    return "I could not reach a chat model, so live copilot reasoning is temporarily unavailable.", "model-unavailable"
