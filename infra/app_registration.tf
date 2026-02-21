data "azuread_client_config" "current" {}

# Microsoft Graph service principal (well-known app ID)
data "azuread_service_principal" "msgraph" {
  client_id = "00000003-0000-0000-c000-000000000000"
}

resource "azuread_application" "semantic_folder" {
  display_name = "Semantic Folder Grounding (${var.environment})"

  required_resource_access {
    resource_app_id = data.azuread_service_principal.msgraph.client_id

    dynamic "resource_access" {
      for_each = var.graph_api_permissions
      content {
        id   = resource_access.value.id
        type = resource_access.value.type
      }
    }
  }

  owners = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "semantic_folder" {
  client_id = azuread_application.semantic_folder.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_password" "semantic_folder" {
  application_id = azuread_application.semantic_folder.id
  display_name   = "semantic-folder-${var.environment}"
  end_date       = "2027-02-21T00:00:00Z"
}
