"""Configuration settings for the Drug Data Enrichment Service."""

from typing import Optional
from pydantic_settings import BaseSettings


class EnrichmentSettings(BaseSettings):
    """Settings for the drug enrichment service."""

    # Cache settings
    cache_ttl: int = 86400  # 24 hours default
    cache_backend: str = "redis"  # redis or memory
    redis_url: str = "redis://localhost:6379/0"

    # Rate limiting
    rate_limit_external: int = 100  # requests per minute for external API keys
    rate_limit_window: int = 60  # seconds

    # Batch processing
    batch_max_sync: int = 100  # max drugs for sync batch
    batch_max_async: int = 10000  # max drugs for async batch
    batch_parallel_limit: int = 10  # concurrent requests per batch

    # External API settings
    enable_external_apis: bool = True
    pubchem_rate_limit: int = 5  # requests per second
    chembl_rate_limit: int = 10
    rxnorm_rate_limit: int = 20

    # Observability
    enable_metrics: bool = True
    enable_tracing: bool = True
    otel_exporter_endpoint: Optional[str] = None
    prometheus_enabled: bool = True

    # Feature flags
    enable_drug_enrichment_api: bool = True
    enable_batch_async: bool = True
    enable_inn_service: bool = True

    class Config:
        env_prefix = "ENRICHMENT_"
        case_sensitive = False


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    host: str = "localhost"
    port: int = 5432
    name: str = "dk_data"
    user: str = "postgres"
    password: str = ""

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    class Config:
        env_prefix = "POSTGRES_"


# Singleton instances
_enrichment_settings: Optional[EnrichmentSettings] = None
_database_settings: Optional[DatabaseSettings] = None


def get_enrichment_settings() -> EnrichmentSettings:
    """Get enrichment settings singleton."""
    global _enrichment_settings
    if _enrichment_settings is None:
        _enrichment_settings = EnrichmentSettings()
    return _enrichment_settings


def get_database_settings() -> DatabaseSettings:
    """Get database settings singleton."""
    global _database_settings
    if _database_settings is None:
        _database_settings = DatabaseSettings()
    return _database_settings
