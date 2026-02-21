# Terraform Infrastructure Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                 │
│  providers.tf                          main.tf                        variables.tf              │
│  ┌───────────────────────────┐         ┌─────────────────────┐        ┌──────────────────────┐  │
│  │ terraform >= 1.5          │         │ locals {             │        │ var.subscription_id  │  │
│  │ azurerm ~> 4.0            │         │   resource_prefix =  │◀───────│ var.project_name     │  │
│  │ azuread ~> 3.0            │         │   "semfolder-dev"   │        │ var.environment      │  │
│  │ backend "local"           │         │ }                   │        │ var.location          │  │
│  └───────────┬───────────────┘         └────────┬────────────┘        │ var.graph_api_perms  │  │
│              │                                  │                     └──────────┬───────────┘  │
│              │ authenticates                    │ naming prefix                  │              │
│              ▼                                  ▼                                │              │
│  ╔═══════════════════════════════════════════════════════════════════════════════════════════╗   │
│  ║                                                                                         ║   │
│  ║  resource_group.tf                                                                      ║   │
│  ║  ┌─────────────────────────────────────────────────────────────────────────────────────┐ ║   │
│  ║  │                     azurerm_resource_group.main                                    │ ║   │
│  ║  │                     "rg-semfolder-dev" @ germanywestcentral                        │ ║   │
│  ║  └─────────────────────────────────┬───────────────────────────────────────────────────┘ ║   │
│  ║                                    │                                                    ║   │
│  ║        ┌───────────────────────────┼───────────────────────────┐                        ║   │
│  ║        │                           │                           │                        ║   │
│  ║        ▼                           ▼                           ▼                        ║   │
│  ║  storage.tf                  function_app.tf              keyvault.tf                   ║   │
│  ║  ┌──────────────────┐        ┌──────────────────┐        ┌────────────────────────────┐ ║   │
│  ║  │ azurerm_storage  │        │ azurerm_service   │        │ azurerm_key_vault.main     │ ║   │
│  ║  │ _account.main    │        │ _plan.main        │        │ "kv-semfolder-dev"         │ ║   │
│  ║  │                  │        │ "asp-semfolder-dev"│        │                            │ ║   │
│  ║  │ "stsemfolderdev" │        │ Linux / Y1 (cons.)│        │ RBAC authorization         │ ║   │
│  ║  │ Standard / LRS   │        └────────┬──────────┘        │ soft_delete = 7d           │ ║   │
│  ║  └───────┬──────────┘                 │                   └──┬──────────┬──────────────┘ ║   │
│  ║          │                            │ service_plan_id      │          │                ║   │
│  ║          │ storage_account_name       ▼                      │          │                ║   │
│  ║          │ storage_account_access_key                        │          │                ║   │
│  ║          │                  ┌──────────────────────────┐     │          │                ║   │
│  ║          └─────────────────▶│ azurerm_linux_function   │     │          │                ║   │
│  ║                             │ _app.main                │     │          │                ║   │
│  ║                             │ "func-semfolder-dev"     │     │          │                ║   │
│  ║                             │                          │     │          │                ║   │
│  ║                             │ Python 3.12              │     │          │                ║   │
│  ║                             │ SystemAssigned Identity ─┼─────┘          │                ║   │
│  ║                             │                          │  role:         │                ║   │
│  ║                             │  app_settings:           │  KV Secrets    │                ║   │
│  ║                             │  ┌────────────────────┐  │  User          │                ║   │
│  ║                             │  │ FUNCTIONS_WORKER_  │  │                │                ║   │
│  ║                             │  │ RUNTIME = python   │  │                │                ║   │
│  ║                             │  │                    │  │                │                ║   │
│  ║                             │  │ GRAPH_CLIENT_ID    │◀─┼─── KV Ref ────┤                ║   │
│  ║                             │  │ GRAPH_CLIENT_SECRET│◀─┼─── KV Ref ────┤                ║   │
│  ║                             │  │ GRAPH_TENANT_ID    │◀─┼─── KV Ref ────┤                ║   │
│  ║                             │  │ KEY_VAULT_URI      │◀─┼─── direct ────┘                ║   │
│  ║                             │  └────────────────────┘  │                                ║   │
│  ║                             └──────────────────────────┘                                ║   │
│  ║                                                                                         ║   │
│  ╚═════════════════════════════════════════════════════════════════════════════════════════╝   │
│                                                                                                 │
│                                                                                                 │
│  keyvault.tf (continued)                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                          │   │
│  │  RBAC Role Assignments                           Secrets (placeholders)                  │   │
│  │  ┌────────────────────────────────┐              ┌────────────────────────────────────┐  │   │
│  │  │ func_keyvault_reader           │              │ graph-client-id      = "placeholder"│  │   │
│  │  │ Principal: Function App MI     │              │ graph-client-secret  = "placeholder"│  │   │
│  │  │ Role: Key Vault Secrets User   │              │ graph-tenant-id      = "placeholder"│  │   │
│  │  ├────────────────────────────────┤              │                                    │  │   │
│  │  │ deployer_keyvault_admin        │              │ ⚠ Replace after terraform apply    │  │   │
│  │  │ Principal: Current deployer    │──creates──▶  │   via az CLI or CI/CD pipeline     │  │   │
│  │  │ Role: Key Vault Secrets Officer│              └────────────────────────────────────┘  │   │
│  │  └────────────────────────────────┘                                                      │   │
│  └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                 │
│                                                                                                 │
│  app_registration.tf                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                          │   │
│  │  ┌──────────────────────────┐     ┌──────────────────────────┐                           │   │
│  │  │ data.azuread_client      │     │ data.azuread_service     │                           │   │
│  │  │ _config.current          │     │ _principal.msgraph       │                           │   │
│  │  │ (current deployer)       │     │ (Microsoft Graph SPN)    │                           │   │
│  │  └───────────┬──────────────┘     └───────────┬──────────────┘                           │   │
│  │              │ owner                          │ resource_app_id                          │   │
│  │              ▼                                ▼                                          │   │
│  │  ┌─────────────────────────────────────────────────────────────┐                         │   │
│  │  │ azuread_application.semantic_folder                         │                         │   │
│  │  │ "Semantic Folder Grounding (dev)"                          │                         │   │
│  │  │                                                            │                         │   │
│  │  │ required_resource_access (Microsoft Graph):                │                         │   │
│  │  │   • Files.ReadWrite.All  (Application / Role)              │                         │   │
│  │  │   • Sites.Read.All       (Application / Role)              │                         │   │
│  │  └────────────┬───────────────────────────────────────────────┘                         │   │
│  │               │                                                                          │   │
│  │        ┌──────┴──────┐                                                                   │   │
│  │        ▼             ▼                                                                   │   │
│  │  ┌────────────┐ ┌──────────────────────────┐                                             │   │
│  │  │ azuread_   │ │ azuread_application      │      Used at runtime by                     │   │
│  │  │ service_   │ │ _password.semantic_folder │ ──▶ Function App to call                   │   │
│  │  │ principal  │ │                           │      Microsoft Graph API                    │   │
│  │  │            │ │ expires: 2027-02-21       │      (via Key Vault secrets)                │   │
│  │  └────────────┘ └──────────────────────────┘                                             │   │
│  └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                 │
│                                                                                                 │
│  outputs.tf                                    terraform.tfvars.example                         │
│  ┌────────────────────────────────────┐        ┌───────────────────────────────┐                │
│  │ function_app_name                  │        │ subscription_id = "000...000" │                │
│  │ function_app_url                   │        │ project_name    = "semfolder" │                │
│  │ key_vault_uri                      │        │ environment     = "dev"       │                │
│  │ storage_account_name               │        │ location        = "germany.." │                │
│  │ storage_connection_string (secret) │        └───────────────────────────────┘                │
│  │ app_registration_client_id         │                                                         │
│  │ resource_group_name                │                                                         │
│  └────────────────────────────────────┘                                                         │
│                                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘


RUNTIME DATA FLOW
═════════════════

  ┌──────────┐       HTTP        ┌───────────────────┐    KV Ref     ┌────────────┐
  │  Client  │ ────────────────▶ │  Azure Function   │ ───────────▶ │  Key Vault │
  │          │                   │  (Managed Identity)│ ◀─ secrets ─ │            │
  └──────────┘                   └─────────┬─────────┘              └────────────┘
                                           │
                                           │ Graph API calls using
                                           │ client_id + client_secret + tenant_id
                                           ▼
                                 ┌───────────────────┐
                                 │  Microsoft Graph   │
                                 │  API               │
                                 │  • Files.ReadWrite │
                                 │  • Sites.Read      │
                                 └───────────────────┘
```
