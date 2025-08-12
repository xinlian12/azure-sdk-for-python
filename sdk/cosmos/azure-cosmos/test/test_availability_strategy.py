import pytest
import time
import threading
from datetime import timedelta
from unittest.mock import Mock, patch

from azure.cosmos._availability_strategy import AvailabilityStrategy
from azure.cosmos._hedging_strategy import CrossRegionHedgingStrategy
from azure.cosmos._request_object import RequestObject
from azure.cosmos.http_constants import ResourceType

def test_cross_region_hedging_strategy_creation():
    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(seconds=1),
        threshold_steps=[0.5, 1.0, 2.0]
    )
    assert strategy.threshold == timedelta(seconds=1)
    assert strategy.threshold_steps == [0.5, 1.0, 2.0]
    assert strategy.max_hedged_requests == 3

def test_hedging_request_execution():
    # Create mock request and response
    mock_response = {"data": "test"}
    mock_headers = {"request-id": "123"}
    
    def mock_execute(*args, **kwargs):
        time.sleep(0.1)  # Simulate network delay
        return mock_response, mock_headers

    # Create strategy
    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=50),
        threshold_steps=[0.5, 1.0]
    )

    # Create request object
    request_params = RequestObject(
        ResourceType.Document,
        "Read",
        {}
    )
    request_params.availability_strategy = strategy

    # Track pending requests
    pending_requests = []

    # Execute request with hedging
    start_time = time.time()
    result = strategy.execute_request(mock_execute, pending_requests)
    end_time = time.time()

    assert result == (mock_response, mock_headers)
    assert end_time - start_time >= 0.1  # Verify minimum execution time
    assert len(pending_requests) > 0  # Verify hedged requests were created

def test_request_cancellation():
    cancelled = threading.Event()
    
    def mock_execute(*args, **kwargs):
        if not cancelled.is_set():
            time.sleep(0.2)  # Long running request
            return {"data": "slow"}, {}
        else:
            # Simulate cancelled request
            raise Exception("Request cancelled")

    def quick_execute(*args, **kwargs):
        time.sleep(0.05)  # Quick response
        cancelled.set()  # Signal to cancel other requests
        return {"data": "fast"}, {}

    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=10),
        threshold_steps=[0.5]
    )

    # Create request object
    request_params = RequestObject(
        ResourceType.Document,
        "Read",
        {}
    )
    request_params.availability_strategy = strategy

    # Track pending requests 
    pending_requests = []

    # Execute requests
    with patch('concurrent.futures.ThreadPoolExecutor') as mock_executor:
        mock_executor.return_value.submit.side_effect = [
            Mock(result=lambda: quick_execute()),
            Mock(result=lambda: mock_execute())
        ]

        result = strategy.execute_request(mock_execute, pending_requests)

    assert result[0]["data"] == "fast"  # Quick response should win
    assert len(pending_requests) > 0  # Verify requests were tracked
    assert cancelled.is_set()  # Verify cancellation was triggered

def test_invalid_strategy_config():
    with pytest.raises(ValueError):
        CrossRegionHedgingStrategy(
            threshold=timedelta(seconds=-1),  # Invalid negative threshold
            threshold_steps=[0.5, 1.0]
        )

    with pytest.raises(ValueError):
        CrossRegionHedgingStrategy(
            threshold=timedelta(seconds=1),
            threshold_steps=[]  # Empty threshold steps
        )

    with pytest.raises(ValueError):
        CrossRegionHedgingStrategy(
            threshold=timedelta(seconds=1),
            threshold_steps=[-0.5, 1.0]  # Invalid negative step
        )

def test_max_hedged_requests():
    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=10),
        threshold_steps=[0.5, 1.0, 2.0, 4.0, 8.0]  # More steps than max allowed
    )

    assert strategy.max_hedged_requests == 4  # Should be capped at max value
    assert len(strategy.threshold_steps) == 4  # Steps should be truncated

def test_hedging_with_excluded_locations():
    # Mock endpoint manager
    mock_endpoint_manager = Mock()
    mock_endpoint_manager.get_ordered_read_locations.return_value = [
        "region1",
        "region2",
        "region3",
        "region4"
    ]
    mock_endpoint_manager.DefaultEndpoint = "https://test.documents.azure.com"

    # Track called locations
    called_locations = []
    def mock_execute(*args, **kwargs):
        if 'request_params' in kwargs:
            called_locations.append(kwargs['request_params'].location_endpoint_to_route)
        time.sleep(0.05)
        return {"data": "test"}, {}

    # Create strategy
    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=10),
        threshold_steps=[0.5, 1.0]
    )

    # Create request object with excluded locations
    request_params = RequestObject(
        ResourceType.Document,
        "Read",
        {}
    )
    request_params.availability_strategy = strategy
    request_params.excluded_locations = ["region2", "region4"]

    # Execute request with hedging
    pending_requests = []
    result = strategy.execute_request(
        mock_execute,
        pending_requests,
        global_endpoint_manager=mock_endpoint_manager,
        request_params=request_params
    )

    # Verify only non-excluded locations were used
    assert all(loc not in ["region2", "region4"] for loc in called_locations)
    assert len(called_locations) > 0

def test_hedging_with_all_locations_excluded():
    # Mock endpoint manager with all locations excluded
    mock_endpoint_manager = Mock()
    mock_endpoint_manager.get_ordered_read_locations.return_value = [
        "region1",
        "region2"
    ]
    mock_endpoint_manager.DefaultEndpoint = "https://test.documents.azure.com"

    def mock_execute(*args, **kwargs):
        time.sleep(0.05)
        return {"data": "test"}, {}

    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=10),
        threshold_steps=[0.5]
    )

    # Create request object excluding all locations
    request_params = RequestObject(
        ResourceType.Document,
        "Read",
        {}
    )
    request_params.availability_strategy = strategy
    request_params.excluded_locations = ["region1", "region2"]

    # Verify hedging is skipped when all locations are excluded
    pending_requests = []
    with pytest.raises(ValueError, match="No available locations"):
        strategy.execute_request(
            mock_execute,
            pending_requests,
            global_endpoint_manager=mock_endpoint_manager,
            request_params=request_params
        )

def test_hedging_location_error_handling():
    # Mock endpoint manager
    mock_endpoint_manager = Mock()
    mock_endpoint_manager.get_ordered_read_locations.return_value = [
        "region1",
        "region2",
        "region3"
    ]
    mock_endpoint_manager.DefaultEndpoint = "https://test.documents.azure.com"

    def mock_execute(*args, **kwargs):
        if 'request_params' in kwargs:
            if kwargs['request_params'].location_endpoint_to_route.endswith("region1"):
                raise Exception("Region1 failed")
            elif kwargs['request_params'].location_endpoint_to_route.endswith("region2"):
                time.sleep(0.05)
                return {"data": "region2"}, {}
        return {"data": "default"}, {}

    strategy = CrossRegionHedgingStrategy(
        threshold=timedelta(milliseconds=10),
        threshold_steps=[0.5]
    )

    # Create request object
    request_params = RequestObject(
        ResourceType.Document,
        "Read",
        {}
    )
    request_params.availability_strategy = strategy
    request_params.excluded_locations = ["region3"]

    # Execute request with hedging
    pending_requests = []
    result = strategy.execute_request(
        mock_execute,
        pending_requests,
        global_endpoint_manager=mock_endpoint_manager,
        request_params=request_params
    )

    # Verify we got result from region2 despite region1 failure
    assert result[0]["data"] == "region2"