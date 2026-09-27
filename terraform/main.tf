terraform {
  required_version = ">= 1.6"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
}

provider "aws" { region = var.region }

# One VPC, one private subnet for the sandbox host, one public subnet for the proxy.
resource "aws_vpc" "warden" { cidr_block = "10.42.0.0/16" }

resource "aws_subnet" "proxy"   { vpc_id = aws_vpc.warden.id  cidr_block = "10.42.1.0/24"  map_public_ip_on_launch = true }
resource "aws_subnet" "sandbox" { vpc_id = aws_vpc.warden.id  cidr_block = "10.42.2.0/24" }

resource "aws_internet_gateway" "igw" { vpc_id = aws_vpc.warden.id }

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.warden.id
  route { cidr_block = "0.0.0.0/0"  gateway_id = aws_internet_gateway.igw.id }
}
resource "aws_route_table_association" "proxy" { subnet_id = aws_subnet.proxy.id  route_table_id = aws_route_table.public.id }
# NOTE: the sandbox subnet deliberately has NO route to the IGW and NO NAT gateway.

# Security groups are the second enforcement layer. Even if the sandbox subnet gained a
# route, the SG only permits egress to the proxy SG on 3128.
resource "aws_security_group" "proxy" {
  name   = "warden-proxy"
  vpc_id = aws_vpc.warden.id
  egress { from_port = 443  to_port = 443  protocol = "tcp"  cidr_blocks = ["0.0.0.0/0"] }
  egress { from_port = 80   to_port = 80   protocol = "tcp"  cidr_blocks = ["0.0.0.0/0"] }
  egress { from_port = 53   to_port = 53   protocol = "udp"  cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_security_group_rule" "proxy_in_from_sandbox" {
  type = "ingress"  from_port = 3128  to_port = 3128  protocol = "tcp"
  security_group_id = aws_security_group.proxy.id
  source_security_group_id = aws_security_group.sandbox.id
}

resource "aws_security_group" "sandbox" {
  name   = "warden-sandbox"
  vpc_id = aws_vpc.warden.id
  # Egress ONLY to the proxy security group, ONLY on 3128. No DNS, no direct 443.
  egress {
    from_port = 3128  to_port = 3128  protocol = "tcp"
    security_groups = [aws_security_group.proxy.id]
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
  filter { name = "name"  values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"] }
}

resource "aws_instance" "proxy" {
  ami = data.aws_ami.ubuntu.id  instance_type = var.instance_type
  subnet_id = aws_subnet.proxy.id  vpc_security_group_ids = [aws_security_group.proxy.id]
  user_data = file("${path.module}/userdata-proxy.sh")
  tags = { Name = "warden-proxy" }
}

resource "aws_instance" "sandbox" {
  ami = data.aws_ami.ubuntu.id  instance_type = var.instance_type
  subnet_id = aws_subnet.sandbox.id  vpc_security_group_ids = [aws_security_group.sandbox.id]
  user_data = templatefile("${path.module}/userdata-sandbox.sh", { proxy_ip = aws_instance.proxy.private_ip })
  metadata_options { http_tokens = "required"  http_endpoint = "disabled" }  # close IMDS temptation at the host too
  tags = { Name = "warden-sandbox" }
}
