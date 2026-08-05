/*
Purpose:
Creates the networking foundation for the Inventory Planner POC, including:
- VPC
- Public subnets
- Private subnet
- Internet connectivity (Internet Gateway and NAT Gateway)
- Public and private route tables

NOTE:
Single private subnet is a deliberate choice — this POC has no stated
HA/multi-AZ requirement (see SOW). Public side uses 2 AZs only because
AWS mandates it for the ALB, not for redundancy purposes here.
*/

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true  # This sets the total IP address range for your isolated cloud network. It directly pulls the value from the variable we analyzed earlier (10.0.0.0/16).
  enable_dns_hostnames = true  #This tells AWS to automatically assign clean public domain names (like ://amazonaws.com) to any resource that gets a public IP address. Your public ALB nodes will need this.

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-vpc"
    }
  )
}

locals {
  public_subnets = {
    for index, az in var.availability_zones :
    az => var.public_subnet_cidrs[index]
  }
}

resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-public-${each.key}"
    }
  )
}

# A single private subnet is intentionally used because the SOW does not
# require high availability or multi-AZ deployment for private workloads.
resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.this.id
  availability_zone = var.availability_zones[0]
  cidr_block        = var.private_subnet_cidr

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-private-${var.availability_zones[0]}"
    }
  )
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-igw"
    }
  )
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-nat-eip"
    }
  )
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id

  # NAT Gateway is intentionally placed in the same Availability Zone as the
  # private subnet so private egress traffic remains intra-AZ.
  subnet_id = aws_subnet.public[var.availability_zones[0]].id

  depends_on = [
    aws_internet_gateway.this
  ]

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-nat-gateway"
    }
  )
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-public-route-table"
    }
  )
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this.id
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-private-route-table"
    }
  )
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}
