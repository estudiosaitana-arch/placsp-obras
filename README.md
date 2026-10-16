# placsp-obras

Fichas de **órganos de contratación** a partir de las **licitaciones de obra** publicadas en los datos abiertos de la Plataforma de Contratación del Sector Público (PLACSP). Ámbito: todo el Estado.

## Qué hace

1. **Descarga** los ficheros de sindicación de la PLACSP:
   - `sindicacion_643`: licitaciones publicadas en la PLACSP (sin contratos menores).
   - `sindicacion_1044`: plataformas autonómicas agregadas (sin contratos menores).
2. **Filtra** los expedientes con tipo de contrato *Obras* (`TypeCode = 3`) y guarda una versión compacta en `data/raw/` (un fichero por fuente y periodo).
3. **Consolida** (se queda con la última versión de cada expediente y descarta los eliminados) y **genera**:
   - `docs/data/indice.json` y `docs/data/o/<órgano>.json`: fichas por órgano.
   - `data/expedientes_obra.csv.gz`, `data/adjudicaciones_obra.csv.gz`, `data/organos_obra.csv`: tablas para Excel (separador `;`, UTF-8).
4. **Publica** el visor `docs/index.html` (GitHub Pages).

## Indicadores de cada ficha

Expedientes e importe licitado (total y por año), PBL mediano, baja media / mediana / percentil 75 (global y por tramo de presupuesto), ofertas por lote, peso medio de los criterios sujetos a juicio de valor, % de expedientes solo con criterios automáticos, % de lotes desiertos, días entre fin de ofertas y adjudicación, % adjudicado a pyme, procedimientos, principales adjudicatarios y listado de expedientes con enlace a la PLACSP y al PCAP.

**Baja** = 1 − importe de adjudicación sin IVA / presupuesto base de licitación sin IVA del lote. Se descartan valores fuera de 0–90 %.

## Uso

Automático: el workflow **Actualizar datos PLACSP** se ejecuta cada lunes (vuelve a descargar el mes anterior y el mes en curso).

Carga histórica (una ejecución por año, desde *Actions → Actualizar datos PLACSP → Run workflow*):

| periodos | qué descarga |
|---|---|
| `auto` | mes anterior + mes en curso |
| `2025` | los 12 ficheros mensuales de 2025 |
| `202401-202406` | rango de meses |

Los meses ya descargados se omiten, así que si una carga se corta por tiempo basta con relanzarla con el mismo periodo. La PLACSP sirve los ficheros a unos 0,2 MB/s por conexión; el script descarga 6 meses en paralelo.

En local (Python 3.10+, sin dependencias):

```bash
python placsp.py descargar --periodos 2025
python placsp.py construir
```

## Limitaciones conocidas

- Los datos son los que publica cada órgano: hay expedientes sin importe de adjudicación, sin número de ofertas o con criterios sin ponderar.
- Los órganos se identifican por su ID de plataforma (o DIR3/NIF); un mismo organismo puede aparecer con varios perfiles.
- Los códigos de procedimiento y resultado se traducen con las listas de códigos CODICE de la PLACSP; los no reconocidos se muestran tal cual.
