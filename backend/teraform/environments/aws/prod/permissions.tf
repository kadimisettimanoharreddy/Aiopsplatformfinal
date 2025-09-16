locals {
  department_permissions = {
    "Engineering" = {
      allowed_instance_types = []
      allowed_regions = []
      max_storage_gb = 0
    }
    "DataScience" = {
      allowed_instance_types = []
      allowed_regions = []
      max_storage_gb = 0
    }
    "DevOps" = {
      allowed_instance_types = ["t3.medium", "t3.large", "m5.large"]
      allowed_regions = ["us-east-1"]
      max_storage_gb = 100
    }
    "Finance" = {
      allowed_instance_types = []
      allowed_regions = []
      max_storage_gb = 0
    }
    "Marketing" = {
      allowed_instance_types = []
      allowed_regions = []
      max_storage_gb = 0
    }
    "HR" = {
      allowed_instance_types = []
      allowed_regions = []
      max_storage_gb = 0
    }
    "unknown" = {
      allowed_instance_types = []
      allowed_regions = []
      max_storage_gb = 0
    }
  }
  current_permissions = lookup(local.department_permissions, var.department, local.department_permissions["unknown"])
}

resource "null_resource" "department_validation" {
  lifecycle {
    precondition {
      condition = length(local.current_permissions.allowed_instance_types) > 0
      error_message = "Department ${var.department} not allowed in PRODUCTION environment"
    }
    precondition {
      condition = contains(local.current_permissions.allowed_instance_types, var.instance_type)
      error_message = "Instance type ${var.instance_type} not allowed for department ${var.department} in PRODUCTION"
    }
    precondition {
      condition = contains(local.current_permissions.allowed_regions, var.region)
      error_message = "Region ${var.region} not allowed for department ${var.department} in PRODUCTION"
    }
    precondition {
      condition = var.storage_size >= 8 && var.storage_size <= local.current_permissions.max_storage_gb
      error_message = "Storage must be between 8GB and ${local.current_permissions.max_storage_gb}GB for department ${var.department} in PRODUCTION"
    }
    precondition {
      condition = var.department != "unknown"
      error_message = "Production deployments require valid department identification"
    }
  }
}