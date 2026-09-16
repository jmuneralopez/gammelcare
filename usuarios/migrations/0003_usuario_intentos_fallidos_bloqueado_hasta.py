# Generated manually — bloqueo de cuenta por intentos fallidos de inicio de sesión

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0002_remove_usuario_rol_usuario_roles_alter_rol_nombre'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='intentos_fallidos',
            field=models.PositiveIntegerField(default=0, verbose_name='Intentos fallidos de inicio de sesión'),
        ),
        migrations.AddField(
            model_name='usuario',
            name='bloqueado_hasta',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Bloqueado hasta'),
        ),
    ]
