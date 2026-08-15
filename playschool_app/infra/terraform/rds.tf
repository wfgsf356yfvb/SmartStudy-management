# Minimal RDS instance scaffold. Customize for production (multi-AZ, parameter groups, subnet groups, encryption, backups).

resource "aws_db_instance" "playschool" {
  allocated_storage    = var.db_allocated_storage
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = "db.t3.micro"
  name                 = "playschool_control"
  username             = var.db_username
  password             = var.db_password
  parameter_group_name = "default.mysql8.0"
  skip_final_snapshot  = true
  publicly_accessible  = false
}
