output "function_app_name" {
  description = "Function App name (for func azure functionapp publish)"
  value       = azurerm_linux_function_app.main.name
}

output "function_app_url" {
  description = "Function App default hostname"
  value       = "https://${azurerm_linux_function_app.main.default_hostname}"
}

output "key_vault_uri" {
  description = "Key Vault URI"
  value       = azurerm_key_vault.main.vault_uri
}

output "storage_account_name" {
  description = "Storage Account name"
  value       = azurerm_storage_account.main.name
}

output "app_registration_client_id" {
  description = "App Registration client ID for Graph API"
  value       = azuread_application.semantic_folder.client_id
}

output "storage_connection_string" {
  description = "Storage Account primary connection string"
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
}

output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.main.name
}
