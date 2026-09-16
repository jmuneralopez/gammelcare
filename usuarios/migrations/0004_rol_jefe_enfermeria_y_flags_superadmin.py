# Generated manually — nuevo rol "Jefe de Enfermería" + sincronización de
# is_staff/is_superuser para usuarios con rol superadmin (acceso a /admin/).

from django.db import migrations, models


def crear_rol_jefe_enfermeria(apps, schema_editor):
    Rol = apps.get_model('usuarios', 'Rol')
    Rol.objects.get_or_create(
        nombre='jefe_enfermeria',
        defaults={'descripcion': 'Jefe de Enfermería'},
    )


def eliminar_rol_jefe_enfermeria(apps, schema_editor):
    Rol = apps.get_model('usuarios', 'Rol')
    Rol.objects.filter(nombre='jefe_enfermeria').delete()


def backfill_flags_superadmin(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    usuarios_superadmin = Usuario.objects.filter(
        roles__nombre='superadmin'
    ).distinct()
    for usuario in usuarios_superadmin:
        actualizar = False
        if not usuario.is_staff:
            usuario.is_staff = True
            actualizar = True
        if not usuario.is_superuser:
            usuario.is_superuser = True
            actualizar = True
        if actualizar:
            usuario.save(update_fields=['is_staff', 'is_superuser'])


def revertir_backfill_flags_superadmin(apps, schema_editor):
    # No reversible de forma segura: no sabemos qué usuarios ya tenían
    # is_staff/is_superuser en True antes de este backfill. No-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0003_usuario_intentos_fallidos_bloqueado_hasta'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rol',
            name='nombre',
            field=models.CharField(choices=[('superadmin', 'Superadministrador'), ('administrador', 'Administrador del Hogar'), ('medico', 'Médico'), ('enfermero', 'Enfermero/a'), ('jefe_enfermeria', 'Jefe de Enfermería'), ('fisioterapeuta', 'Fisioterapeuta'), ('nutricionista', 'Nutricionista'), ('psicologo', 'Psicólogo/a'), ('trabajo_social', 'Trabajador/a Social'), ('terapeuta_ocupacional', 'Terapeuta Ocupacional')], max_length=50, unique=True),
        ),
        migrations.RunPython(
            crear_rol_jefe_enfermeria,
            eliminar_rol_jefe_enfermeria,
        ),
        migrations.RunPython(
            backfill_flags_superadmin,
            revertir_backfill_flags_superadmin,
        ),
    ]
