# coding=utf-8
# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# Code generated by Microsoft (R) AutoRest Code Generator.
# Changes may cause incorrect behavior and will be lost if the code is regenerated.
# --------------------------------------------------------------------------

from azure.identity import DefaultAzureCredential

from azure.mgmt.apimanagement import ApiManagementClient

"""
# PREREQUISITES
    pip install azure-identity
    pip install azure-mgmt-apimanagement
# USAGE
    python api_management_create_api_with_multiple_open_id_connect_providers.py

    Before run the sample, please set the values of the client ID, tenant ID and client secret
    of the AAD application as environment variables: AZURE_CLIENT_ID, AZURE_TENANT_ID,
    AZURE_CLIENT_SECRET. For more info about how to get the value, please see:
    https://docs.microsoft.com/azure/active-directory/develop/howto-create-service-principal-portal
"""


def main():
    client = ApiManagementClient(
        credential=DefaultAzureCredential(),
        subscription_id="00000000-0000-0000-0000-000000000000",
    )

    response = client.api.begin_create_or_update(
        resource_group_name="rg1",
        service_name="apimService1",
        api_id="tempgroup",
        parameters={
            "properties": {
                "authenticationSettings": {
                    "openidAuthenticationSettings": [
                        {
                            "bearerTokenSendingMethods": ["authorizationHeader"],
                            "openidProviderId": "openidProviderId2283",
                        },
                        {
                            "bearerTokenSendingMethods": ["authorizationHeader"],
                            "openidProviderId": "openidProviderId2284",
                        },
                    ]
                },
                "description": "apidescription5200",
                "displayName": "apiname1463",
                "path": "newapiPath",
                "protocols": ["https", "http"],
                "serviceUrl": "http://newechoapi.cloudapp.net/api",
                "subscriptionKeyParameterNames": {"header": "header4520", "query": "query3037"},
            }
        },
    ).result()
    print(response)


# x-ms-original-file: specification/apimanagement/resource-manager/Microsoft.ApiManagement/stable/2024-05-01/examples/ApiManagementCreateApiWithMultipleOpenIdConnectProviders.json
if __name__ == "__main__":
    main()
