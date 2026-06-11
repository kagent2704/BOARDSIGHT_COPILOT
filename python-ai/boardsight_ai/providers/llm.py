from __future__ import annotations

from functools import lru_cache
from typing import Any

from boardsight_ai.config import AppConfig

from .runtime import optional_import


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


def summarize(text: str, config: AppConfig) -> tuple[str, str]:
    summarizer = _summarizer()
    if summarizer is not None:
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
            pass

    return "Summary unavailable because the transformer summarization model is not loaded.", "model-unavailable"


def generate_text(prompt: str, config: AppConfig, max_new_tokens: int = 144, min_new_tokens: int = 24) -> tuple[str, str]:
    summarizer = _summarizer()
    if summarizer is not None:
        try:
            tokenizer, model, torch, device, model_name = summarizer
            normalized_prompt = " ".join(str(prompt or "").split())
            inputs = tokenizer(
                normalized_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            if torch is not None and device != "cpu":
                inputs = {key: value.to(device) for key, value in inputs.items()}
            generated = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                min_new_tokens=min_new_tokens,
                do_sample=False,
                num_beams=4,
                no_repeat_ngram_size=3,
            )
            text = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
            if text:
                return text, f"transformers:{model_name}"
        except Exception:
            pass

    return "", "model-unavailable"
