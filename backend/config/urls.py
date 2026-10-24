"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from django.views.generic.base import RedirectView
from ninja import NinjaAPI

from authentication.api import router as auth_router
from claims.api import router as claims_router, admin_router
from shared.exception_handlers import setup_exception_handlers

api = NinjaAPI(
    title="InfoTrust API",
    version="1.0.0",
    description="InfoTrust — AI-Powered Misinformation Detection & Claim Analysis Platform REST API",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

api.add_router("/auth", auth_router)
api.add_router("/claims", claims_router)
api.add_router("/admin", admin_router)

setup_exception_handlers(api)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/docs/", RedirectView.as_view(url="/api/v1/docs", permanent=False)),
    path("api/v1/", api.urls),
    path("api/docs", RedirectView.as_view(url="/api/v1/docs", permanent=False)),
    path("api/docs/", RedirectView.as_view(url="/api/v1/docs", permanent=False)),
    path("api/openapi.json", RedirectView.as_view(url="/api/v1/openapi.json", permanent=False)),
]
