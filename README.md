# placsp-obras

Fichas de **órganos de contratación** a partir de las **licitaciones de obra** publicadas en los datos abiertos de la Plataforma de Contratación del Sector Público (PLACSP). Ámbito: todo el Estado.

## Qué hace

1. **Descarga** los ficheros de sindicación de la PLACSP:
   - `sindicacion_643`: licitaciones publicadas en la PLACSP (sin contratos menores).
   - `sindicacion_1044`: plataformas autonómicas agregadas (sin contratos menores).
2. **Filtra** los expedientes con tipo de contrato *Obras* (`TypeCode = 3`) y guarda una versión compacta por fuente y mes. Estos ficheros intermedios no se versionan en git: se guardan como adjuntos de la release [`datos`](../../releases/tag/datos).
3. **Consolida** (se queda con la última versión de cada expediente y descarta los eliminados) y **genera**:
   - Fichas por órgano (`indice.json` y `o/<órgano>.json`), publicadas junto al visor.
   - `expedientes_obra.csv.gz`, `adjudicaciones_obra.csv.gz`, `organos_obra.csv`: tablas para Excel (separador `;`, UTF-8), descargables desde la release [`datos`](../../releases/tag/datos).
4. **Publica** el visor `docs/index.html` en GitHub Pages directamente desde el workflow (no se hace commit de los datos).

## Indicadores de cada ficha

Distinción **con juicio de valor / solo criterios automáticos / sin datos de criterios**, según el tipo de cada criterio de adjudicación publicado (`cbc:AwardingCriteriaTypeCode`: OBJ = fórmula, SUBJ = juicio de valor), con baja, ofertas, % de desiertos y peso del precio por grupo y desglose por peso del juicio de valor (≤ 25 %, 25–49 %, ≥ 50 %).

Además: expedientes e importe licitado (total y por año), PBL mediano, baja media / mediana / percentil 75 (global y por tramo de presupuesto), ofertas por lote, peso medio de los criterios sujetos a juicio de valor, % de expedientes solo con criterios automáticos, % de lotes desiertos, días entre fin de ofertas y adjudicación, % adjudicado a pyme, procedimientos, principales adjudicatarios y listado de expedientes con enlace a la PLACSP y al PCAP.

**Baja** = 1 − importe de adjudicación sin IVA / presupuesto base de licitación sin IVA del lote. Se descartan valores fuera de 0–90 %.

## Uso

Automático: el workflow **Actualizar datos PLACSP** se ejecuta cada lunes (vuelve a descargar el mes anterior y el mes en curso).

Carga histórica (una ejecución por año, desde *Actions → Actualizar datos PLACSP → Run workflow*):

| periodos | qué descarga |
|---|---|
| `auto` | mes anterior + mes en curso |
| `2025` | los 12 ficheros mensuales de 2025 |
| `202401-202406` | rango de meses |
| `ninguno` | no descarga; solo regenera las fichas |

Los meses ya descargados se omiten, así que si una carga se corta por tiempo basta con relanzarla con el mismo periodo. La PLACSP sirve los ficheros a unos 0,2 MB/s por conexión; el script descarga 10 ficheros en paralelo.

En local (Python 3.10+, sin dependencias):

```bash
python placsp.py descargar --periodos 2025
python placsp.py construir
```

## Correo mensual

El workflow **Correo mensual de órganos** se ejecuta el día 1 de cada mes: actualiza el mes anterior y el mes en curso, regenera las fichas y el Excel de órganos (`excel_organos.py`) y lo envía por correo desde Gmail. El Excel también queda en la release [`datos`](../../releases/tag/datos).

Necesita tres secretos en *Settings → Secrets and variables → Actions*: `GMAIL_USUARIO` (cuenta Gmail remitente), `GMAIL_CONTRASENA_APP` (contraseña de aplicación de esa cuenta) y `CORREO_DESTINO`. Sin ellos el workflow genera el Excel pero no envía el correo.

## Limitaciones conocidas

- Los datos son los que publica cada órgano: hay expedientes sin importe de adjudicación, sin número de ofertas o con criterios sin ponderar.
- Los órganos se identifican por su ID de plataforma (o DIR3/NIF); un mismo organismo puede aparecer con varios perfiles.
- Los códigos de procedimiento y resultado se traducen con las listas de códigos CODICE de la PLACSP; los no reconocidos se muestran tal cual.
