# Generated by Django 2.2 on 2019-04-19 08:29

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="EnkelvoudigInformatieObject",
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
                ("uuid", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("identificatie", models.CharField(default=uuid.uuid4, max_length=40)),
                ("bronorganisatie", models.CharField(max_length=9)),
                ("creatiedatum", models.DateField()),
                ("titel", models.CharField(max_length=200)),
                ("vertrouwelijkheidaanduiding", models.CharField(max_length=200)),
                ("auteur", models.CharField(max_length=200)),
                ("status", models.CharField(max_length=20)),
                ("beschrijving", models.TextField(max_length=1000)),
                ("ontvangstdatum", models.DateField(blank=True, null=True)),
                ("verzenddatum", models.DateField(blank=True, null=True)),
                ("indicatie_gebruiksrecht", models.NullBooleanField(default=None)),
                ("ondertekening_soort", models.CharField(blank=True, max_length=10)),
                ("ondertekening_datum", models.DateField(blank=True, null=True)),
                ("informatieobjecttype", models.URLField()),
                ("formaat", models.CharField(blank=True, max_length=255)),
                ("taal", models.CharField(blank=True, max_length=255)),
                ("bestandsnaam", models.CharField(blank=True, max_length=255)),
                ("inhoud", models.FileField(upload_to="uploads/%Y/%m/")),
                ("link", models.URLField(blank=True)),
                ("integriteit_algoritme", models.CharField(blank=True, max_length=20)),
                ("integriteit_waarde", models.CharField(blank=True, max_length=128)),
                ("integriteit_datum", models.DateField(blank=True, null=True)),
            ],
        ),
    ]
