data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                       = "kv-${local.resource_prefix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  rbac_authorization_enabled = true
}

# Grant the Function App managed identity access to Key Vault secrets
resource "azurerm_role_assignment" "func_keyvault_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_function_app.main.identity[0].principal_id
}

# Grant the current deployer access to manage secrets
resource "azurerm_role_assignment" "deployer_keyvault_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Secrets populated from Terraform-managed App Registration
resource "azurerm_key_vault_secret" "sf_client_id" {
  name         = "sf-client-id"
  value        = azuread_application.semantic_folder.client_id
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_keyvault_admin]
}

resource "azurerm_key_vault_secret" "sf_client_secret" {
  name         = "sf-client-secret"
  value        = azuread_application_password.semantic_folder.value
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_keyvault_admin]
}

resource "azurerm_key_vault_secret" "sf_tenant_id" {
  name         = "sf-tenant-id"
  value        = data.azuread_client_config.current.tenant_id
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_keyvault_admin]
}
