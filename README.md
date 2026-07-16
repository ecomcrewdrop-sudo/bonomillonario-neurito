# NEURITO

Agente de automatización que monitorea el resultado **"10:10 A"** de **Triple Táchira**,
genera una imagen de anuncio a partir de una plantilla (modificando **solo el número
ganador**) y la publica automáticamente como **Instagram Story** vía la **API oficial de
Meta (Instagram Graph API)**.

Todo opera en la zona horaria de **Colombia (America/Bogota, UTC-5, sin horario de verano)**.

---

## Cómo funciona

1. **Scheduler** (APScheduler) dispara una sesión de monitoreo **todos los días a las 21:10**
   hora de Colombia.
2. **Scraper** consulta el endpoint real del sitio cada **10 s**:
   `GET https://tripletachira.com/pruebah.php?bt=<lunes>&bt2=<domingo>` (fechas `DD/MM/YYYY`).
   Vigila la fila `10:10 A` en la columna del **día actual**.
   - Mientras no sale, la celda trae `--------`.
   - Cuando sale, trae el número de **3 dígitos**.
3. Al detectar el número, **de inmediato**:
   - **Genera** la imagen (Pillow) escribiendo solo el número sobre la plantilla.
   - **Publica** la Story por Graph API (contenedor `STORIES` → `media_publish`).
4. **Límites operativos**:
   - Sitio caído → registra y reintenta cada **30 s**.
   - Sin resultado a las **21:30** → detiene el día y espera hasta mañana.
   - Falla la imagen → **alerta al admin y NO publica**.
   - Falla la publicación tras **3 intentos** → guarda la imagen y registra para revisión manual.

El proceso corre **silencioso**: solo se registran errores, publicaciones exitosas y alertas.

---

## Estructura

```
NEURITO/
├── main.py                 # entrypoint (uvicorn + scheduler) para Railway
├── calibrate.py            # herramienta para posicionar el número en la plantilla
├── requirements.txt
├── Procfile / railway.json / runtime.txt   # despliegue Railway
├── .env.example            # todas las variables (copiar a .env)
├── assets/
│   ├── template/           # <- aquí va plantilla.png
│   └── fonts/              # <- aquí va number.ttf
├── output/                 # imágenes generadas (servidas en /media)
├── tests/
│   └── test_scraper.py     # test del parser con HTML real
└── neurito/
    ├── config.py           # configuración desde variables de entorno
    ├── logger.py           # logging con hora de Colombia
    ├── scraper.py          # consulta y parsea el endpoint
    ├── image_generator.py  # dibuja el número sobre la plantilla
    ├── instagram.py        # publica Story vía Graph API
    ├── notifier.py         # alertas al admin (Telegram opcional)
    ├── monitor.py          # orquesta el protocolo de monitoreo
    └── server.py           # FastAPI: /media, /health, scheduler diario
```

---

## Requisitos de la cuenta de Instagram (API oficial)

La publicación de Stories por API **solo** funciona con:
- Cuenta de Instagram **Business** o **Creator**.
- Vinculada a una **Página de Facebook**.
- Una **app de Meta** con el producto *Instagram Graph API* y permisos:
  `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`.
- Un **long-lived access token** y el **IG User ID** (ID numérico de la cuenta business).

> NEURITO **nunca** usa tu usuario/contraseña. Solo el token, definido como variable de
> entorno en Railway. (El login automático con contraseña viola los Términos de Instagram
> y arriesga el baneo de la cuenta.)

La Graph API **descarga la imagen desde una URL pública**: por eso el servicio la expone en
`PUBLIC_BASE_URL/media/<archivo>`. En Railway, `PUBLIC_BASE_URL` es el dominio público del
servicio (p. ej. `https://neurito-production.up.railway.app`).

---

## Puesta en marcha local (opcional, para probar)

> Requiere Python 3.11+ instalado (en Windows, instálalo desde python.org, no el alias de
> la Microsoft Store).

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env         # y edita valores

# 1) Probar el parser (sin red):
python tests/test_scraper.py

# 2) Probar el scraper contra el sitio en vivo:
python -m neurito.scraper 15/07/2026

# 3) Calibrar la posición del número sobre tu plantilla:
python calibrate.py 888 --x 540 --y 970 --size 240 --color "#FFD200"

# 4) Levantar el servicio completo:
python main.py
```

Modo prueba sin publicar: pon `DRY_RUN=true` en `.env` (genera la imagen pero no publica).

---

## Despliegue en Railway

1. Sube este proyecto a un repositorio Git y conéctalo a Railway
   (o `railway up` con la CLI).
2. En **Railway → Variables**, define todas las de `.env.example`
   (`IG_USER_ID`, `IG_ACCESS_TOKEN`, `PUBLIC_BASE_URL`, coordenadas del número, etc.).
3. Railway asigna un dominio público → cópialo en `PUBLIC_BASE_URL`.
4. La plantilla (`assets/template/plantilla.png`) y la fuente (`assets/fonts/number.ttf`)
   deben ir **incluidas en el repo** para que estén disponibles en el contenedor.
5. Healthcheck: `GET /health`. Estado: `GET /`. Disparo manual de prueba: `POST /run-now`.

---

## Qué falta para dejarlo 100% operativo

- [ ] Plantilla `plantilla.png` en `assets/template/`.
- [ ] Fuente `number.ttf` en `assets/fonts/` (la que usa el número en la plantilla).
- [ ] Coordenadas/estilo del número calibrados (`NUMBER_X`, `NUMBER_Y`, `NUMBER_FONT_SIZE`,
      `NUMBER_COLOR`, `NUMBER_ANCHOR`).
- [ ] `IG_USER_ID` + `IG_ACCESS_TOKEN` (long-lived) de la cuenta Business/Creator.
- [ ] `PUBLIC_BASE_URL` con el dominio de Railway.
- [ ] (Opcional) `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` para alertas al admin.
