terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}
provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Environment = "qa"
      Project     = "aiops-platform"
      ManagedBy   = "terraform"
    }
  }
}
module "ec2_instance" {
  source = "../../../modules/aws/ec2"
  request_id          = var.request_id
  department          = var.department
  created_by          = var.created_by
  environment         = var.environment
  ami_filter          = var.ami_filter
  ami_owners          = var.ami_owners
  instance_type       = var.instance_type
  key_name            = var.key_name
  create_new_keypair  = var.create_new_keypair
  storage_size        = var.storage_size
  associate_public_ip = var.associate_public_ip
  use_existing_vpc    = var.use_existing_vpc
  vpc_id              = var.vpc_id
  use_existing_subnet = var.use_existing_subnet
  subnet_id           = var.subnet_id
  use_existing_sg     = var.use_existing_sg
  security_group_id   = var.security_group_id
  instance_tags       = var.instance_tags
}