# Generated by Django 2.2.10 on 2020-08-11 12:21

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("drc_cmis", "0009_auto_20200810_0830"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cmisconfig",
            name="base_folder_name",
            field=models.CharField(
                default="",
                help_text="Name of the DMS base folder in which the documents will be stored. "
                "If left empty, no base folder will be used.",
                max_length=200,
            ),
        ),
    ]
