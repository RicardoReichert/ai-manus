class AppException(RuntimeError):
    def __init__(
        self,
        code: int,
        msg: str,
        status_code: int = 400,
    ):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status_code = status_code


class NotFoundError(AppException):
    def __init__(self, msg: str = "Resource not found"):
        super().__init__(code=404, msg=msg, status_code=404)


class BadRequestError(AppException):
    def __init__(self, msg: str = "Bad request parameters"):
        super().__init__(code=400, msg=msg, status_code=400)


class ValidationError(AppException):
    def __init__(self, msg: str = "Validation error"):
        super().__init__(code=422, msg=msg, status_code=422)


class ServerError(AppException):
    def __init__(self, msg: str = "Internal server error"):
        super().__init__(code=500, msg=msg, status_code=500)


class UnauthorizedError(AppException):
    def __init__(self, msg: str = "Authentication required"):
        super().__init__(code=401, msg=msg, status_code=401)


class ForbiddenError(AppException):
    """The caller is authenticated but lacks permission for this action
    (e.g. a non-admin user hitting an admin-only route) — distinct from
    UnauthorizedError, which means not authenticated at all."""
    def __init__(self, msg: str = "Permission denied"):
        super().__init__(code=403, msg=msg, status_code=403)