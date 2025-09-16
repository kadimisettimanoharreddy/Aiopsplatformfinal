output "instance_id" {
  value = module.ec2_instance.instance_id
}
output "instance_name" {
  value = module.ec2_instance.instance_name
}
output "public_ip" {
  value = module.ec2_instance.public_ip
}
output "private_ip" {
  value = module.ec2_instance.private_ip
}
output "public_dns" {
  value = module.ec2_instance.public_dns
}
output "availability_zone" {
  value = module.ec2_instance.availability_zone
}
output "ssh_command" {
  value = module.ec2_instance.ssh_command
}
output "console_url" {
  value = module.ec2_instance.console_url
}
output "security_group_id" {
  value = module.ec2_instance.security_group_id
}
output "key_name" {
  value = module.ec2_instance.key_name
}
output "private_key_ssm_parameter" {
  value = module.ec2_instance.private_key_ssm_parameter
}