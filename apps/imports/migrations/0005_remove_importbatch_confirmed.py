from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("imports", "0004_importbatch_confirmed"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="importbatch",
            name="confirmed",
        ),
    ]
