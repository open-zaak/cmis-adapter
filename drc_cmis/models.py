import re

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.translation import gettext_lazy as _

import pytz
from djchoices import ChoiceItem, DjangoChoices
from solo.models import SingletonModel

from .utils.exceptions import NoOtherBaseFolderException, NoZaakBaseFolderException
from .utils.folder import get_folder_structure
from .validators import (
    other_folder_path_validator,
    url_mapping_validator,
    verzoek_folder_path_validator,
    zaak_folder_path_validator,
)


class CMISConfig(SingletonModel):
    BINDING_CHOICES = [
        ("BROWSER", "Browser binding (CMIS 1.1)"),
        ("WEBSERVICE", "Web service binding (CMIS 1.0)"),
    ]

    client_url = models.URLField(
        default="http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
        help_text="API URL for DMS. For example, for alfresco this can be "
        "http://domain_name:port_number/alfresco/api/-default-/public/cmis/versions/1.1/browser",
    )
    binding = models.CharField(
        choices=BINDING_CHOICES,
        default="BROWSER",
        max_length=200,
    )
    time_zone = models.CharField(
        default="UTC",
        choices=[(k, k) for k in pytz.common_timezones],
        max_length=200,
        help_text="The time zone of the DMS. Only needed when using Browser binding.",
    )
    main_repo_id = models.CharField(
        max_length=200,
        blank=True,
        help_text=_(
            "ID of the main repository in the CMS. "
            "Only needed if there are multiple repositories present and Webservice binding is used."
        ),
        verbose_name=_("Main repository ID"),
    )
    client_user = models.CharField(
        max_length=200, default="admin", help_text="Username for logging into DMS"
    )
    client_password = models.CharField(
        max_length=200, default="admin", help_text="Password for logging into DMS"
    )
    zaak_folder_path = models.CharField(
        max_length=500,
        default="/DRC/{{ zaaktype }}/{{ year }}/{{ month }}/{{ day }}/{{ zaak }}/",
        validators=[zaak_folder_path_validator],
        help_text=_("The path where documents related to zaken are saved."),
    )
    verzoek_folder_path = models.CharField(
        max_length=500,
        default="/DRC/Verzoeken/{{ year }}/{{ month }}/{{ day }}/{{ verzoek }}/",
        validators=[verzoek_folder_path_validator],
        help_text=_("The path where documents related to verzoeken are saved."),
    )
    other_folder_path = models.CharField(
        max_length=500,
        default="/DRC/{{ year }}/{{ month }}/{{ day }}/",
        validators=[other_folder_path_validator],
        help_text=_("The path where other documents are saved."),
    )

    def __str__(self):
        return "CMIS Configuration"

    class Meta:
        verbose_name = "CMIS Configuration"

    def get_zaak_base_folder_name(self) -> str:
        folders = get_folder_structure(self.zaak_folder_path)
        if len(folders) > 0:
            folder_name = re.search(r"^{{ (.+?) }}$", folders[0].folder_name)
            if folder_name is not None:
                raise NoZaakBaseFolderException("No zaak base folder in use.")
            return folders[0].folder_name
        raise ImproperlyConfigured("The 'zaak_folder_path' must be configured.")

    def get_other_base_folder_name(self) -> str:
        folders = get_folder_structure(self.other_folder_path)
        if len(folders) > 0:
            folder_name = re.search(r"^{{ (.+?) }}$", folders[0].folder_name)
            if folder_name is not None:
                raise NoOtherBaseFolderException("No other base folder in use.")
            return folders[0].folder_name
        raise ImproperlyConfigured("The 'other_folder_path' must be configured.")


class Vendor(DjangoChoices):
    alfresco = ChoiceItem()
    bct = ChoiceItem()


class UrlMapping(models.Model):
    # Cant use a URL field, because the pattern could be http://testserver, which is an invalid URL
    long_pattern = models.CharField(
        max_length=1000,
        verbose_name=_("Long pattern"),
        help_text=_(
            "Part of the URL to replace. Example: https://somedomain.nl/somesubpath"
        ),
        unique=True,
        validators=[url_mapping_validator],
    )
    short_pattern = models.CharField(
        max_length=15,
        verbose_name=_("Short pattern"),
        help_text=_(
            "Replacement string to make the URL shorter. Example: https://sd.nl"
        ),
        unique=True,
        validators=[url_mapping_validator],
    )
    config = models.ForeignKey(
        to=CMISConfig,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _("URL mapping")
        verbose_name_plural = _("URL mappings")

    def __string__(self):
        return f"{self.long_pattern}: {self.short_pattern}"
