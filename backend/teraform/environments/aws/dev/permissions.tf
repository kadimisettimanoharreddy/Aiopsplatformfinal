locals {
  department_permissions = {
    "Engineering" = {
      allowed_instance_types = ["t3.micro", "t3.small", "t3.medium", "t3.large"]
      allowed_regions = ["us-east-1", "us-west-2", "ap-south-1"]
      max_storage_gb = 50
    }
    "DataScience" = {
      allowed_instance_types = ["t3.medium", "t3.large", "t3.xlarge"]
      allowed_regions = ["us-east-1", "ap-south-1"]
      max_storage_gb = 100
    }
    "DevOps" = {
      allowed_instance_types = ["t3.micro", "t3.small", "t3.medium", "t3.large", "m5.large"]
      allowed_regions = ["us-east-1", "us-west-2", "ap-south-1", "eu-west-1"]
      max_storage_gb = 100
    }
    "Finance" = {
      allowed_instance_types = ["t3.micro"]
      allowed_regions = ["us-east-1"]
      max_storage_gb = 50
    }
    "Marketing" = {
      allowed_instance_types = ["t3.micro", "t3.small"]
      allowed_regions = ["us-east-1"]
      max_storage_gb = 100
    }
    "HR" = {
      allowed_instance_types = ["t3.micro"]
      allowed_regions = ["us-east-1"]
      max_storage_gb = 30
    }
    "unknown" = {
      allowed_instance_types = ["t3.micro"]
      allowed_regions = ["us-east-1"]
      max_storage_gb = 20
    }
  }
  current_permissions = lookup(local.department_permissions, var.department, local.department_permissions["unknown"])
}

resource "null_resource" "department_validation" {
  lifecycle {
    precondition {
      condition = contains(local.current_permissions.allowed_instance_types, var.instance_type)
      error_message = "Instance type ${var.instance_type} not allowed for department ${var.department}"
    }
    precondition {
      condition = contains(local.current_permissions.allowed_regions, var.region)
      error_message = "Region ${var.region} not allowed for department ${var.department}"
    }
    precondition {
      condition = var.storage_size >= 8 && var.storage_size <= local.current_permissions.max_storage_gb
      error_message = "Storage must be between 8GB and ${local.current_permissions.max_storage_gb}GB for department ${var.department}"
    }
  }
}