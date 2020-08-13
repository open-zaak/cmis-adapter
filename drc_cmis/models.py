from django.db import models

import pytz
from djchoices import ChoiceItem, DjangoChoices
from solo.models import SingletonModel


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
        choices=BINDING_CHOICES, default="BROWSER", max_length=200,
    )
    time_zone = models.CharField(
        default="UTC",
        choices=[(k, k) for k in pytz.common_timezones],
        max_length=200,
        help_text="The time zone of the DMS. Only needed when using Browser binding.",
    )
    client_user = models.CharField(
        max_length=200, default="admin", help_text="Username for logging into DMS"
    )
    client_password = models.CharField(
        max_length=200, default="admin", help_text="Password for logging into DMS"
    )
    base_folder_name = models.CharField(
        max_length=200,
        default="",
        blank=True,
        help_text="Name of the DMS base folder in which the documents will be stored. If left empty, no "
        "base folder will be used.",
    )

    def __str__(self):
        return "CMIS Configuration"

    class Meta:
        verbose_name = "CMIS Configuration"


class Vendor(DjangoChoices):
    alfresco = ChoiceItem()
