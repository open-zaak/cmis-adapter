# Generated by Django 2.2.15 on 2020-08-21 15:12

from django.db import migrations, models

import drc_cmis.validators


class Migration(migrations.Migration):

    dependencies = [
        ("drc_cmis", "0011_auto_20200813_1640"),
    ]

    operations = [
        migrations.RemoveField(model_name="cmisconfig", name="base_folder_name",),
        migrations.AddField(
            model_name="cmisconfig",
            name="other_folder_path",
            field=models.CharField(
                default="/DRC/{{ year }}/{{ month }}/{{ day }}/",
                help_text="The path where other documents are saved.",
                max_length=500,
                validators=[drc_cmis.validators.other_folder_path_validator],
            ),
        ),
        migrations.AddField(
            model_name="cmisconfig",
            name="zaak_folder_path",
            field=models.CharField(
                default="/DRC/{{ zaaktype }}/{{ year }}/{{ month }}/{{ day }}/{{ zaak }}/",
                help_text="The path where documents related to zaken are saved.",
                max_length=500,
                validators=[drc_cmis.validators.zaak_folder_path_validator],
            ),
        ),
    ]
