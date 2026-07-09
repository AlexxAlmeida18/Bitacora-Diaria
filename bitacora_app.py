import json
import os
import subprocess
import sys
import tempfile
import threading
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
    ("Trascribir", ("trascrib", "transcrib", "pasar a limpio", "dictad", "copiar texto")),
    ("Tabular", ("tabul", "hoja de calculo", "hoja de cálculo", "en excel", "en csv", "cuadro de datos",
                 "planilla")),
    ("Organizar", ("organiz", "organic", "orden", "clasific", "clasifiqu", "acomod", "archiv",
                   "seleccion de foto", "selección de foto", "descarte de foto")),
    ("Cotizar", ("cotiz", "cotic", "presupuest", "cotización", "propuesta comercial",
                 "propuesta economica", "propuesta económica", "oferta comercial")),
    ("LLamar", ("llam", "telefon", "por teléfono", "por telefono")),
    ("Enviar", ("envi", "mand", "remit", "despach", "correo a", "mensaje a", "compart",
                "public", "publiqu")),
    ("Reunir", ("reun", "junta", "cita con", "mesa de trabajo", "visita comercial",
                "visité al cliente", "visite al cliente")),
    ("Redactar", ("redact", "document", "elabora", "escrib", "preparar informe", "preparar documento",
                  "guion", "guión", "copy", "texto para redes", "texto publicitario")),
    ("Analizar", ("analiz", "analic", "análisis", "revis", "evalu", "verific", "verifiqu", "comprob", "chequ",
                  "estudi", "diagnostic", "concili", "inspec", "audit", "riesgo", "inciden", "accidente",
                  "falla")),
    ("Informar", ("informé", "informe a", "informar a", "informando a", "avis", "notific", "notifiqu",
                  "comuniqu", "comunicar a", "socializ", "puse al tanto", "di a conocer",
                  "informe de avance", "reporte de avance", "asesor", "recomend")),
    ("Gestionar", ("gestion", "gestión", "tramit", "coordin", "administr", "supervis", "manej", "seguimiento",
                   "prospec", "negoci", "cliente potencial", "cierre de venta",
                   "configura", "instal", "mantenimiento", "servidor", "respaldo", "backup", "licencia",
                   "ticket", "soporte", "soluci", "resolv",
                   "entrevist", "induc", "contrat", "seleccion de personal", "selección de personal",
                   "clima laboral", "protocolo", "seguridad industrial",
                   "nomina", "nómina", "liquid", "prestaciones sociales", "seguridad social",
                   "aportes", "incapacidad",
                   "tesorer", "flujo de caja", "egresos", "transferencia",
                   "declar", "retenci", "estados financieros", "cuentas por pagar", "cuentas por cobrar",
                   "cartera")),
    ("Extraer", ("extrac", "extraer", "extraj", "descarg", "recopil", "sacar informacion", "sacar información")),
    ("Digitar", ("digit", "captur", "ingres", "registr", "carg", "aliment", "actualiz", "actualic",
                 "subi", "subí", "factur", "asiento contable")),
    ("Desarrollar", ("desarroll", "programa", "constru", "crear", "cree ", "creé",
                      "imprim", "diseñ", "diagram", "carnet", "diploma",
                      "codigo", "código", "backend", "frontend", "bug", "depur", "testeo", "testing",
                      "despliegue", "desplegué", "modulo", "módulo",
                      "fotograf", "retoc", "retoqu", "edicion de foto", "edición de foto",
                      "cubrir evento", "cobertura")),
    ("Estructurar", ("estructur", "armar formato", "definir estructura", "defin", "esquemat", "diseñar formato",
                      "plane", "planific", "cronograma", "hito")),
]


def sugerir_accion(texto):
    texto = texto.lower()
    mejor_accion = None
    mejor_pos = None
    mejor_len = 0
    for accion, keywords in ACCION_KEYWORDS:
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


APP_VERSION = "1.5.2"
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

    set_text("input_58_6", detalle)

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
        self.pegando_overlay = None

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
        self._mostrar_pegando_overlay("Pegando en el ERP…\nNo cierres esta ventana.")
        threading.Thread(target=self._pegar_en_erp_worker, args=(cedula, datos, row), daemon=True).start()

    def _set_pegar_botones_habilitados(self, habilitado):
        for row in self.rows:
            row.pegar_btn.set_enabled(habilitado)

    def _mostrar_pegando_overlay(self, mensaje):
        self._ocultar_pegando_overlay()
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
        self.pegando_overlay = overlay

    def _ocultar_pegando_overlay(self):
        if self.pegando_overlay is not None:
            try:
                self.pegando_overlay.destroy()
            except Exception:
                pass
            self.pegando_overlay = None

    def _terminar_pegar_en_erp(self):
        self.pegando_en_erp = False
        self._set_pegar_botones_habilitados(True)
        self._ocultar_pegando_overlay()

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
