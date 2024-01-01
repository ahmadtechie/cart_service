# Generated by Django 4.2.5 on 2023-09-28 09:19

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('cart', '0002_alter_cartitem_cart_alter_itemoptions_cart_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemoptions',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='itemoptions',
            name='modified_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='cart',
            name='user_id',
            field=models.CharField(max_length=50, null=True),
        ),
    ]
