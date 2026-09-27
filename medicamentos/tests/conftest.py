"""Fixtures compartidos por toda la suite del módulo de medicamentos.

Un hogar, un usuario por rol relevante y un residente mínimo — sin cama
ni infraestructura, porque el ciclo de vida de medicamentos no depende de
eso. Cada fixture crea lo mínimo indispensable; el resto lo arma cada test
según lo que necesite probar.
"""
from datetime import date, timedelta

import pytest

from hogares.models import Hogar
from residentes.models import Residente
from usuarios.models import Rol, Usuario
from infraestructura.models import Departamento, Habitacion, Cama
from medicamentos.models import Medicamento, Prescripcion, HorarioPrescripcion, IngresoMedicamento


def _crear_usuario(hogar, username, *roles_nombres):
    usuario = Usuario.objects.create_user(
        username=username,
        password='clave-de-prueba-123',
        hogar=hogar,
        first_name=username.replace('_', ' ').title(),
        last_name='Prueba',
    )
    for nombre in roles_nombres:
        rol, _ = Rol.objects.get_or_create(nombre=nombre)
        usuario.roles.add(rol)
    return usuario


@pytest.fixture
def hogar(db):
    return Hogar.objects.create(
        nombre='Hogar de Pruebas',
        nit='900000000-1',
        direccion='Calle Falsa 123',
    )


@pytest.fixture
def usuario_administrador(hogar):
    return _crear_usuario(hogar, 'admin_hogar', Rol.ADMINISTRADOR)


@pytest.fixture
def usuario_medico(hogar):
    return _crear_usuario(hogar, 'medico', Rol.MEDICO)


@pytest.fixture
def usuario_jefe_enfermeria(hogar):
    return _crear_usuario(hogar, 'jefe_enfermeria', Rol.JEFE_ENFERMERIA)


@pytest.fixture
def usuario_enfermero(hogar):
    return _crear_usuario(hogar, 'enfermero', Rol.ENFERMERO)


@pytest.fixture
def usuario_fisioterapeuta(hogar):
    """Rol clínico que NO debería poder registrar ni administrar
    medicamentos — sirve para probar que el módulo lo bloquea."""
    return _crear_usuario(hogar, 'fisioterapeuta', Rol.FISIOTERAPEUTA)


@pytest.fixture
def usuario_sin_hogar():
    """Usuario con rol pero sin hogar asignado — debe quedar bloqueado por
    rol_requerido() antes de llegar a cualquier vista (ver
    usuarios/decorators.py)."""
    usuario = Usuario.objects.create_user(username='sin_hogar', password='clave-de-prueba-123')
    rol, _ = Rol.objects.get_or_create(nombre=Rol.MEDICO)
    usuario.roles.add(rol)
    return usuario


@pytest.fixture
def cama(db, hogar):
    """Una cama real, para que `residente` aparezca en pantallas que
    filtran por cama_actual (atencion_lista, y la ronda por franja)."""
    departamento = Departamento.objects.create(hogar=hogar, nombre='Pabellón A')
    habitacion = Habitacion.objects.create(departamento=departamento, numero='101')
    return Cama.objects.create(habitacion=habitacion, codigo='A', estado=Cama.OCUPADA)


@pytest.fixture
def residente(db, hogar, cama):
    r = Residente(
        hogar=hogar,
        cama_actual=cama,
        fecha_nacimiento=date(1945, 3, 12),
        tipo_documento='CC',
    )
    r.set_nombre('Residente de Prueba')
    r.set_documento('123456789')
    r.set_contacto('3000000000 - Familiar de prueba')
    r.save()
    return r


@pytest.fixture
def medicamento(db):
    return Medicamento.objects.create(
        nombre_generico='Acetaminofén',
        concentracion='500 mg',
        forma_farmaceutica='tableta',
        unidad_dosificacion='tableta',
    )


@pytest.fixture
def prescripcion_horarios_fijos(db, residente, medicamento, usuario_medico):
    p = Prescripcion.objects.create(
        residente=residente,
        medicamento=medicamento,
        dosis_cantidad=1,
        dosis_unidad='tableta',
        tipo_pauta=Prescripcion.HORARIOS_FIJOS,
        fecha_inicio=date.today() - timedelta(days=1),
        formulada_por='Dr. Prueba — EPS Test',
        fecha_formula=date.today() - timedelta(days=1),
        registrada_por=usuario_medico,
    )
    HorarioPrescripcion.objects.create(prescripcion=p, hora='08:00')
    return p


@pytest.fixture
def prescripcion_prn(db, residente, medicamento, usuario_medico):
    return Prescripcion.objects.create(
        residente=residente,
        medicamento=medicamento,
        dosis_cantidad=1,
        dosis_unidad='tableta',
        tipo_pauta=Prescripcion.PRN,
        frecuencia_minima_horas=6,
        dosis_maxima_dia=4,
        fecha_inicio=date.today() - timedelta(days=1),
        formulada_por='Dr. Prueba — EPS Test',
        fecha_formula=date.today() - timedelta(days=1),
        registrada_por=usuario_medico,
    )


@pytest.fixture
def ingreso_residente(db, residente, medicamento, usuario_enfermero):
    return IngresoMedicamento.objects.create(
        residente=residente,
        medicamento=medicamento,
        lote='L-RESIDENTE-1',
        fecha_vencimiento=date.today() + timedelta(days=200),
        cantidad_ingresada=30,
        cantidad_disponible=30,
        unidad='tabletas',
        recibido_por=usuario_enfermero,
    )


@pytest.fixture
def ingreso_botiquin(db, hogar, medicamento, usuario_enfermero):
    return IngresoMedicamento.objects.create(
        hogar=hogar,
        medicamento=medicamento,
        lote='L-BOTIQUIN-1',
        fecha_vencimiento=date.today() + timedelta(days=200),
        cantidad_ingresada=20,
        cantidad_disponible=20,
        unidad='tabletas',
        recibido_por=usuario_enfermero,
    )
