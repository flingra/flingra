from dataclasses import dataclass


@dataclass(slots=True)
class ApiException(Exception):
    code: str
    message: str
    status_code: int = 400


class ServiceUnavailable(ApiException):
    def __init__(self, message: str) -> None:
        super().__init__("SERVICE_UNAVAILABLE", message, 503)
