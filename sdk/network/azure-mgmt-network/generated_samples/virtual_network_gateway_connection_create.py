# pylint: disable=line-too-long,useless-suppression
# coding=utf-8
# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# Code generated by Microsoft (R) AutoRest Code Generator.
# Changes may cause incorrect behavior and will be lost if the code is regenerated.
# --------------------------------------------------------------------------

from azure.identity import DefaultAzureCredential

from azure.mgmt.network import NetworkManagementClient

"""
# PREREQUISITES
    pip install azure-identity
    pip install azure-mgmt-network
# USAGE
    python virtual_network_gateway_connection_create.py

    Before run the sample, please set the values of the client ID, tenant ID and client secret
    of the AAD application as environment variables: AZURE_CLIENT_ID, AZURE_TENANT_ID,
    AZURE_CLIENT_SECRET. For more info about how to get the value, please see:
    https://docs.microsoft.com/azure/active-directory/develop/howto-create-service-principal-portal
"""


def main():
    client = NetworkManagementClient(
        credential=DefaultAzureCredential(),
        subscription_id="subid",
    )

    response = client.virtual_network_gateway_connections.begin_create_or_update(
        resource_group_name="rg1",
        virtual_network_gateway_connection_name="connS2S",
        parameters={
            "location": "centralus",
            "properties": {
                "connectionMode": "Default",
                "connectionProtocol": "IKEv2",
                "connectionType": "IPsec",
                "dpdTimeoutSeconds": 30,
                "egressNatRules": [
                    {
                        "id": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworkGateways/vpngw/natRules/natRule2"
                    }
                ],
                "enableBgp": False,
                "gatewayCustomBgpIpAddresses": [
                    {
                        "customBgpIpAddress": "169.254.21.1",
                        "ipConfigurationId": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworkGateways/vpngw/ipConfigurations/default",
                    },
                    {
                        "customBgpIpAddress": "169.254.21.3",
                        "ipConfigurationId": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworkGateways/vpngw/ipConfigurations/ActiveActive",
                    },
                ],
                "ingressNatRules": [
                    {
                        "id": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworkGateways/vpngw/natRules/natRule1"
                    }
                ],
                "ipsecPolicies": [],
                "localNetworkGateway2": {
                    "id": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/localNetworkGateways/localgw",
                    "location": "centralus",
                    "properties": {
                        "gatewayIpAddress": "x.x.x.x",
                        "localNetworkAddressSpace": {"addressPrefixes": ["10.1.0.0/16"]},
                    },
                    "tags": {},
                },
                "routingWeight": 0,
                "sharedKey": "Abc123",
                "trafficSelectorPolicies": [],
                "tunnelProperties": [
                    {"bgpPeeringAddress": "10.78.1.17", "tunnelIpAddress": "10.78.1.5"},
                    {"bgpPeeringAddress": "10.78.1.20", "tunnelIpAddress": "10.78.1.7"},
                ],
                "usePolicyBasedTrafficSelectors": False,
                "virtualNetworkGateway1": {
                    "id": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworkGateways/vpngw",
                    "location": "centralus",
                    "properties": {
                        "activeActive": False,
                        "bgpSettings": {"asn": 65514, "bgpPeeringAddress": "10.0.1.30", "peerWeight": 0},
                        "enableBgp": False,
                        "gatewayType": "Vpn",
                        "ipConfigurations": [
                            {
                                "id": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworkGateways/vpngw/ipConfigurations/gwipconfig1",
                                "name": "gwipconfig1",
                                "properties": {
                                    "privateIPAllocationMethod": "Dynamic",
                                    "publicIPAddress": {
                                        "id": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/publicIPAddresses/gwpip"
                                    },
                                    "subnet": {
                                        "id": "/subscriptions/subid/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1/subnets/GatewaySubnet"
                                    },
                                },
                            }
                        ],
                        "sku": {"name": "VpnGw1", "tier": "VpnGw1"},
                        "vpnType": "RouteBased",
                    },
                    "tags": {},
                },
            },
        },
    ).result()
    print(response)


# x-ms-original-file: specification/network/resource-manager/Microsoft.Network/stable/2024-07-01/examples/VirtualNetworkGatewayConnectionCreate.json
if __name__ == "__main__":
    main()
