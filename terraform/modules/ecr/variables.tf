variable "project_name" {
  description = "Name of the project used for naming AWS resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)."
  type        = string
}

variable "image_tag_mutability" {
  description = "Whether image tags can be overwritten. IMMUTABLE forces a unique tag per deployment."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be either MUTABLE or IMMUTABLE."
  }
}

# POC-only default. Production should set this to false so images are never
# destroyed implicitly along with the repository.
variable "force_delete" {
  description = "Allow the repository to be deleted while it still contains images."
  type        = bool
  default     = true
}

variable "common_tags" {
  description = "Common tags applied to all supported AWS resources."
  type        = map(string)
  default     = {}
}