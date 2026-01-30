"""
Feature Flags Configuration

Centralized feature flag management for the Pharma-Predictor application.
All feature flags are controlled via environment variables with sensible defaults.
"""

import os
from functools import lru_cache


class FeatureFlags:
    """
    Feature flags for controlling application behavior.

    All flags default to enabled (True) unless explicitly disabled.
    Use environment variables to override defaults.

    Environment variable format: FEATURE_<FLAG_NAME>=true|false
    """

    # Drug Enrichment API
    ENABLE_DRUG_ENRICHMENT_API: bool = True
    ENABLE_EXTERNAL_APIS: bool = True
    ENABLE_BATCH_SYNC: bool = True
    ENABLE_BATCH_ASYNC: bool = True
    ENABLE_WHO_INN_DATA: bool = True

    # Caching
    ENABLE_REDIS_CACHE: bool = True
    ENABLE_MEMORY_CACHE: bool = True
    CACHE_TTL_SECONDS: int = 86400  # 24 hours

    # Rate Limiting
    ENABLE_RATE_LIMITING: bool = True
    RATE_LIMIT_EXTERNAL_RPM: int = 100  # Requests per minute for external API key users
    RATE_LIMIT_INTERNAL_RPM: int = 0  # 0 = unlimited for internal calls

    # Authentication
    ENABLE_API_KEY_AUTH: bool = True
    REQUIRE_API_KEY_EXTERNAL: bool = True
    REQUIRE_API_KEY_INTERNAL: bool = False

    # Observability
    ENABLE_PROMETHEUS_METRICS: bool = True
    ENABLE_OPENTELEMETRY_TRACING: bool = True
    ENABLE_STRUCTURED_LOGGING: bool = True
    ENABLE_WEBSOCKET_UPDATES: bool = True

    # Data Sources
    ENABLE_CHEMBL: bool = True
    ENABLE_PUBCHEM: bool = True
    ENABLE_FDA: bool = True
    ENABLE_SIDER: bool = True
    ENABLE_DRUGBANK: bool = True
    ENABLE_BINDINGDB: bool = True
    ENABLE_RXNORM: bool = True
    ENABLE_CLINICAL_TRIALS: bool = True

    # Computed Features
    ENABLE_FINGERPRINTS: bool = True
    ENABLE_MOLECULAR_DESCRIPTORS: bool = True
    ENABLE_SIMILARITY_SEARCH: bool = True
    ENABLE_PROTEIN_EMBEDDINGS: bool = True

    # Frontend Features
    ENABLE_ENRICHMENT_DASHBOARD: bool = True
    ENABLE_REAL_TIME_METRICS: bool = True
    ENABLE_BATCH_PROGRESS_TRACKING: bool = True

    @classmethod
    def _get_bool_env(cls, name: str, default: bool) -> bool:
        """Get boolean value from environment variable."""
        value = os.getenv(name, "").lower()
        if value in ("true", "1", "yes", "on"):
            return True
        if value in ("false", "0", "no", "off"):
            return False
        return default

    @classmethod
    def _get_int_env(cls, name: str, default: int) -> int:
        """Get integer value from environment variable."""
        value = os.getenv(name)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                pass
        return default

    @classmethod
    def load_from_environment(cls) -> "FeatureFlags":
        """
        Load feature flags from environment variables.

        Returns a new FeatureFlags instance with values from environment.
        """
        flags = cls()

        # Drug Enrichment API
        flags.ENABLE_DRUG_ENRICHMENT_API = cls._get_bool_env(
            "ENABLE_DRUG_ENRICHMENT_API", cls.ENABLE_DRUG_ENRICHMENT_API
        )
        flags.ENABLE_EXTERNAL_APIS = cls._get_bool_env(
            "ENABLE_EXTERNAL_APIS", cls.ENABLE_EXTERNAL_APIS
        )
        flags.ENABLE_BATCH_SYNC = cls._get_bool_env(
            "ENABLE_BATCH_SYNC", cls.ENABLE_BATCH_SYNC
        )
        flags.ENABLE_BATCH_ASYNC = cls._get_bool_env(
            "ENABLE_BATCH_ASYNC", cls.ENABLE_BATCH_ASYNC
        )
        flags.ENABLE_WHO_INN_DATA = cls._get_bool_env(
            "ENABLE_WHO_INN_DATA", cls.ENABLE_WHO_INN_DATA
        )

        # Caching
        flags.ENABLE_REDIS_CACHE = cls._get_bool_env(
            "ENABLE_REDIS_CACHE", cls.ENABLE_REDIS_CACHE
        )
        flags.ENABLE_MEMORY_CACHE = cls._get_bool_env(
            "ENABLE_MEMORY_CACHE", cls.ENABLE_MEMORY_CACHE
        )
        flags.CACHE_TTL_SECONDS = cls._get_int_env(
            "ENRICHMENT_CACHE_TTL", cls.CACHE_TTL_SECONDS
        )

        # Rate Limiting
        flags.ENABLE_RATE_LIMITING = cls._get_bool_env(
            "ENABLE_RATE_LIMITING", cls.ENABLE_RATE_LIMITING
        )
        flags.RATE_LIMIT_EXTERNAL_RPM = cls._get_int_env(
            "ENRICHMENT_RATE_LIMIT_EXTERNAL", cls.RATE_LIMIT_EXTERNAL_RPM
        )

        # Authentication
        flags.ENABLE_API_KEY_AUTH = cls._get_bool_env(
            "ENABLE_API_KEY_AUTH", cls.ENABLE_API_KEY_AUTH
        )
        flags.REQUIRE_API_KEY_EXTERNAL = cls._get_bool_env(
            "REQUIRE_API_KEY_EXTERNAL", cls.REQUIRE_API_KEY_EXTERNAL
        )

        # Observability
        flags.ENABLE_PROMETHEUS_METRICS = cls._get_bool_env(
            "PROMETHEUS_ENABLED", cls.ENABLE_PROMETHEUS_METRICS
        )
        flags.ENABLE_OPENTELEMETRY_TRACING = cls._get_bool_env(
            "OTEL_ENABLED", cls.ENABLE_OPENTELEMETRY_TRACING
        )
        flags.ENABLE_STRUCTURED_LOGGING = cls._get_bool_env(
            "ENABLE_STRUCTURED_LOGGING", cls.ENABLE_STRUCTURED_LOGGING
        )
        flags.ENABLE_WEBSOCKET_UPDATES = cls._get_bool_env(
            "ENABLE_WEBSOCKET_UPDATES", cls.ENABLE_WEBSOCKET_UPDATES
        )

        # Data Sources
        flags.ENABLE_CHEMBL = cls._get_bool_env("ENABLE_CHEMBL", cls.ENABLE_CHEMBL)
        flags.ENABLE_PUBCHEM = cls._get_bool_env("ENABLE_PUBCHEM", cls.ENABLE_PUBCHEM)
        flags.ENABLE_FDA = cls._get_bool_env("ENABLE_FDA", cls.ENABLE_FDA)
        flags.ENABLE_SIDER = cls._get_bool_env("ENABLE_SIDER", cls.ENABLE_SIDER)
        flags.ENABLE_DRUGBANK = cls._get_bool_env("ENABLE_DRUGBANK", cls.ENABLE_DRUGBANK)
        flags.ENABLE_BINDINGDB = cls._get_bool_env("ENABLE_BINDINGDB", cls.ENABLE_BINDINGDB)
        flags.ENABLE_RXNORM = cls._get_bool_env("ENABLE_RXNORM", cls.ENABLE_RXNORM)
        flags.ENABLE_CLINICAL_TRIALS = cls._get_bool_env(
            "ENABLE_CLINICAL_TRIALS", cls.ENABLE_CLINICAL_TRIALS
        )

        # Computed Features
        flags.ENABLE_FINGERPRINTS = cls._get_bool_env(
            "ENABLE_FINGERPRINTS", cls.ENABLE_FINGERPRINTS
        )
        flags.ENABLE_MOLECULAR_DESCRIPTORS = cls._get_bool_env(
            "ENABLE_MOLECULAR_DESCRIPTORS", cls.ENABLE_MOLECULAR_DESCRIPTORS
        )
        flags.ENABLE_SIMILARITY_SEARCH = cls._get_bool_env(
            "ENABLE_SIMILARITY_SEARCH", cls.ENABLE_SIMILARITY_SEARCH
        )

        return flags

    def is_enabled(self, flag_name: str) -> bool:
        """
        Check if a feature flag is enabled.

        Args:
            flag_name: Name of the feature flag (e.g., "ENABLE_DRUG_ENRICHMENT_API")

        Returns:
            True if enabled, False otherwise
        """
        return getattr(self, flag_name, False)

    def get_enabled_sources(self) -> list:
        """Get list of enabled data sources."""
        sources = []
        if self.ENABLE_CHEMBL:
            sources.append("chembl")
        if self.ENABLE_PUBCHEM:
            sources.append("pubchem")
        if self.ENABLE_FDA:
            sources.append("fda")
        if self.ENABLE_SIDER:
            sources.append("sider")
        if self.ENABLE_DRUGBANK:
            sources.append("drugbank")
        if self.ENABLE_BINDINGDB:
            sources.append("bindingdb")
        if self.ENABLE_RXNORM:
            sources.append("rxnorm")
        if self.ENABLE_CLINICAL_TRIALS:
            sources.append("clinical_trials")
        if self.ENABLE_WHO_INN_DATA:
            sources.append("inn")
        return sources

    def to_dict(self) -> dict:
        """Convert all flags to dictionary."""
        return {
            key: getattr(self, key)
            for key in dir(self)
            if key.isupper() and not key.startswith("_")
        }


# Singleton instance
@lru_cache(maxsize=1)
def get_feature_flags() -> FeatureFlags:
    """Get the feature flags singleton instance."""
    return FeatureFlags.load_from_environment()


# Convenience function for checking flags
def is_feature_enabled(flag_name: str) -> bool:
    """
    Check if a feature is enabled.

    Args:
        flag_name: Name of the feature flag

    Returns:
        True if enabled, False otherwise
    """
    flags = get_feature_flags()
    return flags.is_enabled(flag_name)
