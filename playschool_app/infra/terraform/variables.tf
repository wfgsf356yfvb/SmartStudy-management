variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "db_username" {
  type = string
}

variable "db_password" {
  type = string
}

variable "db_allocated_storage" {
  type = number
  default = 20
}
