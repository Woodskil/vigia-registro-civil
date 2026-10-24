"""Vigila las agendas públicas del Registro Civil (SAE) y avisa por Telegram
cuando aparecen cupos para inscribir partidas extranjeras.

Las agendas se ven sin iniciar sesión en sae.mec.gub.uy. Cuando no hay lugar,
la página dice "En la oficina seleccionada no hay cupos disponibles"; cuando
ese texto desaparece, avisamos.

Uso:
    python vigia.py               # una revisión (para el Programador de tareas)
    python vigia.py --test        # manda un mensaje de prueba a Telegram
    python vigia.py --test-alarm  # manda la alarma de Pushover (probar en silencio)

Los avisos (Telegram y Pushover) van en ruso.
"""

import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import certifi
import requests
from dotenv import load_dotenv

AQUI = Path(__file__).parent
# En la nube se usa otro archivo (estado-nube.json, que sí va al repo) para no
# pisar el estado de la tarea local.
ESTADO = AQUI / os.environ.get("VIGIA_ESTADO", "estado.json")
LOG = AQUI / "vigia.log"

# sae.mec.gub.uy manda solo su certificado, sin los intermedios (Abitab SSL DV
# y Certum Global Services CA SHA2). Los navegadores y curl en Windows los
# completan solos; Python no, y falla con CERTIFICATE_VERIFY_FAILED. Se bajaron
# de las URLs AIA del propio certificado y se suman a las raíces de certifi:
# la verificación sigue activa, nunca verify=False. Vencen en 2027.
INTERMEDIOS = AQUI / "certs" / "intermedios.pem"
CA_BUNDLE = AQUI / ".ca-bundle.pem"

URL_SAE = "https://sae.mec.gub.uy/sae/agendarReserva/Paso1.xhtml?e=9&a={a}"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

# Prioridad de emergencia de Pushover: suena aunque el iPhone esté en silencio
# (Alertas críticas) y se repite cada REPETIR_CADA segundos hasta que se
# confirma en la app, o hasta DEJAR_DE_REPETIR (máximo de Pushover: 3 h).
REPETIR_CADA = 180
DEJAR_DE_REPETIR = 3 * 60 * 60

# id de agenda SAE -> (nombre que muestra la página, enlace para reservar con login)
AGENDAS = {
    82: (
        "Inscripción Extranjeros Exclusiva para Titulares",
        "https://bpmgob.mec.gub.uy/autenticacion/login?redirect=https://bpmgob.mec.gub.uy/tramites/iniciar/8942",
    ),
    84: (
        "Inscripción de partidas extranjeras titulares o representantes",
        "https://bpmgob.mec.gub.uy/autenticacion/login?redirect=https://bpmgob.mec.gub.uy/tramites/iniciar/8945",
    ),
}

# Cómo se llama cada agenda en los avisos (en ruso); el nombre oficial de
# AGENDAS se sigue usando para reconocer la página.
NOMBRES_AVISO = {
    82: "Регистрация иностранных свидетельств — только сам владелец",
    84: "Регистрация иностранных свидетельств — владелец или представитель",
}

USO = "Uso: python vigia.py [--test | --test-alarm]"

SIN_CUPOS = "no hay cupos disponibles"

# Tras cuántas revisiones seguidas con página rara avisamos que el vigía puede
# estar ciego (cambio del sitio, caída larga).
ERRORES_PARA_AVISAR = 6


def clasificar(html, nombre):
    """Devuelve 'sin_cupos', 'con_cupos' o 'desconocido'.

    'con_cupos' exige ver el nombre de la agenda y el paso "Agendar reserva":
    así una página en blanco o de error no se confunde con lugar libre.
    """
    if SIN_CUPOS in html:
        return "sin_cupos"
    if nombre in html and "Agendar reserva" in html:
        return "con_cupos"
    return "desconocido"


