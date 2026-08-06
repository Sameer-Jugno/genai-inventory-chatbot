variable "project_name" {
  description = "Name of the project used for naming AWS resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)."
  type        = string
}

variable "data_access_principal_arns" {
  description = "IAM principal ARNs allowed to read/write the collection (Lambda + ECS task roles + optional bootstrap user)."
  type        = list(string)
  default     = []
}

variable "common_tags" {
  description = "Common tags applied to all supported AWS resources."
  type        = map(string)
  default     = {}
}
