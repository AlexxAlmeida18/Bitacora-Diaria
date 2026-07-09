import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _resource_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", _app_dir())
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _app_dir()
DATA_FILE = os.path.join(APP_DIR, "bitacoras_data.json")
CONFIG_FILE = os.path.join(APP_DIR, "bitacora_config.json")
ICON_FILE = os.path.join(_resource_dir(), "bitacora.ico")
REPORTS_DIR = os.path.join(APP_DIR, "Reportes")
NOTIF_STATE_FILE = os.path.join(APP_DIR, "notif_state.json")
HEARTBEAT_FILE = os.path.join(APP_DIR, "app_heartbeat.txt")

ERP_URL = "https://erp.datadiscol.com/bitacora"

_MORNING = [f"{m // 60:02d}:{m % 60:02d}" for m in range(7 * 60 + 30, 12 * 60 + 1, 15)]
_AFTERNOON = [f"{m // 60:02d}:{m % 60:02d}" for m in range(14 * 60, 17 * 60 + 1, 15)]
TIME_OPTIONS = _MORNING + _AFTERNOON

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

HORAS_DIA_SEMANA = 7.5
HORAS_SABADO = 4.5


def _domingo_pascua(anio):
    a = anio % 19
    b = anio // 100
    c = anio % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _mover_a_lunes(d):
    if d.weekday() == 0:
        return d
    return d + timedelta(days=(7 - d.weekday()))


def festivos_colombia(anio):
    pascua = _domingo_pascua(anio)
    fijos_no_trasladables = [
        date(anio, 1, 1), date(anio, 5, 1), date(anio, 7, 20),
        date(anio, 8, 7), date(anio, 12, 8), date(anio, 12, 25),
    ]
    fijos_trasladables = [
        date(anio, 1, 6), date(anio, 3, 19), date(anio, 6, 29),
        date(anio, 8, 15), date(anio, 10, 12), date(anio, 11, 1), date(anio, 11, 11),
    ]
    basados_pascua_fijos = [pascua - timedelta(days=3), pascua - timedelta(days=2)]
    basados_pascua_trasladables = [
        pascua + timedelta(days=39), pascua + timedelta(days=60), pascua + timedelta(days=68),
    ]

    festivos = set(fijos_no_trasladables) | set(basados_pascua_fijos)
    for f in fijos_trasladables + basados_pascua_trasladables:
        festivos.add(_mover_a_lunes(f))
    return festivos


def horas_esperadas_dia(fecha):
    if fecha in festivos_colombia(fecha.year):
        return 0.0
    if fecha.weekday() < 5:
        return HORAS_DIA_SEMANA
    if fecha.weekday() == 5:
        return HORAS_SABADO
    return 0.0

TIPO_ACTIVIDAD_OPTIONS = [
    "Gestion/Trabajo administrativo",
    "Gestion/Trabajo Operativo",
    "Reunion de Trabajo",
    "Capacitación / Formación",
    "Desplazamiento / Traslado",
    "Atención al cliente/ Usuario",
    "Gestion Informes/Análisis",
    "Trabajo en Campo",
    "Extraccion de Datos",
]

ACCION_OPTIONS = [
    "Trascribir", "Tabular", "Organizar", "Cotizar", "LLamar", "Enviar",
    "Reunir", "Redactar", "Analizar", "Informar", "Gestionar", "Extraer",
    "Digitar", "Desarrollar", "Estructurar",
]

