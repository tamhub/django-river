# Generated by Django 4.2.11 on 2024-05-07 10:31

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("river", "0003_alter_onapprovedhook_callback_function_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transitionmeta",
            name="name",
            field=models.CharField(
                blank=True, max_length=255, null=True, verbose_name="Name"
            ),
        ),
    ]
