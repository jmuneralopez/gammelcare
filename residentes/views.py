from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from usuarios.decorators import administrador_requerido, clinico_requerido
from auditoria.models import RegistroAuditoria
from infraestructura.models import Cama
from .models import Residente, AsignacionCama, ExpedienteIngreso, ExamenIngreso, DiagnosticoResidente
from .forms import ResidenteForm, ExpedienteIngresoForm, ExamenIngresoForm, DiagnosticoForm
from django.http import HttpResponse
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


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

@login_required
@clinico_requerido
def residente_exportar_pdf(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    expediente = getattr(residente, 'expediente', None)
    examen = getattr(residente, 'examen_ingreso', None)
    diagnosticos = residente.diagnosticos.filter(activo=True).select_related('codigo_cie10')
    notas = residente.notas.all().order_by('-fecha_creacion')[:20]

    registrar_auditoria(
        usuario=request.user,
        accion=RegistroAuditoria.EXPORTACION,
        descripcion=f'Exportación PDF del expediente del residente #{residente.pk}',
        request=request
    )

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="expediente_{residente.pk}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter,
                            topMargin=0.5*inch, bottomMargin=0.5*inch,
                            leftMargin=0.75*inch, rightMargin=0.75*inch)

    styles = getSampleStyleSheet()
    BLUE_DARK = colors.HexColor('#1F4E79')
    BLUE_MID  = colors.HexColor('#2E75B6')
    BLUE_LIGHT = colors.HexColor('#D6E4F0')
    BLUE_XLIGHT = colors.HexColor('#EBF3FA')

    style_titulo = ParagraphStyle('titulo', parent=styles['Title'],
                                   fontSize=20, textColor=BLUE_DARK,
                                   spaceAfter=4, alignment=TA_CENTER)
    style_subtitulo = ParagraphStyle('subtitulo', parent=styles['Normal'],
                                      fontSize=10, textColor=BLUE_MID,
                                      spaceAfter=2, alignment=TA_CENTER)
    style_seccion = ParagraphStyle('seccion', parent=styles['Normal'],
                                    fontSize=11, textColor=colors.white,
                                    backColor=BLUE_DARK, spaceBefore=12,
                                    spaceAfter=6, leftIndent=6,
                                    fontName='Helvetica-Bold')
    style_label = ParagraphStyle('label', parent=styles['Normal'],
                                  fontSize=8, textColor=colors.grey)
    style_valor = ParagraphStyle('valor', parent=styles['Normal'],
                                  fontSize=9, textColor=colors.black,
                                  fontName='Helvetica-Bold')
    style_body = ParagraphStyle('body', parent=styles['Normal'],
                                 fontSize=9, textColor=colors.black,
                                 spaceAfter=4)
    style_footer = ParagraphStyle('footer', parent=styles['Normal'],
                                   fontSize=7, textColor=colors.grey,
                                   alignment=TA_CENTER)

    story = []

    # ENCABEZADO
    story.append(Paragraph("GammelCare", style_titulo))
    story.append(Paragraph("Sistema Web para Hogares Geriátricos", style_subtitulo))
    story.append(Paragraph(f"Hogar: {residente.hogar.nombre}", style_subtitulo))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE_MID, spaceAfter=8))
    story.append(Paragraph("EXPEDIENTE DEL RESIDENTE", ParagraphStyle(
        'exp', parent=styles['Normal'], fontSize=13, textColor=BLUE_DARK,
        fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=12
    )))

    # DATOS PERSONALES
    story.append(Paragraph(" Datos Personales", style_seccion))
    datos = [
        [Paragraph("Nombre completo", style_label), Paragraph(residente.get_nombre(), style_valor),
         Paragraph("Documento", style_label), Paragraph(f"{residente.get_tipo_documento_display()} {residente.get_documento()}", style_valor)],
        [Paragraph("Fecha de nacimiento", style_label), Paragraph(str(residente.fecha_nacimiento), style_valor),
         Paragraph("Nacionalidad", style_label), Paragraph(residente.nacionalidad or "—", style_valor)],
        [Paragraph("EPS", style_label), Paragraph(str(residente.eps) if residente.eps else "—", style_valor),
         Paragraph("Ambulancia", style_label), Paragraph(str(residente.servicio_ambulancia) if residente.servicio_ambulancia else "—", style_valor)],
        [Paragraph("Contacto emergencia", style_label), Paragraph(residente.get_contacto(), style_valor),
         Paragraph("Cama actual", style_label), Paragraph(
             f"{residente.cama_actual.codigo} — Hab. {residente.cama_actual.habitacion.numero}" if residente.cama_actual else "Sin asignación",
             style_valor)],
        [Paragraph("Estado", style_label), Paragraph("Activo" if residente.activo else f"Alta — {residente.get_motivo_retiro_display()}", style_valor),
         Paragraph("Fecha ingreso", style_label), Paragraph(residente.fecha_ingreso.strftime("%d/%m/%Y %H:%M"), style_valor)],
    ]
    t = Table(datos, colWidths=[1.4*inch, 2.3*inch, 1.4*inch, 2.3*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, BLUE_XLIGHT]),
        ('GRID', (0,0), (-1,-1), 0.3, BLUE_LIGHT),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)

    # DIAGNÓSTICOS
    if diagnosticos:
        story.append(Paragraph(" Diagnósticos", style_seccion))
        diag_data = [[
            Paragraph("Código", ParagraphStyle('h', parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold')),
            Paragraph("Descripción", ParagraphStyle('h', parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold')),
            Paragraph("Observación", ParagraphStyle('h', parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold')),
            Paragraph("Fecha", ParagraphStyle('h', parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold')),
        ]]
        for d in diagnosticos:
            diag_data.append([
                Paragraph(d.codigo_cie10.codigo, style_body),
                Paragraph(d.codigo_cie10.descripcion[:60], style_body),
                Paragraph(d.observacion[:40] if d.observacion else "—", style_body),
                Paragraph(d.fecha_registro.strftime("%d/%m/%Y"), style_body),
            ])
        dt = Table(diag_data, colWidths=[0.8*inch, 2.8*inch, 2.2*inch, 1.0*inch])
        dt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), BLUE_MID),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BLUE_XLIGHT]),
            ('GRID', (0,0), (-1,-1), 0.3, BLUE_LIGHT),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(dt)

    # EXAMEN DE INGRESO
    if examen:
        story.append(Paragraph(" Examen de Ingreso", style_seccion))
        ex_data = [
            [Paragraph("Peso", style_label), Paragraph(f"{examen.peso} kg" if examen.peso else "—", style_valor),
             Paragraph("Talla", style_label), Paragraph(f"{examen.talla} cm" if examen.talla else "—", style_valor),
             Paragraph("IMC", style_label), Paragraph(str(examen.imc()) if examen.imc() else "—", style_valor)],
            [Paragraph("Presión arterial", style_label), Paragraph(examen.presion_arterial or "—", style_valor),
             Paragraph("Frec. cardíaca", style_label), Paragraph(f"{examen.frecuencia_cardiaca} lpm" if examen.frecuencia_cardiaca else "—", style_valor),
             Paragraph("Temperatura", style_label), Paragraph(f"{examen.temperatura} °C" if examen.temperatura else "—", style_valor)],
            [Paragraph("Sat. O2", style_label), Paragraph(f"{examen.saturacion_oxigeno} %" if examen.saturacion_oxigeno else "—", style_valor),
             Paragraph("Procedencia", style_label), Paragraph(examen.get_procedencia_display() if examen.procedencia else "—", style_valor),
             Paragraph("Estado mental", style_label), Paragraph(examen.get_estado_mental_display() if examen.estado_mental else "—", style_valor)],
            [Paragraph("Movilidad", style_label), Paragraph(examen.get_movilidad_display() if examen.movilidad else "—", style_valor),
             Paragraph("Cond. nutricional", style_label), Paragraph(examen.get_condicion_nutricional_display() if examen.condicion_nutricional else "—", style_valor),
             Paragraph("", style_label), Paragraph("", style_valor)],
        ]
        et = Table(ex_data, colWidths=[1.2*inch, 1.5*inch, 1.2*inch, 1.5*inch, 1.2*inch, 1.0*inch])
        et.setStyle(TableStyle([
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, BLUE_XLIGHT]),
            ('GRID', (0,0), (-1,-1), 0.3, BLUE_LIGHT),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(et)

        if examen.observaciones_fisicas:
            story.append(Spacer(1, 6))
            story.append(Paragraph("Observaciones físicas:", style_label))
            story.append(Paragraph(examen.observaciones_fisicas, style_body))
        if examen.antecedentes_medicos:
            story.append(Paragraph("Antecedentes médicos:", style_label))
            story.append(Paragraph(examen.antecedentes_medicos, style_body))
        if examen.antecedentes_familiares:
            story.append(Paragraph("Antecedentes familiares:", style_label))
            story.append(Paragraph(examen.antecedentes_familiares, style_body))

    # EXPEDIENTE
    if expediente:
        story.append(Paragraph(" Expediente de Ingreso", style_seccion))
        if expediente.alergias:
            story.append(Paragraph("Alergias:", style_label))
            story.append(Paragraph(expediente.alergias, style_body))
        if expediente.inventario_ingreso:
            story.append(Paragraph("Inventario de ingreso:", style_label))
            story.append(Paragraph(expediente.inventario_ingreso, style_body))
        if expediente.observaciones:
            story.append(Paragraph("Observaciones generales:", style_label))
            story.append(Paragraph(expediente.observaciones, style_body))

    # NOTAS CLÍNICAS
    if notas:
        story.append(Paragraph(" Notas Clínicas (últimas 20)", style_seccion))
        for nota in notas:
            nota_header = Table([[
                Paragraph(nota.get_tipo_display(), ParagraphStyle('nh', parent=styles['Normal'],
                          fontSize=8, textColor=colors.white, fontName='Helvetica-Bold')),
                Paragraph(nota.fecha_creacion.strftime("%d/%m/%Y %H:%M"), ParagraphStyle('nd', parent=styles['Normal'],
                          fontSize=8, textColor=colors.white, alignment=TA_RIGHT)),
                Paragraph(nota.autor.get_full_name() or nota.autor.username, ParagraphStyle('na', parent=styles['Normal'],
                          fontSize=8, textColor=colors.white, alignment=TA_RIGHT)),
            ]], colWidths=[2.5*inch, 2*inch, 3*inch])
            nota_header.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), BLUE_MID),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(nota_header)
            story.append(Paragraph(nota.contenido, ParagraphStyle('nc', parent=styles['Normal'],
                                   fontSize=9, leftIndent=6, spaceAfter=2)))
            if nota.tipo == 'enfermeria':
                indicadores = []
                if nota.diuresis:
                    indicadores.append("✓ Diuresis positiva")
                if nota.deposicion:
                    indicadores.append("✓ Deposición positiva")
                if indicadores:
                    story.append(Paragraph(" | ".join(indicadores), ParagraphStyle('ind', parent=styles['Normal'],
                                           fontSize=8, textColor=BLUE_MID, leftIndent=6, spaceAfter=2)))
            story.append(Spacer(1, 4))

    # FOOTER
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_LIGHT, spaceBefore=12))
    from django.utils import timezone as tz
    story.append(Paragraph(
        f"Documento generado el {tz.now().strftime('%d/%m/%Y %H:%M')} por {request.user.get_full_name() or request.user.username} — GammelCare",
        style_footer
    ))

    doc.build(story)
    return response