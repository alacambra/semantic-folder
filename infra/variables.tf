variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "semfolder"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "germanywestcentral"
}

variable "graph_api_permissions" {
  description = "Microsoft Graph API permissions for the App Registration"
  type = list(object({
    id   = string
    type = string
  }))
  default = [
    {
      # Files.ReadWrite.All (Application)
      id   = "75359482-378d-4052-8f01-80520e7db3cd"
      type = "Role"
    },
    {
      # Sites.Read.All (Application)
      id   = "332a536c-c7ef-4017-ab91-336970924f0d"
      type = "Role"
    },
  ]
}
