# Generated by Django 2.2.10 on 2020-08-03 07:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drc_cmis", "0006_cmisconfig_binding"),
    ]

    operations = [
        migrations.AddField(
            model_name="cmisconfig",
            name="time_zone",
            field=models.CharField(
                default="UTC",
                help_text="The time zone of the DMS. Only needed when using Browser binding.",
                max_length=200,
            ),
        ),
    ]
