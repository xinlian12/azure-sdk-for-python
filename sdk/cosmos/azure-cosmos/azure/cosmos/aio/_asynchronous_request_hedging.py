# The MIT License (MIT)
# Copyright (c) 2021 Microsoft Corporation

"""Asynchronous request hedging in the Azure Cosmos database service."""

import asyncio
import copy
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from azure.cosmos._location_cache import LocationCache
from azure.core.pipeline.policies import AsyncRetryPolicy
from azure.core.utils import CaseInsensitiveDict

from .._availability_strategy import AvailabilityStrategy
from ..exceptions import CosmosClientTimeoutError

logger = logging.getLogger(__name__)

async def execute_hedged_requests(
    func: Any,
    args: List[Any],
    kwargs: Dict[str, Any],
    availability_strategy: AvailabilityStrategy,
    timeout: Optional[float] = None
) -> Tuple[Dict[str, Any], CaseInsensitiveDict]:
    """Executes the given function with hedged requests using asyncio tasks.
    
    :param func: The function to execute
    :param args: The function arguments
    :param kwargs: The function keyword arguments
    :param availability_strategy: The availability strategy instance
    :param timeout: Optional timeout in seconds
    :returns: Tuple of (result, headers)
    :rtype: tuple of (dict, dict)
    :raises: CosmosClientTimeoutError if timeout is exceeded
    """
    # Track all tasks
    tasks: List[asyncio.Task] = []
    
    # Get required objects from kwargs
    global_endpoint_manager = kwargs.get('global_endpoint_manager')
    request_params = kwargs.get('request_params')
    if not global_endpoint_manager or not request_params:
        raise ValueError("global_endpoint_manager and request_params are required")

    # Get timing parameters
    start_time = kwargs.get('timeout', 0)
    threshold = availability_strategy.threshold
    threshold_steps = availability_strategy.threshold_steps

    # Get available locations excluding excluded ones
    available_locations = global_endpoint_manager.get_ordered_read_locations()
    if request_params.excluded_locations:
        available_locations = [loc for loc in available_locations
                             if loc not in request_params.excluded_locations]

    # Create initial tasks based on available locations
    max_requests = min(len(available_locations), availability_strategy.max_hedged_requests)

    try:
        # Create first task
        first_params = copy.deepcopy(request_params)
        first_params.is_hedging_request = True
        first_params.route_to_location(
            LocationCache.GetLocationalEndpoint(
                global_endpoint_manager.DefaultEndpoint,
                available_locations[0]
            )
        )
        tasks.append(asyncio.create_task(func(*args, request_params=first_params, **kwargs)))

        # Create remaining tasks with threshold-based timing
        location_index = 1
        while location_index < max_requests:
            # Wait for threshold duration or until a task completes
            try:
                done, pending = await asyncio.wait(
                    tasks,
                    timeout=threshold,
                    return_when=asyncio.FIRST_COMPLETED
                )

                # If we got a result, process it and cancel other tasks
                for completed_task in done:
                    try:
                        result = completed_task.result()
                        # Success - cancel all other tasks
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        return result
                    except exceptions.CosmosHttpResponseError as e:
                        # Check if error is non-transient
                        status_code = e.status_code
                        sub_status = e.sub_status
                        if (status_code in [400, 409, 405, 412, 413, 401] or
                            (status_code == 404 and sub_status == 0)):
                            # Non-transient error - cancel remaining tasks and propagate
                            for task in tasks:
                                if not task.done():
                                    task.cancel()
                            raise
                        # Log transient error and continue hedging
                        logger.debug("Hedged request failed with transient error: %s", str(e))
                    except Exception as e:  # pylint: disable=broad-except
                        # Log other exceptions but continue with hedging
                        logger.debug("Hedged request failed with error: %s", str(e))

                # Process completed tasks
                for completed_task in done:
                    try:
                        result = completed_task.result()
                        # Success - cancel all other tasks
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        return result
                    except exceptions.CosmosHttpResponseError as e:
                        # Check if error is non-transient
                        status_code = e.status_code
                        sub_status = e.sub_status
                        if (status_code in [400, 409, 405, 412, 413, 401] or
                            (status_code == 404 and sub_status == 0)):
                            # Non-transient error - cancel remaining tasks and propagate
                            for task in tasks:
                                if not task.done():
                                    task.cancel()
                            raise
                        # Log transient error and continue hedging
                        logger.debug("Hedged request failed with transient error: %s", str(e))
                    except Exception as e:  # pylint: disable=broad-except
                        # Log other exceptions but continue with hedging
                        logger.debug("Hedged request failed with error: %s", str(e))

                # Create next hedged request if threshold elapsed without success
                current_params = copy.deepcopy(request_params)
                current_params.is_hedging_request = True
                current_params.route_to_location(
                    LocationCache.GetLocationalEndpoint(
                        global_endpoint_manager.DefaultEndpoint,
                        available_locations[location_index]
                    )
                )
                tasks.append(asyncio.create_task(func(*args, request_params=current_params, **kwargs)))
                location_index += 1

                # Increase threshold for next iteration
                threshold *= threshold_steps

            except asyncio.TimeoutError:
                # If no task completed within threshold, continue with next request
                if location_index < max_requests:
                    current_params = copy.deepcopy(request_params)
                    current_params.is_hedging_request = True
                    current_params.route_to_location(
                        LocationCache.GetLocationalEndpoint(
                            global_endpoint_manager.DefaultEndpoint,
                            available_locations[location_index]
                        )
                    )
                    tasks.append(asyncio.create_task(func(*args, request_params=current_params, **kwargs)))
                    location_index += 1
                    threshold *= threshold_steps

        # If we've exhausted all hedging attempts, wait for any remaining tasks
        done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
        
        # Check results from remaining tasks
        exceptions = []
        for task in done:
            try:
                result = task.result()
                return result
            except Exception as e:  # pylint: disable=broad-except
                exceptions.append(e)

        # If all tasks failed, check if any were non-transient
        non_transient_errors = []
        transient_errors = []
        for e in exceptions:
            if isinstance(e, exceptions.CosmosHttpResponseError):
                status_code = e.status_code
                sub_status = e.sub_status
                if (status_code in [400, 409, 405, 412, 413, 401] or
                    (status_code == 404 and sub_status == 0)):
                    non_transient_errors.append(e)
                else:
                    transient_errors.append(e)
            else:
                transient_errors.append(e)

        # Raise non-transient error if any exist, otherwise last transient error
        if non_transient_errors:
            raise non_transient_errors[0]
        if transient_errors:
            raise transient_errors[-1]
        raise Exception("All hedged requests failed")

    except asyncio.TimeoutError:
        # Cancel all pending tasks
        for task in tasks:
            task.cancel()
        raise CosmosClientTimeoutError()

    finally:
        # Ensure all tasks are cancelled
        for task in tasks:
            if not task.done():
                task.cancel()

