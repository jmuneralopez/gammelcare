from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from usuarios.decorators import administrador_requerido, clinico_requerido
from auditoria.models import RegistroAuditoria
from infraestructura.models import Cama
from .models import Residente, AsignacionCama, ExpedienteIngreso, ExamenIngreso, DiagnosticoResidente
from .forms import ResidenteForm, ExpedienteIngresoForm, ExamenIngresoForm, DiagnosticoForm


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
    expediente_form = ExpedienteIngresoForm(request.POST or None)
    examen_form = ExamenIngresoForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid() and expediente_form.is_valid() and examen_form.is_valid():
            cama = form.cleaned_data.get('cama')

            residente = Residente(
                hogar=hogar,
                fecha_nacimiento=form.cleaned_data['fecha_nacimiento'],
                tipo_documento=form.cleaned_data['tipo_documento'],
                nacionalidad=form.cleaned_data['nacionalidad'],
                eps=form.cleaned_data.get('eps'),
                servicio_ambulancia=form.cleaned_data.get('servicio_ambulancia'),
            )
            residente.set_nombre(form.cleaned_data['nombre_completo'])
            residente.set_documento(form.cleaned_data['numero_documento'])
            residente.set_contacto(form.cleaned_data['contacto_emergencia'])

            if cama:
                residente.cama_actual = cama
            residente.save()

            if cama:
                cama.estado = 'ocupada'
                cama.save()
                AsignacionCama.objects.create(
                    residente=residente,
                    cama=cama,
                    activo=True
                )

            expediente = expediente_form.save(commit=False)
            expediente.residente = residente
            expediente.save()

            examen = examen_form.save(commit=False)
            examen.residente = residente
            examen.save()

            registrar_auditoria(
                usuario=request.user,
                accion=RegistroAuditoria.CREACION_RESIDENTE,
                descripcion=f'Registro de residente #{residente.pk} en hogar {hogar.nombre}',
                request=request
            )

            messages.success(request, 'Residente registrado correctamente.')
            return redirect('residente_detalle', pk=residente.pk)

    return render(request, 'residentes/residente_form.html', {
        'form': form,
        'expediente_form': expediente_form,
        'examen_form': examen_form,
        'titulo': 'Nuevo Residente',
        'accion': 'Registrar'
    })


@login_required
@clinico_requerido
def residente_detalle(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    expediente = getattr(residente, 'expediente', None)
    examen = getattr(residente, 'examen_ingreso', None)
    diagnosticos = residente.diagnosticos.filter(activo=True).select_related('codigo_cie10')

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
        'expediente': expediente,
        'examen': examen,
        'diagnosticos': diagnosticos,
        'notas': residente.notas.all().order_by('-fecha_creacion'),
        'asignaciones': residente.asignaciones.all().order_by('-fecha_inicio'),
    })


@login_required
@administrador_requerido
def residente_editar(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    hogar = request.user.hogar
    expediente, _ = ExpedienteIngreso.objects.get_or_create(residente=residente)
    examen, _ = ExamenIngreso.objects.get_or_create(residente=residente)

    initial = {
        'nombre_completo': residente.get_nombre(),
        'numero_documento': residente.get_documento(),
        'fecha_nacimiento': residente.fecha_nacimiento,
        'tipo_documento': residente.tipo_documento,
        'nacionalidad': residente.nacionalidad,
        'eps': residente.eps,
        'servicio_ambulancia': residente.servicio_ambulancia,
        'contacto_emergencia': residente.get_contacto(),
        'cama': residente.cama_actual,
    }

    form = ResidenteForm(
        request.POST or None,
        hogar=hogar,
        cama_actual=residente.cama_actual,
        initial=initial
    )
    expediente_form = ExpedienteIngresoForm(request.POST or None, instance=expediente)
    examen_form = ExamenIngresoForm(request.POST or None, instance=examen)

    if request.method == 'POST':
        if form.is_valid() and expediente_form.is_valid() and examen_form.is_valid():
            residente.set_nombre(form.cleaned_data['nombre_completo'])
            residente.set_documento(form.cleaned_data['numero_documento'])
            residente.set_contacto(form.cleaned_data['contacto_emergencia'])
            residente.fecha_nacimiento = form.cleaned_data['fecha_nacimiento']
            residente.tipo_documento = form.cleaned_data['tipo_documento']
            residente.nacionalidad = form.cleaned_data['nacionalidad']
            residente.eps = form.cleaned_data.get('eps')
            residente.servicio_ambulancia = form.cleaned_data.get('servicio_ambulancia')

            nueva_cama = form.cleaned_data.get('cama')
            if nueva_cama and nueva_cama != residente.cama_actual:
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
            expediente_form.save()
            examen_form.save()

            messages.success(request, 'Residente actualizado correctamente.')
            return redirect('residente_detalle', pk=residente.pk)

    return render(request, 'residentes/residente_form.html', {
        'form': form,
        'expediente_form': expediente_form,
        'examen_form': examen_form,
        'titulo': 'Editar Residente',
        'accion': 'Guardar cambios'
    })


@login_required
@administrador_requerido
def residente_desactivar(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)

    if request.method == 'POST':
        motivo = request.POST.get('motivo_retiro')
        residente.activo = False
        residente.motivo_retiro = motivo

        if residente.cama_actual:
            residente.cama_actual.estado = 'disponible'
            residente.cama_actual.save()
            AsignacionCama.objects.filter(
                residente=residente, activo=True
            ).update(fecha_fin=timezone.now(), activo=False)
            residente.cama_actual = None

        residente.save()
        messages.success(request, 'Residente dado de alta correctamente.')
        return redirect('residente_lista')

    return render(request, 'residentes/residente_confirmar_alta.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'motivos': Residente.MOTIVO_RETIRO,
    })


@login_required
@administrador_requerido
def residente_reactivar(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    residente.activo = True
    residente.motivo_retiro = None
    residente.save()
    messages.success(request, 'Residente reactivado correctamente.')
    return redirect('residente_lista')


@login_required
@clinico_requerido
def diagnostico_agregar(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    form = DiagnosticoForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        diagnostico = form.save(commit=False)
        diagnostico.residente = residente
        diagnostico.save()
        messages.success(request, 'Diagnóstico agregado correctamente.')
        return redirect('residente_detalle', pk=residente.pk)

    return render(request, 'residentes/diagnostico_form.html', {
        'form': form,
        'residente': residente,
        'nombre': residente.get_nombre(),
    })


@login_required
@clinico_requerido
def diagnostico_desactivar(request, pk, dpk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    diagnostico = get_object_or_404(DiagnosticoResidente, pk=dpk, residente=residente)
    diagnostico.activo = False
    diagnostico.save()
    messages.success(request, 'Diagnóstico removido correctamente.')
    return redirect('residente_detalle', pk=residente.pk)