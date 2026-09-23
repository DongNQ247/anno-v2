"""Stable errors at the public CLI boundary."""


class AnnoError(ValueError):
    def __init__(self, message, code="INVALID_REQUEST", details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
