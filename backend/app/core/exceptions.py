from dataclasses import dataclass


@dataclass
class DomainError(Exception):
    code: str
    message: str
    details: dict | None = None
    status_code: int = 400


class InfraError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class NotFoundError(DomainError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(code="NOT_FOUND", message=message, details=details, status_code=404)
