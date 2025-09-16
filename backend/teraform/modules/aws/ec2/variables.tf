variable "request_id" {
  type = string
}

variable "department" {
  type = string
}

variable "created_by" {
  type = string
}

variable "environment" {
  type = string
}

variable "ami_filter" {
  type    = string
  default = "ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"
}

variable "ami_owners" {
  type    = list(string)
  default = ["099720109477"]
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "key_name" {
  type = string
}

variable "create_new_keypair" {
  type    = bool
  default = false
}

variable "use_existing_vpc" {
  type    = bool
  default = false
}

variable "vpc_id" {
  type    = string
  default = ""
}

variable "use_existing_subnet" {
  type    = bool
  default = false
}

variable "subnet_id" {
  type    = string
  default = ""
}

variable "use_existing_sg" {
  type    = bool
  default = false
}

variable "security_group_id" {
  type    = string
  default = ""
}

variable "storage_size" {
  type    = number
  default = 8
}

variable "associate_public_ip" {
  type    = bool
  default = true
}

variable "instance_tags" {
  type    = map(string)
  default = {}
}