ACCION_KEYWORDS = [
    ("Trascribir", (
        "trascrib", "transcrib", "pasar a limpio", "dictad",
        "copiar texto", "mecanograf", "pasar a digital", "audio a texto",
        "digitalización", "digitalización compras", "digitalización ventas", "digitalización contabilidad",
        "digitalización finanzas", "digitalización logística", "digitalización producción", "digitalización recursos humanos",
        "digitalización jurídica", "digitalización tecnología", "digitalización calidad", "digitalización sst",
        "digitalización gerencia", "digitalizar", "digitalicé", "digitalice",
        "escanear", "escaneo", "convertir a pdf", "pasar a pdf",
    )),
    ("Tabular", (
        "tabul", "hoja de calculo", "hoja de cálculo", "en excel",
        "en csv", "cuadro de datos", "planilla", "google sheets",
        "consolidar datos", "consolidado", "matriz de", "vaciar informacion",
        "vaciar información",
    )),
    ("Organizar", (
        "organiz", "organic", "orden", "clasific",
        "clasifiqu", "acomod", "archiv", "seleccion de foto",
        "selección de foto", "descarte de foto", "depurar", "depuracion",
        "depuración", "carpetas", "etiquetar", "categoriz",
        "archivo", "archivo administrativa", "archivo financiera", "archivo comercial",
        "archivo operativa", "archivo logística", "archivo tecnológica", "archivo jurídica",
        "archivo contable", "archivo recursos humanos", "archivo calidad", "archivo sst",
        "archivo digital", "archivo digital administrativa", "archivo digital financiera", "archivo digital comercial",
        "archivo digital operativa", "archivo digital logística", "archivo digital tecnológica", "archivo digital jurídica",
        "archivo digital contable", "archivo digital recursos humanos", "archivo digital calidad", "archivo digital sst",
        "archivo físico", "archivo físico administrativa", "archivo físico financiera", "archivo físico comercial",
        "archivo físico operativa", "archivo físico logística", "archivo físico tecnológica", "archivo físico jurídica",
        "archivo físico contable", "archivo físico recursos humanos", "archivo físico calidad", "archivo físico sst",
        "clasificación", "clasificación compras", "clasificación ventas", "clasificación contabilidad",
        "clasificación finanzas", "clasificación logística", "clasificación producción", "clasificación recursos humanos",
        "clasificación jurídica", "clasificación tecnología", "clasificación calidad", "clasificación sst",
        "clasificación gerencia", "expediente", "expediente compras", "expediente ventas",
        "expediente contabilidad", "expediente finanzas", "expediente logística", "expediente producción",
        "expediente recursos humanos", "expediente jurídica", "expediente tecnología", "expediente calidad",
        "expediente sst", "expediente gerencia",
    )),
    ("Cotizar", (
        "cotiz", "cotic", "presupuest", "cotización",
        "propuesta comercial", "propuesta economica", "propuesta económica", "oferta comercial",
        "precio a cliente", "enviar precios", "lista de precios", "tarifa",
        "cotización administrativa", "cotización financiera", "cotización comercial", "cotización operativa",
        "cotización logística", "cotización tecnológica", "cotización jurídica", "cotización contable",
        "cotización recursos humanos", "cotización calidad", "cotización sst", "presupuesto",
        "presupuesto administrativa", "presupuesto financiera", "presupuesto comercial", "presupuesto operativa",
        "presupuesto logística", "presupuesto tecnológica", "presupuesto jurídica", "presupuesto contable",
        "presupuesto recursos humanos", "presupuesto calidad", "presupuesto sst", "estimación",
        "estimación compras", "estimación ventas", "estimación contabilidad", "estimación finanzas",
        "estimación logística", "estimación producción", "estimación recursos humanos", "estimación jurídica",
        "estimación tecnología", "estimación calidad", "estimación sst", "estimación gerencia",
    )),
    ("LLamar", (
        "llam", "telefon", "por teléfono", "por telefono",
        "video llamada", "videollamada", "conferencia telefonica", "conferencia telefónica",
    )),
    ("Enviar", (
        "envi", "mand", "remit", "despach",
        "correo a", "mensaje a", "compart", "public",
        "publiqu", "wsp a", "whatsapp a", "subir a redes",
        "posteo", "postear", "entrega", "despacho",
        "despacho administrativa", "despacho financiera", "despacho comercial", "despacho operativa",
        "despacho logística", "despacho tecnológica", "despacho jurídica", "despacho contable",
        "despacho recursos humanos", "despacho calidad", "despacho sst", "entrega administrativa",
        "entrega financiera", "entrega comercial", "entrega operativa", "entrega logística",
        "entrega tecnológica", "entrega jurídica", "entrega contable", "entrega recursos humanos",
        "entrega calidad", "entrega sst",
    )),
    ("Reunir", (
        "reun", "junta", "cita con", "mesa de trabajo",
        "visita comercial", "visité al cliente", "visite al cliente", "call con",
        "comite", "comité", "capacitacion", "capacitación",
        "charla con", "capacitación administrativa", "capacitación financiera", "capacitación comercial",
        "capacitación operativa", "capacitación logística", "capacitación tecnológica", "capacitación jurídica",
        "capacitación contable", "capacitación recursos humanos", "capacitación calidad", "capacitación sst",
        "capacitación virtual", "capacitación virtual compras", "capacitación virtual ventas", "capacitación virtual contabilidad",
        "capacitación virtual finanzas", "capacitación virtual logística", "capacitación virtual producción", "capacitación virtual recursos humanos",
        "capacitación virtual jurídica", "capacitación virtual tecnología", "capacitación virtual calidad", "capacitación virtual sst",
        "capacitación virtual gerencia", "comité compras", "comité ventas", "comité contabilidad",
        "comité finanzas", "comité logística", "comité producción", "comité recursos humanos",
        "comité jurídica", "comité tecnología", "comité calidad", "comité sst",
        "comité gerencia", "formación", "formación compras", "formación ventas",
        "formación contabilidad", "formación finanzas", "formación logística", "formación producción",
        "formación recursos humanos", "formación jurídica", "formación tecnología", "formación calidad",
        "formación sst", "formación gerencia", "charla", "charla informativa",
        "conversatorio", "webinar", "taller", "sesión de trabajo",
        "sesion de trabajo", "encuentro con", "punto de control", "daily",
        "standup", "sync con",
    )),
    ("Redactar", (
        "redact", "document", "elabora", "escrib",
        "preparar informe", "preparar documento", "guion", "guión",
        "copy", "texto para redes", "texto publicitario", "carta a",
        "oficio", "acta de", "minuta", "community manager",
        "periodista", "comunicador social", "acta", "acuerdo",
        "acta administrativa", "acta financiera", "acta comercial", "acta operativa",
        "acta logística", "acta tecnológica", "acta jurídica", "acta contable",
        "acta recursos humanos", "acta calidad", "acta sst", "acta de reunión",
        "acta de reunión administrativa", "acta de reunión financiera", "acta de reunión comercial", "acta de reunión operativa",
        "acta de reunión logística", "acta de reunión tecnológica", "acta de reunión jurídica", "acta de reunión contable",
        "acta de reunión recursos humanos", "acta de reunión calidad", "acta de reunión sst", "acta de comité",
        "acta de comité administrativa", "acta de comité financiera", "acta de comité comercial", "acta de comité operativa",
        "acta de comité logística", "acta de comité tecnológica", "acta de comité jurídica", "acta de comité contable",
        "acta de comité recursos humanos", "acta de comité calidad", "acta de comité sst", "acuerdo administrativa",
        "acuerdo financiera", "acuerdo comercial", "acuerdo operativa", "acuerdo logística",
        "acuerdo tecnológica", "acuerdo jurídica", "acuerdo contable", "acuerdo recursos humanos",
        "acuerdo calidad", "acuerdo sst", "documentación", "documentación administrativa",
        "documentación financiera", "documentación comercial", "documentación operativa", "documentación logística",
        "documentación tecnológica", "documentación jurídica", "documentación contable", "documentación recursos humanos",
        "documentación calidad", "documentación sst", "anexo", "anexo compras",
        "anexo ventas", "anexo contabilidad", "anexo finanzas", "anexo logística",
        "anexo producción", "anexo recursos humanos", "anexo jurídica", "anexo tecnología",
        "anexo calidad", "anexo sst", "anexo gerencia", "campaña",
        "campaña compras", "campaña ventas", "campaña contabilidad", "campaña finanzas",
        "campaña logística", "campaña producción", "campaña recursos humanos", "campaña jurídica",
        "campaña tecnología", "campaña calidad", "campaña sst", "campaña gerencia",
        "documento soporte", "documento soporte compras", "documento soporte ventas", "documento soporte contabilidad",
        "documento soporte finanzas", "documento soporte logística", "documento soporte producción", "documento soporte recursos humanos",
        "documento soporte jurídica", "documento soporte tecnología", "documento soporte calidad", "documento soporte sst",
        "documento soporte gerencia", "manual", "manual compras", "manual ventas",
        "manual contabilidad", "manual finanzas", "manual logística", "manual producción",
        "manual recursos humanos", "manual jurídica", "manual tecnología", "manual calidad",
        "manual sst", "manual gerencia",
    )),
    ("Analizar", (
        "analiz", "analic", "análisis", "revis",
        "evalu", "verific", "verifiqu", "comprob",
        "chequ", "estudi", "diagnostic", "concili",
        "inspec", "audit", "riesgo", "inciden",
        "accidente", "falla", "control de calidad", "seguimiento a indicadores",
        "indicadores", "kpi", "acción correctiva", "accion correctiva",
        "acción preventiva", "accion preventiva", "indicador", "acción correctiva administrativa",
        "acción correctiva financiera", "acción correctiva comercial", "acción correctiva operativa", "acción correctiva logística",
        "acción correctiva tecnológica", "acción correctiva jurídica", "acción correctiva contable", "acción correctiva recursos humanos",
        "acción correctiva calidad", "acción correctiva sst", "acción preventiva administrativa", "acción preventiva financiera",
        "acción preventiva comercial", "acción preventiva operativa", "acción preventiva logística", "acción preventiva tecnológica",
        "acción preventiva jurídica", "acción preventiva contable", "acción preventiva recursos humanos", "acción preventiva calidad",
        "acción preventiva sst", "análisis administrativa", "análisis financiera", "análisis comercial",
        "análisis operativa", "análisis logística", "análisis tecnológica", "análisis jurídica",
        "análisis contable", "análisis recursos humanos", "análisis calidad", "análisis sst",
        "análisis financiero", "análisis financiero administrativa", "análisis financiero financiera", "análisis financiero comercial",
        "análisis financiero operativa", "análisis financiero logística", "análisis financiero tecnológica", "análisis financiero jurídica",
        "análisis financiero contable", "análisis financiero recursos humanos", "análisis financiero calidad", "análisis financiero sst",
        "análisis de datos", "análisis de datos administrativa", "análisis de datos financiera", "análisis de datos comercial",
        "análisis de datos operativa", "análisis de datos logística", "análisis de datos tecnológica", "análisis de datos jurídica",
        "análisis de datos contable", "análisis de datos recursos humanos", "análisis de datos calidad", "análisis de datos sst",
        "análisis de riesgos", "análisis de riesgos administrativa", "análisis de riesgos financiera", "análisis de riesgos comercial",
        "análisis de riesgos operativa", "análisis de riesgos logística", "análisis de riesgos tecnológica", "análisis de riesgos jurídica",
        "análisis de riesgos contable", "análisis de riesgos recursos humanos", "análisis de riesgos calidad", "análisis de riesgos sst",
        "auditoría", "auditoría administrativa", "auditoría financiera", "auditoría comercial",
        "auditoría operativa", "auditoría logística", "auditoría tecnológica", "auditoría jurídica",
        "auditoría contable", "auditoría recursos humanos", "auditoría calidad", "auditoría sst",
        "control de calidad administrativa", "control de calidad financiera", "control de calidad comercial", "control de calidad operativa",
        "control de calidad logística", "control de calidad tecnológica", "control de calidad jurídica", "control de calidad contable",
        "control de calidad recursos humanos", "control de calidad calidad", "control de calidad sst", "evaluación",
        "evaluación administrativa", "evaluación financiera", "evaluación comercial", "evaluación operativa",
        "evaluación logística", "evaluación tecnológica", "evaluación jurídica", "evaluación contable",
        "evaluación recursos humanos", "evaluación calidad", "evaluación sst", "evaluación de desempeño",
        "evaluación de desempeño administrativa", "evaluación de desempeño financiera", "evaluación de desempeño comercial", "evaluación de desempeño operativa",
        "evaluación de desempeño logística", "evaluación de desempeño tecnológica", "evaluación de desempeño jurídica", "evaluación de desempeño contable",
        "evaluación de desempeño recursos humanos", "evaluación de desempeño calidad", "evaluación de desempeño sst", "indicador administrativa",
        "indicador financiera", "indicador comercial", "indicador operativa", "indicador logística",
        "indicador tecnológica", "indicador jurídica", "indicador contable", "indicador recursos humanos",
        "indicador calidad", "indicador sst", "riesgo administrativa", "riesgo financiera",
        "riesgo comercial", "riesgo operativa", "riesgo logística", "riesgo tecnológica",
        "riesgo jurídica", "riesgo contable", "riesgo recursos humanos", "riesgo calidad",
        "riesgo sst", "alerta", "alerta compras", "alerta ventas",
        "alerta contabilidad", "alerta finanzas", "alerta logística", "alerta producción",
        "alerta recursos humanos", "alerta jurídica", "alerta tecnología", "alerta calidad",
        "alerta sst", "alerta gerencia", "arqueo de caja", "arqueo de caja compras",
        "arqueo de caja ventas", "arqueo de caja contabilidad", "arqueo de caja finanzas", "arqueo de caja logística",
        "arqueo de caja producción", "arqueo de caja recursos humanos", "arqueo de caja jurídica", "arqueo de caja tecnología",
        "arqueo de caja calidad", "arqueo de caja sst", "arqueo de caja gerencia", "calibración",
        "calibración compras", "calibración ventas", "calibración contabilidad", "calibración finanzas",
        "calibración logística", "calibración producción", "calibración recursos humanos", "calibración jurídica",
        "calibración tecnología", "calibración calidad", "calibración sst", "calibración gerencia",
        "conciliación", "conciliación compras", "conciliación ventas", "conciliación contabilidad",
        "conciliación finanzas", "conciliación logística", "conciliación producción", "conciliación recursos humanos",
        "conciliación jurídica", "conciliación tecnología", "conciliación calidad", "conciliación sst",
        "conciliación gerencia", "control interno", "control interno compras", "control interno ventas",
        "control interno contabilidad", "control interno finanzas", "control interno logística", "control interno producción",
        "control interno recursos humanos", "control interno jurídica", "control interno tecnología", "control interno calidad",
        "control interno sst", "control interno gerencia", "cumplimiento", "cumplimiento compras",
        "cumplimiento ventas", "cumplimiento contabilidad", "cumplimiento finanzas", "cumplimiento logística",
        "cumplimiento producción", "cumplimiento recursos humanos", "cumplimiento jurídica", "cumplimiento tecnología",
        "cumplimiento calidad", "cumplimiento sst", "cumplimiento gerencia", "diagnóstico",
        "diagnóstico compras", "diagnóstico ventas", "diagnóstico contabilidad", "diagnóstico finanzas",
        "diagnóstico logística", "diagnóstico producción", "diagnóstico recursos humanos", "diagnóstico jurídica",
        "diagnóstico tecnología", "diagnóstico calidad", "diagnóstico sst", "diagnóstico gerencia",
        "eficiencia", "eficiencia compras", "eficiencia ventas", "eficiencia contabilidad",
        "eficiencia finanzas", "eficiencia logística", "eficiencia producción", "eficiencia recursos humanos",
        "eficiencia jurídica", "eficiencia tecnología", "eficiencia calidad", "eficiencia sst",
        "eficiencia gerencia", "evaluación de riesgos", "evaluación de riesgos compras", "evaluación de riesgos ventas",
        "evaluación de riesgos contabilidad", "evaluación de riesgos finanzas", "evaluación de riesgos logística", "evaluación de riesgos producción",
        "evaluación de riesgos recursos humanos", "evaluación de riesgos jurídica", "evaluación de riesgos tecnología", "evaluación de riesgos calidad",
        "evaluación de riesgos sst", "evaluación de riesgos gerencia", "evidencia", "evidencia compras",
        "evidencia ventas", "evidencia contabilidad", "evidencia finanzas", "evidencia logística",
        "evidencia producción", "evidencia recursos humanos", "evidencia jurídica", "evidencia tecnología",
        "evidencia calidad", "evidencia sst", "evidencia gerencia", "incidente",
        "incidente compras", "incidente ventas", "incidente contabilidad", "incidente finanzas",
        "incidente logística", "incidente producción", "incidente recursos humanos", "incidente jurídica",
        "incidente tecnología", "incidente calidad", "incidente sst", "incidente gerencia",
        "indicador KPI", "indicador KPI compras", "indicador KPI ventas", "indicador KPI contabilidad",
        "indicador KPI finanzas", "indicador KPI logística", "indicador KPI producción", "indicador KPI recursos humanos",
        "indicador KPI jurídica", "indicador KPI tecnología", "indicador KPI calidad", "indicador KPI sst",
        "indicador KPI gerencia", "inspección", "inspección compras", "inspección ventas",
        "inspección contabilidad", "inspección finanzas", "inspección logística", "inspección producción",
        "inspección recursos humanos", "inspección jurídica", "inspección tecnología", "inspección calidad",
        "inspección sst", "inspección gerencia", "mejora continua", "mejora continua compras",
        "mejora continua ventas", "mejora continua contabilidad", "mejora continua finanzas", "mejora continua logística",
        "mejora continua producción", "mejora continua recursos humanos", "mejora continua jurídica", "mejora continua tecnología",
        "mejora continua calidad", "mejora continua sst", "mejora continua gerencia", "optimización",
        "optimización compras", "optimización ventas", "optimización contabilidad", "optimización finanzas",
        "optimización logística", "optimización producción", "optimización recursos humanos", "optimización jurídica",
        "optimización tecnología", "optimización calidad", "optimización sst", "optimización gerencia",
        "trazabilidad", "trazabilidad compras", "trazabilidad ventas", "trazabilidad contabilidad",
        "trazabilidad finanzas", "trazabilidad logística", "trazabilidad producción", "trazabilidad recursos humanos",
        "trazabilidad jurídica", "trazabilidad tecnología", "trazabilidad calidad", "trazabilidad sst",
        "trazabilidad gerencia", "validación", "validación compras", "validación ventas",
        "validación contabilidad", "validación finanzas", "validación logística", "validación producción",
        "validación recursos humanos", "validación jurídica", "validación tecnología", "validación calidad",
        "validación sst", "validación gerencia", "verificación", "verificación compras",
        "verificación ventas", "verificación contabilidad", "verificación finanzas", "verificación logística",
        "verificación producción", "verificación recursos humanos", "verificación jurídica", "verificación tecnología",
        "verificación calidad", "verificación sst", "verificación gerencia",
    )),
    ("Informar", (
        "informé", "informe a", "informar a", "informando a",
        "avis", "notific", "notifiqu", "comuniqu",
        "comunicar a", "socializ", "puse al tanto", "di a conocer",
        "informe de avance", "reporte de avance", "asesor", "recomend",
        "retroalimentacion", "retroalimentación", "feedback", "actualizacion de estado",
        "actualización de estado", "reporte", "reporte administrativa", "reporte financiera",
        "reporte comercial", "reporte operativa", "reporte logística", "reporte tecnológica",
        "reporte jurídica", "reporte contable", "reporte recursos humanos", "reporte calidad",
        "reporte sst", "comunicación interna", "comunicación interna compras", "comunicación interna ventas",
        "comunicación interna contabilidad", "comunicación interna finanzas", "comunicación interna logística", "comunicación interna producción",
        "comunicación interna recursos humanos", "comunicación interna jurídica", "comunicación interna tecnología", "comunicación interna calidad",
        "comunicación interna sst", "comunicación interna gerencia", "resultado", "resultado compras",
        "resultado ventas", "resultado contabilidad", "resultado finanzas", "resultado logística",
        "resultado producción", "resultado recursos humanos", "resultado jurídica", "resultado tecnología",
        "resultado calidad", "resultado sst", "resultado gerencia",
    )),
    ("Gestionar", (
        "gestion", "gestión", "tramit", "coordin",
        "administr", "supervis", "manej", "seguimiento",
        "prospec", "negoci", "cliente potencial", "cierre de venta",
        "configura", "instal", "mantenimiento", "servidor",
        "respaldo", "backup", "licencia", "ticket",
        "soporte", "soluci", "resolv", "entrevist",
        "induc", "contrat", "seleccion de personal", "selección de personal",
        "clima laboral", "protocolo", "seguridad industrial", "nomina",
        "nómina", "liquid", "prestaciones sociales", "seguridad social",
        "aportes", "incapacidad", "afiliacion", "afiliación",
        "eps", "arl", "vacante", "reclutamiento",
        "hoja de vida", "hojas de vida", "tesorer", "flujo de caja",
        "egresos", "transferencia", "renovacion", "renovación",
        "poliza", "póliza", "declar", "retenci",
        "estados financieros", "cuentas por pagar", "cuentas por cobrar", "cartera",
        "asesor comercial", "ejecutivo de ventas", "representante de ventas", "gerente comercial",
        "coordinador comercial", "vendedor", "gerente de cuenta", "key account",
        "coordinador de talento humano", "analista de recursos humanos", "gerente de recursos humanos", "jefe de personal",
        "reclutador", "psicologo organizacional", "psicólogo organizacional", "auxiliar contable",
        "contador publico", "contador público", "analista financiero", "gerente financiero",
        "coordinador de cartera", "analista de cartera", "revisor fiscal", "gerente general",
        "subgerente", "director", "secretaria", "recepcionista",
        "asistente ejecutiv", "coordinador logistico", "coordinador logístico", "jefe de operaciones",
        "supervisor de planta", "jefe de bodega", "auxiliar logistico", "auxiliar logístico",
        "abogado", "asesor juridico", "asesor jurídico", "coordinador juridico",
        "coordinador jurídico", "coordinador sst", "tecnico en salud ocupacional", "técnico en salud ocupacional",
        "almacén", "almacen", "almacenamiento", "atención al cliente",
        "atencion al cliente", "bienestar laboral", "compra", "conciliación bancaria",
        "conciliacion bancaria", "cuenta por cobrar", "cuenta por pagar", "finanzas",
        "gerencia", "inventario", "logística", "logistica",
        "mercadeo", "orden de compra", "pedido", "producción",
        "produccion", "proveedor", "servicio al cliente", "transporte",
        "venta", "administración", "administración administrativa", "administración financiera",
        "administración comercial", "administración operativa", "administración logística", "administración tecnológica",
        "administración jurídica", "administración contable", "administración recursos humanos", "administración calidad",
        "administración sst", "administración de contratos", "administración de contratos administrativa", "administración de contratos financiera",
        "administración de contratos comercial", "administración de contratos operativa", "administración de contratos logística", "administración de contratos tecnológica",
        "administración de contratos jurídica", "administración de contratos contable", "administración de contratos recursos humanos", "administración de contratos calidad",
        "administración de contratos sst", "administración de proyectos", "administración de proyectos administrativa", "administración de proyectos financiera",
        "administración de proyectos comercial", "administración de proyectos operativa", "administración de proyectos logística", "administración de proyectos tecnológica",
        "administración de proyectos jurídica", "administración de proyectos contable", "administración de proyectos recursos humanos", "administración de proyectos calidad",
        "administración de proyectos sst", "almacén administrativa", "almacén financiera", "almacén comercial",
        "almacén operativa", "almacén logística", "almacén tecnológica", "almacén jurídica",
        "almacén contable", "almacén recursos humanos", "almacén calidad", "almacén sst",
        "almacenamiento administrativa", "almacenamiento financiera", "almacenamiento comercial", "almacenamiento operativa",
        "almacenamiento logística", "almacenamiento tecnológica", "almacenamiento jurídica", "almacenamiento contable",
        "almacenamiento recursos humanos", "almacenamiento calidad", "almacenamiento sst", "atención al cliente administrativa",
        "atención al cliente financiera", "atención al cliente comercial", "atención al cliente operativa", "atención al cliente logística",
        "atención al cliente tecnológica", "atención al cliente jurídica", "atención al cliente contable", "atención al cliente recursos humanos",
        "atención al cliente calidad", "atención al cliente sst", "bienestar laboral administrativa", "bienestar laboral financiera",
        "bienestar laboral comercial", "bienestar laboral operativa", "bienestar laboral logística", "bienestar laboral tecnológica",
        "bienestar laboral jurídica", "bienestar laboral contable", "bienestar laboral recursos humanos", "bienestar laboral calidad",
        "bienestar laboral sst", "cartera administrativa", "cartera financiera", "cartera comercial",
        "cartera operativa", "cartera logística", "cartera tecnológica", "cartera jurídica",
        "cartera contable", "cartera recursos humanos", "cartera calidad", "cartera sst",
        "cliente", "cliente administrativa", "cliente financiera", "cliente comercial",
        "cliente operativa", "cliente logística", "cliente tecnológica", "cliente jurídica",
        "cliente contable", "cliente recursos humanos", "cliente calidad", "cliente sst",
        "compra administrativa", "compra financiera", "compra comercial", "compra operativa",
        "compra logística", "compra tecnológica", "compra jurídica", "compra contable",
        "compra recursos humanos", "compra calidad", "compra sst", "compras",
        "compras administrativa", "compras financiera", "compras comercial", "compras operativa",
        "compras logística", "compras tecnológica", "compras jurídica", "compras contable",
        "compras recursos humanos", "compras calidad", "compras sst", "conciliación bancaria administrativa",
        "conciliación bancaria financiera", "conciliación bancaria comercial", "conciliación bancaria operativa", "conciliación bancaria logística",
        "conciliación bancaria tecnológica", "conciliación bancaria jurídica", "conciliación bancaria contable", "conciliación bancaria recursos humanos",
        "conciliación bancaria calidad", "conciliación bancaria sst", "contrato", "contrato administrativa",
        "contrato financiera", "contrato comercial", "contrato operativa", "contrato logística",
        "contrato tecnológica", "contrato jurídica", "contrato contable", "contrato recursos humanos",
        "contrato calidad", "contrato sst", "cuenta por cobrar administrativa", "cuenta por cobrar financiera",
        "cuenta por cobrar comercial", "cuenta por cobrar operativa", "cuenta por cobrar logística", "cuenta por cobrar tecnológica",
        "cuenta por cobrar jurídica", "cuenta por cobrar contable", "cuenta por cobrar recursos humanos", "cuenta por cobrar calidad",
        "cuenta por cobrar sst", "cuenta por pagar administrativa", "cuenta por pagar financiera", "cuenta por pagar comercial",
        "cuenta por pagar operativa", "cuenta por pagar logística", "cuenta por pagar tecnológica", "cuenta por pagar jurídica",
        "cuenta por pagar contable", "cuenta por pagar recursos humanos", "cuenta por pagar calidad", "cuenta por pagar sst",
        "empleado", "empleado administrativa", "empleado financiera", "empleado comercial",
        "empleado operativa", "empleado logística", "empleado tecnológica", "empleado jurídica",
        "empleado contable", "empleado recursos humanos", "empleado calidad", "empleado sst",
        "finanzas administrativa", "finanzas financiera", "finanzas comercial", "finanzas operativa",
        "finanzas logística", "finanzas tecnológica", "finanzas jurídica", "finanzas contable",
        "finanzas recursos humanos", "finanzas calidad", "finanzas sst", "gestión administrativa",
        "gestión financiera", "gestión comercial", "gestión operativa", "gestión logística",
        "gestión tecnológica", "gestión jurídica", "gestión contable", "gestión recursos humanos",
        "gestión calidad", "gestión sst", "gestión documental", "gestión documental administrativa",
        "gestión documental financiera", "gestión documental comercial", "gestión documental operativa", "gestión documental logística",
        "gestión documental tecnológica", "gestión documental jurídica", "gestión documental contable", "gestión documental recursos humanos",
        "gestión documental calidad", "gestión documental sst", "gerencia administrativa", "gerencia financiera",
        "gerencia comercial", "gerencia operativa", "gerencia logística", "gerencia tecnológica",
        "gerencia jurídica", "gerencia contable", "gerencia recursos humanos", "gerencia calidad",
        "gerencia sst", "inventario administrativa", "inventario financiera", "inventario comercial",
        "inventario operativa", "inventario logística", "inventario tecnológica", "inventario jurídica",
        "inventario contable", "inventario recursos humanos", "inventario calidad", "inventario sst",
        "logística administrativa", "logística financiera", "logística comercial", "logística operativa",
        "logística logística", "logística tecnológica", "logística jurídica", "logística contable",
        "logística recursos humanos", "logística calidad", "logística sst", "mantenimiento administrativa",
        "mantenimiento financiera", "mantenimiento comercial", "mantenimiento operativa", "mantenimiento logística",
        "mantenimiento tecnológica", "mantenimiento jurídica", "mantenimiento contable", "mantenimiento recursos humanos",
        "mantenimiento calidad", "mantenimiento sst", "mantenimiento correctivo", "mantenimiento correctivo administrativa",
        "mantenimiento correctivo financiera", "mantenimiento correctivo comercial", "mantenimiento correctivo operativa", "mantenimiento correctivo logística",
        "mantenimiento correctivo tecnológica", "mantenimiento correctivo jurídica", "mantenimiento correctivo contable", "mantenimiento correctivo recursos humanos",
        "mantenimiento correctivo calidad", "mantenimiento correctivo sst", "mantenimiento preventivo", "mantenimiento preventivo administrativa",
        "mantenimiento preventivo financiera", "mantenimiento preventivo comercial", "mantenimiento preventivo operativa", "mantenimiento preventivo logística",
        "mantenimiento preventivo tecnológica", "mantenimiento preventivo jurídica", "mantenimiento preventivo contable", "mantenimiento preventivo recursos humanos",
        "mantenimiento preventivo calidad", "mantenimiento preventivo sst", "mercadeo administrativa", "mercadeo financiera",
        "mercadeo comercial", "mercadeo operativa", "mercadeo logística", "mercadeo tecnológica",
        "mercadeo jurídica", "mercadeo contable", "mercadeo recursos humanos", "mercadeo calidad",
        "mercadeo sst", "nómina administrativa", "nómina financiera", "nómina comercial",
        "nómina operativa", "nómina logística", "nómina tecnológica", "nómina jurídica",
        "nómina contable", "nómina recursos humanos", "nómina calidad", "nómina sst",
        "orden de compra administrativa", "orden de compra financiera", "orden de compra comercial", "orden de compra operativa",
        "orden de compra logística", "orden de compra tecnológica", "orden de compra jurídica", "orden de compra contable",
        "orden de compra recursos humanos", "orden de compra calidad", "orden de compra sst", "pedido administrativa",
        "pedido financiera", "pedido comercial", "pedido operativa", "pedido logística",
        "pedido tecnológica", "pedido jurídica", "pedido contable", "pedido recursos humanos",
        "pedido calidad", "pedido sst", "producción administrativa", "producción financiera",
        "producción comercial", "producción operativa", "producción logística", "producción tecnológica",
        "producción jurídica", "producción contable", "producción recursos humanos", "producción calidad",
        "producción sst", "proveedor administrativa", "proveedor financiera", "proveedor comercial",
        "proveedor operativa", "proveedor logística", "proveedor tecnológica", "proveedor jurídica",
        "proveedor contable", "proveedor recursos humanos", "proveedor calidad", "proveedor sst",
        "reclutamiento administrativa", "reclutamiento financiera", "reclutamiento comercial", "reclutamiento operativa",
        "reclutamiento logística", "reclutamiento tecnológica", "reclutamiento jurídica", "reclutamiento contable",
        "reclutamiento recursos humanos", "reclutamiento calidad", "reclutamiento sst", "selección de personal administrativa",
        "selección de personal financiera", "selección de personal comercial", "selección de personal operativa", "selección de personal logística",
        "selección de personal tecnológica", "selección de personal jurídica", "selección de personal contable", "selección de personal recursos humanos",
        "selección de personal calidad", "selección de personal sst", "servicio", "servicio administrativa",
        "servicio financiera", "servicio comercial", "servicio operativa", "servicio logística",
        "servicio tecnológica", "servicio jurídica", "servicio contable", "servicio recursos humanos",
        "servicio calidad", "servicio sst", "servicio al cliente administrativa", "servicio al cliente financiera",
        "servicio al cliente comercial", "servicio al cliente operativa", "servicio al cliente logística", "servicio al cliente tecnológica",
        "servicio al cliente jurídica", "servicio al cliente contable", "servicio al cliente recursos humanos", "servicio al cliente calidad",
        "servicio al cliente sst", "soporte técnico", "soporte técnico administrativa", "soporte técnico financiera",
        "soporte técnico comercial", "soporte técnico operativa", "soporte técnico logística", "soporte técnico tecnológica",
        "soporte técnico jurídica", "soporte técnico contable", "soporte técnico recursos humanos", "soporte técnico calidad",
        "soporte técnico sst", "supervisión", "supervisión administrativa", "supervisión financiera",
        "supervisión comercial", "supervisión operativa", "supervisión logística", "supervisión tecnológica",
        "supervisión jurídica", "supervisión contable", "supervisión recursos humanos", "supervisión calidad",
        "supervisión sst", "tesorería", "tesorería administrativa", "tesorería financiera",
        "tesorería comercial", "tesorería operativa", "tesorería logística", "tesorería tecnológica",
        "tesorería jurídica", "tesorería contable", "tesorería recursos humanos", "tesorería calidad",
        "tesorería sst", "transporte administrativa", "transporte financiera", "transporte comercial",
        "transporte operativa", "transporte logística", "transporte tecnológica", "transporte jurídica",
        "transporte contable", "transporte recursos humanos", "transporte calidad", "transporte sst",
        "venta administrativa", "venta financiera", "venta comercial", "venta operativa",
        "venta logística", "venta tecnológica", "venta jurídica", "venta contable",
        "venta recursos humanos", "venta calidad", "venta sst", "abastecimiento",
        "abastecimiento compras", "abastecimiento ventas", "abastecimiento contabilidad", "abastecimiento finanzas",
        "abastecimiento logística", "abastecimiento producción", "abastecimiento recursos humanos", "abastecimiento jurídica",
        "abastecimiento tecnología", "abastecimiento calidad", "abastecimiento sst", "abastecimiento gerencia",
        "abastecer", "abastecer compras", "abastecer ventas", "abastecer contabilidad",
        "abastecer finanzas", "abastecer logística", "abastecer producción", "abastecer recursos humanos",
        "abastecer jurídica", "abastecer tecnología", "abastecer calidad", "abastecer sst",
        "abastecer gerencia", "acceso", "acceso compras", "acceso ventas",
        "acceso contabilidad", "acceso finanzas", "acceso logística", "acceso producción",
        "acceso recursos humanos", "acceso jurídica", "acceso tecnología", "acceso calidad",
        "acceso sst", "acceso gerencia", "acreditación", "acreditación compras",
        "acreditación ventas", "acreditación contabilidad", "acreditación finanzas", "acreditación logística",
        "acreditación producción", "acreditación recursos humanos", "acreditación jurídica", "acreditación tecnología",
        "acreditación calidad", "acreditación sst", "acreditación gerencia", "adquisición",
        "adquisición compras", "adquisición ventas", "adquisición contabilidad", "adquisición finanzas",
        "adquisición logística", "adquisición producción", "adquisición recursos humanos", "adquisición jurídica",
        "adquisición tecnología", "adquisición calidad", "adquisición sst", "adquisición gerencia",
        "afiliación compras", "afiliación ventas", "afiliación contabilidad", "afiliación finanzas",
        "afiliación logística", "afiliación producción", "afiliación recursos humanos", "afiliación jurídica",
        "afiliación tecnología", "afiliación calidad", "afiliación sst", "afiliación gerencia",
        "almacenista", "almacenista compras", "almacenista ventas", "almacenista contabilidad",
        "almacenista finanzas", "almacenista logística", "almacenista producción", "almacenista recursos humanos",
        "almacenista jurídica", "almacenista tecnología", "almacenista calidad", "almacenista sst",
        "almacenista gerencia", "ambiente laboral", "ambiente laboral compras", "ambiente laboral ventas",
        "ambiente laboral contabilidad", "ambiente laboral finanzas", "ambiente laboral logística", "ambiente laboral producción",
        "ambiente laboral recursos humanos", "ambiente laboral jurídica", "ambiente laboral tecnología", "ambiente laboral calidad",
        "ambiente laboral sst", "ambiente laboral gerencia", "aprobación", "aprobación compras",
        "aprobación ventas", "aprobación contabilidad", "aprobación finanzas", "aprobación logística",
        "aprobación producción", "aprobación recursos humanos", "aprobación jurídica", "aprobación tecnología",
        "aprobación calidad", "aprobación sst", "aprobación gerencia", "asignación",
        "asignación compras", "asignación ventas", "asignación contabilidad", "asignación finanzas",
        "asignación logística", "asignación producción", "asignación recursos humanos", "asignación jurídica",
        "asignación tecnología", "asignación calidad", "asignación sst", "asignación gerencia",
        "asistencia técnica", "asistencia técnica compras", "asistencia técnica ventas", "asistencia técnica contabilidad",
        "asistencia técnica finanzas", "asistencia técnica logística", "asistencia técnica producción", "asistencia técnica recursos humanos",
        "asistencia técnica jurídica", "asistencia técnica tecnología", "asistencia técnica calidad", "asistencia técnica sst",
        "asistencia técnica gerencia", "beneficio", "beneficio compras", "beneficio ventas",
        "beneficio contabilidad", "beneficio finanzas", "beneficio logística", "beneficio producción",
        "beneficio recursos humanos", "beneficio jurídica", "beneficio tecnología", "beneficio calidad",
        "beneficio sst", "beneficio gerencia", "bonificación", "bonificación compras",
        "bonificación ventas", "bonificación contabilidad", "bonificación finanzas", "bonificación logística",
        "bonificación producción", "bonificación recursos humanos", "bonificación jurídica", "bonificación tecnología",
        "bonificación calidad", "bonificación sst", "bonificación gerencia", "cancelación",
        "cancelación compras", "cancelación ventas", "cancelación contabilidad", "cancelación finanzas",
        "cancelación logística", "cancelación producción", "cancelación recursos humanos", "cancelación jurídica",
        "cancelación tecnología", "cancelación calidad", "cancelación sst", "cancelación gerencia",
        "carga laboral", "carga laboral compras", "carga laboral ventas", "carga laboral contabilidad",
        "carga laboral finanzas", "carga laboral logística", "carga laboral producción", "carga laboral recursos humanos",
        "carga laboral jurídica", "carga laboral tecnología", "carga laboral calidad", "carga laboral sst",
        "carga laboral gerencia", "cierre operativo", "cierre operativo compras", "cierre operativo ventas",
        "cierre operativo contabilidad", "cierre operativo finanzas", "cierre operativo logística", "cierre operativo producción",
        "cierre operativo recursos humanos", "cierre operativo jurídica", "cierre operativo tecnología", "cierre operativo calidad",
        "cierre operativo sst", "cierre operativo gerencia", "cobranza", "cobranza compras",
        "cobranza ventas", "cobranza contabilidad", "cobranza finanzas", "cobranza logística",
        "cobranza producción", "cobranza recursos humanos", "cobranza jurídica", "cobranza tecnología",
        "cobranza calidad", "cobranza sst", "cobranza gerencia", "comisión",
        "comisión compras", "comisión ventas", "comisión contabilidad", "comisión finanzas",
        "comisión logística", "comisión producción", "comisión recursos humanos", "comisión jurídica",
        "comisión tecnología", "comisión calidad", "comisión sst", "comisión gerencia",
        "configuración", "configuración compras", "configuración ventas", "configuración contabilidad",
        "configuración finanzas", "configuración logística", "configuración producción", "configuración recursos humanos",
        "configuración jurídica", "configuración tecnología", "configuración calidad", "configuración sst",
        "configuración gerencia", "devolución", "devolución compras", "devolución ventas",
        "devolución contabilidad", "devolución finanzas", "devolución logística", "devolución producción",
        "devolución recursos humanos", "devolución jurídica", "devolución tecnología", "devolución calidad",
        "devolución sst", "devolución gerencia", "distribución", "distribución compras",
        "distribución ventas", "distribución contabilidad", "distribución finanzas", "distribución logística",
        "distribución producción", "distribución recursos humanos", "distribución jurídica", "distribución tecnología",
        "distribución calidad", "distribución sst", "distribución gerencia", "entrevista",
        "entrevista compras", "entrevista ventas", "entrevista contabilidad", "entrevista finanzas",
        "entrevista logística", "entrevista producción", "entrevista recursos humanos", "entrevista jurídica",
        "entrevista tecnología", "entrevista calidad", "entrevista sst", "entrevista gerencia",
        "flujo de caja compras", "flujo de caja ventas", "flujo de caja contabilidad", "flujo de caja finanzas",
        "flujo de caja logística", "flujo de caja producción", "flujo de caja recursos humanos", "flujo de caja jurídica",
        "flujo de caja tecnología", "flujo de caja calidad", "flujo de caja sst", "flujo de caja gerencia",
        "garantía", "garantía compras", "garantía ventas", "garantía contabilidad",
        "garantía finanzas", "garantía logística", "garantía producción", "garantía recursos humanos",
        "garantía jurídica", "garantía tecnología", "garantía calidad", "garantía sst",
        "garantía gerencia", "hoja de vida compras", "hoja de vida ventas", "hoja de vida contabilidad",
        "hoja de vida finanzas", "hoja de vida logística", "hoja de vida producción", "hoja de vida recursos humanos",
        "hoja de vida jurídica", "hoja de vida tecnología", "hoja de vida calidad", "hoja de vida sst",
        "hoja de vida gerencia", "instalación", "instalación compras", "instalación ventas",
        "instalación contabilidad", "instalación finanzas", "instalación logística", "instalación producción",
        "instalación recursos humanos", "instalación jurídica", "instalación tecnología", "instalación calidad",
        "instalación sst", "instalación gerencia", "inventario físico", "inventario físico compras",
        "inventario físico ventas", "inventario físico contabilidad", "inventario físico finanzas", "inventario físico logística",
        "inventario físico producción", "inventario físico recursos humanos", "inventario físico jurídica", "inventario físico tecnología",
        "inventario físico calidad", "inventario físico sst", "inventario físico gerencia", "licencia compras",
        "licencia ventas", "licencia contabilidad", "licencia finanzas", "licencia logística",
        "licencia producción", "licencia recursos humanos", "licencia jurídica", "licencia tecnología",
        "licencia calidad", "licencia sst", "licencia gerencia", "negociación",
        "negociación compras", "negociación ventas", "negociación contabilidad", "negociación finanzas",
        "negociación logística", "negociación producción", "negociación recursos humanos", "negociación jurídica",
        "negociación tecnología", "negociación calidad", "negociación sst", "negociación gerencia",
        "orden de servicio", "orden de servicio compras", "orden de servicio ventas", "orden de servicio contabilidad",
        "orden de servicio finanzas", "orden de servicio logística", "orden de servicio producción", "orden de servicio recursos humanos",
        "orden de servicio jurídica", "orden de servicio tecnología", "orden de servicio calidad", "orden de servicio sst",
        "orden de servicio gerencia", "recepción", "recepción compras", "recepción ventas",
        "recepción contabilidad", "recepción finanzas", "recepción logística", "recepción producción",
        "recepción recursos humanos", "recepción jurídica", "recepción tecnología", "recepción calidad",
        "recepción sst", "recepción gerencia", "requisición", "requisición compras",
        "requisición ventas", "requisición contabilidad", "requisición finanzas", "requisición logística",
        "requisición producción", "requisición recursos humanos", "requisición jurídica", "requisición tecnología",
        "requisición calidad", "requisición sst", "requisición gerencia", "respaldo compras",
        "respaldo ventas", "respaldo contabilidad", "respaldo finanzas", "respaldo logística",
        "respaldo producción", "respaldo recursos humanos", "respaldo jurídica", "respaldo tecnología",
        "respaldo calidad", "respaldo sst", "respaldo gerencia", "seguimiento compras",
        "seguimiento ventas", "seguimiento contabilidad", "seguimiento finanzas", "seguimiento logística",
        "seguimiento producción", "seguimiento recursos humanos", "seguimiento jurídica", "seguimiento tecnología",
        "seguimiento calidad", "seguimiento sst", "seguimiento gerencia", "solicitud",
        "solicitud compras", "solicitud ventas", "solicitud contabilidad", "solicitud finanzas",
        "solicitud logística", "solicitud producción", "solicitud recursos humanos", "solicitud jurídica",
        "solicitud tecnología", "solicitud calidad", "solicitud sst", "solicitud gerencia",
        "soporte remoto", "asistencia remota", "mesa de ayuda", "help desk",
    )),
    ("Extraer", (
        "extrac", "extraer", "extraj", "descarg",
        "recopil", "sacar informacion", "sacar información", "consultar base de datos",
        "buscar informacion", "buscar información", "obtener datos", "encuesta",
        "base de datos", "base de datos administrativa", "base de datos financiera", "base de datos comercial",
        "base de datos operativa", "base de datos logística", "base de datos tecnológica", "base de datos jurídica",
        "base de datos contable", "base de datos recursos humanos", "base de datos calidad", "base de datos sst",
        "encuesta administrativa", "encuesta financiera", "encuesta comercial", "encuesta operativa",
        "encuesta logística", "encuesta tecnológica", "encuesta jurídica", "encuesta contable",
        "encuesta recursos humanos", "encuesta calidad", "encuesta sst", "encuesta de satisfacción",
        "encuesta de satisfacción compras", "encuesta de satisfacción ventas", "encuesta de satisfacción contabilidad", "encuesta de satisfacción finanzas",
        "encuesta de satisfacción logística", "encuesta de satisfacción producción", "encuesta de satisfacción recursos humanos", "encuesta de satisfacción jurídica",
        "encuesta de satisfacción tecnología", "encuesta de satisfacción calidad", "encuesta de satisfacción sst", "encuesta de satisfacción gerencia",
        "levantamiento", "levantamiento compras", "levantamiento ventas", "levantamiento contabilidad",
        "levantamiento finanzas", "levantamiento logística", "levantamiento producción", "levantamiento recursos humanos",
        "levantamiento jurídica", "levantamiento tecnología", "levantamiento calidad", "levantamiento sst",
        "levantamiento gerencia",
    )),
    ("Digitar", (
        "digit", "captur", "ingres", "registr",
        "carg", "aliment", "actualiz", "actualic",
        "subi", "subí", "factur", "asiento contable",
        "diligenciar", "llenar formulario", "asistencia", "balance general",
        "cierre contable", "asistencia administrativa", "asistencia financiera", "asistencia comercial",
        "asistencia operativa", "asistencia logística", "asistencia tecnológica", "asistencia jurídica",
        "asistencia contable", "asistencia recursos humanos", "asistencia calidad", "asistencia sst",
        "balance general administrativa", "balance general financiera", "balance general comercial", "balance general operativa",
        "balance general logística", "balance general tecnológica", "balance general jurídica", "balance general contable",
        "balance general recursos humanos", "balance general calidad", "balance general sst", "cierre contable administrativa",
        "cierre contable financiera", "cierre contable comercial", "cierre contable operativa", "cierre contable logística",
        "cierre contable tecnológica", "cierre contable jurídica", "cierre contable contable", "cierre contable recursos humanos",
        "cierre contable calidad", "cierre contable sst", "factura", "factura administrativa",
        "factura financiera", "factura comercial", "factura operativa", "factura logística",
        "factura tecnológica", "factura jurídica", "factura contable", "factura recursos humanos",
        "factura calidad", "factura sst", "facturación", "facturación administrativa",
        "facturación financiera", "facturación comercial", "facturación operativa", "facturación logística",
        "facturación tecnológica", "facturación jurídica", "facturación contable", "facturación recursos humanos",
        "facturación calidad", "facturación sst", "registro", "registro administrativa",
        "registro financiera", "registro comercial", "registro operativa", "registro logística",
        "registro tecnológica", "registro jurídica", "registro contable", "registro recursos humanos",
        "registro calidad", "registro sst", "actualización", "actualización compras",
        "actualización ventas", "actualización contabilidad", "actualización finanzas", "actualización logística",
        "actualización producción", "actualización recursos humanos", "actualización jurídica", "actualización tecnología",
        "actualización calidad", "actualización sst", "actualización gerencia", "bitácora",
        "bitácora compras", "bitácora ventas", "bitácora contabilidad", "bitácora finanzas",
        "bitácora logística", "bitácora producción", "bitácora recursos humanos", "bitácora jurídica",
        "bitácora tecnología", "bitácora calidad", "bitácora sst", "bitácora gerencia",
        "factura electrónica", "factura electrónica compras", "factura electrónica ventas", "factura electrónica contabilidad",
        "factura electrónica finanzas", "factura electrónica logística", "factura electrónica producción", "factura electrónica recursos humanos",
        "factura electrónica jurídica", "factura electrónica tecnología", "factura electrónica calidad", "factura electrónica sst",
        "factura electrónica gerencia", "registro compras", "registro ventas", "registro contabilidad",
        "registro finanzas", "registro producción", "registro tecnología", "registro gerencia",
    )),
    ("Desarrollar", (
        "desarroll", "programa", "constru", "crear",
        "cree ", "creé", "imprim", "diseñ",
        "diagram", "carnet", "diploma", "codigo",
        "código", "backend", "frontend", "bug",
        "depur", "testeo", "testing", "despliegue",
        "desplegué", "modulo", "módulo", "fotograf",
        "retoc", "retoqu", "edicion de foto", "edición de foto",
        "cubrir evento", "cobertura", "aplicacion", "aplicación",
        "automatizacion", "automatización", "pagina web", "página web",
        "video edicion", "video edición", "montaje", "ingeniero de sistemas",
        "ingeniero de software", "analista de sistemas", "arquitecto de software", "administrador de bases de datos",
        "dba", "diseñador ux", "diseñador ui", "editor de video",
        "editor multimedia", "desarrollo", "desarrollo administrativa", "desarrollo financiera",
        "desarrollo comercial", "desarrollo operativa", "desarrollo logística", "desarrollo tecnológica",
        "desarrollo jurídica", "desarrollo contable", "desarrollo recursos humanos", "desarrollo calidad",
        "desarrollo sst", "desarrollo de software", "desarrollo de software administrativa", "desarrollo de software financiera",
        "desarrollo de software comercial", "desarrollo de software operativa", "desarrollo de software logística", "desarrollo de software tecnológica",
        "desarrollo de software jurídica", "desarrollo de software contable", "desarrollo de software recursos humanos", "desarrollo de software calidad",
        "desarrollo de software sst", "sistema", "sistema administrativa", "sistema financiera",
        "sistema comercial", "sistema operativa", "sistema logística", "sistema tecnológica",
        "sistema jurídica", "sistema contable", "sistema recursos humanos", "sistema calidad",
        "sistema sst", "automatización compras", "automatización ventas", "automatización contabilidad",
        "automatización finanzas", "automatización logística", "automatización producción", "automatización recursos humanos",
        "automatización jurídica", "automatización tecnología", "automatización calidad", "automatización sst",
        "automatización gerencia", "backlog", "backlog compras", "backlog ventas",
        "backlog contabilidad", "backlog finanzas", "backlog logística", "backlog producción",
        "backlog recursos humanos", "backlog jurídica", "backlog tecnología", "backlog calidad",
        "backlog sst", "backlog gerencia", "dashboard", "dashboard compras",
        "dashboard ventas", "dashboard contabilidad", "dashboard finanzas", "dashboard logística",
        "dashboard producción", "dashboard recursos humanos", "dashboard jurídica", "dashboard tecnología",
        "dashboard calidad", "dashboard sst", "dashboard gerencia", "implementación",
        "implementación compras", "implementación ventas", "implementación contabilidad", "implementación finanzas",
        "implementación logística", "implementación producción", "implementación recursos humanos", "implementación jurídica",
        "implementación tecnología", "implementación calidad", "implementación sst", "implementación gerencia",
        "programación", "programación compras", "programación ventas", "programación contabilidad",
        "programación finanzas", "programación logística", "programación producción", "programación recursos humanos",
        "programación jurídica", "programación tecnología", "programación calidad", "programación sst",
        "programación gerencia", "automaticé", "automatice", "robotizar",
        "rpa", "bot de", "proceso automatico", "proceso automático",
        "flujo automatizado",
    )),
    ("Estructurar", (
        "estructur", "armar formato", "definir estructura", "defin",
        "esquemat", "diseñar formato", "plane", "planific",
        "cronograma", "hito", "roadmap", "plan de trabajo",
        "flujo de proceso", "procedimiento", "agenda", "proyecto",
        "agenda administrativa", "agenda financiera", "agenda comercial", "agenda operativa",
        "agenda logística", "agenda tecnológica", "agenda jurídica", "agenda contable",
        "agenda recursos humanos", "agenda calidad", "agenda sst", "planeación",
        "planeación administrativa", "planeación financiera", "planeación comercial", "planeación operativa",
        "planeación logística", "planeación tecnológica", "planeación jurídica", "planeación contable",
        "planeación recursos humanos", "planeación calidad", "planeación sst", "proyecto administrativa",
        "proyecto financiera", "proyecto comercial", "proyecto operativa", "proyecto logística",
        "proyecto tecnológica", "proyecto jurídica", "proyecto contable", "proyecto recursos humanos",
        "proyecto calidad", "proyecto sst", "agenda corporativa", "agenda corporativa compras",
        "agenda corporativa ventas", "agenda corporativa contabilidad", "agenda corporativa finanzas", "agenda corporativa logística",
        "agenda corporativa producción", "agenda corporativa recursos humanos", "agenda corporativa jurídica", "agenda corporativa tecnología",
        "agenda corporativa calidad", "agenda corporativa sst", "agenda corporativa gerencia", "cronograma compras",
        "cronograma ventas", "cronograma contabilidad", "cronograma finanzas", "cronograma logística",
        "cronograma producción", "cronograma recursos humanos", "cronograma jurídica", "cronograma tecnología",
        "cronograma calidad", "cronograma sst", "cronograma gerencia", "estandarización",
        "estandarización compras", "estandarización ventas", "estandarización contabilidad", "estandarización finanzas",
        "estandarización logística", "estandarización producción", "estandarización recursos humanos", "estandarización jurídica",
        "estandarización tecnología", "estandarización calidad", "estandarización sst", "estandarización gerencia",
        "normalización", "normalización compras", "normalización ventas", "normalización contabilidad",
        "normalización finanzas", "normalización logística", "normalización producción", "normalización recursos humanos",
        "normalización jurídica", "normalización tecnología", "normalización calidad", "normalización sst",
        "normalización gerencia", "objetivo", "objetivo compras", "objetivo ventas",
        "objetivo contabilidad", "objetivo finanzas", "objetivo logística", "objetivo producción",
        "objetivo recursos humanos", "objetivo jurídica", "objetivo tecnología", "objetivo calidad",
        "objetivo sst", "objetivo gerencia", "plan de acción", "plan de acción compras",
        "plan de acción ventas", "plan de acción contabilidad", "plan de acción finanzas", "plan de acción logística",
        "plan de acción producción", "plan de acción recursos humanos", "plan de acción jurídica", "plan de acción tecnología",
        "plan de acción calidad", "plan de acción sst", "plan de acción gerencia", "plan estratégico",
        "plan estratégico compras", "plan estratégico ventas", "plan estratégico contabilidad", "plan estratégico finanzas",
        "plan estratégico logística", "plan estratégico producción", "plan estratégico recursos humanos", "plan estratégico jurídica",
        "plan estratégico tecnología", "plan estratégico calidad", "plan estratégico sst", "plan estratégico gerencia",
        "política", "política compras", "política ventas", "política contabilidad",
        "política finanzas", "política logística", "política producción", "política recursos humanos",
        "política jurídica", "política tecnología", "política calidad", "política sst",
        "política gerencia", "procedimiento compras", "procedimiento ventas", "procedimiento contabilidad",
        "procedimiento finanzas", "procedimiento logística", "procedimiento producción", "procedimiento recursos humanos",
        "procedimiento jurídica", "procedimiento tecnología", "procedimiento calidad", "procedimiento sst",
        "procedimiento gerencia",
    )),
]