def revisar(agenda_id):
    nombre, _ = AGENDAS[agenda_id]
    try:
        resp = requests.get(
            URL_SAE.format(a=agenda_id),
            timeout=30,
            verify=str(CA_BUNDLE),
            headers={"User-Agent": "vigia-partida-nacimiento (uso personal)"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return "desconocido", f"error de red: {exc}"
    return clasificar(resp.text, nombre), ""


def enviar_telegram(texto):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        registrar("faltan TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID en .env, no se envía")
        return False
    try:
        resp = requests.post(
            TELEGRAM_URL.format(token=token),
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        registrar(f"falló el envío a Telegram: {type(exc).__name__}")
        return False


def enviar_pushover_emergencia(agenda_id):
    """Alarma que atraviesa el modo silencio. Opcional: sin claves no hace nada."""
    token = os.environ.get("PUSHOVER_APP_TOKEN")
    usuario = os.environ.get("PUSHOVER_USER_KEY")
    if not token or not usuario:
        return False
    _, reservar = AGENDAS[agenda_id]
    try:
        resp = requests.post(
            PUSHOVER_URL,
            data={
                "token": token,
                "user": usuario,
                "title": "Есть места в Registro Civil!",
                "message": f"{NOMBRES_AVISO[agenda_id]}. Бронируйте сейчас и оплатите в течение 48 ч.",
                "url": reservar,
                "url_title": "Забронировать",
                "priority": 2,
                "retry": REPETIR_CADA,
                "expire": DEJAR_DE_REPETIR,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        registrar(f"falló el envío a Pushover: {type(exc).__name__}")
        return False


def registrar(linea):
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{marca} {linea}\n")
    print(f"{marca} {linea}")


def cargar_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mensaje_cupos(agenda_id):
    nombre, reservar = AGENDAS[agenda_id]
    return (
        f"🟢 <b>Есть свободные места в Registro Civil!</b>\n"
        f"{NOMBRES_AVISO[agenda_id]}\n"
        f"<i>{nombre}</i>\n\n"
        # En parse_mode HTML, Telegram exige "&amp;" en vez de "&" (las URLs lo traen).
        f"Забронировать: {html.escape(reservar)}\n"
        f"Посмотреть расписание: {html.escape(URL_SAE.format(a=agenda_id))}\n\n"
        f"Важно: после бронирования нужно оплатить $U 1.436 в течение 48 часов, "
        f"иначе бронь отменят."
    )


def mensaje_ciego(agenda_id, detalle):
    return (
        f"⚠️ <b>Бот не может прочитать страницу записи Registro Civil</b>\n"
        f"{NOMBRES_AVISO[agenda_id]}\n"
        f"Уже {ERRORES_PARA_AVISAR} проверок подряд страница не распознаётся "
        f"({html.escape(detalle) or 'формат не тот, что ожидался'}). Возможно, места появились, "
        f"но страница выглядит иначе, или сайт изменился. Проверьте вручную: {html.escape(URL_SAE.format(a=agenda_id))}"
    )


def procesar(agenda_id, resultado, detalle, previo):
    """Decide qué mensaje mandar (o ninguno) y devuelve (mensaje, estado_nuevo).

    Solo avisa en los cambios: cuando aparecen cupos tras no haberlos, y una
    sola vez cuando la página deja de reconocerse por varias revisiones.
    """
    errores = previo.get("errores", 0)
    nuevo = {"resultado": previo.get("resultado"), "errores": errores, "avisado_ciego": previo.get("avisado_ciego", False)}

    if resultado == "desconocido":
        nuevo["errores"] = errores + 1
        if nuevo["errores"] >= ERRORES_PARA_AVISAR and not nuevo["avisado_ciego"]:
            nuevo["avisado_ciego"] = True
            return mensaje_ciego(agenda_id, detalle), nuevo
        return None, nuevo

    nuevo.update(resultado=resultado, errores=0, avisado_ciego=False)
    if resultado == "con_cupos" and previo.get("resultado") != "con_cupos":
        return mensaje_cupos(agenda_id), nuevo
    return None, nuevo


def main():
    load_dotenv(AQUI / ".env")

    # Un flag mal escrito (p. ej. "--tes") no debe pasar por una revisión normal.
    args = sys.argv[1:]
    if len(args) > 1 or (args and args[0] not in ("--test", "--test-alarm")):
        print(f"Argumento desconocido: {' '.join(args)}\n{USO}", file=sys.stderr)
        return 2

    if "--test" in args:
        ok = enviar_telegram("🔔 Тестовое сообщение от бота Registro Civil. Если вы его видите, уведомления работают.")
        registrar(f"mensaje de prueba {'enviado' if ok else 'NO enviado'}")
        return 0 if ok else 1

    if "--test-alarm" in args:
        # Manda la alarma real de Pushover (agenda 82), para probarla con el iPhone en silencio.
        ok = enviar_pushover_emergencia(82)
        registrar(f"alarma de prueba {'enviada' if ok else 'NO enviada (¿faltan claves de Pushover en .env?)'}")
        return 0 if ok else 1

    CA_BUNDLE.write_text(
        Path(certifi.where()).read_text(encoding="utf-8") + "\n" + INTERMEDIOS.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    estado = cargar_estado()
    for agenda_id in AGENDAS:
        clave = str(agenda_id)
        resultado, detalle = revisar(agenda_id)
        mensaje, estado[clave] = procesar(agenda_id, resultado, detalle, estado.get(clave, {}))
        registrar(f"a={agenda_id} {resultado} {detalle}".rstrip())
        if not mensaje:
            continue
        enviado = enviar_telegram(mensaje)
        if resultado == "con_cupos":
            # Se manda aunque Telegram haya fallado: es el aviso que despierta.
            enviado = enviar_pushover_emergencia(agenda_id) or enviado
        if not enviado:
            # Si ningún aviso salió, no lo damos por avisado: se reintenta la próxima vez.
            estado[clave] = estado.get(clave, {}) | {"resultado": None, "avisado_ciego": False}

    ESTADO.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
