# Generated manually — nueva acción de auditoría "Restablecimiento de
# contraseña" (usuarios.views.usuario_resetear_password). Solo cambia los
# choices del campo (metadato de validación), no hay cambio de esquema.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auditoria', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registroauditoria',
            name='accion',
            field=models.CharField(choices=[('inicio_sesion', 'Inicio de sesión'), ('cierre_sesion', 'Cierre de sesión'), ('consulta_expediente', 'Consulta de expediente'), ('creacion_nota', 'Creación de nota clínica'), ('exportacion', 'Exportación de expediente'), ('creacion_residente', 'Registro de residente'), ('asignacion_cama', 'Asignación de cama'), ('reseteo_password', 'Restablecimiento de contraseña')], max_length=50),
        ),
    ]
