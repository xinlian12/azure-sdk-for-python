"""Availability strategy for the Azure Cosmos database service.

This module provides availability strategies that can be used to improve request latency and
availability in multi-region deployments. Strategies can be configured at the client level
and overridden per request.

Example:
    ```python
    from azure.cosmos import CosmosClient
    from azure.cosmos._availability_strategy import CrossRegionHedgingStrategy, DisabledStrategy
    from datetime import timedelta

    # Configure hedging strategy with 100ms threshold and 50% step increases
    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=100),
        threshold_steps=[0.5, 1.0, 2.0]  # Will try at 50ms, 100ms, 200ms
    )

    # Create client with configured strategy
    client = CosmosClient(url, credential, availability_strategy=strategy)
    container = client.get_container_client("dbname", "containername")
    
    # Strategy will be used automatically for read operations
    items = list(container.read_all_items())

    # Override strategy for a specific request
    custom_strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=50),
        threshold_steps=[0.5]
    )
    items = list(container.read_all_items(availability_strategy=custom_strategy))

    # Disable hedging for a specific request
    items = list(container.read_all_items(availability_strategy=DisabledStrategy()))
    ```
"""

import abc
from datetime import timedelta
from typing import List, Optional, Tuple, Any, Dict, Callable, Union


class AvailabilityStrategy(abc.ABC):
    """Abstract base class for availability strategies.
    
    This class defines the interface that all availability strategies must implement.
    Strategies can modify how requests are executed to improve availability and latency.
    Strategies can be configured at the client level and overridden per request.
    """

    @property
    @abc.abstractmethod
    def max_hedged_requests(self) -> int:
        """Maximum number of concurrent hedged requests allowed.

        :return: Maximum number of hedged requests
        :rtype: int
        """
        pass

    @abc.abstractmethod
    def execute_request(
        self,
        request_fn: Callable[[], Tuple[Dict[str, Any], Dict[str, Any]]],
        pending_requests: List[Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Execute a request with the availability strategy.

        :param request_fn: Function that executes the actual request
        :type request_fn: Callable[[], Tuple[Dict[str, Any], Dict[str, Any]]]
        :param pending_requests: List to track pending requests for cancellation
        :type pending_requests: List[Any]
        :return: Tuple of (response_body, response_headers)
        :rtype: Tuple[Dict[str, Any], Dict[str, Any]]
        """
        pass


class DisabledStrategy(AvailabilityStrategy):
    """Strategy that disables request hedging.

    This strategy executes requests directly without any hedging or retries.
    It can be used to disable hedging for specific requests when a client
    has a default hedging strategy configured.

    Example:
        ```python
        # Disable hedging for a specific request
        items = container.read_all_items(
            availability_strategy=DisabledStrategy()
        )
        ```
    """

    @property
    def max_hedged_requests(self) -> int:
        """Maximum number of concurrent hedged requests allowed.

        :return: Always returns 1 as hedging is disabled
        :rtype: int
        """
        return 1

    def execute_request(
        self,
        request_fn: Callable[[], Tuple[Dict[str, Any], Dict[str, Any]]],
        pending_requests: List[Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Execute a request without hedging.

        :param request_fn: Function that executes the actual request
        :type request_fn: Callable[[], Tuple[Dict[str, Any], Dict[str, Any]]]
        :param pending_requests: List to track pending requests for cancellation
        :type pending_requests: List[Any]
        :return: Tuple of (response_body, response_headers)
        :rtype: Tuple[Dict[str, Any], Dict[str, Any]]
        """
        return request_fn()


class CrossRegionHedgingStrategy(AvailabilityStrategy):
    """Strategy that implements cross-region request hedging.

    This strategy improves tail latency by sending duplicate requests to other regions
    after configured time thresholds. When the first successful response arrives,
    any pending requests are cancelled.

    The hedging thresholds are calculated as:
    threshold * (1 + step) for each step in threshold_steps

    For example, with threshold=100ms and steps=[0.5, 1.0, 2.0]:
    - Original request sent at t=0
    - Second request at t=50ms (100ms * 0.5)  
    - Third request at t=100ms (100ms * 1.0)
    - Fourth request at t=200ms (100ms * 2.0)

    The maximum number of concurrent requests is capped at 4.

    :param threshold: Base threshold before sending hedged requests
    :type threshold: timedelta
    :param threshold_steps: List of multipliers for calculating progressive thresholds
    :type threshold_steps: List[float]
    :raises ValueError: If threshold is negative or threshold_steps is invalid
    """

    def __init__(self, threshold: timedelta, threshold_steps: List[float]) -> None:
        """Initialize the cross-region hedging strategy.

        :param threshold: Base threshold before sending hedged requests
        :type threshold: timedelta
        :param threshold_steps: List of multipliers for calculating progressive thresholds
        :type threshold_steps: List[float]
        :raises ValueError: If threshold is negative or threshold_steps is invalid
        """
        if threshold.total_seconds() < 0:
            raise ValueError("Threshold must be non-negative")
        if not threshold_steps:
            raise ValueError("Must provide at least one threshold step")
        if any(step < 0 for step in threshold_steps):
            raise ValueError("Threshold steps must be non-negative")

        self._threshold = threshold
        # Cap number of steps to maintain max_hedged_requests limit
        self._threshold_steps = threshold_steps[:4]  
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate the strategy configuration."""
        if not self._threshold_steps:
            raise ValueError("Must provide at least one threshold step")
        if len(self._threshold_steps) > self.max_hedged_requests:
            self._threshold_steps = self._threshold_steps[:self.max_hedged_requests]

    @property
    def max_hedged_requests(self) -> int:
        """Maximum number of concurrent hedged requests allowed.

        :return: Maximum number of hedged requests (4)
        :rtype: int
        """
        return 4

    @property
    def threshold(self) -> timedelta:
        """Get the base threshold before sending hedged requests.

        :return: Base threshold
        :rtype: timedelta
        """
        return self._threshold

    @property
    def threshold_steps(self) -> List[float]:
        """Get the list of threshold step multipliers.

        :return: List of threshold steps
        :rtype: List[float]
        """
        return self._threshold_steps.copy()

    def execute_request(
        self,
        request_fn: Callable[[], Tuple[Dict[str, Any], Dict[str, Any]]],
        pending_requests: List[Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Execute a request with cross-region hedging.

        :param request_fn: Function that executes the actual request
        :type request_fn: Callable[[], Tuple[Dict[str, Any], Dict[str, Any]]]
        :param pending_requests: List to track pending requests for cancellation
        :type pending_requests: List[Any]
        :return: Tuple of (response_body, response_headers)
        :rtype: Tuple[Dict[str, Any], Dict[str, Any]]
        """
        # Request execution is handled by _synchronized_request.py which:
        # 1. Creates copies of the request for hedging
        # 2. Executes requests in parallel with appropriate delays
        # 3. Cancels pending requests when first response arrives
        # 4. Cleans up resources
        return request_fn()