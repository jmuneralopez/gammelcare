from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from notas_clinicas.models import NotaClinica
from usuarios.decorators import clinico_requerido

from . import calendario
from .models import Residente


@login_required
@clinico_requerido
def calendario_residente(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    autores = (NotaClinica.objects.filter(residente=residente)
               .values('autor_id', 'autor__first_name', 'autor__last_name').distinct()
               .order_by('autor__first_name', 'autor__last_name'))
    return render(request, 'residentes/calendario.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'autores': autores, 'capas': calendario.CAPAS,
        'capa_inicial': request.GET.get('capa', ''),
    })


@login_required
@clinico_requerido
def calendario_residente_data(request, pk):
    from notas_clinicas.views import _filtrar_notas_por_querystring
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    hoy = timezone.localdate()
    desde = calendario.parse_fecha(request.GET.get('start'), hoy - timedelta(days=31))
    hasta = calendario.parse_fecha(request.GET.get('end'), hoy + timedelta(days=31))
    if (hasta - desde).days > 400:
        hasta = desde + timedelta(days=400)
    validas = [c for c, _, _ in calendario.CAPAS]
    pedidas = request.GET.get('capas')
    capas = [c for c in pedidas.split(',') if c in validas] if pedidas is not None else validas
    notas_qs, _ = _filtrar_notas_por_querystring(NotaClinica.objects.filter(residente=residente), request)
    eventos = calendario.eventos_residente(residente, desde, hasta, capas, notas_qs)
    return JsonResponse([e.para_calendario() for e in eventos], safe=False)