class _HedgingRetryPolicy(AsyncRetryPolicy):
    """Implements hedging retry policy for async requests."""

    def __init__(self, availability_strategy: Optional[AvailabilityStrategy] = None, **kwargs):
        super().__init__(**{k: v for k, v in kwargs.items() if v is not None})
        self.availability_strategy = availability_strategy

    async def send(self, request):
        """Sends request with hedging if enabled."""
        if not self.availability_strategy or not self.availability_strategy.enabled:
            return await super().send(request)

        # Extract timeout from context
        timeout = request.context.options.get('timeout')

        # Execute with hedging
        try:
            return await execute_hedged_requests(
                self.next.send,
                [request],
                {},
                self.availability_strategy,
                timeout
            )
        except Exception as e:
            # If hedging fails, fall back to normal retry policy
            logger.debug("Hedging failed, falling back to normal retry: %s", str(e))
            return await super().send(request)
class _HedgingRetryPolicy(AsyncRetryPolicy):
    """Implements hedging retry policy for async requests."""

    def __init__(self, availability_strategy: Optional[AvailabilityStrategy] = None, **kwargs):
        super().__init__(**{k: v for k, v in kwargs.items() if v is not None})
        self.availability_strategy = availability_strategy

    async def send(self, request):
        """Sends request with hedging if enabled."""
        if not self.availability_strategy or not self.availability_strategy.enabled:
            return await super().send(request)

        # Extract timeout from context
        timeout = request.context.options.get('timeout')

        # Execute with hedging
        try:
            return await execute_hedged_requests(
                self.next.send,
                [request],
                {},
                self.availability_strategy,
                timeout
            )
        except Exception as e:
            # If hedging fails, fall back to normal retry policy
            logger.debug("Hedging failed, falling back to normal retry: %s", str(e))
            return await super().send(request)