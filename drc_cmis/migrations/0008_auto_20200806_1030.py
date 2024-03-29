# Generated by Django 2.2.10 on 2020-08-06 10:30

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("drc_cmis", "0007_cmisconfig_time_zone"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cmisconfig",
            name="base_folder_name",
            field=models.CharField(
                default="Zaken",
                help_text="Name of the DMS base folder in which the documents will be stored.",
                max_length=200,
            ),
        ),
    ]
