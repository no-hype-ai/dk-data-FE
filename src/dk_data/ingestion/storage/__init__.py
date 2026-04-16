"""Object-storage adapters for dk-data ingestion.

Currently exposes the SeaweedFS S3 client. Named ``minio_admin`` after
the dk-alchemy convention where "MinIO" refers to the S3 surface, not
any specific implementation.
"""

from dk_data.ingestion.storage.minio_admin import ObjectStore, from_env

__all__ = ["ObjectStore", "from_env"]
