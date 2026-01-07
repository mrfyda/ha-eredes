"""Exceptions for the E-REDES API client."""


class ERedesError(Exception):
    """Base exception for E-REDES API errors."""


class ERedesAuthenticationError(ERedesError):
    """Exception raised when authentication fails."""


class ERedesConnectionError(ERedesError):
    """Exception raised when connection to E-REDES fails."""
