"""
Credential Store Service

Secure storage for API credentials with AES-256 encryption.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import os
import hashlib
import secrets
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from dataclasses import dataclass
from enum import Enum
import logging
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class CredentialType(str, Enum):
    """Types of credentials."""
    API_KEY = "api_key"
    OAUTH2_CLIENT = "oauth2_client"
    BASIC_AUTH = "basic_auth"
    BEARER_TOKEN = "bearer_token"
    CERTIFICATE = "certificate"


@dataclass
class StoredCredential:
    """A stored credential record."""
    id: UUID
    source_name: str
    credential_type: CredentialType
    key_name: str
    encrypted_value: bytes
    nonce: bytes
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class CredentialValue:
    """Decrypted credential value."""
    key_name: str
    value: str
    credential_type: CredentialType
    expires_at: Optional[datetime] = None


class CredentialStore:
    """
    Secure credential storage with AES-256-GCM encryption.

    Features:
    - AES-256-GCM encryption for all credentials
    - Key derivation using PBKDF2
    - Automatic nonce generation
    - Credential expiration tracking
    - Audit logging
    """

    # PBKDF2 parameters
    PBKDF2_ITERATIONS = 100000
    SALT_SIZE = 16
    NONCE_SIZE = 12  # 96 bits for GCM
    KEY_SIZE = 32  # 256 bits

    def __init__(self, db_pool, master_key: Optional[str] = None):
        """
        Initialize credential store.

        Args:
            db_pool: Database connection pool
            master_key: Master encryption key (from env var if not provided)
        """
        self.db_pool = db_pool

        # Get master key from environment if not provided
        if master_key is None:
            master_key = os.environ.get("DK_CREDENTIAL_MASTER_KEY")
            if not master_key:
                raise ValueError(
                    "Master key required. Set DK_CREDENTIAL_MASTER_KEY environment variable."
                )

        # Derive encryption key from master key
        self._encryption_key = self._derive_key(master_key)

    def _derive_key(self, master_key: str) -> bytes:
        """Derive encryption key from master key using PBKDF2."""
        # Use a fixed salt derived from master key for deterministic key derivation
        salt = hashlib.sha256(master_key.encode()).digest()[:self.SALT_SIZE]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(master_key.encode())

    def _encrypt(self, plaintext: str) -> tuple[bytes, bytes]:
        """
        Encrypt plaintext using AES-256-GCM.

        Args:
            plaintext: Data to encrypt

        Returns:
            Tuple of (ciphertext, nonce)
        """
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(self._encryption_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return ciphertext, nonce

    def _decrypt(self, ciphertext: bytes, nonce: bytes) -> str:
        """
        Decrypt ciphertext using AES-256-GCM.

        Args:
            ciphertext: Encrypted data
            nonce: Nonce used for encryption

        Returns:
            Decrypted plaintext
        """
        aesgcm = AESGCM(self._encryption_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

    async def store_credential(
        self,
        source_name: str,
        key_name: str,
        value: str,
        credential_type: CredentialType,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """
        Store an encrypted credential.

        Args:
            source_name: Name of the data source
            key_name: Name of the credential (e.g., "api_key", "client_id")
            value: The credential value to encrypt
            credential_type: Type of credential
            expires_at: Optional expiration datetime
            metadata: Optional additional metadata

        Returns:
            UUID of the stored credential
        """
        # Encrypt the credential
        encrypted_value, nonce = self._encrypt(value)

        credential_id = uuid4()

        async with self.db_pool.acquire() as conn:
            # Check if credential already exists
            existing = await conn.fetchrow("""
                SELECT id FROM platform.credentials
                WHERE source_name = $1 AND key_name = $2
            """, source_name, key_name)

            if existing:
                # Update existing credential
                await conn.execute("""
                    UPDATE platform.credentials
                    SET encrypted_value = $1,
                        nonce = $2,
                        credential_type = $3,
                        expires_at = $4,
                        metadata = $5,
                        updated_at = NOW()
                    WHERE source_name = $6 AND key_name = $7
                """,
                    encrypted_value, nonce, credential_type.value,
                    expires_at, metadata, source_name, key_name
                )
                credential_id = existing['id']
                logger.info(f"Updated credential {key_name} for source {source_name}")
            else:
                # Insert new credential
                await conn.execute("""
                    INSERT INTO platform.credentials (
                        id, source_name, key_name, encrypted_value, nonce,
                        credential_type, expires_at, metadata, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                """,
                    credential_id, source_name, key_name, encrypted_value, nonce,
                    credential_type.value, expires_at, metadata
                )
                logger.info(f"Stored new credential {key_name} for source {source_name}")

            # Log audit event
            await self._log_audit(conn, source_name, key_name, "store")

        return credential_id

    async def get_credential(
        self,
        source_name: str,
        key_name: str
    ) -> Optional[CredentialValue]:
        """
        Retrieve and decrypt a credential.

        Args:
            source_name: Name of the data source
            key_name: Name of the credential

        Returns:
            CredentialValue with decrypted value, or None if not found
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT encrypted_value, nonce, credential_type, expires_at
                FROM platform.credentials
                WHERE source_name = $1 AND key_name = $2
            """, source_name, key_name)

            if not row:
                return None

            # Check expiration
            if row['expires_at'] and row['expires_at'] < datetime.utcnow():
                logger.warning(f"Credential {key_name} for {source_name} has expired")
                return None

            # Decrypt the credential
            try:
                decrypted_value = self._decrypt(row['encrypted_value'], row['nonce'])
            except Exception as e:
                logger.error(f"Failed to decrypt credential: {e}")
                return None

            # Log access audit
            await self._log_audit(conn, source_name, key_name, "access")

            return CredentialValue(
                key_name=key_name,
                value=decrypted_value,
                credential_type=CredentialType(row['credential_type']),
                expires_at=row['expires_at'],
            )

    async def get_credentials_for_source(
        self,
        source_name: str
    ) -> Dict[str, CredentialValue]:
        """
        Get all credentials for a data source.

        Args:
            source_name: Name of the data source

        Returns:
            Dict mapping key_name to CredentialValue
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT key_name, encrypted_value, nonce, credential_type, expires_at
                FROM platform.credentials
                WHERE source_name = $1
            """, source_name)

            credentials = {}
            for row in rows:
                # Check expiration
                if row['expires_at'] and row['expires_at'] < datetime.utcnow():
                    continue

                try:
                    decrypted_value = self._decrypt(row['encrypted_value'], row['nonce'])
                    credentials[row['key_name']] = CredentialValue(
                        key_name=row['key_name'],
                        value=decrypted_value,
                        credential_type=CredentialType(row['credential_type']),
                        expires_at=row['expires_at'],
                    )
                except Exception as e:
                    logger.error(f"Failed to decrypt credential {row['key_name']}: {e}")

            return credentials

    async def delete_credential(
        self,
        source_name: str,
        key_name: str
    ) -> bool:
        """
        Delete a credential.

        Args:
            source_name: Name of the data source
            key_name: Name of the credential

        Returns:
            True if deleted, False if not found
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM platform.credentials
                WHERE source_name = $1 AND key_name = $2
            """, source_name, key_name)

            deleted = result == "DELETE 1"
            if deleted:
                await self._log_audit(conn, source_name, key_name, "delete")
                logger.info(f"Deleted credential {key_name} for source {source_name}")

            return deleted

    async def rotate_credential(
        self,
        source_name: str,
        key_name: str,
        new_value: str,
        expires_at: Optional[datetime] = None
    ) -> bool:
        """
        Rotate a credential with a new value.

        Args:
            source_name: Name of the data source
            key_name: Name of the credential
            new_value: New credential value
            expires_at: New expiration datetime

        Returns:
            True if rotated successfully
        """
        # Get existing credential to preserve type and metadata
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT credential_type, metadata FROM platform.credentials
                WHERE source_name = $1 AND key_name = $2
            """, source_name, key_name)

            if not row:
                logger.warning(f"Credential {key_name} for {source_name} not found")
                return False

        # Store new value
        await self.store_credential(
            source_name=source_name,
            key_name=key_name,
            value=new_value,
            credential_type=CredentialType(row['credential_type']),
            expires_at=expires_at,
            metadata=row['metadata'],
        )

        # Log rotation audit
        async with self.db_pool.acquire() as conn:
            await self._log_audit(conn, source_name, key_name, "rotate")

        logger.info(f"Rotated credential {key_name} for source {source_name}")
        return True

    async def list_credentials(
        self,
        source_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List credentials (without decrypting values).

        Args:
            source_name: Optional filter by source

        Returns:
            List of credential metadata
        """
        async with self.db_pool.acquire() as conn:
            if source_name:
                rows = await conn.fetch("""
                    SELECT id, source_name, key_name, credential_type,
                           created_at, updated_at, expires_at
                    FROM platform.credentials
                    WHERE source_name = $1
                    ORDER BY source_name, key_name
                """, source_name)
            else:
                rows = await conn.fetch("""
                    SELECT id, source_name, key_name, credential_type,
                           created_at, updated_at, expires_at
                    FROM platform.credentials
                    ORDER BY source_name, key_name
                """)

            return [
                {
                    "id": str(r['id']),
                    "source_name": r['source_name'],
                    "key_name": r['key_name'],
                    "credential_type": r['credential_type'],
                    "created_at": r['created_at'].isoformat() if r['created_at'] else None,
                    "updated_at": r['updated_at'].isoformat() if r['updated_at'] else None,
                    "expires_at": r['expires_at'].isoformat() if r['expires_at'] else None,
                    "is_expired": r['expires_at'] < datetime.utcnow() if r['expires_at'] else False,
                }
                for r in rows
            ]

    async def check_expiring_credentials(
        self,
        days_threshold: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Check for credentials expiring soon.

        Args:
            days_threshold: Number of days to consider "expiring soon"

        Returns:
            List of expiring credentials
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, source_name, key_name, expires_at
                FROM platform.credentials
                WHERE expires_at IS NOT NULL
                AND expires_at <= NOW() + INTERVAL '%s days'
                ORDER BY expires_at
            """, days_threshold)

            return [
                {
                    "id": str(r['id']),
                    "source_name": r['source_name'],
                    "key_name": r['key_name'],
                    "expires_at": r['expires_at'].isoformat(),
                    "days_until_expiry": (r['expires_at'] - datetime.utcnow()).days,
                }
                for r in rows
            ]

    async def _log_audit(
        self,
        conn,
        source_name: str,
        key_name: str,
        action: str
    ):
        """Log credential audit event."""
        await conn.execute("""
            INSERT INTO platform.credential_audit_log (
                id, source_name, key_name, action, timestamp
            ) VALUES ($1, $2, $3, $4, NOW())
        """, uuid4(), source_name, key_name, action)
