from django.db import models

from solo.models import SingletonModel


class CMISConfig(SingletonModel):
    client_url = models.URLField(
        default="http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
        help_text="API URL for DMS. For example, for alfresco this can be "
        "http://domain_name:port_number/alfresco/api/-default-/public/cmis/versions/1.1/browser",
    )
    client_user = models.CharField(
        max_length=200, default="admin", help_text="Username for logging into DMS",
    )
    client_password = models.CharField(
        max_length=200, default="admin", help_text="Password for logging into DMS"
    )
    base_folder = models.CharField(
        max_length=200,
        default="DRC",
        help_text="Name of the DMS folder in which the documents will be stored.",
    )

    def __str__(self):
        return "CMIS Configuration"

    class Meta:
        verbose_name = "CMIS Configuration"
