from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from usuarios.decorators import clinico_requerido
from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from .models import NotaClinica, NotaAclaratoria
from .forms import NotaClinicaForm, NotaAclaratoriaForm
from django.http import JsonResponse
from django.utils import timezone as dj_timezone
from urllib.parse import urlencode

def registrar_auditoria(usuario, accion, descripcion, request):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        descripcion=descripcion,
        ip_address=get_client_ip(request)
    )


def _filtrar_notas_por_querystring(queryset, request):
    """Aplica sobre `queryset` los filtros de tipo/autor/texto que lleguen por la
    URL (?tipos=a,b&autor=<id>&q=texto) y devuelve (queryset_filtrado, filtro_qs),
    donde filtro_qs es un dict listo para reconstruir esa misma querystring —
    así el mismo filtro se puede propagar de una nota a la siguiente."""
    filtro_qs = {}

    tipos_raw = request.GET.get('tipos')
    if tipos_raw is not None:
        tipos_lista = [t for t in tipos_raw.split(',') if t]
        queryset = queryset.filter(tipo__in=tipos_lista)
        filtro_qs['tipos'] = tipos_raw

    autor_id = request.GET.get('autor', '').strip()
    if autor_id:
        queryset = queryset.filter(autor_id=autor_id)
        filtro_qs['autor'] = autor_id

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(contenido__icontains=q)
        filtro_qs['q'] = q

    return queryset, filtro_qs

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
    tipos_permitidos = request.user.tipos_nota_permitidos()
    if not tipos_permitidos:
        messages.error(
            request,
            'Tu rol no tiene un tipo de nota clínica asociado para registrar.'
        )
        return redirect('residente_detalle', pk=residente.pk)
    form = NotaClinicaForm(request.POST or None, tipos_permitidos=tipos_permitidos)

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

    base_qs, filtro_qs = _filtrar_notas_por_querystring(
        NotaClinica.objects.filter(residente=nota.residente),
        request
    )
    nota_anterior = base_qs.filter(
        fecha_creacion__lt=nota.fecha_creacion
    ).order_by('-fecha_creacion').first()
    nota_siguiente = base_qs.filter(
        fecha_creacion__gt=nota.fecha_creacion
    ).order_by('fecha_creacion').first()

    return render(request, 'notas_clinicas/nota_detalle.html', {
        'nota': nota,
        'aclaraciones': aclaraciones,
        'nombre': nota.residente.get_nombre(),
        'nota_anterior': nota_anterior,
        'nota_siguiente': nota_siguiente,
        'filtro_querystring': urlencode(filtro_qs),
        'filtro_activo': bool(filtro_qs),
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

@login_required
@clinico_requerido
def notas_calendario_data(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)

    notas_qs, filtro_qs = _filtrar_notas_por_querystring(
        NotaClinica.objects.filter(residente=residente),
        request
    )
    sufijo = f'?{urlencode(filtro_qs)}' if filtro_qs else ''

    notas = notas_qs.values(
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
            'start': dj_timezone.localtime(nota['fecha_creacion']).isoformat(),
            'color': colores.get(nota['tipo'], '#2E75B6'),
            'extendedProps': {
                'autor': autor or 'Sin nombre',
                'url': f'/notas/{nota["pk"]}/{sufijo}'
            }
        })

    return JsonResponse(eventos, safe=False)


@login_required
@clinico_requerido
def notas_calendario(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    autores = (
        NotaClinica.objects
        .filter(residente=residente)
        .values('autor_id', 'autor__first_name', 'autor__last_name')
        .distinct()
        .order_by('autor__first_name', 'autor__last_name')
    )
    return render(request, 'notas_clinicas/notas_calendario.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'autores': autores,
    })