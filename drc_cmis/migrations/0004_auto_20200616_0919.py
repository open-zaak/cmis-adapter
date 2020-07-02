# Generated by Django 2.2.10 on 2020-06-16 09:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drc_cmis", "0003_auto_20191029_1349"),
    ]

    operations = [
        migrations.RemoveField(model_name="cmisconfig", name="locations",),
        migrations.AddField(
            model_name="cmisconfig",
            name="base_folder",
            field=models.CharField(
                default="DRC",
                help_text="Name of the DMS folder in which the documents will be stored.",
                max_length=200,
            ),
        ),
        migrations.AlterField(
            model_name="cmisconfig",
            name="client_password",
            field=models.CharField(
                default="admin",
                help_text="Password for logging into DMS",
                max_length=200,
            ),
        ),
        migrations.AlterField(
            model_name="cmisconfig",
            name="client_url",
            field=models.URLField(
                default="http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
                help_text="API URL for DMS. For example, for alfresco this can be http://domain_name:port_number/alfresco/api/-default-/public/cmis/versions/1.1/browser",
            ),
        ),
        migrations.AlterField(
            model_name="cmisconfig",
            name="client_user",
            field=models.CharField(
                default="admin",
                help_text="Username for logging into DMS",
                max_length=200,
            ),
        ),
        migrations.DeleteModel(name="CMISFolderLocation",),
    ]
