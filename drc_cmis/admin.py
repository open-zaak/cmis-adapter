from django.conf import settings
from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from solo.admin import SingletonModelAdmin

from .models import CMISConfig


@admin.register(CMISConfig)
class CMISConfigAdmin(SingletonModelAdmin):
    readonly_fields = [
        "cmis_enabled",
    ]
    fieldsets = (
        (_("General"), {"fields": ("cmis_enabled",)}),
        (
            _("Configuration"),
            {"fields": ("client_url", "binding", "time_zone", "base_folder_name")},
        ),
        (_("Credentials"), {"fields": ("client_user", "client_password",)}),
    )

    def cmis_enabled(self, obj):
        return settings.CMIS_ENABLED

    cmis_enabled.short_description = _("Enabled")
    cmis_enabled.boolean = True

    def has_change_permission(self, *args, **kwargs):
        return settings.CMIS_ENABLED
