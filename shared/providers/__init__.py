"""External model providers (Groq LLM, Hugging Face embeddings)."""

from shared.providers.secrets import load_local_dotenv, require_secret

__all__ = ["load_local_dotenv", "require_secret"]
