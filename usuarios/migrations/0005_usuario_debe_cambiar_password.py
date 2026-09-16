# Generated manually — campo para forzar el cambio de contraseña en el
# próximo inicio de sesión (usado por el restablecimiento de contraseña
# hecho por un administrador).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0004_rol_jefe_enfermeria_y_flags_superadmin'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='debe_cambiar_password',
            field=models.BooleanField(default=False, verbose_name='Debe cambiar la contraseña en el próximo inicio de sesión'),
        ),
    ]
