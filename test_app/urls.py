from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "test-url/<version>/<uuid>",
        TemplateView.as_view(),
        name="enkelvoudiginformatieobject-detail",
    ),
    path(
        "test-url/<version>/<uuid>/download/",
        TemplateView.as_view(),
        name="enkelvoudiginformatieobject-download",
    ),
    path(
        "test-url2/<version>/<uuid>",
        TemplateView.as_view(),
        name="objectinformatieobject-detail",
    ),
    path("ref/", include("vng_api_common.notifications.urls")),
]
