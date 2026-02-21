resource "azurerm_service_plan" "main" {
  name                = "asp-${local.resource_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1"
}

resource "azurerm_linux_function_app" "main" {
  name                = "func-${local.resource_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  storage_account_name       = azurerm_storage_account.main.name
  storage_account_access_key = azurerm_storage_account.main.primary_access_key
  service_plan_id            = azurerm_service_plan.main.id

  site_config {
    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME" = "python"
    "GRAPH_CLIENT_ID"          = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.graph_client_id.id})"
    "GRAPH_CLIENT_SECRET"      = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.graph_client_secret.id})"
    "GRAPH_TENANT_ID"          = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.graph_tenant_id.id})"
    "KEY_VAULT_URI"            = azurerm_key_vault.main.vault_uri
  }

  identity {
    type = "SystemAssigned"
  }
}
