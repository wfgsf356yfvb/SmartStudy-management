output "db_endpoint" {
  value = aws_db_instance.playschool.address
}

output "db_port" {
  value = aws_db_instance.playschool.port
}
