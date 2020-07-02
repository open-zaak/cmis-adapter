# Generated by Django 2.0.13 on 2019-05-17 07:54

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CMISConfig",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "client_url",
                    models.URLField(default="http://localhost:8082/alfresco/cmisatom"),
                ),
                ("client_user", models.CharField(default="admin", max_length=200)),
                ("client_password", models.CharField(default="admin", max_length=200)),
            ],
            options={"verbose_name": "CMIS Configuration"},
        )
    ]
