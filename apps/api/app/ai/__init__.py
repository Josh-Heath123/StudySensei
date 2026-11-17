"""AI access (decision 0002): one OpenAI-compatible adapter for Gemini, Groq and Ollama.

Use ``get_llm_client()`` and build prompts only from ``app.ai.sources``.
"""

from app.ai.client import LLMClient, get_llm_client, set_llm_client
from app.ai.errors import AIInvalidOutput, AIUnavailable
from app.ai.messages import Image, Message, system, user

__all__ = [
    "AIInvalidOutput",
    "AIUnavailable",
    "Image",
    "LLMClient",
    "Message",
    "get_llm_client",
    "set_llm_client",
    "system",
    "user",
]
