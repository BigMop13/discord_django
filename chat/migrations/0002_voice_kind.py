from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="channel",
            name="kind",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("private", "Private"),
                    ("voice", "Voice"),
                ],
                default="public",
                max_length=10,
            ),
        ),
    ]