def _sin_tildes(texto):
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )


# Palabras cortas donde la tilde depende del significado (el/él, si/sí, mas/más,
# tu/tú, esta/está, como/cómo...): a proposito NO se corrigen solas porque
# adivinar mal es peor que dejarlas como las escribio la persona.
_DICCIONARIO_TILDES = {
    "area": "área", "numero": "número", "codigo": "código", "segun": "según",
    "analisis": "análisis", "tecnico": "técnico", "tecnica": "técnica",
    "economico": "económico", "economica": "económica", "juridico": "jurídico",
    "juridica": "jurídica", "logistica": "logística", "politica": "política",
    "estrategico": "estratégico", "estrategica": "estratégica", "unico": "único",
    "unica": "única", "proximo": "próximo", "proxima": "próxima",
    "especifico": "específico", "especifica": "específica", "basico": "básico",
    "basica": "básica", "publico": "público", "publica": "pública",
    "auditoria": "auditoría", "garantia": "garantía", "categoria": "categoría",
    "tesoreria": "tesorería", "modulo": "módulo", "titulo": "título",
    "simbolo": "símbolo", "facil": "fácil", "dificil": "difícil", "util": "útil",
    "nomina": "nómina", "telefono": "teléfono", "maximo": "máximo",
    "minimo": "mínimo", "rapido": "rápido", "articulo": "artículo",
    "kilometro": "kilómetro",
}

