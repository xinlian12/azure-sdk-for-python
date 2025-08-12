"""Create, read, and delete databases in the Azure Cosmos DB SQL API service.

The CosmosClient provides client-side logical representation to manage requests to the Azure Cosmos DB service.
A single client instance can manage multiple accounts and can be used to perform operations across different
databases, collections, documents, etc.

Client configuration such as request hedging strategies, retry policies, and connection settings are configured
during client initialization and can be overridden per-request where supported.
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional, Union, cast, Callable
import warnings

from azure.core.tracing.decorator import distributed_trace
from azure.core.paging import ItemPaged
from azure.core.credentials import TokenCredential
from azure.core.pipeline.policies import RetryMode

from ._cosmos_client_connection import CosmosClientConnection, CredentialDict
from ._base import build_options, _set_throughput_options
from .offer import ThroughputProperties
from ._retry_utility import ConnectionRetryPolicy
from ._constants import _Constants as Constants
from .database import DatabaseProxy, _get_database_link
from .documents import ConnectionPolicy, DatabaseAccount
from .exceptions import CosmosResourceNotFoundError
from ._availability_strategy import AvailabilityStrategy, DisabledStrategy


__all__ = ("CosmosClient",)


def _parse_connection_str(conn_str: str, credential: Optional[Any]) -> Dict[str, str]:
    conn_str = conn_str.rstrip(";")
    conn_settings = dict([s.split("=", 1) for s in conn_str.split(";")])
    if 'AccountEndpoint' not in conn_settings:
        raise ValueError("Connection string missing setting 'AccountEndpoint'.")
    if not credential and 'AccountKey' not in conn_settings:
        raise ValueError("Connection string missing setting 'AccountKey'.")
    return conn_settings


def _build_auth(credential: CredentialType) -> CredentialDict:
    auth: CredentialDict = {}
    if isinstance(credential, str):
        auth['masterKey'] = credential
    elif isinstance(credential, Mapping):
        if any(k for k in credential.keys() if k in ['masterKey', 'resourceTokens', 'permissionFeed']):
            return cast(CredentialDict, credential)  # Backwards compatible
        auth['resourceTokens'] = credential
    elif isinstance(credential, Iterable):
        auth['permissionFeed'] = cast(Iterable[Mapping[str, Any]], credential)
    elif isinstance(credential, TokenCredential):
        auth['clientSecretCredential'] = credential
    else:
        raise TypeError(
            "Unrecognized credential type. Please supply the master key as a string "
            "or a dictionary, or resource tokens, or a list of permissions, or any instance of a class implementing"
            " TokenCredential (see azure.identity module for specific implementations such as ClientSecretCredential).")
    return auth


def _build_connection_policy(kwargs: Dict[str, Any]) -> ConnectionPolicy:
    # pylint: disable=protected-access
    policy = kwargs.pop('connection_policy', ConnectionPolicy())

    # Availability config
    policy.AvailabilityStrategy = kwargs.pop('availability_strategy', None)

    # Connection config
    # `request_timeout` is supported as a legacy parameter later replaced by `connection_timeout`
    if 'request_timeout' in kwargs:
        policy.RequestTimeout = kwargs.pop('request_timeout') / 1000.0
    else:
        policy.RequestTimeout = kwargs.pop('connection_timeout', policy.RequestTimeout)
    policy.ConnectionMode = kwargs.pop('connection_mode', policy.ConnectionMode)
    policy.ProxyConfiguration = kwargs.pop('proxy_config', policy.ProxyConfiguration)
    policy.EnableEndpointDiscovery = kwargs.pop('enable_endpoint_discovery', policy.EnableEndpointDiscovery)
    policy.PreferredLocations = kwargs.pop('preferred_locations', policy.PreferredLocations)
    policy.ExcludedLocations = kwargs.pop('excluded_locations', policy.ExcludedLocations)
    policy.UseMultipleWriteLocations = kwargs.pop('multiple_write_locations', policy.UseMultipleWriteLocations)

    # SSL config
    verify = kwargs.pop('connection_verify', None)
    policy.DisableSSLVerification = not bool(verify if verify is not None else True)
    ssl = kwargs.pop('ssl_config', policy.SSLConfiguration)
    if ssl:
        ssl.SSLCertFile = kwargs.pop('connection_cert', ssl.SSLCertFile)
        ssl.SSLCaCerts = verify or ssl.SSLCaCerts
        policy.SSLConfiguration = ssl

    # Retry config 
    retry_options = kwargs.pop('retry_options', None)
    if retry_options is not None:
        warnings.warn(
            "'retry_options' has been deprecated and will be removed from the SDK in a future release.",
            DeprecationWarning
        )
    retry_options = policy.RetryOptions
    total_retries = kwargs.pop('retry_total', None)
    total_throttle_retries = kwargs.pop('retry_throttle_total', None)
    retry_options._max_retry_attempt_count = \
        total_throttle_retries or total_retries or retry_options._max_retry_attempt_count
    retry_options._fixed_retry_interval_in_milliseconds = kwargs.pop('retry_fixed_interval', None) or \
        retry_options._fixed_retry_interval_in_milliseconds
    max_backoff = kwargs.pop('retry_backoff_max', None)
    max_throttle_backoff = kwargs.pop('retry_throttle_backoff_max', None)
    retry_options._max_wait_time_in_seconds = \
        max_throttle_backoff or max_backoff or retry_options._max_wait_time_in_seconds
    policy.RetryOptions = retry_options
    connection_retry = kwargs.pop('connection_retry_policy', None)
    if connection_retry is not None:
        warnings.warn(
            "'connection_retry_policy' has been deprecated and will be removed from the SDK in a future release.",
            DeprecationWarning
        )
    if not connection_retry:
        connection_retry = ConnectionRetryPolicy(
            retry_total=total_retries,
            retry_connect=kwargs.pop('retry_connect', None),
            retry_read=kwargs.pop('retry_read', None),
            retry_status=kwargs.pop('retry_status', None),
            retry_backoff_max=max_backoff or retry_options._max_wait_time_in_seconds,
            retry_mode=kwargs.pop('retry_mode', RetryMode.Fixed),
            retry_on_status_codes=kwargs.pop('retry_on_status_codes', []),
            retry_backoff_factor=kwargs.pop('retry_backoff_factor', 1),
        )
    policy.ConnectionRetryConfiguration = connection_retry
    policy.ResponsePayloadOnWriteDisabled = kwargs.pop('no_response_on_write', False)
    policy.RetryNonIdempotentWrites = kwargs.pop(Constants.Kwargs.RETRY_WRITE, False)
    return policy
