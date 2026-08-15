from typing import Optional, List, Dict, Any, Tuple
from config import ModelConfig, ProviderConfig, ConfigManager, default_timeout
from providers.openai_provider import OpenAIProvider
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


def get_provider(
    model_config: ModelConfig, 
    provider_config: ProviderConfig, 
    config_mgr: Optional[ConfigManager] = None
):
    """Factory returning the appropriate provider implementation (OpenAIProvider or AnthropicProvider)."""
    if is_anthropic_provider(model_config, provider_config):
        return AnthropicProvider(model_config, provider_config, config_mgr)
    return OpenAIProvider(model_config, provider_config, config_mgr)


async def fetch_models_details(
    provider_config: ProviderConfig,
    timeout: float = default_timeout("api"),
    config_mgr: Optional[ConfigManager] = None
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """Factory helper executing model discovery across provider types."""
    p_name = (provider_config.name or "").lower()
    base_url = (provider_config.base_url or "").lower()
    
    if "anthropic" in p_name or "api.anthropic.com" in base_url:
        return await AnthropicProvider.fetch_available_models_details(provider_config, timeout=timeout, config_mgr=config_mgr)
    return await OpenAIProvider.fetch_available_models_details(provider_config, timeout=timeout, config_mgr=config_mgr)


__all__ = [
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
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