_RE_ION = re.compile(r"\b(\w+)ion\b")


def _corregir_tildes_detalle(texto):
    """Arregla tildes faltantes en patrones sin ambiguedad (ej. 'gestion' ->
    'gestión'), pensado para el texto que se pega en el ERP. No toca palabras
    cortas ambiguas ni lo que la persona guardo localmente."""
    texto = _RE_ION.sub(lambda m: m.group(1) + "ión", texto)
    palabras = texto.split(" ")
    for i, palabra in enumerate(palabras):
        limpia = palabra.strip(".,;:()")
        reemplazo = _DICCIONARIO_TILDES.get(limpia.lower())
        if reemplazo is None:
            continue
        if limpia[0].isupper():
            reemplazo = reemplazo[0].upper() + reemplazo[1:]
        palabras[i] = palabra.replace(limpia, reemplazo, 1)
    return " ".join(palabras)


# Precalculado una sola vez (no en cada tecla presionada): asi 'gestion', 'gestión'
# y 'gestion' escrito sin enie tambien coinciden, sin tener que mantener a mano
# cada palabra clave duplicada con y sin tilde.
ACCION_KEYWORDS_SIN_TILDES = [
    (accion, tuple(_sin_tildes(kw) for kw in keywords))
    for accion, keywords in ACCION_KEYWORDS
]


