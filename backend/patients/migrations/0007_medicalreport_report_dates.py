# Generated by Django 4.2.23 on 2025-06-20 08:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0006_rename_advice_medicalreport_advise'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicalreport',
            name='report_dates',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
