from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from usuarios.decorators import administrador_requerido, clinico_requerido
from auditoria.models import RegistroAuditoria
from infraestructura.models import Cama
from .models import Residente, AsignacionCama
from .forms import ResidenteForm


def registrar_auditoria(usuario, accion, descripcion, request):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        descripcion=descripcion,
        ip_address=get_client_ip(request)
    )


@login_required
@clinico_requerido
def residente_lista(request):
    hogar = request.user.hogar
    residentes = Residente.objects.filter(hogar=hogar).order_by('-fecha_ingreso')
    lista = []
    for r in residentes:
        lista.append({
            'obj': r,
            'nombre': r.get_nombre(),
            'documento': r.get_documento(),
        })
    return render(request, 'residentes/residente_lista.html', {
        'residentes': lista
    })


@login_required
@administrador_requerido
def residente_crear(request):
    hogar = request.user.hogar
    form = ResidenteForm(request.POST or None, hogar=hogar)

    if request.method == 'POST' and form.is_valid():
        cama = form.cleaned_data['cama']

        residente = Residente(hogar=hogar, fecha_nacimiento=form.cleaned_data['fecha_nacimiento'])
        residente.set_nombre(form.cleaned_data['nombre_completo'])
        residente.set_documento(form.cleaned_data['numero_documento'])
        residente.set_contacto(form.cleaned_data['contacto_emergencia'])
        residente.cama_actual = cama
        residente.save()

        cama.estado = 'ocupada'
        cama.save()

        AsignacionCama.objects.create(
            residente=residente,
            cama=cama,
            activo=True
        )

        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.CREACION_RESIDENTE,
            descripcion=f'Registro de residente #{residente.pk} en hogar {hogar.nombre}',
            request=request
        )

        messages.success(request, 'Residente registrado correctamente.')
        return redirect('residente_lista')

    return render(request, 'residentes/residente_form.html', {
        'form': form,
        'titulo': 'Nuevo Residente',
        'accion': 'Registrar'
    })


@login_required
@clinico_requerido
def residente_detalle(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)

    registrar_auditoria(
        usuario=request.user,
        accion=RegistroAuditoria.CONSULTA_EXPEDIENTE,
        descripcion=f'Consulta de expediente del residente #{residente.pk}',
        request=request
    )

    return render(request, 'residentes/residente_detalle.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'documento': residente.get_documento(),
        'contacto': residente.get_contacto(),
        'notas': residente.notas.all().order_by('-fecha_creacion'),
        'asignaciones': residente.asignaciones.all().order_by('-fecha_inicio'),
    })


@login_required
@administrador_requerido
def residente_editar(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    hogar = request.user.hogar

    initial = {
        'nombre_completo': residente.get_nombre(),
        'numero_documento': residente.get_documento(),
        'fecha_nacimiento': residente.fecha_nacimiento,
        'contacto_emergencia': residente.get_contacto(),
        'cama': residente.cama_actual,
    }

    form = ResidenteForm(request.POST or None, hogar=hogar, initial=initial)

    if request.method == 'POST' and form.is_valid():
        residente.set_nombre(form.cleaned_data['nombre_completo'])
        residente.set_documento(form.cleaned_data['numero_documento'])
        residente.set_contacto(form.cleaned_data['contacto_emergencia'])
        residente.fecha_nacimiento = form.cleaned_data['fecha_nacimiento']

        nueva_cama = form.cleaned_data['cama']
        if nueva_cama != residente.cama_actual:
            if residente.cama_actual:
                residente.cama_actual.estado = 'disponible'
                residente.cama_actual.save()
                AsignacionCama.objects.filter(
                    residente=residente, activo=True
                ).update(fecha_fin=timezone.now(), activo=False)

            nueva_cama.estado = 'ocupada'
            nueva_cama.save()
            residente.cama_actual = nueva_cama
            AsignacionCama.objects.create(
                residente=residente,
                cama=nueva_cama,
                activo=True
            )

        residente.save()
        messages.success(request, 'Residente actualizado correctamente.')
        return redirect('residente_lista')

    return render(request, 'residentes/residente_form.html', {
        'form': form,
        'titulo': 'Editar Residente',
        'accion': 'Guardar cambios'
    })


@login_required
@administrador_requerido
def residente_desactivar(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    residente.activo = not residente.activo

    if not residente.activo and residente.cama_actual:
        residente.cama_actual.estado = 'disponible'
        residente.cama_actual.save()
        AsignacionCama.objects.filter(
            residente=residente, activo=True
        ).update(fecha_fin=timezone.now(), activo=False)
        residente.cama_actual = None

    residente.save()
    estado = 'activado' if residente.activo else 'dado de alta'
    messages.success(request, f'Residente {estado} correctamente.')
    return redirect('residente_lista')