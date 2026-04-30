from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import CodigoCIE10, EPS, ServicioAmbulancia


@login_required
def buscar_cie10(request):
    term = request.GET.get('term', '').strip()
    if len(term) < 2:
        return JsonResponse({'results': []})

    resultados = CodigoCIE10.objects.filter(
        codigo__icontains=term
    ) | CodigoCIE10.objects.filter(
        descripcion__icontains=term
    )
    resultados = resultados.order_by('codigo')[:20]

    data = {
        'results': [
            {
                'id': r.pk,
                'text': f'{r.codigo} — {r.descripcion}'
            }
            for r in resultados
        ]
    }
    return JsonResponse(data)


@login_required
def buscar_eps(request):
    term = request.GET.get('term', '').strip()
    qs = EPS.objects.filter(activo=True)
    if term:
        qs = qs.filter(nombre__icontains=term)
    qs = qs.order_by('nombre')[:20]

    data = {
        'results': [
            {'id': r.pk, 'text': r.nombre}
            for r in qs
        ]
    }
    return JsonResponse(data)


@login_required
def buscar_ambulancia(request):
    term = request.GET.get('term', '').strip()
    qs = ServicioAmbulancia.objects.filter(activo=True)
    if term:
        qs = qs.filter(nombre__icontains=term)
    qs = qs.order_by('nombre')[:20]

    data = {
        'results': [
            {'id': r.pk, 'text': r.nombre}
            for r in qs
        ]
    }
    return JsonResponse(data)