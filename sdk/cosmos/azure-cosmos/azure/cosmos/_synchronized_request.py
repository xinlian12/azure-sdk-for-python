# The MIT License (MIT)
# Copyright (c) 2014 Microsoft Corporation

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Synchronized request in the Azure Cosmos database service.
"""
import copy
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future

from urllib.parse import urlparse
from azure.core.exceptions import DecodeError  # type: ignore
from azure.core import PipelineClient
from typing import Any

from . import exceptions, http_constants, _retry_utility
from .documents import ConnectionPolicy
from ._request_object import RequestObject
from ._global_partition_endpoint_manager_per_partition_automatic_failover import _GlobalPartitionEndpointManagerForPerPartitionAutomaticFailover


def _is_readable_stream(obj):
    """Checks whether obj is a file-like readable stream.

    :param Union[str, unicode, file-like stream object, dict, list, None] obj: the object to be checked.
    :returns: whether the object is a file-like readable stream.
    :rtype: boolean
    """
    if hasattr(obj, "read") and callable(getattr(obj, "read")):
        return True
    return False


def _request_body_from_data(data):
    """Gets request body from data.

    When `data` is dict and list into unicode string; otherwise return `data`
    without making any change.

    :param Union[str, unicode, file-like stream object, dict, list, None] data:
    :returns: the json dump data.
    :rtype: Union[str, unicode, file-like stream object, None]

    """
    if data is None or isinstance(data, str) or _is_readable_stream(data):
        return data
    if isinstance(data, (dict, list, tuple)):
        json_dumped = json.dumps(data, separators=(",", ":"))

        return json_dumped
    return None


def _Request(
        global_endpoint_manager: _GlobalPartitionEndpointManagerForPerPartitionAutomaticFailover,
        request_params: RequestObject,
        connection_policy: ConnectionPolicy,
        pipeline_client: PipelineClient,
        request: Any,
        **kwargs): # pylint: disable=too-many-statements
    """Makes one http request using the requests module.

    :param _GlobalEndpointManager global_endpoint_manager:
    :param ~azure.cosmos._request_object.RequestObject request_params:
        contains information for the request, like the resource_type, operation_type, and endpoint_override
    :param documents.ConnectionPolicy connection_policy:
    :param azure.core.PipelineClient pipeline_client:
        Pipeline client to process the request
    :param azure.core.pipeline.transport.HttpRequest request:
        The request object to send through the pipeline
    :return: tuple of (result, headers)
    :rtype: tuple of (dict, dict)

    """
    # pylint: disable=protected-access

    connection_timeout = connection_policy.RequestTimeout
    connection_timeout = kwargs.pop("connection_timeout", connection_timeout)
    read_timeout = connection_policy.ReadTimeout
    read_timeout = kwargs.pop("read_timeout", read_timeout)

    # Every request tries to perform a refresh
    client_timeout = kwargs.get('timeout')
    start_time = time.time()
    if request_params.healthy_tentative_location:
        read_timeout = connection_policy.RecoveryReadTimeout
    if request_params.resource_type != http_constants.ResourceType.DatabaseAccount:
        global_endpoint_manager.refresh_endpoint_list(None, **kwargs)
    else:
        # always override database account call timeouts
        read_timeout = connection_policy.DBAReadTimeout
        connection_timeout = connection_policy.DBAConnectionTimeout
    if client_timeout is not None:
        kwargs['timeout'] = client_timeout - (time.time() - start_time)
        if kwargs['timeout'] <= 0:
            raise exceptions.CosmosClientTimeoutError()

    if request_params.endpoint_override:
        base_url = request_params.endpoint_override
    else:
        pk_range_wrapper = None
        if (global_endpoint_manager.is_circuit_breaker_applicable(request_params) or
                global_endpoint_manager.is_per_partition_automatic_failover_applicable(request_params)):
            # Circuit breaker or per-partition failover are applicable, so we need to use the endpoint from the request
            pk_range_wrapper = global_endpoint_manager.create_pk_range_wrapper(request_params)
        base_url = global_endpoint_manager.resolve_service_endpoint_for_partition(request_params, pk_range_wrapper)
    if not request.url.startswith(base_url):
        request.url = _replace_url_prefix(request.url, base_url)

    parse_result = urlparse(request.url)

    # The requests library now expects header values to be strings only starting 2.11,
    # and will raise an error on validation if they are not, so casting all header values to strings.
    request.headers.update({header: str(value) for header, value in request.headers.items()})

    # We are disabling the SSL verification for local emulator(localhost/127.0.0.1) or if the user
    # has explicitly specified to disable SSL verification.
    is_ssl_enabled = (
        parse_result.hostname != "localhost"
        and parse_result.hostname != "127.0.0.1"
        and not connection_policy.DisableSSLVerification
    )

    if connection_policy.SSLConfiguration or "connection_cert" in kwargs:
        ca_certs = connection_policy.SSLConfiguration.SSLCaCerts
        cert_files = (connection_policy.SSLConfiguration.SSLCertFile, connection_policy.SSLConfiguration.SSLKeyFile)
        response = _PipelineRunFunction(
            pipeline_client,
            request,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            connection_verify=kwargs.pop("connection_verify", ca_certs),
            connection_cert=kwargs.pop("connection_cert", cert_files),
            request_params=request_params,
            global_endpoint_manager=global_endpoint_manager,
            **kwargs
        )
    else:
        response = _PipelineRunFunction(
            pipeline_client,
            request,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            # If SSL is disabled, verify = false
            connection_verify=kwargs.pop("connection_verify", is_ssl_enabled),
            request_params=request_params,
            global_endpoint_manager=global_endpoint_manager,
            **kwargs
        )

    response = response.http_response
    headers = copy.copy(response.headers)

    data = response.body()
    if data:
        data = data.decode("utf-8")

    if response.status_code == 404:
        raise exceptions.CosmosResourceNotFoundError(message=data, response=response)
    if response.status_code == 409:
        raise exceptions.CosmosResourceExistsError(message=data, response=response)
    if response.status_code == 412:
        raise exceptions.CosmosAccessConditionFailedError(message=data, response=response)
    if response.status_code >= 400:
        raise exceptions.CosmosHttpResponseError(message=data, response=response)

    result = None
    if data:
        try:
            result = json.loads(data)
        except Exception as e:
            raise DecodeError(
                message="Failed to decode JSON data: {}".format(e),
                response=response,
                error=e) from e

    return result, headers


def _replace_url_prefix(original_url, new_prefix):
    parts = original_url.split('/', 3)

    if not new_prefix.endswith('/'):
        new_prefix += '/'

    new_url = new_prefix + parts[3] if len(parts) > 3 else new_prefix

    return new_url


def _PipelineRunFunction(pipeline_client, request, **kwargs):
    # pylint: disable=protected-access

    return pipeline_client._pipeline.run(request, **kwargs)

def SynchronizedRequest(
        client,
        request_params,
        global_endpoint_manager,
        connection_policy,
        pipeline_client,
        request,
        request_data,
        **kwargs
):
    """Performs one synchronized http request according to the parameters.

    :param object client: Document client instance
    :param dict request_params:
    :param _GlobalEndpointManager global_endpoint_manager:
    :param documents.ConnectionPolicy connection_policy:
    :param azure.core.PipelineClient pipeline_client: PipelineClient to process the request.
    :param HttpRequest request: the HTTP request to be sent
    :param (str, unicode, file-like stream object, dict, list or None) request_data: the data to be sent in the request
    :return: tuple of (result, headers)
    :rtype: tuple of (dict dict)
    """
    def prepare_request(req, req_data):
        """Helper to prepare request data and headers"""
        req.data = _request_body_from_data(req_data)
        if req.data and isinstance(req.data, str):
            req.headers[http_constants.HttpHeaders.ContentLength] = len(req.data)
        elif req.data is None:
            req.headers[http_constants.HttpHeaders.ContentLength] = 0
        return req

    # Prepare the original request
    request = prepare_request(request, request_data)

    # Handle hedging if strategy is configured
    if request_params.availability_strategy and not request_params.is_hedging_request:
        # Get available locations from global endpoint manager
        available_locations = global_endpoint_manager.get_ordered_read_locations()
        
        # Filter out excluded locations
        if request_params.excluded_locations:
            available_locations = [loc for loc in available_locations
                                 if loc not in request_params.excluded_locations]
        
        # Set up thread pool for parallel execution
        max_requests = min(len(available_locations),
                         request_params.availability_strategy.max_hedged_requests)
        executor = ThreadPoolExecutor(max_workers=max_requests)
        futures = []
        threshold = request_params.availability_strategy.threshold
        threshold_steps = request_params.availability_strategy.threshold_steps

        def execute_request(req, params):
            """Helper to execute a single request"""
            try:
                return _retry_utility.Execute(
                    client,
                    global_endpoint_manager,
                    _Request,
                    params,
                    connection_policy,
                    pipeline_client,
                    req,
                    **kwargs
                )
            except exceptions.CosmosHttpResponseError as e:
                # Check if error is non-transient
                status_code = e.status_code
                sub_status = e.sub_status
                if (status_code in [400, 409, 405, 412, 413, 401] or
                    (status_code == 404 and sub_status == 0)):
                    # Non-transient error - propagate it
                    raise
                return None, None
            except Exception as e:  # pylint: disable=broad-except
                return None, None

        # Create and execute initial request
        futures.append(executor.submit(execute_request, request, request_params))

        # Create hedged requests based on threshold
        for _ in range(request_params.availability_strategy.max_hedged_requests - 1):
            # Wait for threshold duration
            time.sleep(threshold)
            
            # Check for completed requests
            for future in futures:
                if future.done():
                    try:
                        result = future.result()
                        if result[0] is not None:  # Valid response received
                            executor.shutdown(wait=False)
                            return result
                    except exceptions.CosmosHttpResponseError as e:
                        # If non-transient error occurred, stop hedging
                        status_code = e.status_code
                        sub_status = e.sub_status
                        if (status_code in [400, 409, 405, 412, 413, 401] or
                            (status_code == 404 and sub_status == 0)):
                            executor.shutdown(wait=False)
                            raise
                    except Exception:  # pylint: disable=broad-except
                        pass  # Continue if request failed with transient error

            # Create new hedged request targeting next available location
            if len(futures) < len(available_locations):
                hedged_params = copy.deepcopy(request_params)
                hedged_params.is_hedging_request = True
                # Route request to specific location
                location = available_locations[len(futures)]
                hedged_params.route_to_location(
                    LocationCache.GetLocationalEndpoint(
                        global_endpoint_manager.DefaultEndpoint,
                        location
                    )
                )
                hedged_request = copy.deepcopy(request)
                future = executor.submit(execute_request, hedged_request, hedged_params)
                futures.append(future)

            # Track for cancellation
            if hasattr(request_params, "pending_requests"):
                request_params.pending_requests.append(future)

            # Increase threshold for next iteration
            threshold *= threshold_steps

        # Wait for any remaining requests
        for future in futures:
            try:
                result = future.result()
                if result[0] is not None:  # Valid response received
                    return result
            except Exception:  # pylint: disable=broad-except
                continue

        # If all requests failed, raise the last exception
        raise exceptions.CosmosClientError("All hedged requests failed")


    # Regular execution path for non-hedged requests
    return _retry_utility.Execute(
        client,
        global_endpoint_manager,
        _Request,
        request_params,
        connection_policy,
        pipeline_client,
        request,
        **kwargs
    )