def sugerir_accion(texto):
    texto = _sin_tildes(texto.lower())
    mejor_accion = None
    mejor_pos = None
    mejor_len = 0
    for accion, keywords in ACCION_KEYWORDS_SIN_TILDES:
        for kw in keywords:
            pos = texto.find(kw)
            if pos == -1:
                continue
            if mejor_pos is None or pos < mejor_pos or (pos == mejor_pos and len(kw) > mejor_len):
                mejor_accion, mejor_pos, mejor_len = accion, pos, len(kw)
    return mejor_accion

BG = "#F2F2F7"
CARD_BG = "#FFFFFF"
ROW_BG = "#FAFAFA"
BORDER = "#E5E5EA"
TEXT_PRIMARY = "#1C1C1E"
TEXT_SECONDARY = "#8E8E93"
ACCENT = "#007AFF"
ACCENT_PRESSED = "#0060DF"
ACCENT_LIGHT = "#E8F1FF"
DANGER = "#FF3B30"
DANGER_LIGHT = "#FFEBEA"
SUCCESS = "#34C759"
WARNING = "#FF9500"

F_TITLE = ("Segoe UI Semibold", 22)
F_SUBTITLE = ("Segoe UI", 11)
F_LABEL = ("Segoe UI", 10)
F_CAPTION = ("Segoe UI", 8)
F_LABEL_BOLD = ("Segoe UI Semibold", 10)
F_BUTTON = ("Segoe UI Semibold", 10)
F_STAT_BIG = ("Segoe UI Semibold", 30)
F_STAT_LABEL = ("Segoe UI Semibold", 13)


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


APP_VERSION = "1.5.7"
UPDATE_REPO = "AlexxAlmeida18/Bitacora-Diaria"

NOTIF_TASK_NAME = "BitacoraDiaria Recordatorios"
POWERSHELL_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
HEARTBEAT_MAX_EDAD_SEG = 10 * 60  # la app viva actualiza el heartbeat cada 5 min

