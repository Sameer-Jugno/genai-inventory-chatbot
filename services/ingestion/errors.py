"""Domain errors that should fail ingestion and surface through the Lambda DLQ."""


class InventoryFormatError(ValueError):
    """The uploaded object is readable but not a supported inventory format."""
