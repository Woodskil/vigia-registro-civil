from pathlib import Path

import vigia

PAGINAS = Path(__file__).parent / "paginas"
NOMBRE_82 = vigia.AGENDAS[82][0]


def leer(nombre):
    return (PAGINAS / nombre).read_text(encoding="utf-8")


# --- clasificar, con páginas reales bajadas de sae.mec.gub.uy el 2026-10-12 ---

def test_pagina_real_sin_cupos():
    assert vigia.clasificar(leer("sin_cupos_82.html"), NOMBRE_82) == "sin_cupos"


def test_misma_pagina_sin_el_cartel_es_con_cupos():
    # No tenemos una página real con cupos: simulamos quitando el cartel.
    html = leer("sin_cupos_82.html").replace("no hay cupos disponibles", "")
    assert vigia.clasificar(html, NOMBRE_82) == "con_cupos"


def test_agenda_vacia_no_es_con_cupos():
    assert vigia.clasificar(leer("agenda_vacia.html"), NOMBRE_82) == "desconocido"


def test_redireccion_al_login_no_es_con_cupos():
    assert vigia.clasificar(leer("login_gubuy.html"), NOMBRE_82) == "desconocido"


# --- procesar: cuándo se avisa ---

def test_avisa_cuando_aparecen_cupos():
    mensaje, estado = vigia.procesar(82, "con_cupos", "", {"resultado": "sin_cupos"})
    assert "Есть свободные места" in mensaje
    assert "tramites/iniciar/8942" in mensaje
    assert estado["resultado"] == "con_cupos"


def test_no_repite_el_aviso_mientras_sigue_habiendo_cupos():
    mensaje, _ = vigia.procesar(82, "con_cupos", "", {"resultado": "con_cupos"})
    assert mensaje is None


def test_vuelve_a_avisar_si_los_cupos_se_acaban_y_reaparecen():
    _, estado = vigia.procesar(82, "sin_cupos", "", {"resultado": "con_cupos"})
    mensaje, _ = vigia.procesar(82, "con_cupos", "", estado)
    assert mensaje is not None


def test_primera_revision_con_cupos_avisa():
    mensaje, _ = vigia.procesar(82, "con_cupos", "", {})
    assert mensaje is not None


def test_sin_cupos_no_avisa():
    mensaje, _ = vigia.procesar(82, "sin_cupos", "", {})
    assert mensaje is None


def test_errores_sueltos_no_avisan_ni_borran_el_ultimo_resultado():
    mensaje, estado = vigia.procesar(82, "desconocido", "error de red", {"resultado": "sin_cupos"})
    assert mensaje is None
    assert estado["resultado"] == "sin_cupos"
    assert estado["errores"] == 1


def test_aviso_ciego_escapa_el_error_para_el_html_de_telegram():
    # Los errores de requests traen cosas como "<urllib3.connection... at 0x..>",
    # que Telegram rechaza con parse_mode HTML: el aviso no llegaría nunca.
    detalle = "error de red: (<urllib3.connection.HTTPSConnection object at 0x7f>)"
    mensaje = vigia.mensaje_ciego(82, detalle)
    assert "<urllib3" not in mensaje
    assert "&lt;urllib3.connection.HTTPSConnection object at 0x7f&gt;" in mensaje


def test_avisa_una_sola_vez_cuando_queda_ciego():
    estado = {}
    mensajes = []
    for _ in range(vigia.ERRORES_PARA_AVISAR + 3):
        mensaje, estado = vigia.procesar(82, "desconocido", "", estado)
        mensajes.append(mensaje)
    avisos = [m for m in mensajes if m]
    assert len(avisos) == 1
    assert "не может прочитать" in avisos[0]


def test_al_recuperarse_reinicia_el_contador_de_errores():
    estado = {"resultado": "sin_cupos", "errores": 4, "avisado_ciego": True}
    _, estado = vigia.procesar(82, "sin_cupos", "", estado)
    assert estado["errores"] == 0
    assert estado["avisado_ciego"] is False


# --- alarma de Pushover ---

class _Resp:
    def raise_for_status(self):
        pass


def test_alarma_pushover_es_de_emergencia_y_repite_cada_3_minutos(monkeypatch):
    enviado = {}
    monkeypatch.setenv("PUSHOVER_APP_TOKEN", "app")
    monkeypatch.setenv("PUSHOVER_USER_KEY", "usuario")
    monkeypatch.setattr(vigia.requests, "post", lambda url, data, timeout: enviado.update(data) or _Resp())

    assert vigia.enviar_pushover_emergencia(82) is True
    assert enviado["priority"] == 2
    assert enviado["retry"] == 180
    assert enviado["expire"] <= 10800  # máximo que acepta Pushover
    assert "tramites/iniciar/8942" in enviado["url"]


def test_sin_claves_de_pushover_no_intenta_enviar(monkeypatch):
    monkeypatch.delenv("PUSHOVER_APP_TOKEN", raising=False)
    monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
    monkeypatch.setattr(vigia.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía enviar")))
    assert vigia.enviar_pushover_emergencia(82) is False


def test_mensajes_escapan_el_ampersand_de_las_urls():
    # Telegram (parse_mode HTML) pide "&amp;"; la URL de la agenda trae "&a=".
    for mensaje in (vigia.mensaje_cupos(82), vigia.mensaje_ciego(82, "")):
        assert "e=9&amp;a=82" in mensaje
        assert "e=9&a=82" not in mensaje


# --- argumentos ---

def test_flag_desconocido_no_hace_una_revision(monkeypatch):
    monkeypatch.setattr(vigia.sys, "argv", ["vigia.py", "--tes"])
    monkeypatch.setattr(vigia, "revisar", lambda *a: (_ for _ in ()).throw(AssertionError("no debía revisar")))
    assert vigia.main() == 2
