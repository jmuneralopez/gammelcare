from django.db import models
from django.contrib.auth.models import AbstractUser
from hogares.models import Hogar


class Rol(models.Model):
    SUPERADMIN = 'superadmin'
    ADMINISTRADOR = 'administrador'
    MEDICO = 'medico'
    ENFERMERO = 'enfermero'
    FISIOTERAPEUTA = 'fisioterapeuta'
    NUTRICIONISTA = 'nutricionista'
    PSICOLOGO = 'psicologo'
    TRABAJO_SOCIAL = 'trabajo_social'
    TERAPEUTA_OCUPACIONAL = 'terapeuta_ocupacional'

    ROLES = [
        (SUPERADMIN, 'Superadministrador'),
        (ADMINISTRADOR, 'Administrador del Hogar'),
        (MEDICO, 'Médico'),
        (ENFERMERO, 'Enfermero/a'),
        (FISIOTERAPEUTA, 'Fisioterapeuta'),
        (NUTRICIONISTA, 'Nutricionista'),
        (PSICOLOGO, 'Psicólogo/a'),
        (TRABAJO_SOCIAL, 'Trabajador/a Social'),
        (TERAPEUTA_OCUPACIONAL, 'Terapeuta Ocupacional'),
    ]

    ROLES_CLINICOS = [
        MEDICO, ENFERMERO, FISIOTERAPEUTA,
        NUTRICIONISTA, PSICOLOGO, TRABAJO_SOCIAL,
        TERAPEUTA_OCUPACIONAL
    ]

    ROLES_EXPORTACION = [SUPERADMIN, ADMINISTRADOR, MEDICO]

    NOTA_POR_ROL = {
        MEDICO: 'evolucion',
        ENFERMERO: 'enfermeria',
        FISIOTERAPEUTA: 'fisioterapia',
        NUTRICIONISTA: 'nutricion',
        PSICOLOGO: 'psicologia',
        TRABAJO_SOCIAL: 'trabajo_social',
        TERAPEUTA_OCUPACIONAL: 'terapia_ocupacional',
    }

    nombre = models.CharField(max_length=50, unique=True, choices=ROLES)
    descripcion = models.TextField(blank=True)

    class Meta:
        db_table = 'roles'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.get_nombre_display()

    def es_clinico(self):
        return self.nombre in self.ROLES_CLINICOS

    def es_administrativo(self):
        return self.nombre in [self.SUPERADMIN, self.ADMINISTRADOR]

    def puede_exportar(self):
        return self.nombre in self.ROLES_EXPORTACION


class Usuario(AbstractUser):
    roles = models.ManyToManyField(
        Rol,
        blank=True,
        related_name='usuarios',
        verbose_name='Roles'
    )
    hogar = models.ForeignKey(
        Hogar,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='usuarios'
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f'{self.get_full_name()} ({self.username})'

    def tiene_rol(self, *nombres):
        return self.roles.filter(nombre__in=nombres).exists()

    def es_clinico(self):
        return self.roles.filter(nombre__in=Rol.ROLES_CLINICOS).exists()

    def es_administrativo(self):
        return self.tiene_rol(Rol.SUPERADMIN, Rol.ADMINISTRADOR)

    def es_superadmin(self):
        return self.tiene_rol(Rol.SUPERADMIN)

    def puede_exportar(self):
        return self.roles.filter(nombre__in=Rol.ROLES_EXPORTACION).exists()

    def tipos_nota_permitidos(self):
        """Retorna lista de tipos de nota que puede crear según sus roles."""
        if self.tiene_rol(Rol.SUPERADMIN, Rol.ADMINISTRADOR):
            from notas_clinicas.models import NotaClinica
            return [t[0] for t in NotaClinica.TIPOS]
        tipos = []
        for rol in self.roles.filter(nombre__in=Rol.NOTA_POR_ROL.keys()):
            tipo = Rol.NOTA_POR_ROL.get(rol.nombre)
            if tipo and tipo not in tipos:
                tipos.append(tipo)
        return tipos

    def roles_display(self):
        return ", ".join([r.get_nombre_display() for r in self.roles.all()])