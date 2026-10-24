# Inscripción de partida de nacimiento extranjera en Uruguay

> **Эта копия** — форк [lgarciaj94/vigia-registro-civil](https://github.com/lgarciaj94/vigia-registro-civil)
> с изменениями:
> - зависимости закреплены по версиям и хешам (`pip install --require-hashes`);
>   pytest вынесен в `requirements-dev.txt`, в Actions не ставится;
> - экшены закреплены по SHA (checkout v7.0.1, setup-python v7.0.0);
> - текст ошибки экранируется перед отправкой в Telegram (HTML);
> - запуск в облаке: cron-job.org каждые 5 мин дёргает `workflow_dispatch`
>   (свой cron GitHub срабатывает раз в 2–5 часов и оставлен как запасной);
> - workflow делает пустой коммит, если репозиторий молчит 45+ дней
>   (иначе GitHub отключает его через 60);
> - локально: задача Планировщика Windows раз в минуту через `pythonw.exe`.
>
> Установка локально:
> `python -m venv .venv` и
> `.venv\Scripts\python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt`.
> Обновлять зависимости — только с новыми хешами с PyPI, версии не моложе недели.

Objetivo: inscribir (transcribir) mi partida de nacimiento extranjera en la
Dirección Nacional del Registro de Estado Civil (DNREC), para tener la partida
en formato uruguayo.

Información tomada de gub.uy el 2026-10-12.

## Qué trámite reservar

Hay dos versiones del mismo trámite. Cuestan lo mismo y se hacen en el mismo lugar.

| Trámite | Para quién | Enlace para reservar |
|---|---|---|
| **Trámite exclusivo para titulares** (el que corresponde si voy yo con mi propia partida) | El titular de la partida. Puede sumar hasta 4 documentos más, solo de cónyuge o hijos. No acepta representantes. | [Reservar (8942)](https://bpmgob.mec.gub.uy/autenticacion/login?redirect=https://bpmgob.mec.gub.uy/tramites/iniciar/8942) |
| Titulares y/o representantes | Si va otra persona en mi nombre (con autorización firmada, punto 3 del formulario) | [Reservar (8945)](https://bpmgob.mec.gub.uy/autenticacion/login?redirect=https://bpmgob.mec.gub.uy/tramites/iniciar/8945) |

Fichas oficiales:
- https://www.gub.uy/tramites/inscripcion-partidas-extranjeras-tramite-exclusivo-titulares-documentos-extranjeros
- https://www.gub.uy/tramites/inscripcion-partidas-extranjeras-tramite-titulares-yo-representantes

## Vigía de cupos

`vigia.py` revisa las agendas públicas del Registro Civil, que se ven sin login:

- [a=82 · Exclusiva para titulares](https://sae.mec.gub.uy/sae/agendarReserva/Paso1.xhtml?e=9&a=82)
- [a=84 · Titulares o representantes](https://sae.mec.gub.uy/sae/agendarReserva/Paso1.xhtml?e=9&a=84)

Cuando desaparece el cartel "no hay cupos disponibles", avisa por dos vías:

- **Telegram:** un mensaje con el enlace para reservar.
- **Pushover (alarma):** prioridad de emergencia. Suena aunque el iPhone esté en
  silencio (Alertas críticas) y **se repite cada 3 minutos hasta confirmarla** en
  la app, por un máximo de 3 horas. Es lo que despierta de madrugada.

Avisa una vez por apertura de cupos. Si la página deja de reconocerse 6 veces
seguidas, avisa por Telegram, porque el vigía podría estar ciego.

### Dónde corre

| Dónde | Cada cuánto | Cuándo funciona |
|---|---|---|
| GitHub Actions (`.github/workflows/vigia.yml`) | 5 min (GitHub suele atrasarlo entre 5 y 20 min) | Siempre, aunque la PC esté apagada |
| Tarea de Windows **"Vigia cupos Registro Civil"** | 5 min | Solo con la PC prendida y la sesión iniciada |

Cada uno guarda su propio estado, así que cuando abren cupos pueden llegar dos
alarmas (una de cada lado).

El repo es público a propósito: así los minutos de Actions son ilimitados. Las
claves van como *secrets* del repo y en `.env` local, nunca en el código.
GitHub pausa los cron de repos sin actividad por 60 días.

### Claves (`.env` local y secrets del repo)

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `PUSHOVER_APP_TOKEN`, `PUSHOVER_USER_KEY`.
Sin las de Pushover, el vigía avisa solo por Telegram.

### Comandos

- Probar Telegram: `.venv\Scripts\python vigia.py --prueba`
- Probar la alarma (con el iPhone en silencio): `.venv\Scripts\python vigia.py --prueba-alarma`
- Tests: `.venv\Scripts\python -m pytest tests`
- Historial local: `vigia.log`. Último estado: `estado.json` (local) y `estado-nube.json` (Actions).
- Apagar el vigía cuando ya tenga la cita (los dos lados):
  `Unregister-ScheduledTask -TaskName "Vigia cupos Registro Civil"` y
  `gh workflow disable vigia.yml`

`certs/intermedios.pem`: el servidor no manda sus certificados intermedios y
Python lo rechaza. Están bajados de las URLs oficiales del certificado y vencen
en 2027.

## Pasos para sacar la cita

1. Entrar al enlace con usuario gub.uy (o DNI digital, Identidad Digital Abitab, TuID Antel).
2. Completar los datos del formulario en línea.
3. Elegir día y hora.
4. **Pagar dentro de las 48 horas**, si no la reserva se cae. Costo: **$U 1.436**. No se devuelve.
   Si pago por redes de cobranza (Abitab / Red Pagos), sacarle foto al ticket.
5. Esperar los correos de confirmación.

## Qué llevar el día de la cita

- [ ] Documento de identidad (el mismo con el que creé el usuario gub.uy)
- [ ] Partida de nacimiento **original**, emitida en el país donde nací
- [ ] Partida **apostillada** (o legalizada si el país no es parte del Convenio de La Haya)
- [ ] Fotocopia completa de la partida (la sellan y la devuelven)
- [ ] [Formulario de inscripción](formulario-inscripcion-partidas.pdf) completo, con el chequeo de la página 1 hecho
- [ ] Comprobante de pago
- [ ] Solo si la partida no está en español: traducción de traductor público uruguayo (con timbre profesional) o del Consulado de Uruguay
- [ ] Solo si quiero recuperar el original: **testimonio por exhibición** hecho por escribano en Uruguay

> **Ojo:** sin testimonio por exhibición, la partida original **no se devuelve**: queda
> archivada en el Registro (Ley 13.426, art. 82).

## Dónde

DNREC, **Uruguay 933**, Montevideo. Atención de 10:15 a 15:00, solo con agenda.

Consultas: (+598) 2 1825, lunes a viernes de 9 a 17 · atencionalusuario@mec.gub.uy

## Estado

- [ ] Partida apostillada en mano
- [ ] Decidido si hago testimonio por exhibición
- [ ] Cita reservada (fecha: ____ )
- [ ] Pagado (fecha: ____ )
- [ ] Trámite presentado
- [ ] Partida uruguaya retirada
