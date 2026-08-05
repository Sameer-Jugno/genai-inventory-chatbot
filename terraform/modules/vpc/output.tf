output "vpc_id" {
  description = "The ID of the VPC."

  value = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "List of IDs for the two public subnets."

  value = [
    for az in var.availability_zones :
    aws_subnet.public[az].id
  ]
}

output "private_subnet_id" {
  description = "The ID of the private subnet."

  value = aws_subnet.private.id
}

output "vpc_cidr_block" {
  description = "The CIDR block associated with the VPC."

  value = aws_vpc.this.cidr_block
}