TOAST_TEMPLATE = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$Template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{msg}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($Template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{aumid}').Show($toast)
"""


def _mostrar_toast(title, msg):
    script = TOAST_TEMPLATE.format(title=title, msg=msg, aumid=POWERSHELL_AUMID)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _parse_minutos(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _asegurar_tarea_programada():
    """Registra (si hace falta) la tarea de Windows que revisa recordatorios cada 15 min
    aunque la app esté cerrada. Se auto-repara si apunta a un ejecutable/ruta viejos."""
    if getattr(sys, "frozen", False):
        comando = f'"{sys.executable}" --notificar'
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        comando = f'"{pyw}" "{os.path.abspath(__file__)}" --notificar'

    try:
        existente = subprocess.run(
            ["schtasks", "/query", "/tn", NOTIF_TASK_NAME, "/fo", "LIST", "/v"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if existente.returncode == 0 and comando in existente.stdout:
            return  # ya está registrada y apunta al ejecutable correcto

        usuario = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"
        subprocess.run(
            ["schtasks", "/create", "/tn", NOTIF_TASK_NAME, "/tr", comando,
             "/sc", "MINUTE", "/mo", "15", "/ru", usuario, "/it", "/f"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        pass


def _version_mayor(a, b):
    def norm(v):
        partes = []
        for p in v.split("."):
            try:
                partes.append(int(p))
            except ValueError:
                partes.append(0)
        return tuple(partes)
    return norm(a) > norm(b)


def _consultar_ultima_release():
    url = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "BitacoraDiaria"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        info = json.load(resp)
    tag = info.get("tag_name", "").lstrip("vV")
    zip_url = None
    for asset in info.get("assets", []):
        if asset.get("name", "").lower().endswith(".zip"):
            zip_url = asset.get("browser_download_url")
            break
    return tag, zip_url


def revisar_recordatorio_en_segundo_plano():
    """Modo sin interfaz (--notificar): pensado para que lo dispare el Programador de
    tareas de Windows cada 15 min, aunque la app principal esté cerrada."""
    if os.path.exists(HEARTBEAT_FILE):
        edad = datetime.now().timestamp() - os.path.getmtime(HEARTBEAT_FILE)
        if edad < HEARTBEAT_MAX_EDAD_SEG:
            return  # la app ya está abierta y muestra sus propios recordatorios

    hoy = date.today().isoformat()
    estado = load_json(NOTIF_STATE_FILE, {})
    if estado.get("fecha") != hoy:
        estado = {"fecha": hoy, "umbral": 0, "pausada": False}

    if estado.get("pausada"):
        save_json(NOTIF_STATE_FILE, estado)
        return

    ahora = datetime.now()
    ahora_min = ahora.hour * 60 + ahora.minute
    en_horario = (7 * 60 + 30 <= ahora_min <= 12 * 60) or (14 * 60 <= ahora_min <= 17 * 60)
    if not en_horario:
        save_json(NOTIF_STATE_FILE, estado)
        return

    data = load_json(DATA_FILE, {})
    entrada = data.get(hoy, {})
    candidatos = [act["fin"] for act in entrada.get("activities", []) if act.get("fin")]
    ultima_fin = max(candidatos, key=_parse_minutos) if candidatos else None
    ultima_fin_min = _parse_minutos(ultima_fin) if ultima_fin else 7 * 60 + 30
    gap = ahora_min - ultima_fin_min

    if gap < 60:
        estado["umbral"] = 0
        save_json(NOTIF_STATE_FILE, estado)
        return

    umbral_actual = (gap // 60) * 60
    if umbral_actual > estado.get("umbral", 0):
        estado["umbral"] = umbral_actual
        if ultima_fin:
            msg = f"No has registrado actividad desde las {ultima_fin}. ¿Qué has hecho desde entonces?"
        else:
            msg = "Aún no has registrado ninguna actividad hoy."
        _mostrar_toast("⏰ Bitácora", msg)

    save_json(NOTIF_STATE_FILE, estado)


def round_rect_points(x1, y1, x2, y2, radius):
    return [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]


class RoundedCard(tk.Frame):
    def __init__(self, parent, page_bg=BG, fill=CARD_BG, radius=16, **kwargs):
        super().__init__(parent, bg=page_bg, highlightthickness=0, **kwargs)
        self.fill = fill
        self.radius = radius
        self.canvas = tk.Canvas(self, bg=page_bg, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=fill)
        self._window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync)
        self.canvas.bind("<Configure>", self._sync)

    def _sync(self, _event=None):
        w = max(self.canvas.winfo_width(), self.inner.winfo_reqwidth())
        h = self.inner.winfo_reqheight()
        self.canvas.itemconfig(self._window, width=w)
        self.canvas.config(height=h)
        self.canvas.delete("bg")
        if w > 4 and h > 4:
            self.canvas.create_polygon(
                round_rect_points(1, 1, w - 1, h - 1, self.radius),
                smooth=True, fill=self.fill, outline=BORDER, tags="bg",
            )
            self.canvas.tag_lower("bg")


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, bg=ACCENT, fg="white",
                 hover=None, width=140, height=36, radius=None, font=F_BUTTON, page_bg=BG):
        super().__init__(parent, width=width, height=height, bg=page_bg, highlightthickness=0)
        self.command = command
        self.bg_color = bg
        self.hover_color = hover or bg
        self.fg = fg
        self.text = text
        self.font = font
        self.w = width
        self.h = height
        self.radius = radius if radius is not None else height // 2
        self.enabled = True
        self._paint(self.bg_color)
        self.bind("<Button-1>", lambda e: self.command() if self.command and self.enabled else None)
        self.bind("<Enter>", lambda e: self._paint(self.hover_color) if self.enabled else None)
        self.bind("<Leave>", lambda e: self._paint(self.bg_color) if self.enabled else None)
        self.configure(cursor="hand2")

    def _paint(self, color, fg=None):
        self.delete("all")
        self.create_polygon(
            round_rect_points(1, 1, self.w - 1, self.h - 1, self.radius),
            smooth=True, fill=color, outline=color,
        )
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=fg or self.fg, font=self.font)

    def set_text(self, text):
        self.text = text
        self._paint(self.bg_color if self.enabled else "#E3E6EA", fg=self.fg if self.enabled else "#9AA3AD")

    def set_enabled(self, enabled):
        if self.enabled == enabled:
            return
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._paint(self.bg_color if enabled else "#E3E6EA", fg=self.fg if enabled else "#9AA3AD")


CHROMIUM_FAST_ARGS = [
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-client-side-phishing-detection",
    "--disable-default-apps",
    "--no-first-run",
    "--no-default-browser-check",
]


def _driver_con_opciones(driver_cls, options_cls, argumentos=None):
    options = options_cls()
    options.page_load_strategy = "eager"
    for arg in argumentos or []:
        options.add_argument(arg)
    return driver_cls(options=options)


def crear_driver():
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions

    intentos = [
        ("Edge", lambda: _driver_con_opciones(webdriver.Edge, EdgeOptions, CHROMIUM_FAST_ARGS)),
        ("Chrome", lambda: _driver_con_opciones(webdriver.Chrome, ChromeOptions, CHROMIUM_FAST_ARGS)),
        ("Firefox", lambda: _driver_con_opciones(webdriver.Firefox, FirefoxOptions)),
    ]
    errores = []
    for nombre, factory in intentos:
        try:
            return factory(), nombre
        except Exception as exc:
            errores.append(f"{nombre}: {exc}")
    detalle_errores = "\n".join(errores)
    raise RuntimeError(
        "No se encontró un navegador compatible instalado (se probó Chrome, Edge y Firefox).\n"
        f"{detalle_errores}"
    )


def fill_erp_form(driver, cedula, tipo, accion, detalle, inicio, fin):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    driver.maximize_window()
    driver.get(ERP_URL)
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.ID, "input_58_1")))

    def set_text(elem_id, value):
        el = driver.find_element(By.ID, elem_id)
        el.clear()
        if value:
            el.send_keys(value)

    cedula_el = driver.find_element(By.ID, "input_58_1")
    cedula_el.clear()
    cedula_el.send_keys(cedula)
    cedula_el.send_keys(Keys.TAB)

    try:
        driver.switch_to.alert.accept()
    except Exception:
        pass

    def _nombre_autocompletado(d):
        try:
            return d.find_element(By.ID, "input_58_3").get_attribute("value").strip() != ""
        except Exception:
            return False

    try:
        WebDriverWait(driver, 5, poll_frequency=0.25).until(_nombre_autocompletado)
    except TimeoutException:
        pass

    set_text("input_58_6", _corregir_tildes_detalle(detalle))

    if tipo in TIPO_ACTIVIDAD_OPTIONS:
        idx = TIPO_ACTIVIDAD_OPTIONS.index(tipo)
        driver.find_element(By.ID, f"choice_58_5_{idx}").click()

    if accion in ACCION_OPTIONS:
        idx = ACCION_OPTIONS.index(accion)
        driver.find_element(By.ID, f"choice_58_10_{idx}").click()

    if inicio:
        Select(driver.find_element(By.ID, "input_58_12")).select_by_value(inicio)
    if fin:
        Select(driver.find_element(By.ID, "input_58_13")).select_by_value(fin)


class ActivityRow:
    def __init__(self, parent, on_remove, on_pegar, page_bg=CARD_BG, on_tipo_change=None, on_fin_change=None,
                 on_change=None):
        self.page_bg = page_bg
        self.on_change = on_change
        self.expanded = True
        self.enviado = False
        self.frame = tk.Frame(parent, bg=page_bg)

        header = tk.Frame(self.frame, bg=page_bg)
        header.pack(fill="x", pady=(8, 0))
        self.toggle_btn = tk.Label(header, text="▾", font=("Segoe UI", 12), bg=page_bg,
                                    fg=TEXT_SECONDARY, cursor="hand2", width=2)
        self.toggle_btn.pack(side="left")
        self.toggle_btn.bind("<Button-1>", lambda e: self.toggle())
        self.badge_var = tk.StringVar(value="")
        tk.Label(header, textvariable=self.badge_var, font=("Segoe UI Semibold", 8),
                 bg=page_bg, fg=SUCCESS).pack(side="left", padx=(0, 6))
        self.resumen_var = tk.StringVar(value="")
        self.resumen_label = tk.Label(header, textvariable=self.resumen_var, font=F_LABEL,
                                       bg=page_bg, fg=TEXT_PRIMARY, anchor="w", cursor="hand2")
        self.resumen_label.bind("<Button-1>", lambda e: self.toggle())

        self.body = tk.Frame(self.frame, bg=page_bg)
        self.body.pack(fill="x")
        pad = dict(padx=4, pady=(2, 0))

        r0 = tk.Frame(self.body, bg=page_bg)
        r0.pack(fill="x", pady=(6, 2))
        self.inicio = self._field(r0, "Inicio", "combo", TIME_OPTIONS, width=7, page_bg=page_bg)
        self.fin = self._field(r0, "Fin", "combo", TIME_OPTIONS, width=7, page_bg=page_bg)
        self.tipo = self._field(r0, "Tipo de actividad", "combo", TIPO_ACTIVIDAD_OPTIONS, width=26, page_bg=page_bg)
        self.accion = self._field(r0, "Acción (sugerida al escribir el detalle)", "combo", ACCION_OPTIONS, width=16, page_bg=page_bg)

        r1 = tk.Frame(self.body, bg=page_bg)
        r1.pack(fill="x", pady=2)
        self.detalle = self._field(r1, "Detalle", "entry", None, width=60, page_bg=page_bg, expand=True)

        if on_tipo_change:
            self.tipo.bind("<<ComboboxSelected>>", lambda e: on_tipo_change(self.tipo.get()))
        if on_fin_change:
            self.fin.bind("<<ComboboxSelected>>", lambda e: on_fin_change(self.fin.get()))
        self.detalle.bind("<KeyRelease>", self._on_detalle_key)
        if self.on_change:
            for widget in (self.inicio, self.fin, self.tipo, self.accion):
                widget.bind("<<ComboboxSelected>>", lambda e: self.on_change(), add="+")
            self.detalle.bind("<KeyRelease>", lambda e: self.on_change(), add="+")

        r3 = tk.Frame(self.body, bg=page_bg)
        r3.pack(fill="x", pady=(4, 8))
        self.pegar_btn = RoundedButton(r3, "Pegar en ERP", command=lambda: on_pegar(self),
                                        bg=ACCENT_LIGHT, fg=ACCENT, hover="#D6E9FF",
                                        width=120, height=30, radius=15, page_bg=page_bg)
        self.pegar_btn.pack(side="left")
        self.remove_btn = RoundedButton(r3, "Quitar", command=lambda: on_remove(self),
                                         bg=DANGER_LIGHT, fg=DANGER, hover="#FFD9D6",
                                         width=70, height=30, radius=15, page_bg=page_bg)
        self.remove_btn.pack(side="left", padx=8)

        self.separator = tk.Frame(parent, bg=BORDER, height=1)

    def toggle(self):
        self.expanded = not self.expanded
        self._refresh_visibility()

    def _refresh_visibility(self):
        if self.expanded:
            self.toggle_btn.config(text="▾")
            self.resumen_label.pack_forget()
            self.body.pack(fill="x")
        else:
            self.toggle_btn.config(text="▸")
            self._actualizar_resumen()
            self.body.pack_forget()
            self.resumen_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def _actualizar_resumen(self):
        d = self.get()
        rango = f"{d['inicio']}–{d['fin']}" if d["inicio"] or d["fin"] else ""
        detalle_corto = d["detalle"][:70] + ("…" if len(d["detalle"]) > 70 else "")
        partes = [p for p in [rango, d["tipo"], detalle_corto] if p]
        self.resumen_var.set("  ·  ".join(partes) if partes else "(actividad vacía)")

    def marcar_enviado(self):
        self.enviado = True
        self.badge_var.set("✓ Enviado")
        if self.expanded:
            self.toggle()
        if self.on_change:
            self.on_change()

    def _field(self, parent, label, kind, values, width, page_bg, expand=False):
        wrap = tk.Frame(parent, bg=page_bg)
        wrap.pack(side="left", padx=(0, 10), fill="x" if expand else None, expand=expand)
        tk.Label(wrap, text=label, font=F_CAPTION, bg=page_bg, fg=TEXT_SECONDARY).pack(anchor="w")
        if kind == "combo":
            widget = ttk.Combobox(wrap, width=width, state="readonly", values=values,
                                   style="Modern.TCombobox", font=F_LABEL)
        else:
            widget = ttk.Entry(wrap, width=width, style="Modern.TEntry", font=F_LABEL)
        widget.pack(fill="x" if expand else None)
        return widget

    def _on_detalle_key(self, _event):
        sugerido = sugerir_accion(self.detalle.get())
        if sugerido:
            self.accion.set(sugerido)

    def pack(self):
        self.frame.pack(fill="x", padx=4)
        self.separator.pack(fill="x", padx=4)

    def set(self, data):
        self.inicio.set(data.get("inicio", ""))
        self.fin.set(data.get("fin", ""))
        self.tipo.set(data.get("tipo", ""))
        self.accion.set(data.get("accion", ""))
        self.detalle.delete(0, tk.END)
        self.detalle.insert(0, data.get("detalle", ""))
        if data.get("enviado"):
            self.marcar_enviado()

    def get(self):
        return {
            "inicio": self.inicio.get().strip(),
            "fin": self.fin.get().strip(),
            "tipo": self.tipo.get().strip(),
            "accion": self.accion.get().strip(),
            "detalle": self.detalle.get().strip(),
            "enviado": self.enviado,
        }

    def destroy(self):
        self.frame.destroy()
        self.separator.destroy()


class BitacoraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Bitácora Diaria - Datadiscol")
        self.root.configure(bg=BG)
        if os.path.exists(ICON_FILE):
            try:
                self.root.iconbitmap(ICON_FILE)
            except Exception:
                pass

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = min(900, screen_w - 60)
        win_h = min(780, screen_h - 100)
        pos_x = max(0, (screen_w - win_w) // 2)
        pos_y = max(0, (screen_h - win_h) // 2)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(520, 400)

        self.data = load_json(DATA_FILE, {})
        self.config = load_json(CONFIG_FILE, {"cedula": ""})
        self.rows = []
        self.driver = None
        self.driver_nombre = None
        self.driver_lock = threading.Lock()
        self.pegando_en_erp = False
        self.overlay = None

        self._setup_style()

        outer_canvas = tk.Canvas(root, bg=BG, borderwidth=0, highlightthickness=0)
        outer_scroll = ttk.Scrollbar(root, orient="vertical", command=outer_canvas.yview,
                                      style="Modern.Vertical.TScrollbar")
        outer_canvas.configure(yscrollcommand=outer_scroll.set)
        outer_canvas.pack(side="left", fill="both", expand=True)
        outer_scroll.pack(side="right", fill="y")

        content = tk.Frame(outer_canvas, bg=BG)
        content_window = outer_canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: outer_canvas.configure(scrollregion=outer_canvas.bbox("all")))
        outer_canvas.bind("<Configure>", lambda e: outer_canvas.itemconfig(content_window, width=e.width))

        def _on_wheel(event):
            outer_canvas.yview_scroll(int(-event.delta / 120), "units")

        outer_canvas.bind("<Enter>", lambda e: outer_canvas.bind_all("<MouseWheel>", _on_wheel))
        outer_canvas.bind("<Leave>", lambda e: outer_canvas.unbind_all("<MouseWheel>"))

        def _combobox_wheel(event):
            _on_wheel(event)
            return "break"

        self.root.bind_class("TCombobox", "<MouseWheel>", _combobox_wheel)

        header = tk.Frame(content, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 12))

        header_top = tk.Frame(header, bg=BG)
        header_top.pack(fill="x")

        header_izq = tk.Frame(header_top, bg=BG)
        header_izq.pack(side="left", fill="both", expand=True)
        titulo_fila = tk.Frame(header_izq, bg=BG)
        titulo_fila.pack(fill="x", anchor="w")
        tk.Label(titulo_fila, text="Bitácora diaria", font=F_TITLE, bg=BG, fg=TEXT_PRIMARY).pack(side="left")
        self.reloj_var = tk.StringVar(value="")
        tk.Label(titulo_fila, textvariable=self.reloj_var, font=("Segoe UI Semibold", 16),
                 bg=BG, fg=ACCENT).pack(side="left", padx=(16, 0))
        tk.Label(header_izq, text="Datadiscol · registra tu día y envíalo al ERP", font=F_SUBTITLE,
                 bg=BG, fg=TEXT_SECONDARY).pack(anchor="w")
        stats = tk.Frame(header_izq, bg=BG)
        stats.pack(fill="x", pady=(14, 0))

        def _stat_tile(valor_var, caption, font_valor=F_STAT_LABEL, fg_valor=TEXT_PRIMARY):
            tile = tk.Frame(stats, bg=BG)
            tk.Label(tile, textvariable=valor_var, font=font_valor, bg=BG, fg=fg_valor).pack(anchor="w")
            tk.Label(tile, text=caption, font=F_CAPTION, bg=BG, fg=TEXT_SECONDARY).pack(anchor="w")
            return tile

        self.total_actividades_var = tk.StringVar(value="0")
        self.mes_actual_var = tk.StringVar(value="")
        self.ultima_hora_var = tk.StringVar(value="--:--")

        _stat_tile(self.total_actividades_var, "actividades registradas",
                   font_valor=F_STAT_BIG, fg_valor=ACCENT).pack(side="left", padx=(0, 36))
        _stat_tile(self.mes_actual_var, "mes actual").pack(side="left", padx=(0, 36))
        _stat_tile(self.ultima_hora_var, "última hora registrada").pack(side="left")

        header_der = tk.Frame(header_top, bg=BG)
        header_der.pack(side="right", anchor="ne")
        self._build_cumplimiento_compacto(header_der)

        card_datos = RoundedCard(content, page_bg=BG)
        card_datos.pack(fill="x", padx=24, pady=8)
        self._build_datos_card(card_datos.inner)

        card_actividades = RoundedCard(content, page_bg=BG)
        card_actividades.pack(fill="x", padx=24, pady=8)
        self._build_actividades_card(card_actividades.inner)

        actions = tk.Frame(content, bg=BG)
        actions.pack(fill="x", padx=24, pady=(4, 8))
        RoundedButton(actions, "Guardar día", command=self.guardar_dia,
                      bg=ACCENT, fg="white", hover=ACCENT_PRESSED,
                      width=160, height=40, radius=20, page_bg=BG).pack(side="left")
        self.autoguardado_var = tk.StringVar(value="")
        tk.Label(actions, textvariable=self.autoguardado_var, font=F_CAPTION, bg=BG, fg=TEXT_SECONDARY)\
            .pack(side="left", padx=(12, 0))

        self.status_var = tk.StringVar(value="")
        tk.Label(content, textvariable=self.status_var, font=F_LABEL, bg=BG, fg=SUCCESS,
                 wraplength=760, justify="left").pack(anchor="w", padx=28, pady=(0, 20))

        hoy = date.today().isoformat()
        if hoy in self.data:
            self.cargar_dia(hoy)
        else:
            self.agregar_fila()
        self.actualizar_contador()
        self.actualizar_cumplimiento_mensual()

        self._tocar_heartbeat()
        self._actualizar_reloj()
        self._autoguardado_job = None
        self.root.after(30000, self._tick_autoguardado)
        self.root.after(60000, self._tick_periodico)
        threading.Thread(target=_asegurar_tarea_programada, daemon=True).start()
        threading.Thread(target=self._revisar_actualizaciones, daemon=True).start()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Modern.TEntry", fieldbackground="white", background="white",
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                         foreground=TEXT_PRIMARY, padding=6, relief="flat")
        style.map("Modern.TEntry", bordercolor=[("focus", ACCENT)])

        style.configure("Modern.TCombobox", fieldbackground="white", background="white",
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                         foreground=TEXT_PRIMARY, arrowcolor=TEXT_SECONDARY, padding=6, relief="flat")
        style.map("Modern.TCombobox", bordercolor=[("focus", ACCENT)],
                  fieldbackground=[("readonly", "white")])

        self.root.option_add("*TCombobox*Listbox.font", F_LABEL)
        self.root.option_add("*TCombobox*Listbox.background", "white")
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")

        style.configure("Modern.Vertical.TScrollbar", background=BORDER, troughcolor=CARD_BG,
                         bordercolor=CARD_BG, arrowcolor=TEXT_SECONDARY, relief="flat")

    def _build_cumplimiento_compacto(self, parent):
        ancho_barra = 190

        def _fila_barra(titulo):
            tk.Frame(parent, bg=BG, height=6).pack()
            cab = tk.Frame(parent, bg=BG)
            cab.pack(fill="x")
            tk.Label(cab, text=titulo, font=F_CAPTION, bg=BG, fg=TEXT_SECONDARY).pack(side="left")
            estado_var = tk.StringVar(value="")
            estado_label = tk.Label(cab, textvariable=estado_var, font=("Segoe UI Semibold", 8), bg=BG)
            estado_label.pack(side="right")
            canvas = tk.Canvas(parent, width=ancho_barra, height=8, bg=BG, highlightthickness=0)
            canvas.pack(anchor="e", pady=(2, 0))
            detalle_var = tk.StringVar(value="")
            tk.Label(parent, textvariable=detalle_var, font=F_CAPTION, bg=BG, fg=TEXT_SECONDARY,
                     anchor="e").pack(anchor="e")
            return canvas, estado_var, estado_label, detalle_var

        (self.cumplimiento_canvas, self.cumplimiento_estado_var,
         self.cumplimiento_estado_label, self.cumplimiento_detalle_var) = _fila_barra("Horas de hoy")

    def _dibujar_barra(self, canvas, ratio, color=None):
        canvas.delete("all")
        w = int(str(canvas["width"]))
        h = int(str(canvas["height"]))
        radio = h // 2
        canvas.create_polygon(round_rect_points(1, 1, w - 1, h - 1, radio),
                               smooth=True, fill=BORDER, outline=BORDER)
        if color is None:
            color = SUCCESS if ratio >= 1.0 else DANGER
        fill_w = min(w - 2, max(0, w * min(ratio, 1.0)))
        if fill_w > h:
            canvas.create_polygon(round_rect_points(1, 1, 1 + fill_w, h - 1, radio),
                                   smooth=True, fill=color, outline=color)

    def _actualizar_reloj(self):
        self.reloj_var.set(datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._actualizar_reloj)

    @staticmethod
    def _nivel_3(ratio, umbral_regular=0.9, umbral_excelente=1.0):
        if ratio >= umbral_excelente:
            return "Excelente", SUCCESS
        if ratio >= umbral_regular:
            return "Regular", WARNING
        return "Mal", DANGER

    def actualizar_cumplimiento_mensual(self):
        hoy = date.today()
        horas_esperadas_hoy = horas_esperadas_dia(hoy)

        if horas_esperadas_hoy <= 0:
            self._cumplimiento_ratio = 0.0
            self.cumplimiento_detalle_var.set("Día no laboral")
            self.cumplimiento_estado_var.set("")
            self.cumplimiento_estado_label.config(fg=TEXT_SECONDARY)
            self._dibujar_barra(self.cumplimiento_canvas, 0.0, BORDER)
            return

        horas_registradas = 0.0
        entrada = self.data.get(hoy.isoformat(), {})
        for act in entrada.get("activities", []):
            ini = self._minutos(act.get("inicio", ""))
            fin = self._minutos(act.get("fin", ""))
            if ini is not None and fin is not None and fin > ini:
                horas_registradas += (fin - ini) / 60

        self._cumplimiento_ratio = horas_registradas / horas_esperadas_hoy

        self.cumplimiento_detalle_var.set(f"{horas_registradas:.1f}h / {horas_esperadas_hoy:.1f}h")
        nivel, color = self._nivel_3(self._cumplimiento_ratio)
        self.cumplimiento_estado_var.set(nivel)
        self.cumplimiento_estado_label.config(fg=color)

        self._dibujar_barra(self.cumplimiento_canvas, self._cumplimiento_ratio, color)

    def _build_datos_card(self, parent):
        parent.configure(padx=20, pady=18)

        identidad = tk.Frame(parent, bg=CARD_BG)
        identidad.pack(fill="x", pady=(0, 12))
        tk.Label(identidad, text="Cédula", font=F_CAPTION, bg=CARD_BG, fg=TEXT_SECONDARY).grid(row=0, column=0, sticky="w")
        tk.Label(identidad, text="El ERP llena Nombre y Proyecto/Área solo, al detectar la cédula", font=F_CAPTION,
                 bg=CARD_BG, fg=TEXT_SECONDARY).grid(row=0, column=1, sticky="w", padx=(24, 0))
        self.cedula_var = tk.StringVar(value=self.config.get("cedula", ""))
        cedula_entry = ttk.Entry(identidad, textvariable=self.cedula_var, width=18, style="Modern.TEntry", font=F_LABEL)
        cedula_entry.grid(row=1, column=0, sticky="w")
        cedula_entry.bind("<FocusOut>", lambda e: self.guardar_config())

        fila = tk.Frame(parent, bg=CARD_BG)
        fila.pack(fill="x")
        tk.Label(fila, text="Fecha", font=F_CAPTION, bg=CARD_BG, fg=TEXT_SECONDARY).grid(row=0, column=0, sticky="w")
        tk.Label(fila, text="Días guardados", font=F_CAPTION, bg=CARD_BG, fg=TEXT_SECONDARY).grid(row=0, column=1, sticky="w", padx=(24, 0))

        self.fecha_var = tk.StringVar(value=date.today().isoformat())
        self.fecha_entry = ttk.Entry(fila, textvariable=self.fecha_var, width=14,
                                      style="Modern.TEntry", font=F_LABEL)
        self.fecha_entry.grid(row=1, column=0, sticky="w")

        self.historial_combo = ttk.Combobox(fila, width=14, state="readonly",
                                             style="Modern.TCombobox", font=F_LABEL)
        self.historial_combo.grid(row=1, column=1, sticky="w", padx=(24, 0))
        self.refresh_historial()

        btns = tk.Frame(fila, bg=CARD_BG)
        btns.grid(row=1, column=2, sticky="e", padx=(24, 0))
        RoundedButton(btns, "Cargar día", command=lambda: self.cargar_dia(),
                      bg=ACCENT_LIGHT, fg=ACCENT, hover="#D6E9FF",
                      width=100, height=32, radius=16, page_bg=CARD_BG).pack(side="left", padx=4)
        RoundedButton(btns, "Ver día", command=lambda: self.ver_dia(),
                      bg="#F2F2F7", fg=TEXT_PRIMARY, hover="#E5E5EA",
                      width=90, height=32, radius=16, page_bg=CARD_BG).pack(side="left", padx=4)
        RoundedButton(btns, "Reporte semanal", command=lambda: self.reporte_semanal(),
                      bg="#F2F2F7", fg=TEXT_PRIMARY, hover="#E5E5EA",
                      width=130, height=32, radius=16, page_bg=CARD_BG).pack(side="left", padx=4)
        RoundedButton(btns, "Día nuevo", command=self.dia_nuevo,
                      bg="#F2F2F7", fg=TEXT_PRIMARY, hover="#E5E5EA",
                      width=100, height=32, radius=16, page_bg=CARD_BG).pack(side="left", padx=4)
        fila.columnconfigure(2, weight=1)

    def _build_actividades_card(self, parent):
        parent.configure(padx=20, pady=18)
        tk.Label(parent, text="Actividades del día", font=F_LABEL_BOLD, bg=CARD_BG, fg=TEXT_PRIMARY)\
            .pack(anchor="w", pady=(0, 10))

        self.rows_frame = tk.Frame(parent, bg=CARD_BG)
        self.rows_frame.pack(fill="x", pady=(0, 10))

        RoundedButton(parent, "+  Agregar actividad", command=self.agregar_fila,
                      bg="#F2F2F7", fg=ACCENT, hover=ACCENT_LIGHT,
                      width=180, height=34, radius=17, page_bg=CARD_BG).pack(anchor="w")

    def actualizar_contador(self):
        total = sum(len(entrada.get("activities", [])) for entrada in self.data.values())
        self.total_actividades_var.set(str(total))

        hoy = date.today()
        self.mes_actual_var.set(f"{MESES[hoy.month - 1]} {hoy.year}")

        self.ultima_hora_var.set(self._ultima_hora_registrada() or "--:--")

    def _ultima_hora_registrada(self):
        for fecha in sorted(self.data.keys(), reverse=True):
            actividades = self.data[fecha].get("activities", [])
            for act in reversed(actividades):
                if act.get("fin"):
                    return act["fin"]
        return None

    @staticmethod
    def _tocar_heartbeat():
        try:
            with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
                f.write(datetime.now().isoformat())
        except OSError:
            pass

    def _revisar_actualizaciones(self):
        if not getattr(sys, "frozen", False):
            return
        try:
            tag, zip_url = _consultar_ultima_release()
        except Exception:
            return
        if not tag or not zip_url or not _version_mayor(tag, APP_VERSION):
            return
        self.root.after(0, lambda: self._ofrecer_actualizacion(tag, zip_url))

    def _ofrecer_actualizacion(self, tag, zip_url):
        if not messagebox.askyesno(
                "Bitácora",
                f"Hay una nueva versión disponible (v{tag}, tienes v{APP_VERSION}).\n"
                "¿Actualizar y reiniciar la app ahora?"):
            return
        self.status_var.set("Descargando actualización…")
        self._mostrar_overlay("Descargando actualización…\nLa app se va a reiniciar sola.")
        threading.Thread(target=self._descargar_e_instalar, args=(zip_url,), daemon=True).start()

    def _descargar_e_instalar(self, zip_url):
        try:
            tmp_dir = tempfile.mkdtemp(prefix="bitacora_update_")
            zip_path = os.path.join(tmp_dir, "update.zip")
            req = urllib.request.Request(zip_url, headers={"User-Agent": "BitacoraDiaria"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, "wb") as f:
                f.write(resp.read())

            extract_dir = os.path.join(tmp_dir, "extraido")
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(extract_dir)

            origen = os.path.join(extract_dir, "BitacoraDiaria")
            if not os.path.isdir(origen):
                raise RuntimeError("El paquete de actualización no tiene el formato esperado.")

            bat_path = os.path.join(tmp_dir, "actualizar.bat")
            exe_path = os.path.join(APP_DIR, "BitacoraDiaria.exe")
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(
                    "@echo off\r\n"
                    "chcp 65001 > NUL\r\n"
                    "timeout /t 3 /nobreak > NUL\r\n"
                    f'robocopy "{origen}" "{APP_DIR}" /E /R:5 /W:1 > NUL\r\n'
                    f'start "" "{exe_path}"\r\n'
                    f'rmdir /s /q "{tmp_dir}"\r\n'
                )
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            self.root.after(0, self.root.destroy)
        except Exception as exc:
            msg = str(exc)
            self.root.after(0, self._ocultar_overlay)
            self.root.after(0, lambda: messagebox.showerror("Bitácora", f"No se pudo actualizar:\n{msg}"))
            self.root.after(0, lambda: self.status_var.set(""))

    def _tick_periodico(self):
        self.root.after(5 * 60 * 1000, self._tick_periodico)
        self._tocar_heartbeat()
        self.actualizar_cumplimiento_mensual()

    def _semanas_disponibles(self):
        lunes_set = set()
        for fecha_str, entrada in self.data.items():
            if not entrada.get("activities"):
                continue
            try:
                d = date.fromisoformat(fecha_str)
            except ValueError:
                continue
            lunes_set.add(d - timedelta(days=d.weekday()))
        return sorted(lunes_set, reverse=True)

    def refresh_historial(self):
        dias = sorted(self.data.keys(), reverse=True)
        self.historial_combo["values"] = dias
        if dias:
            self.historial_combo.current(0)

    def agregar_fila(self, data=None):
        if data is None:
            for fila in self.rows:
                if fila.expanded:
                    fila.toggle()
        row = ActivityRow(self.rows_frame, self.quitar_fila, self.pegar_en_erp,
                           on_tipo_change=self.on_tipo_change, on_fin_change=self.on_fin_change,
                           on_change=self._programar_autoguardado)
        row.pack()
        if data:
            row.set(data)
        elif self.config.get("last_tipo"):
            row.tipo.set(self.config["last_tipo"])
        self.rows.append(row)

    def on_tipo_change(self, value):
        if value:
            self.config["last_tipo"] = value
            save_json(CONFIG_FILE, self.config)

    def on_fin_change(self, _value):
        self._actualizar_ultima_hora_en_vivo()

    def _actualizar_ultima_hora_en_vivo(self):
        for row in reversed(self.rows):
            fin = row.fin.get().strip()
            if fin:
                self.ultima_hora_var.set(fin)
                self.actualizar_cumplimiento_mensual()
                return
        self.ultima_hora_var.set(self._ultima_hora_registrada() or "--:--")
        self.actualizar_cumplimiento_mensual()

    def quitar_fila(self, row):
        row.destroy()
        self.rows.remove(row)
        self._actualizar_ultima_hora_en_vivo()
        self._programar_autoguardado()

    def limpiar_filas(self):
        for row in self.rows:
            row.destroy()
        self.rows = []

    def dia_nuevo(self):
        self._cancelar_autoguardado_pendiente()
        self.fecha_var.set(date.today().isoformat())
        self.limpiar_filas()
        self.agregar_fila()
        self.status_var.set("")

    def cargar_dia(self, fecha=None):
        self._cancelar_autoguardado_pendiente()
        fecha = fecha or self.historial_combo.get()
        if not fecha:
            messagebox.showinfo("Bitácora", "No hay días guardados para cargar.")
            return
        entrada = self.data.get(fecha)
        if not entrada:
            messagebox.showwarning("Bitácora", f"No se encontró la fecha {fecha}.")
            return
        self.fecha_var.set(fecha)
        self.limpiar_filas()
        for act in entrada.get("activities", []):
            self.agregar_fila(act)
        if not entrada.get("activities"):
            self.agregar_fila()
        self.status_var.set(f"Día {fecha} cargado.")

    def ver_dia(self, fecha=None):
        fecha = fecha or self.historial_combo.get()
        if not fecha:
            messagebox.showinfo("Bitácora", "No hay días guardados para ver.")
            return
        entrada = self.data.get(fecha)
        if not entrada:
            messagebox.showwarning("Bitácora", f"No se encontró la fecha {fecha}.")
            return
        actividades = entrada.get("activities", [])

        ventana = tk.Toplevel(self.root)
        ventana.title(f"Bitácora del {fecha}")
        ventana.configure(bg=BG)
        win_w, win_h = 620, 520
        screen_w = ventana.winfo_screenwidth()
        screen_h = ventana.winfo_screenheight()
        ventana.geometry(f"{win_w}x{win_h}+{(screen_w - win_w) // 2}+{(screen_h - win_h) // 2}")
        if os.path.exists(ICON_FILE):
            try:
                ventana.iconbitmap(ICON_FILE)
            except Exception:
                pass

        tk.Label(ventana, text=f"Actividades del {fecha}", font=F_TITLE, bg=BG,
                 fg=TEXT_PRIMARY).pack(anchor="w", padx=24, pady=(20, 4))

        if not actividades:
            tk.Label(ventana, text="Este día no tiene actividades guardadas.", font=F_LABEL,
                     bg=BG, fg=TEXT_SECONDARY).pack(anchor="w", padx=24, pady=(0, 20))
            return

        canvas = tk.Canvas(ventana, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(ventana, orient="vertical", command=canvas.yview,
                                style="Modern.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(24, 0), pady=(0, 20))
        scroll.pack(side="right", fill="y", pady=(0, 20))

        lista = tk.Frame(canvas, bg=BG)
        lista_window = canvas.create_window((0, 0), window=lista, anchor="nw")
        lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(lista_window, width=e.width))

        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        for act in actividades:
            self._crear_card_actividad(lista, act)

    def _crear_card_actividad(self, parent, act):
        card = RoundedCard(parent, page_bg=BG)
        card.pack(fill="x", pady=6, padx=2)
        inner = card.inner
        inner.configure(padx=16, pady=12)

        rango = f"{act.get('inicio', '')} – {act.get('fin', '')}".strip(" –")
        top = tk.Frame(inner, bg=CARD_BG)
        top.pack(fill="x")
        if rango:
            tk.Label(top, text=rango, font=F_LABEL_BOLD, bg=CARD_BG, fg=ACCENT).pack(side="left")
        if act.get("tipo"):
            tk.Label(top, text=act["tipo"], font=F_LABEL, bg=CARD_BG,
                     fg=TEXT_SECONDARY).pack(side="left", padx=(10, 0))
        if act.get("accion"):
            tk.Label(inner, text=act["accion"], font=F_LABEL_BOLD, bg=CARD_BG,
                     fg=TEXT_PRIMARY).pack(anchor="w", pady=(6, 0))
        if act.get("detalle"):
            tk.Label(inner, text=act["detalle"], font=F_LABEL, bg=CARD_BG, fg=TEXT_PRIMARY,
                     wraplength=520, justify="left").pack(anchor="w", pady=(2, 0))

    @staticmethod
    def _minutos(hhmm):
        try:
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return None

    def reporte_semanal(self, fecha=None):
        fecha_str = fecha or self.fecha_var.get().strip() or date.today().isoformat()
        try:
            referencia = date.fromisoformat(fecha_str)
        except ValueError:
            referencia = date.today()
        lunes = referencia - timedelta(days=referencia.weekday())
        dias_semana = [lunes + timedelta(days=i) for i in range(7)]
        nombres_dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

        ventana = tk.Toplevel(self.root)
        ventana.title(f"Reporte semanal: {dias_semana[0].isoformat()} – {dias_semana[-1].isoformat()}")
        ventana.configure(bg=BG)
        win_w, win_h = 680, 640
        screen_w = ventana.winfo_screenwidth()
        screen_h = ventana.winfo_screenheight()
        ventana.geometry(f"{win_w}x{win_h}+{(screen_w - win_w) // 2}+{(screen_h - win_h) // 2}")
        if os.path.exists(ICON_FILE):
            try:
                ventana.iconbitmap(ICON_FILE)
            except Exception:
                pass

        titulo_fila = tk.Frame(ventana, bg=BG)
        titulo_fila.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(titulo_fila, text="Reporte semanal", font=F_TITLE, bg=BG,
                 fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(titulo_fila, text=f"{dias_semana[0].isoformat()} – {dias_semana[-1].isoformat()}",
                 font=F_SUBTITLE, bg=BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(0, 4))

        btn_frame = tk.Frame(ventana, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=(8, 0))
        boton_minimizar = RoundedButton(btn_frame, "Minimizar días", command=None,
                                         bg="#F2F2F7", fg=TEXT_PRIMARY, hover="#E5E5EA",
                                         width=120, height=34, radius=17, page_bg=BG)
        boton_minimizar.pack(side="left", padx=(0, 8))
        boton_semana = RoundedButton(btn_frame, "Minimizar semana", command=None,
                                      bg="#F2F2F7", fg=TEXT_PRIMARY, hover="#E5E5EA",
                                      width=140, height=34, radius=17, page_bg=BG)
        boton_semana.pack(side="left", padx=(0, 8))
        RoundedButton(btn_frame, "Descargar PDF", command=lambda: _descargar_pdf(),
                      bg=ACCENT, fg="white", hover=ACCENT_PRESSED,
                      width=140, height=34, radius=17, page_bg=BG).pack(side="left")

        canvas = tk.Canvas(ventana, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(ventana, orient="vertical", command=canvas.yview,
                                style="Modern.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(24, 0), pady=(8, 20))
        scroll.pack(side="right", fill="y", pady=(8, 20))

        lista = tk.Frame(canvas, bg=BG)
        lista_window = canvas.create_window((0, 0), window=lista, anchor="nw")
        lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(lista_window, width=e.width))

        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        total_minutos = 0
        total_actividades = 0
        minutos_por_tipo = {}
        dias_datos = []
        bloques_dias = []

        dias_container = tk.Frame(lista, bg=BG)
        dias_container.pack(fill="x")

        selector_semanas = tk.Frame(lista, bg=BG)

        for nombre, dia in zip(nombres_dias, dias_semana):
            fecha_iso = dia.isoformat()
            entrada = self.data.get(fecha_iso)
            actividades = entrada.get("activities", []) if entrada else []
            dias_datos.append((nombre, fecha_iso, actividades))

            bloque = tk.Frame(dias_container, bg=BG)
            bloque.pack(fill="x", pady=(14, 4))

            encabezado = tk.Frame(bloque, bg=BG)
            encabezado.pack(fill="x")
            tk.Label(encabezado, text=f"{nombre} {fecha_iso}", font=F_LABEL_BOLD,
                     bg=BG, fg=TEXT_PRIMARY).pack(side="left")

            contenido = tk.Frame(bloque, bg=BG)
            contenido.pack(fill="x")

            dia_minutos = 0
            if not actividades:
                tk.Label(contenido, text="Sin actividades guardadas.", font=F_LABEL,
                         bg=BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(0, 4))
            else:
                for act in actividades:
                    self._crear_card_actividad(contenido, act)
                    total_actividades += 1
                    ini = self._minutos(act.get("inicio", ""))
                    fin = self._minutos(act.get("fin", ""))
                    if ini is not None and fin is not None and fin > ini:
                        dur = fin - ini
                        total_minutos += dur
                        dia_minutos += dur
                        tipo = act.get("tipo") or "(sin tipo)"
                        minutos_por_tipo[tipo] = minutos_por_tipo.get(tipo, 0) + dur

            dh, dm = divmod(dia_minutos, 60)
            resumen_texto = (f"{len(actividades)} actividades  ·  {dh}h {dm}min"
                              if actividades else "Sin actividades guardadas.")
            resumen_label = tk.Label(bloque, text=resumen_texto, font=F_LABEL,
                                      bg=BG, fg=TEXT_SECONDARY)
            bloques_dias.append((contenido, resumen_label))

        resumen = RoundedCard(lista, page_bg=BG)
        resumen.pack(fill="x", pady=(16, 6), padx=2)
        inner = resumen.inner
        inner.configure(padx=16, pady=12)
        tk.Label(inner, text="Resumen de la semana", font=F_LABEL_BOLD, bg=CARD_BG,
                 fg=TEXT_PRIMARY).pack(anchor="w")
        horas, mins = divmod(total_minutos, 60)
        tk.Label(inner, text=f"{total_actividades} actividades  ·  {horas}h {mins}min registradas",
                 font=F_LABEL, bg=CARD_BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(4, 8))
        for tipo, mins_tipo in sorted(minutos_por_tipo.items(), key=lambda kv: -kv[1]):
            h, m = divmod(mins_tipo, 60)
            fila = tk.Frame(inner, bg=CARD_BG)
            fila.pack(fill="x", pady=1)
            tk.Label(fila, text=tipo, font=F_LABEL, bg=CARD_BG, fg=TEXT_PRIMARY,
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(fila, text=f"{h}h {m}min", font=F_LABEL, bg=CARD_BG,
                     fg=TEXT_SECONDARY).pack(side="right")

        estado = {"minimizado": False}

        def _toggle_minimizar():
            estado["minimizado"] = not estado["minimizado"]
            for contenido, resumen_label in bloques_dias:
                if estado["minimizado"]:
                    contenido.pack_forget()
                    resumen_label.pack(anchor="w", pady=(0, 4))
                else:
                    resumen_label.pack_forget()
                    contenido.pack(fill="x")
            boton_minimizar.set_text("Expandir días" if estado["minimizado"] else "Minimizar días")

        boton_minimizar.command = _toggle_minimizar

        estado_semana = {"minimizado": False}

        def _ir_a_semana(lunes_elegido):
            ventana.destroy()
            self.reporte_semanal(fecha=lunes_elegido.isoformat())

        def _construir_selector_semanas():
            for w in selector_semanas.winfo_children():
                w.destroy()
            semanas = self._semanas_disponibles()
            if not semanas:
                tk.Label(selector_semanas, text="No hay semanas con actividades guardadas.",
                         font=F_LABEL, bg=BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(0, 4))
                return
            tk.Label(selector_semanas, text="Elige la semana que quieres ver:", font=F_LABEL_BOLD,
                     bg=BG, fg=TEXT_PRIMARY).pack(anchor="w", pady=(0, 10))
            for semana_lunes in semanas:
                semana_fin = semana_lunes + timedelta(days=6)
                total_semana = sum(
                    len(self.data.get((semana_lunes + timedelta(days=i)).isoformat(), {}).get("activities", []))
                    for i in range(7)
                )
                es_actual = semana_lunes == lunes
                texto = f"{semana_lunes.isoformat()} – {semana_fin.isoformat()}  ·  {total_semana} actividades"
                if es_actual:
                    texto += "  (semana actual)"
                fila = tk.Label(selector_semanas, text=texto, font=F_LABEL, bg=BG,
                                 fg=TEXT_SECONDARY if es_actual else ACCENT,
                                 cursor="arrow" if es_actual else "hand2", anchor="w")
                fila.pack(fill="x", pady=4)
                if not es_actual:
                    fila.bind("<Button-1>", lambda e, m=semana_lunes: _ir_a_semana(m))

        def _toggle_semana():
            estado_semana["minimizado"] = not estado_semana["minimizado"]
            if estado_semana["minimizado"]:
                dias_container.pack_forget()
                _construir_selector_semanas()
                selector_semanas.pack(fill="x", before=resumen)
            else:
                selector_semanas.pack_forget()
                dias_container.pack(fill="x", before=resumen)
            boton_semana.set_text("Expandir semana" if estado_semana["minimizado"] else "Minimizar semana")

        boton_semana.command = _toggle_semana

        def _descargar_pdf():
            try:
                ruta = self._generar_pdf_semanal(
                    dias_semana, dias_datos, total_actividades, total_minutos, minutos_por_tipo)
            except Exception as exc:
                messagebox.showerror("Bitácora", f"No se pudo generar el PDF:\n{exc}")
                return
            messagebox.showinfo("Bitácora", f"Reporte guardado en:\n{ruta}")

    def _generar_pdf_semanal(self, dias_semana, dias_datos, total_actividades, total_minutos, minutos_por_tipo):
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 10, "Reporte semanal - Bitacora Datadiscol", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 8, f"{dias_semana[0].isoformat()} a {dias_semana[-1].isoformat()}",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

        for nombre, fecha_iso, actividades in dias_datos:
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 8, f"{nombre} {fecha_iso}", new_x="LMARGIN", new_y="NEXT")

            if not actividades:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(140, 140, 140)
                pdf.cell(0, 6, "Sin actividades guardadas.", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
            else:
                for act in actividades:
                    rango = f"{act.get('inicio', '')} - {act.get('fin', '')}".strip(" -")
                    encabezado = "  ·  ".join(
                        p for p in [rango, act.get("tipo", ""), act.get("accion", "")] if p)
                    if encabezado:
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.multi_cell(0, 6, encabezado, new_x="LMARGIN", new_y="NEXT")
                    if act.get("detalle"):
                        pdf.set_font("Helvetica", "", 10)
                        pdf.multi_cell(0, 6, act["detalle"], new_x="LMARGIN", new_y="NEXT")
                    pdf.ln(2)
            pdf.ln(3)

        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Resumen de la semana", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        horas, mins = divmod(total_minutos, 60)
        pdf.cell(0, 7, f"{total_actividades} actividades - {horas}h {mins}min registradas",
                 new_x="LMARGIN", new_y="NEXT")
        for tipo, mins_tipo in sorted(minutos_por_tipo.items(), key=lambda kv: -kv[1]):
            h, m = divmod(mins_tipo, 60)
            pdf.cell(0, 6, f"  {tipo}: {h}h {m}min", new_x="LMARGIN", new_y="NEXT")

        os.makedirs(REPORTS_DIR, exist_ok=True)
        nombre_archivo = f"Reporte_semanal_{dias_semana[0].isoformat()}_a_{dias_semana[-1].isoformat()}.pdf"
        ruta = os.path.join(REPORTS_DIR, nombre_archivo)
        pdf.output(ruta)
        return ruta

    def recolectar_actividades(self):
        actividades = []
        for row in self.rows:
            valores = row.get()
            if any(valores.values()):
                actividades.append(valores)
        return actividades

    def guardar_config(self):
        self.config["cedula"] = self.cedula_var.get().strip()
        save_json(CONFIG_FILE, self.config)

    def _cancelar_autoguardado_pendiente(self):
        job = getattr(self, "_autoguardado_job", None)
        if job:
            self.root.after_cancel(job)
        self._autoguardado_job = None

    def _programar_autoguardado(self):
        self._cancelar_autoguardado_pendiente()
        self._autoguardado_job = self.root.after(2000, self._autoguardar_silencioso)

    def _tick_autoguardado(self):
        self.root.after(30000, self._tick_autoguardado)
        self._autoguardar_silencioso()

    def _autoguardar_silencioso(self):
        self._autoguardado_job = None
        fecha = self.fecha_var.get().strip()
        if not fecha:
            return
        actividades = self.recolectar_actividades()
        if not actividades:
            return
        if self.data.get(fecha, {}).get("activities") == actividades:
            return
        self.data[fecha] = {"activities": actividades}
        save_json(DATA_FILE, self.data)
        self.autoguardado_var.set(f"Autoguardado {datetime.now().strftime('%H:%M:%S')}")

    def guardar_dia(self):
        fecha = self.fecha_var.get().strip()
        if not fecha:
            messagebox.showwarning("Bitácora", "Ingresa una fecha válida.")
            return
        actividades = self.recolectar_actividades()
        self.data[fecha] = {"activities": actividades}
        save_json(DATA_FILE, self.data)
        self.guardar_config()
        self.refresh_historial()
        self.actualizar_contador()
        self.actualizar_cumplimiento_mensual()
        if fecha == date.today().isoformat():
            save_json(NOTIF_STATE_FILE, {"fecha": fecha, "umbral": 0, "pausada": True})
        self.status_var.set(f"Día {fecha} guardado en {DATA_FILE}")

    def pegar_en_erp(self, row):
        if self.pegando_en_erp:
            return  # ya hay una actividad pegandose; los botones estan deshabilitados mientras tanto
        self.guardar_config()
        cedula = self.cedula_var.get().strip()
        if not cedula:
            messagebox.showwarning("Bitácora", "Ingresa tu Cédula arriba antes de usar 'Pegar en ERP'.")
            return
        datos = row.get()
        if not datos["detalle"]:
            messagebox.showwarning("Bitácora", "Escribe el Detalle de la actividad antes de pegarla en el ERP.")
            return

        self.pegando_en_erp = True
        self._set_pegar_botones_habilitados(False)
        self.status_var.set("Abriendo el ERP y llenando el formulario…")
        self._mostrar_overlay("Pegando en el ERP…\nNo cierres esta ventana.")
        threading.Thread(target=self._pegar_en_erp_worker, args=(cedula, datos, row), daemon=True).start()

    def _set_pegar_botones_habilitados(self, habilitado):
        for row in self.rows:
            row.pegar_btn.set_enabled(habilitado)

    def _mostrar_overlay(self, mensaje):
        self._ocultar_overlay()
        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.configure(bg=ACCENT)
        frame = tk.Frame(overlay, bg=ACCENT, padx=32, pady=20)
        frame.pack()
        tk.Label(frame, text=mensaje, bg=ACCENT, fg="white", font=F_BUTTON,
                 wraplength=320, justify="center").pack()
        overlay.update_idletasks()
        self.root.update_idletasks()
        ancho, alto = overlay.winfo_reqwidth(), overlay.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - ancho) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - alto) // 2
        overlay.geometry(f"{ancho}x{alto}+{max(x, 0)}+{max(y, 0)}")
        overlay.deiconify()
        self.overlay = overlay

    def _ocultar_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except Exception:
                pass
            self.overlay = None

    def _terminar_pegar_en_erp(self):
        self.pegando_en_erp = False
        self._set_pegar_botones_habilitados(True)
        self._ocultar_overlay()

    def _pegar_en_erp_worker(self, cedula, datos, row):
        try:
            with self.driver_lock:
                for intento in range(2):
                    if self.driver is None:
                        self.driver, self.driver_nombre = crear_driver()
                    try:
                        fill_erp_form(self.driver, cedula, datos["tipo"], datos["accion"],
                                      datos["detalle"], datos["inicio"], datos["fin"])
                        break
                    except Exception:
                        try:
                            self.driver.quit()
                        except Exception:
                            pass
                        self.driver = None
                        if intento == 1:
                            raise
            self.root.after(0, lambda: self.status_var.set(
                f"Formulario llenado en {self.driver_nombre}. No cierres esa ventana mientras se llena; "
                "verifica que Nombre y Proyecto/Área hayan quedado bien y da clic en Enviar allí."))
            self.root.after(0, row.marcar_enviado)
        except Exception as exc:
            msg = str(exc)
            self.root.after(0, lambda: messagebox.showerror(
                "Bitácora", f"No se pudo llenar el formulario en el ERP:\n{msg}"))
            self.root.after(0, lambda: self.status_var.set(""))
        finally:
            self.root.after(0, self._terminar_pegar_en_erp)


if __name__ == "__main__":
    if "--notificar" in sys.argv:
        revisar_recordatorio_en_segundo_plano()
        sys.exit(0)

    root = tk.Tk()
    app = BitacoraApp(root)
    root.mainloop()
