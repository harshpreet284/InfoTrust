from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import Http404
from ninja import NinjaAPI
from ninja.errors import (
    AuthenticationError,
    AuthorizationError,
    HttpError,
    ValidationError,
)

from shared.schemas import ErrorResponse


def setup_exception_handlers(api: NinjaAPI):
    @api.exception_handler(ValidationError)
    def validation_errors(request, exc: ValidationError):
        error_messages = []
        for error in exc.errors:
            field = ".".join(str(loc) for loc in error.get("loc", []) if loc != "body")
            msg = error.get("msg", "Invalid value")
            error_messages.append(f"{field}: {msg}" if field else msg)
            
        message = " | ".join(error_messages) if error_messages else "Validation Error"
        response = ErrorResponse(message=message, error_code="VALIDATION_ERROR")
        return api.create_response(request, response.model_dump(), status=422)

    @api.exception_handler(AuthenticationError)
    def authentication_errors(request, exc: AuthenticationError):
        response = ErrorResponse(
            message=str(exc) or "Authentication failed.", 
            error_code="AUTHENTICATION_ERROR"
        )
        return api.create_response(request, response.model_dump(), status=401)

    @api.exception_handler(AuthorizationError)
    def authorization_errors(request, exc: AuthorizationError):
        response = ErrorResponse(
            message=str(exc) or "Permission denied.", 
            error_code="PERMISSION_DENIED"
        )
        return api.create_response(request, response.model_dump(), status=403)

    @api.exception_handler(HttpError)
    def http_errors(request, exc: HttpError):
        if exc.status_code == 401:
            error_code = "AUTHENTICATION_ERROR"
        elif exc.status_code == 403:
            error_code = "PERMISSION_DENIED"
        elif exc.status_code == 404:
            error_code = "NOT_FOUND"
        else:
            error_code = f"HTTP_{exc.status_code}_ERROR"
            
        response = ErrorResponse(
            message=str(exc) or "An HTTP error occurred.", 
            error_code=error_code
        )
        return api.create_response(request, response.model_dump(), status=exc.status_code)

    @api.exception_handler(Http404)
    def http_404_errors(request, exc: Http404):
        response = ErrorResponse(
            message=str(exc) or "Not found.", 
            error_code="NOT_FOUND"
        )
        return api.create_response(request, response.model_dump(), status=404)

    @api.exception_handler(ObjectDoesNotExist)
    def not_found_errors(request, exc: ObjectDoesNotExist):
        response = ErrorResponse(
            message=str(exc) or "Object does not exist.", 
            error_code="NOT_FOUND"
        )
        return api.create_response(request, response.model_dump(), status=404)

    @api.exception_handler(IntegrityError)
    def database_integrity_errors(request, exc: IntegrityError):
        response = ErrorResponse(
            message="Database integrity error.", 
            error_code="DATABASE_ERROR"
        )
        return api.create_response(request, response.model_dump(), status=409)

    @api.exception_handler(Exception)
    def unexpected_errors(request, exc: Exception):
        response = ErrorResponse(
            message="An unexpected server error occurred.", 
            error_code="INTERNAL_ERROR"
        )
        return api.create_response(request, response.model_dump(), status=500)
