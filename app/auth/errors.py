"""Authentication-related exceptions raised across the app."""


class NotAuthenticated(Exception):
    """Raised when a protected route/endpoint has no valid session."""


class NotAuthorized(Exception):
    """Raised when a user lacks permission for the requested action."""