import os
import django
import csv

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gammelcare.settings')
django.setup()

from catalogos.models import CodigoCIE10

ARCHIVO = r"C:\gammelcare\CIE10\catalogo_cie10.csv"

print("Leyendo archivo CIE-10 en español...")

# Primero eliminamos los 500 códigos en inglés que ya cargamos
CodigoCIE10.objects.all().delete()
print("Códigos anteriores eliminados.")

creados = 0
omitidos = 0
total = 0

with open(ARCHIVO, encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    for row in reader:
        codigo = row.get('CATALOG_KEY', '').strip()
        descripcion = row.get('NOMBRE', '').strip()
        categoria = row.get('CAPITULO', '').strip()

        if not codigo or not descripcion:
            omitidos += 1
            continue

        obj, created = CodigoCIE10.objects.get_or_create(
            codigo=codigo,
            defaults={
                'descripcion': descripcion,
                'categoria': categoria
            }
        )
        if created:
            creados += 1

        total += 1
        if total % 2000 == 0:
            print(f"  Procesados: {total}...")

print(f"\nCarga completa.")
print(f"Creados: {creados} | Omitidos: {omitidos} | Total: {total}")