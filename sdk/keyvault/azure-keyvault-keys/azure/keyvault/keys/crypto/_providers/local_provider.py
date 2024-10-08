# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
import abc
import os
from typing import Optional, TYPE_CHECKING, Union

from azure.core.exceptions import AzureError

from .. import DecryptResult, EncryptResult, SignResult, UnwrapResult, VerifyResult, WrapResult
from ... import KeyOperation

ABC = abc.ABC

if TYPE_CHECKING:
    from .._internal.key import Key
    from .. import EncryptionAlgorithm, KeyWrapAlgorithm, SignatureAlgorithm
    from ... import JsonWebKey

    Algorithm = Union[EncryptionAlgorithm, KeyWrapAlgorithm, SignatureAlgorithm]


class LocalCryptographyProvider(ABC):
    def __init__(self, key: "JsonWebKey") -> None:
        self._allowed_ops = frozenset(key.key_ops or [])  # type: ignore[attr-defined]
        self._internal_key = self._get_internal_key(key)
        self._key = key

    @abc.abstractmethod
    def _get_internal_key(self, key: "JsonWebKey") -> "Key":
        pass

    @abc.abstractmethod
    def supports(self, operation: KeyOperation, algorithm: "Algorithm") -> bool:
        pass

    @property
    def key_id(self) -> "Optional[str]":
        """The full identifier of the provider's key.

        :returns: The full identifier of the provider's key.
        :rtype: str or None
        """
        return self._key.kid  # type: ignore[attr-defined]

    def _raise_if_unsupported(self, operation: KeyOperation, algorithm: "Algorithm") -> None:
        if not self.supports(operation, algorithm):
            raise NotImplementedError(
                f'This key does not support the "{operation}" operation with algorithm "{algorithm}"'
            )
        if operation not in self._allowed_ops:
            raise AzureError(f'This key does not allow the "{operation}" operation')

    def encrypt(
        self, algorithm: "EncryptionAlgorithm", plaintext: bytes, iv: "Optional[bytes]" = None
    ) -> EncryptResult:
        self._raise_if_unsupported(KeyOperation.encrypt, algorithm)

        # If an IV isn't provided with AES-CBCPAD encryption, try to create one
        if iv is None and algorithm.value.endswith("CBCPAD"):
            try:
                iv = os.urandom(16)
            except NotImplementedError as ex:
                raise ValueError(
                    "An IV could not be generated on this OS. Please provide your own cryptographically random, "
                    "non-repeating IV for local cryptography."
                ) from ex

        ciphertext = self._internal_key.encrypt(plaintext, algorithm=algorithm.value, iv=iv)
        return EncryptResult(
            key_id=self._key.kid, algorithm=algorithm, ciphertext=ciphertext, iv=iv  # type: ignore[attr-defined]
        )

    def decrypt(
        self, algorithm: "EncryptionAlgorithm", ciphertext: bytes, iv: "Optional[bytes]" = None
    ) -> DecryptResult:
        self._raise_if_unsupported(KeyOperation.decrypt, algorithm)
        plaintext = self._internal_key.decrypt(ciphertext, iv=iv, algorithm=algorithm.value)
        return DecryptResult(
            key_id=self._key.kid, algorithm=algorithm, plaintext=plaintext  # type: ignore[attr-defined]
        )

    def wrap_key(self, algorithm: "KeyWrapAlgorithm", key: bytes) -> "WrapResult":
        self._raise_if_unsupported(KeyOperation.wrap_key, algorithm)
        encrypted_key = self._internal_key.wrap_key(key, algorithm=algorithm.value)
        return WrapResult(
            key_id=self._key.kid, algorithm=algorithm, encrypted_key=encrypted_key  # type: ignore[attr-defined]
        )

    def unwrap_key(self, algorithm: "KeyWrapAlgorithm", encrypted_key: bytes) -> "UnwrapResult":
        self._raise_if_unsupported(KeyOperation.unwrap_key, algorithm)
        unwrapped_key = self._internal_key.unwrap_key(encrypted_key, algorithm=algorithm.value)
        return UnwrapResult(key_id=self._key.kid, algorithm=algorithm, key=unwrapped_key)  # type: ignore[attr-defined]

    def sign(self, algorithm: "SignatureAlgorithm", digest: bytes) -> "SignResult":
        self._raise_if_unsupported(KeyOperation.sign, algorithm)
        signature = self._internal_key.sign(digest, algorithm=algorithm.value)
        return SignResult(key_id=self._key.kid, algorithm=algorithm, signature=signature)  # type: ignore[attr-defined]

    def verify(self, algorithm: "SignatureAlgorithm", digest: bytes, signature: bytes) -> "VerifyResult":
        self._raise_if_unsupported(KeyOperation.verify, algorithm)
        is_valid = self._internal_key.verify(digest, signature, algorithm=algorithm.value)
        return VerifyResult(key_id=self._key.kid, algorithm=algorithm, is_valid=is_valid)  # type: ignore[attr-defined]
