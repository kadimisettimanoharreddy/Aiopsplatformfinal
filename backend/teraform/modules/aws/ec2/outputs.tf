output "instance_id" {
  value = aws_instance.main.id
}

output "instance_name" {
  value = aws_instance.main.tags["Name"]
}

output "public_ip" {
  value = aws_instance.main.public_ip
}

output "private_ip" {
  value = aws_instance.main.private_ip
}

output "public_dns" {
  value = aws_instance.main.public_dns
}

output "availability_zone" {
  value = aws_instance.main.availability_zone
}

output "security_group_id" {
  value = var.use_existing_sg ? var.security_group_id : aws_security_group.default[0].id
}

output "key_name" {
  value = aws_instance.main.key_name
}

output "ssh_command" {
  value = aws_instance.main.public_ip != "" ? "ssh -i ${local.final_key_name}.pem ubuntu@${aws_instance.main.public_ip}" : "No SSH access"
}

output "console_url" {
  value = "https://console.aws.amazon.com/ec2/v2/home?region=${data.aws_region.current.name}#InstanceDetails:instanceId=${aws_instance.main.id}"
}

output "private_key_ssm_parameter" {
  value = var.create_new_keypair ? aws_ssm_parameter.private_key[0].name : null
}