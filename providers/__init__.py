from typing import Optional, List, Dict, Any, Tuple
from config import ModelConfig, ProviderConfig, ConfigManager, default_timeout
from providers.openai_chat_provider import OpenAIProvider
from providers.openai_responses_provider import OpenAIResponsesProvider
from providers.anthropic_provider import AnthropicProvider
from providers.retry import (
    compute_backoff_delay,
    is_transient_error,
    get_retry_params,
    DEFAULT_RETRIES,
    DEFAULT_INITIAL_DELAY,
    DEFAULT_MAX_DELAY,
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_JITTER
)


def is_anthropic_provider(model_config: ModelConfig, provider_config: ProviderConfig) -> bool:
    """Detects whether a model/provider configuration targets the native Anthropic API."""
    p_key = (model_config.provider or "").lower()
    p_name = (provider_config.name or "").lower()
    base_url = (provider_config.base_url or "").lower()
    
    return p_key == "anthropic" or "anthropic" in p_name or "api.anthropic.com" in base_url


def detect_api_type(provider_key: str, provider_config: ProviderConfig) -> str:
    """Heuristic used when no api_type is configured: Anthropic's own API -> 'anthropic', else 'openai-chat'."""
    p_key = (provider_key or "").lower()
    p_name = (provider_config.name or "").lower()
    base_url = (provider_config.base_url or "").lower()
    if p_key == "anthropic" or "anthropic" in p_name or "api.anthropic.com" in base_url:
        return "anthropic"
    return "openai-chat"


def resolve_api_type(model_config: ModelConfig, provider_config: ProviderConfig) -> str:
    """
    Resolves the effective endpoint type for a model.

    Order: the model's api_type, then its provider's api_type, then auto-detection.
    """
    model_type = getattr(model_config, "api_type", "auto") or "auto"
    if model_type != "auto":
        return model_type
    provider_type = getattr(provider_config, "api_type", "auto") or "auto"
    if provider_type != "auto":
        return provider_type
    return detect_api_type(model_config.provider, provider_config)


def get_provider(
    model_config: ModelConfig, 
    provider_config: ProviderConfig, 
    config_mgr: Optional[ConfigManager] = None
):
    """Factory returning the provider implementation for the model's resolved endpoint type."""
    api_type = resolve_api_type(model_config, provider_config)
    if api_type == "anthropic":
        return AnthropicProvider(model_config, provider_config, config_mgr)
    if api_type == "openai-responses":
        return OpenAIResponsesProvider(model_config, provider_config, config_mgr)
    return OpenAIProvider(model_config, provider_config, config_mgr)


async def fetch_models_details(
    provider_config: ProviderConfig,
    timeout: float = default_timeout("api"),
    config_mgr: Optional[ConfigManager] = None
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """Factory helper executing model discovery; uses the provider's api_type (else detection)."""
    api_type = getattr(provider_config, "api_type", "auto") or "auto"
    if api_type == "auto":
        api_type = detect_api_type("", provider_config)

    if api_type == "anthropic":
        return await AnthropicProvider.fetch_available_models_details(provider_config, timeout=timeout, config_mgr=config_mgr)
    return await OpenAIProvider.fetch_available_models_details(provider_config, timeout=timeout, config_mgr=config_mgr)


__all__ = [
    "OpenAIProvider",
    "OpenAIResponsesProvider",
    "AnthropicProvider",
    "get_provider",
    "resolve_api_type",
    "detect_api_type",
    "is_anthropic_provider",
    "fetch_models_details",
    "compute_backoff_delay",
    "is_transient_error",
    "get_retry_params",
    "DEFAULT_RETRIES",
    "DEFAULT_INITIAL_DELAY",
    "DEFAULT_MAX_DELAY",
    "DEFAULT_BACKOFF_FACTOR",
    "DEFAULT_JITTER"
]
