resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.resource_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "main" {
  name                = "appi-${local.resource_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
}

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
    application_insights_connection_string = azurerm_application_insights.main.connection_string
  }

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME" = "python"
    "SF_CLIENT_ID"             = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.sf_client_id.id})"
    "SF_CLIENT_SECRET"         = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.sf_client_secret.id})"
    "SF_TENANT_ID"             = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.sf_tenant_id.id})"
    "SF_DRIVE_USER"            = "alacambra@datamantics.onmicrosoft.com"
    "SF_ANTHROPIC_API_KEY"     = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.sf_anthropic_api_key.id})"
    "SF_MAX_FILE_CONTENT_BYTES" = "5242880"
    "KEY_VAULT_URI"            = azurerm_key_vault.main.vault_uri
  }

  identity {
    type = "SystemAssigned"
  }
}
