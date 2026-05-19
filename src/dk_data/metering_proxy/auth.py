"""Consumer key validation for the metering proxy.

Reads consumer configuration from a ConfigMap-mounted YAML file
or falls back to environment-based configuration.

Key format: dk_data_{app_alias}_{random_suffix}
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog
import yaml

logger = structlog.get_logger(__name__)

# Default path where the ConfigMap is mounted
CONSUMERS_CONFIG_PATH = os.getenv(
    "CONSUMERS_CONFIG_PATH", "/etc/dk-data/consumers.yaml"
)


@dataclass
class ConsumerConfig:
    """Configuration for a single consumer."""

    name: str
    alias: str
    allowed_schemas: list[str]
    rpm_limit: int
    tier: str
    api_keys: list[str] = field(default_factory=list)
    # Concurrency cap: maximum in-flight requests per consumer at once.
    # This is the KEY guard against cluster death — rate-limiting by
    # RPM alone lets N slow queries (from M replicas) saturate the DB
    # connection pool long before the RPM budget hits. Default 20 is
    # headroom-sized against `PGRST_DB_POOL=30` per replica: one
    # runaway consumer can hold 2/3 of the pool and still leave the
    # rest of the fleet operational.
    max_in_flight: int = 20


class ConsumerKeyStore:
    """Manages consumer API keys and their configuration.

    Loads consumer configuration from a YAML file (mounted from ConfigMap)
    and provides lookup by API key.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._config_path = config_path or CONSUMERS_CONFIG_PATH
        self._consumers: dict[str, ConsumerConfig] = {}
        self._key_to_consumer: dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        """Load consumer configuration from YAML file."""
        config_file = Path(self._config_path)
        if not config_file.exists():
            logger.warning(
                "consumers_config_not_found",
                path=self._config_path,
                msg="Using empty consumer configuration",
            )
            self._loaded = True
            return

        try:
            with open(config_file) as f:
                data = yaml.safe_load(f)

            consumers = data.get("consumers", {})
            for name, cfg in consumers.items():
                consumer = ConsumerConfig(
                    name=name,
                    alias=cfg.get("alias", name),
                    allowed_schemas=cfg.get("allowed_schemas", []),
                    rpm_limit=cfg.get("rpm_limit", 100),
                    tier=cfg.get("tier", "standard"),
                    api_keys=cfg.get("api_keys", []),
                    max_in_flight=cfg.get("max_in_flight", 20),
                )
                self._consumers[consumer.alias] = consumer
                for key in consumer.api_keys:
                    self._key_to_consumer[key] = consumer.alias

            logger.info(
                "consumers_config_loaded",
                count=len(self._consumers),
                consumers=list(self._consumers.keys()),
            )
            self._loaded = True

        except Exception:
            logger.exception("consumers_config_load_error", path=self._config_path)
            self._loaded = True

    def reload(self) -> None:
        """Reload configuration (e.g., after ConfigMap update)."""
        self._consumers.clear()
        self._key_to_consumer.clear()
        self._loaded = False
        self.load()

    def validate_key(self, api_key: str) -> Optional[ConsumerConfig]:
        """Validate an API key and return the consumer config.

        Args:
            api_key: The bearer token from the Authorization header.

        Returns:
            ConsumerConfig if key is valid, None otherwise.
        """
        if not self._loaded:
            self.load()

        alias = self._key_to_consumer.get(api_key)
        if alias is None:
            return None
        return self._consumers.get(alias)

    def get_consumer(self, alias: str) -> Optional[ConsumerConfig]:
        """Get consumer config by alias."""
        if not self._loaded:
            self.load()
        return self._consumers.get(alias)

    @property
    def consumer_count(self) -> int:
        """Number of configured consumers."""
        if not self._loaded:
            self.load()
        return len(self._consumers)
