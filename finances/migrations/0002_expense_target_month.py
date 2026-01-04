from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finances", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="target_month",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text="Month (1-12) when this annual expense is paid",
            ),
        ),
    ]
