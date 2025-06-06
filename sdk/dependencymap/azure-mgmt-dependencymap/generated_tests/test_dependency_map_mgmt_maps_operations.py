# coding=utf-8
# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# Code generated by Microsoft (R) Python Code Generator.
# Changes may cause incorrect behavior and will be lost if the code is regenerated.
# --------------------------------------------------------------------------
import pytest
from azure.mgmt.dependencymap import DependencyMapMgmtClient

from devtools_testutils import AzureMgmtRecordedTestCase, RandomNameResourceGroupPreparer, recorded_by_proxy

AZURE_LOCATION = "eastus"


@pytest.mark.skip("you may need to update the auto-generated test case before run it")
class TestDependencyMapMgmtMapsOperations(AzureMgmtRecordedTestCase):
    def setup_method(self, method):
        self.client = self.create_mgmt_client(DependencyMapMgmtClient)

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_get(self, resource_group):
        response = self.client.maps.get(
            resource_group_name=resource_group.name,
            map_name="str",
        )

        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_begin_create_or_update(self, resource_group):
        response = self.client.maps.begin_create_or_update(
            resource_group_name=resource_group.name,
            map_name="str",
            resource={
                "location": "str",
                "id": "str",
                "name": "str",
                "properties": {"provisioningState": "str"},
                "systemData": {
                    "createdAt": "2020-02-20 00:00:00",
                    "createdBy": "str",
                    "createdByType": "str",
                    "lastModifiedAt": "2020-02-20 00:00:00",
                    "lastModifiedBy": "str",
                    "lastModifiedByType": "str",
                },
                "tags": {"str": "str"},
                "type": "str",
            },
        ).result()  # call '.result()' to poll until service return final result

        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_begin_update(self, resource_group):
        response = self.client.maps.begin_update(
            resource_group_name=resource_group.name,
            map_name="str",
            properties={"tags": {"str": "str"}},
        ).result()  # call '.result()' to poll until service return final result

        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_begin_delete(self, resource_group):
        response = self.client.maps.begin_delete(
            resource_group_name=resource_group.name,
            map_name="str",
        ).result()  # call '.result()' to poll until service return final result

        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_list_by_resource_group(self, resource_group):
        response = self.client.maps.list_by_resource_group(
            resource_group_name=resource_group.name,
        )
        result = [r for r in response]
        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_list_by_subscription(self, resource_group):
        response = self.client.maps.list_by_subscription()
        result = [r for r in response]
        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_begin_get_dependency_view_for_focused_machine(self, resource_group):
        response = self.client.maps.begin_get_dependency_view_for_focused_machine(
            resource_group_name=resource_group.name,
            map_name="str",
            body={
                "focusedMachineId": "str",
                "filters": {
                    "dateTime": {"endDateTimeUtc": "2020-02-20 00:00:00", "startDateTimeUtc": "2020-02-20 00:00:00"},
                    "processNameFilter": {"operator": "str", "processNames": ["str"]},
                },
            },
        ).result()  # call '.result()' to poll until service return final result

        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_begin_get_connections_with_connected_machine_for_focused_machine(self, resource_group):
        response = self.client.maps.begin_get_connections_with_connected_machine_for_focused_machine(
            resource_group_name=resource_group.name,
            map_name="str",
            body={
                "connectedMachineId": "str",
                "focusedMachineId": "str",
                "filters": {
                    "dateTime": {"endDateTimeUtc": "2020-02-20 00:00:00", "startDateTimeUtc": "2020-02-20 00:00:00"},
                    "processNameFilter": {"operator": "str", "processNames": ["str"]},
                },
            },
        ).result()  # call '.result()' to poll until service return final result

        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_begin_get_connections_for_process_on_focused_machine(self, resource_group):
        response = self.client.maps.begin_get_connections_for_process_on_focused_machine(
            resource_group_name=resource_group.name,
            map_name="str",
            body={
                "focusedMachineId": "str",
                "processIdOnFocusedMachine": "str",
                "filters": {
                    "dateTime": {"endDateTimeUtc": "2020-02-20 00:00:00", "startDateTimeUtc": "2020-02-20 00:00:00"},
                    "processNameFilter": {"operator": "str", "processNames": ["str"]},
                },
            },
        ).result()  # call '.result()' to poll until service return final result

        # please add some check logic here by yourself
        # ...

    @RandomNameResourceGroupPreparer(location=AZURE_LOCATION)
    @recorded_by_proxy
    def test_maps_begin_export_dependencies(self, resource_group):
        response = self.client.maps.begin_export_dependencies(
            resource_group_name=resource_group.name,
            map_name="str",
            body={
                "focusedMachineId": "str",
                "filters": {
                    "dateTime": {"endDateTimeUtc": "2020-02-20 00:00:00", "startDateTimeUtc": "2020-02-20 00:00:00"},
                    "processNameFilter": {"operator": "str", "processNames": ["str"]},
                },
            },
        ).result()  # call '.result()' to poll until service return final result

        # please add some check logic here by yourself
        # ...
