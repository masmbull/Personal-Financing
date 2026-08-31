"""Authentication-related exceptions raised across the app."""


class NotAuthenticated(Exception):
    """Raised when a protected route/endpoint has no valid session."""