# Password Service - Bcrypt-based password hashing
import bcrypt
from typing import Tuple


class PasswordService:
    """
    Password hashing and verification service using bcrypt.

    Bcrypt is designed to be slow, making it resistant to brute-force attacks.
    It also includes a salt by default, so no separate salt storage is needed.
    """

    # Number of rounds for bcrypt (higher = more secure but slower)
    # 12 rounds = ~250ms per hash, good balance for auth
    ROUNDS = 12

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string (includes salt and algorithm info)
        """
        # Convert password to bytes
        password_bytes = password.encode('utf-8')

        # Generate salt and hash
        salt = bcrypt.gensalt(rounds=cls.ROUNDS)
        hashed = bcrypt.hashpw(password_bytes, salt)

        # Return as string for storage
        return hashed.decode('utf-8')

    @classmethod
    def verify_password(cls, password: str, password_hash: str) -> bool:
        """
        Verify a password against a hash.

        Args:
            password: Plain text password to verify
            password_hash: Stored password hash

        Returns:
            True if password matches, False otherwise
        """
        try:
            password_bytes = password.encode('utf-8')
            hash_bytes = password_hash.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception:
            return False

    @classmethod
    def needs_rehash(cls, password_hash: str) -> bool:
        """
        Check if a hash needs to be rehashed (e.g., if rounds changed).

        Args:
            password_hash: Current password hash

        Returns:
            True if hash should be rehashed
        """
        try:
            hash_bytes = password_hash.encode('utf-8')
            return bcrypt.check_needs_rehash(hash_bytes, rounds=cls.ROUNDS)
        except Exception:
            return False


# Global instance
password_service = PasswordService()
