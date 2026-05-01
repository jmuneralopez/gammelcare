from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from usuarios.decorators import clinico_requerido
from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from .models import NotaClinica, NotaAclaratoria
from .forms import NotaClinicaForm, NotaAclaratoriaForm
from django.http import JsonResponse

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
def atencion_lista(request):
    hogar = request.user.hogar
    busqueda = request.GET.get('q', '').strip()

    residentes = Residente.objects.filter(
        hogar=hogar,
        activo=True,
        cama_actual__isnull=False
    ).select_related(
        'cama_actual__habitacion__departamento'
    ).order_by(
        'cama_actual__habitacion__departamento__nombre',
        'cama_actual__habitacion__numero',
        'cama_actual__codigo'
    )

    lista = []
    for r in residentes:
        nombre = r.get_nombre()
        cama = r.cama_actual.codigo if r.cama_actual else ''
        habitacion = r.cama_actual.habitacion.numero if r.cama_actual else ''

        if busqueda:
            if (busqueda.lower() in nombre.lower() or
                busqueda.lower() in cama.lower() or
                busqueda.lower() in habitacion.lower()):
                lista.append({
                    'obj': r,
                    'nombre': nombre,
                    'cama': cama,
                    'habitacion': habitacion,
                    'departamento': r.cama_actual.habitacion.departamento.nombre if r.cama_actual else '',
                })
        else:
            lista.append({
                'obj': r,
                'nombre': nombre,
                'cama': cama,
                'habitacion': habitacion,
                'departamento': r.cama_actual.habitacion.departamento.nombre if r.cama_actual else '',
            })

    return render(request, 'notas_clinicas/atencion_lista.html', {
        'residentes': lista,
        'busqueda': busqueda,
        'total': len(lista),
    })

@login_required
@clinico_requerido
def nota_crear(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    form = NotaClinicaForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        nota = form.save(commit=False)
        nota.residente = residente
        nota.autor = request.user
        nota.save()

        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.CREACION_NOTA,
            descripcion=f'Nota clínica #{nota.pk} creada para residente #{residente.pk}',
            request=request
        )

        messages.success(request, 'Nota clínica registrada correctamente.')
        return redirect('residente_detalle', pk=residente.pk)

    return render(request, 'notas_clinicas/nota_form.html', {
        'form': form,
        'residente': residente,
        'nombre': residente.get_nombre(),
    })


@login_required
@clinico_requerido
def nota_detalle(request, pk):
    nota = get_object_or_404(
        NotaClinica,
        pk=pk,
        residente__hogar=request.user.hogar
    )
    aclaraciones = nota.aclaraciones.all().order_by('fecha_creacion')

    return render(request, 'notas_clinicas/nota_detalle.html', {
        'nota': nota,
        'aclaraciones': aclaraciones,
        'nombre': nota.residente.get_nombre(),
    })


@login_required
@clinico_requerido
def aclaratoria_crear(request, pk):
    nota = get_object_or_404(
        NotaClinica,
        pk=pk,
        residente__hogar=request.user.hogar
    )
    form = NotaAclaratoriaForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        aclaratoria = form.save(commit=False)
        aclaratoria.nota_original = nota
        aclaratoria.autor = request.user
        aclaratoria.save()

        messages.success(request, 'Nota aclaratoria registrada correctamente.')
        return redirect('nota_detalle', pk=nota.pk)

    return render(request, 'notas_clinicas/aclaratoria_form.html', {
        'form': form,
        'nota': nota,
        'nombre': nota.residente.get_nombre(),
    })

from django.http import JsonResponse


@login_required
@clinico_requerido
def notas_calendario_data(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    notas = NotaClinica.objects.filter(residente=residente).values(
        'pk', 'tipo', 'fecha_creacion', 'autor__first_name', 'autor__last_name'
    )

    eventos = []
    colores = {
        'enfermeria':        '#2E75B6',
        'evolucion':         '#1F4E79',
        'fisioterapia':      '#198754',
        'nutricion':         '#fd7e14',
        'psicologia':        '#6f42c1',
        'trabajo_social':    '#0dcaf0',
        'terapia_ocupacional': '#d63384',
    }

    tipos_display = dict(NotaClinica.TIPOS)

    for nota in notas:
        autor = f"{nota['autor__first_name']} {nota['autor__last_name']}".strip()
        eventos.append({
            'id': nota['pk'],
            'title': tipos_display.get(nota['tipo'], nota['tipo']),
            'start': nota['fecha_creacion'].isoformat(),
            'color': colores.get(nota['tipo'], '#2E75B6'),
            'extendedProps': {
                'autor': autor or 'Sin nombre',
                'url': f'/notas/{nota["pk"]}/'
            }
        })

    return JsonResponse(eventos, safe=False)

@login_required
@clinico_requerido
def notas_calendario_data(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    notas = NotaClinica.objects.filter(residente=residente).values(
        'pk', 'tipo', 'fecha_creacion', 'autor__first_name', 'autor__last_name'
    )

    eventos = []
    colores = {
        'enfermeria':        '#2E75B6',
        'evolucion':         '#1F4E79',
        'fisioterapia':      '#198754',
        'nutricion':         '#fd7e14',
        'psicologia':        '#6f42c1',
        'trabajo_social':    '#0dcaf0',
        'terapia_ocupacional': '#d63384',
    }

    tipos_display = dict(NotaClinica.TIPOS)

    for nota in notas:
        autor = f"{nota['autor__first_name']} {nota['autor__last_name']}".strip()
        eventos.append({
            'id': nota['pk'],
            'title': tipos_display.get(nota['tipo'], nota['tipo']),
            'start': nota['fecha_creacion'].isoformat(),
            'color': colores.get(nota['tipo'], '#2E75B6'),
            'extendedProps': {
                'autor': autor or 'Sin nombre',
                'url': f'/notas/{nota["pk"]}/'
            }
        })

    return JsonResponse(eventos, safe=False)


@login_required
@clinico_requerido
def notas_calendario(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    return render(request, 'notas_clinicas/notas_calendario.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
    })