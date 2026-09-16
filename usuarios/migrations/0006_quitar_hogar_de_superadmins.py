# Generated manually — corrige datos existentes: ningún usuario con el rol
# "superadmin" debe tener un hogar asignado (ver forms.py / views.py de esta
# misma app, que ahora impiden esta combinación hacia adelante). Este backfill
# limpia cuentas que ya hubieran quedado en ese estado antes del arreglo.

from django.db import migrations


def quitar_hogar_de_superadmins(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    afectados = Usuario.objects.filter(
        roles__nombre='superadmin', hogar__isnull=False
    ).distinct()
    total = 0
    for usuario in afectados:
        usuario.hogar = None
        usuario.save(update_fields=['hogar'])
        total += 1
    if total:
        print(
            f'[migración usuarios 0006] Se quitó el hogar asignado a {total} '
            'usuario(s) con rol superadmin.'
        )


def revertir_quitar_hogar_de_superadmins(apps, schema_editor):
    # No reversible de forma segura: no se guarda qué hogar tenía cada
    # usuario antes de esta limpieza. No-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_usuario_debe_cambiar_password'),
    ]

    operations = [
        migrations.RunPython(
            quitar_hogar_de_superadmins,
            revertir_quitar_hogar_de_superadmins,
        ),
    ]
