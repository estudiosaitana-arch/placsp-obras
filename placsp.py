#!/usr/bin/env python3
"""
placsp-obras · Fichas de órganos de contratación (licitaciones de OBRA)
a partir de los datos abiertos de la Plataforma de Contratación del Sector Público.

Uso:
  python placsp.py descargar --periodos auto            # mes anterior + mes en curso
  python placsp.py descargar --periodos 2025            # los 12 zips mensuales de 2025
  python placsp.py descargar --periodos 202601-202609   # rango de meses
  python placsp.py construir                            # consolida y genera docs/data/*

Solo usa la biblioteca estándar de Python (3.10+).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

RAIZ = Path(__file__).resolve().parent
RAW = RAIZ / "data" / "raw"
SALIDA_DATA = RAIZ / "data"
SALIDA_WEB = RAIZ / "docs" / "data"

BASE = "https://contrataciondelsectorpublico.gob.es/sindicacion"
FUENTES = {
    # Licitaciones publicadas en la PLACSP (perfiles de contratante), sin menores
    "placsp": {
        "zip": BASE + "/sindicacion_643/licitacionesPerfilesContratanteCompleto3_{p}.zip",
    },
    # Plataformas autonómicas agregadas (Madrid, Cataluña, Euskadi, Andalucía, Galicia...), sin menores
    "agregadas": {
        "zip": BASE + "/sindicacion_1044/PlataformasAgregadasSinMenores_{p}.zip",
    },
}
UA = "placsp-obras/1.0 (+https://github.com/estudiosaitana-arch/placsp-obras)"
TIPO_OBRA = "3"

# ---------------------------------------------------------------- códigos
PROCEDIMIENTO = {
    "1": "Abierto", "2": "Restringido", "3": "Negociado sin publicidad",
    "4": "Negociado con publicidad", "5": "Diálogo competitivo", "6": "Concurso de proyectos",
    "7": "Asociación para la innovación", "8": "Licitación con negociación",
    "9": "Abierto simplificado", "100": "Normas internas", "999": "Otros",
}
ESTADO = {
    "PRE": "Anuncio previo", "PUB": "En plazo", "EV": "Pendiente de adjudicación",
    "ADJ": "Adjudicada", "RES": "Resuelta", "ANUL": "Anulada",
}
RESULTADO = {
    "1": "Adjudicado provisionalmente", "2": "Adjudicado definitivamente", "3": "Desierto",
    "4": "Desistimiento", "5": "Renuncia", "6": "Desierto provisionalmente",
    "7": "Desierto definitivamente", "8": "Adjudicado", "9": "Formalizado",
    "10": "Licitador mejor valorado: requerimiento de documentación",
    "11": "Licitador mejor valorado: requerimiento de documentación",
}
UNIDAD = {"DAY": "días", "MON": "meses", "ANN": "años", "WEE": "semanas"}
RESULTADOS_DESIERTO = {"3", "6", "7"}
RESULTADOS_SIN_ADJ = {"3", "4", "5", "6", "7"}
TIPO_ADMIN = {
    "1": "Administración General del Estado", "2": "Comunidad Autónoma",
    "3": "Administración Local", "4": "Otras entidades del sector público", "5": "Otros",
}
PROVINCIA_CP = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería", "05": "Ávila",
    "06": "Badajoz", "07": "Illes Balears", "08": "Barcelona", "09": "Burgos", "10": "Cáceres",
    "11": "Cádiz", "12": "Castellón", "13": "Ciudad Real", "14": "Córdoba", "15": "A Coruña",
    "16": "Cuenca", "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa",
    "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León", "25": "Lleida",
    "26": "La Rioja", "27": "Lugo", "28": "Madrid", "29": "Málaga", "30": "Murcia",
    "31": "Navarra", "32": "Ourense", "33": "Asturias", "34": "Palencia", "35": "Las Palmas",
    "36": "Pontevedra", "37": "Salamanca", "38": "Santa Cruz de Tenerife", "39": "Cantabria",
    "40": "Segovia", "41": "Sevilla", "42": "Soria", "43": "Tarragona", "44": "Teruel",
    "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia", "49": "Zamora",
    "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}

PROVINCIA_NUTS = {
    "ES111": "A Coruña", "ES112": "Lugo", "ES113": "Ourense", "ES114": "Pontevedra", "ES120": "Asturias",
    "ES130": "Cantabria", "ES211": "Álava", "ES212": "Gipuzkoa", "ES213": "Bizkaia", "ES220": "Navarra",
    "ES230": "La Rioja", "ES241": "Huesca", "ES242": "Teruel", "ES243": "Zaragoza", "ES300": "Madrid",
    "ES411": "Ávila", "ES412": "Burgos", "ES413": "León", "ES414": "Palencia", "ES415": "Salamanca",
    "ES416": "Segovia", "ES417": "Soria", "ES418": "Valladolid", "ES419": "Zamora", "ES421": "Albacete",
    "ES422": "Ciudad Real", "ES423": "Cuenca", "ES424": "Guadalajara", "ES425": "Toledo", "ES431": "Badajoz",
    "ES432": "Cáceres", "ES511": "Barcelona", "ES512": "Girona", "ES513": "Lleida", "ES514": "Tarragona",
    "ES521": "Alicante", "ES522": "Castellón", "ES523": "Valencia", "ES530": "Illes Balears",
    "ES531": "Illes Balears", "ES532": "Illes Balears", "ES533": "Illes Balears", "ES611": "Almería",
    "ES612": "Cádiz", "ES613": "Córdoba", "ES614": "Granada", "ES615": "Huelva", "ES616": "Jaén",
    "ES617": "Málaga", "ES618": "Sevilla", "ES620": "Murcia", "ES630": "Ceuta", "ES640": "Melilla",
    "ES703": "Santa Cruz de Tenerife", "ES704": "Las Palmas", "ES705": "Las Palmas",
    "ES706": "Santa Cruz de Tenerife", "ES707": "Santa Cruz de Tenerife", "ES708": "Las Palmas",
    "ES709": "Santa Cruz de Tenerife",
}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- descarga
def _abrir(url: str, intentos: int = 4):
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            ultimo = e
        except Exception as e:  # noqa: BLE001
            ultimo = e
        time.sleep(5 * (i + 1))
    raise ultimo  # type: ignore[misc]


def descargar_fichero(url: str, destino: Path) -> bool:
    try:
        t0, n, aviso = time.time(), 0, 50e6
        nombre = url.rsplit("/", 1)[-1]
        with _abrir(url) as r, open(destino, "wb") as f:
            total = r.headers.get("Content-Length")
            ctype = r.headers.get("Content-Type", "")
            if url.endswith(".zip") and "html" in ctype:
                log(f"  no disponible (la plataforma devuelve una página HTML): {nombre}")
                return False
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                n += len(b)
                if n >= aviso:
                    v = n / 1e6 / max(time.time() - t0, 1e-3)
                    log(f"    {nombre}: {n / 1e6:.0f} MB" + (f" de {int(total) / 1e6:.0f}" if total else "") + f" · {v:.2f} MB/s")
                    aviso += 50e6
        log(f"  descargado {nombre} ({n / 1e6:.1f} MB en {(time.time() - t0) / 60:.1f} min)")
        return True
    except urllib.error.HTTPError as e:
        log(f"  no disponible ({e.code}): {url}")
        return False


# ---------------------------------------------------------------- parseo
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _limpiar_ns(el: ET.Element) -> None:
    for e in el.iter():
        e.tag = _local(e.tag)
        if e.attrib:
            e.attrib = {_local(k): v for k, v in e.attrib.items()}


def _t(el, path, default=""):
    if el is None:
        return default
    x = el.find(path)
    return (x.text or "").strip() if x is not None and x.text else default


def _num(el, path):
    v = _t(el, path)
    try:
        return round(float(v), 2) if v != "" else None
    except ValueError:
        return None


def _criterios(terms):
    """Devuelve lista de criterios y resumen de pesos (subjetivos / precio / total)."""
    crit = []
    if terms is None:
        return crit
    for c in terms.findall("AwardingTerms/AwardingCriteria"):
        tipo = _t(c, "AwardingCriteriaTypeCode") or "OBJ"
        sub = _t(c, "AwardingCriteriaSubTypeCode")
        desc = _t(c, "Description")[:160]
        try:
            peso = float(_t(c, "WeightNumeric") or "nan")
        except ValueError:
            peso = float("nan")
        crit.append({"tipo": tipo, "sub": sub, "desc": desc, "peso": None if peso != peso else peso})
    return crit


def _resumen_criterios(crit):
    pesos = [c for c in crit if c["peso"] is not None]
    if not pesos:
        return None, None, None
    total = sum(c["peso"] for c in pesos) or None
    if not total:
        return None, None, None
    subj = sum(c["peso"] for c in pesos if c["tipo"] == "SUBJ")
    precio = sum(
        c["peso"] for c in pesos
        if c["sub"] == "1" or re.search(r"\b(precio|oferta econ|econ[oó]mic)", c["desc"], re.I)
    )
    return round(total, 2), round(100 * subj / total, 1), round(100 * precio / total, 1)


def _organo(lcp):
    party = lcp.find("Party") if lcp is not None else None
    ids = {}
    if party is not None:
        for i in party.findall("PartyIdentification/ID"):
            ids[i.get("schemeName", "ID")] = (i.text or "").strip()
    nombre = _t(party, "PartyName/Name")
    # Cadena de dependencia (de más cercano a raíz)
    dep = []
    p = lcp.find("ParentLocatedParty") if lcp is not None else None
    while p is not None:
        n = _t(p, "PartyName/Name")
        if n:
            dep.append(n)
        p = p.find("ParentLocatedParty")
    cp = _t(party, "PostalAddress/PostalZone")
    oid = ids.get("ID_PLATAFORMA") or ids.get("DIR3") or ids.get("NIF")
    if not oid:
        oid = "N" + hashlib.md5(nombre.lower().encode()).hexdigest()[:12]
    return {
        "org_id": re.sub(r"[^A-Za-z0-9_-]", "", oid),
        "org_nombre": nombre,
        "org_nif": ids.get("NIF", ""),
        "org_dir3": ids.get("DIR3", ""),
        "org_tipo": _t(lcp, "ContractingPartyTypeCode"),
        "org_ciudad": _t(party, "PostalAddress/CityName"),
        "org_cp": cp,
        "org_provincia": PROVINCIA_CP.get(cp[:2], "") if len(cp) >= 2 else "",
        "org_web": _t(party, "WebsiteURI"),
        "org_email": _t(party, "Contact/ElectronicMail"),
        "org_dependencia": " › ".join(d for d in reversed(dep) if d.lower() != "sector público"),
        "org_perfil": _t(lcp, "BuyerProfileURIID"),
    }


def parsear_entry(entry: ET.Element, fuente: str):
    _limpiar_ns(entry)
    cfs = entry.find("ContractFolderStatus")
    if cfs is None:
        return None
    pp = cfs.find("ProcurementProject")
    if _t(pp, "TypeCode") != TIPO_OBRA:
        return None
    link = entry.find("link")
    rec = {
        "id": _t(entry, "id"),
        "updated": _t(entry, "updated"),
        "fuente": fuente,
        "url": link.get("href", "") if link is not None else "",
        "expediente": _t(cfs, "ContractFolderID"),
        "estado": _t(cfs, "ContractFolderStatusCode"),
        "objeto": _t(pp, "Name") or _t(entry, "title"),
        "subtipo": _t(pp, "SubTypeCode"),
        "valor_estimado": _num(pp, "BudgetAmount/EstimatedOverallContractAmount"),
        "pbl_sin_iva": _num(pp, "BudgetAmount/TaxExclusiveAmount"),
        "pbl_con_iva": _num(pp, "BudgetAmount/TotalAmount"),
        "cpv": [ (c.text or "").strip() for c in pp.findall("RequiredCommodityClassification/ItemClassificationCode")][:6],
        "nuts": _t(pp, "RealizedLocation/CountrySubentityCode"),
        "lugar": _t(pp, "RealizedLocation/CountrySubentity"),
        "plazo_ejecucion": _t(pp, "PlannedPeriod/DurationMeasure"),
        "plazo_unidad": (pp.find("PlannedPeriod/DurationMeasure").get("unitCode", "")
                          if pp.find("PlannedPeriod/DurationMeasure") is not None else ""),
    }
    rec.update(_organo(cfs.find("LocatedContractingParty")))

    tp = cfs.find("TenderingProcess")
    rec["procedimiento"] = _t(tp, "ProcedureCode")
    rec["urgencia"] = _t(tp, "UrgencyCode")
    rec["fin_ofertas"] = _t(tp, "TenderSubmissionDeadlinePeriod/EndDate")
    rec["sara"] = _t(tp, "OverThresholdIndicator")

    # Fechas de publicación por tipo de anuncio
    pub = {}
    for v in cfs.findall("ValidNoticeInfo"):
        tipo = _t(v, "NoticeTypeCode")
        fechas = [(_t(a, "AdditionalPublicationDocumentReference/IssueDate"))
                  for a in v.findall("AdditionalPublicationStatus")]
        fechas = [f for f in fechas if f]
        if tipo and fechas:
            pub[tipo] = min([pub.get(tipo, "9999")] + fechas)
    rec["f_anuncio"] = pub.get("DOC_CN") or pub.get("DOC_PIN") or ""
    rec["f_adj_anuncio"] = pub.get("DOC_CAN_ADJ", "")
    rec["f_formalizacion_anuncio"] = pub.get("DOC_FORM", "")

    # Pliegos
    rec["pcap"] = _t(cfs, "LegalDocumentReference/Attachment/ExternalReference/URI")
    rec["ppt"] = _t(cfs, "TechnicalDocumentReference/Attachment/ExternalReference/URI")

    # Criterios de adjudicación (expediente o, si no hay, primer lote)
    terms = cfs.find("TenderingTerms")
    crit = _criterios(terms)
    if not crit:
        for lot in cfs.findall("ProcurementProjectLot"):
            crit = _criterios(lot.find("TenderingTerms"))
            if crit:
                break
    rec["criterios"] = crit
    rec["peso_total"], rec["pct_juicio_valor"], rec["pct_precio"] = _resumen_criterios(crit)
    rec["recursos"] = _t(terms, "ReceivedAppealQuantity")

    # Lotes
    lotes = {}
    for lot in cfs.findall("ProcurementProjectLot"):
        lid = _t(lot, "ID")
        lpp = lot.find("ProcurementProject")
        lotes[lid] = {
            "id": lid,
            "nombre": _t(lpp, "Name")[:200],
            "pbl_sin_iva": _num(lpp, "BudgetAmount/TaxExclusiveAmount"),
        }
    rec["n_lotes"] = len(lotes) or 1

    # Resultados (uno por lote adjudicado)
    res = []
    for tr in cfs.findall("TenderResult"):
        lid = _t(tr, "AwardedTenderedProject/ProcurementProjectLotID")
        base = (lotes.get(lid) or {}).get("pbl_sin_iva") if lid else None
        if base is None and len(lotes) <= 1:
            base = rec["pbl_sin_iva"]
        adj = _num(tr, "AwardedTenderedProject/LegalMonetaryTotal/TaxExclusiveAmount")
        baja = None
        if adj is not None and base:
            b = 1 - adj / base
            if 0 <= b < 0.9:
                baja = round(100 * b, 2)
        wp = tr.find("WinningParty")
        res.append({
            "lote": lid,
            "resultado": _t(tr, "ResultCode"),
            "f_adjudicacion": _t(tr, "AwardDate"),
            "ofertas": _num(tr, "ReceivedTenderQuantity"),
            "ofertas_pyme": _num(tr, "SMEsReceivedTenderQuantity"),
            "oferta_min": _num(tr, "LowerTenderAmount"),
            "oferta_max": _num(tr, "HigherTenderAmount"),
            "adjudicatario": _t(wp, "PartyName/Name"),
            "adjudicatario_nif": _t(wp, "PartyIdentification/ID").upper().replace(" ", ""),
            "adjudicatario_nuts": _t(wp, "PhysicalLocation/CountrySubentityCode"),
            "pyme": _t(tr, "SMEAwardedIndicator"),
            "importe_adj_sin_iva": adj,
            "importe_adj_con_iva": _num(tr, "AwardedTenderedProject/LegalMonetaryTotal/PayableAmount"),
            "base_sin_iva": base,
            "baja_pct": baja,
            "f_contrato": _t(tr, "Contract/IssueDate"),
        })
    rec["resultados"] = res
    return rec


def parsear_atom(fich, fuente: str, salida: list, borrados: list):
    """Parsea un fichero .atom (ruta o file-like) y añade los registros de obra."""
    feed_updated = None
    ctx = ET.iterparse(fich, events=("start", "end"))
    profundidad = 0
    for ev, el in ctx:
        nombre = _local(el.tag)
        if ev == "start":
            profundidad += 1
            continue
        profundidad -= 1
        if nombre == "entry":
            try:
                r = parsear_entry(el, fuente)
                if r:
                    salida.append(r)
            except Exception as e:  # noqa: BLE001
                log("  aviso: entry no parseable:", e)
            el.clear()
        elif nombre == "deleted-entry":
            borrados.append({"id": el.get("ref", ""), "when": el.get("when", "")})
            el.clear()
        elif nombre == "updated" and profundidad == 1 and feed_updated is None:
            feed_updated = (el.text or "").strip()
    return feed_updated


def guardar_raw(fuente: str, periodo: str, regs: list, borrados: list):
    RAW.mkdir(parents=True, exist_ok=True)
    ruta = RAW / f"{fuente}_{periodo}.jsonl.gz"
    with gzip.open(ruta, "wt", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
        for b in borrados:
            f.write(json.dumps({"_borrado": b["id"], "when": b["when"]}, separators=(",", ":")) + "\n")
    log(f"  guardado {ruta.relative_to(RAIZ)}: {len(regs)} registros de obra, {len(borrados)} borrados")


def procesar_zip(fuente: str, periodo: str) -> bool:
    url = FUENTES[fuente]["zip"].format(p=periodo)
    log(f"[{fuente}] {periodo}: descargando")
    with tempfile.TemporaryDirectory() as tmp:
        z = Path(tmp) / "f.zip"
        if not descargar_fichero(url, z):
            return False
        regs, borr = [], []
        with zipfile.ZipFile(z) as zf:
            nombres = [n for n in zf.namelist() if n.endswith(".atom")]
            log(f"[{fuente}] {periodo}: {len(nombres)} ficheros atom en el zip")
            for i, n in enumerate(nombres, 1):
                with zf.open(n) as fh:
                    parsear_atom(fh, fuente, regs, borr)
                if i % 200 == 0:
                    log(f"[{fuente}] {periodo}: {i}/{len(nombres)} ({len(regs)} obras)")
        guardar_raw(fuente, periodo, regs, borr)
    return True


def periodos_desde(txt: str, hoy: dt.date):
    """'auto' | '2025' | '202601-202609' | lista separada por comas. Devuelve meses AAAAMM."""
    actual = hoy.strftime("%Y%m")
    out = []
    for parte in [p.strip() for p in txt.split(",") if p.strip()]:
        if parte in ("ninguno", "no"):
            continue
        if parte == "auto":
            prev = (hoy.replace(day=1) - dt.timedelta(days=1))
            out += [prev.strftime("%Y%m"), actual]
            continue
        if re.fullmatch(r"\d{4}", parte):
            a, b = parte + "01", parte + "12"
        elif re.fullmatch(r"\d{6}-\d{6}", parte):
            a, b = parte.split("-")
        elif re.fullmatch(r"\d{6}", parte):
            a = b = parte
        else:
            sys.exit(f"Periodo no reconocido: {parte}")
        y, m = int(a[:4]), int(a[4:])
        while f"{y:04d}{m:02d}" <= min(b, actual):
            out.append(f"{y:04d}{m:02d}")
            m += 1
            if m == 13:
                y, m = y + 1, 1
    return list(dict.fromkeys(out))


def cmd_descargar(args):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    hoy = dt.date.today()
    recientes = set(periodos_desde("auto", hoy))
    fuentes = [f.strip() for f in args.fuentes.split(",")]
    tareas = []
    for p in periodos_desde(args.periodos, hoy):
        for fu in fuentes:
            ya = (RAW / f"{fu}_{p}.jsonl.gz").exists()
            if ya and p not in recientes and not args.forzar:
                log(f"[{fu}] {p}: ya descargado, se omite (use --forzar para repetir)")
                continue
            tareas.append((fu, p))
    log(f"{len(tareas)} ficheros a descargar con {args.hilos} descargas en paralelo")
    fallos = []
    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        futs = {ex.submit(procesar_zip, fu, p): (fu, p) for fu, p in tareas}
        for f in as_completed(futs):
            fu, p = futs[f]
            try:
                if not f.result():
                    fallos.append(f"{fu}_{p}")
            except Exception as e:  # noqa: BLE001
                log(f"[{fu}] {p}: ERROR {e}")
                fallos.append(f"{fu}_{p}")
    if fallos:
        log("No descargados:", ", ".join(sorted(fallos)))


# ---------------------------------------------------------------- construir
def cargar_registros():
    ultimos: dict[str, dict] = {}
    borrados: dict[str, str] = {}
    ficheros = sorted(RAW.glob("*.jsonl.gz"))
    for fch in ficheros:
        with gzip.open(fch, "rt", encoding="utf-8") as f:
            for linea in f:
                r = json.loads(linea)
                if "_borrado" in r:
                    if r["when"] > borrados.get(r["_borrado"], ""):
                        borrados[r["_borrado"]] = r["when"]
                    continue
                k = r["id"] or (r["org_id"] + "|" + r["expediente"])
                if k not in ultimos or r["updated"] >= ultimos[k]["updated"]:
                    ultimos[k] = r
    regs = [r for k, r in ultimos.items() if not (k in borrados and borrados[k] >= r["updated"])]
    log(f"{len(ficheros)} ficheros raw · {len(regs)} expedientes de obra únicos "
        f"({len(ultimos) - len(regs)} eliminados por tombstone)")
    return regs


def _anio(r):
    f = r.get("f_anuncio") or r.get("fin_ofertas") or r.get("updated") or ""
    return f[:4]


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def _media(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def _dias(a, b):
    try:
        return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days
    except Exception:  # noqa: BLE001
        return None


CLASES_JV = {"jv": "Con juicio de valor", "auto": "Solo criterios automáticos", "sd": "Sin datos de criterios"}


def clase_jv(r) -> str:
    """Clasifica el expediente por sus criterios de adjudicación (AwardingCriteriaTypeCode)."""
    crit = r.get("criterios") or []
    if not crit:
        return "sd"
    if any(c["tipo"] == "SUBJ" and (c["peso"] is None or c["peso"] > 0) for c in crit):
        return "jv"
    return "auto"


def tramo_jv(p):
    if p is None:
        return None
    return "JV ≤ 25 %" if p <= 25 else "JV 25–49 %" if p < 50 else "JV ≥ 50 %"


def _stats_grupo(rs_g, ids_adj):
    """Indicadores de un subconjunto de expedientes (no anulados)."""
    res = [x for r in rs_g for x in r["resultados"]]
    adj = [x for x in res if id(x) in ids_adj]
    bajas = [x["baja_pct"] for x in adj if x["baja_pct"] is not None]
    ofertas = [x["ofertas"] for x in adj if x["ofertas"] is not None]
    n_res = len([x for x in res if x["resultado"]])
    des = len([x for x in res if x["resultado"] in RESULTADOS_DESIERTO])
    return {
        "n": len(rs_g),
        "pbl_total": round(sum(r["pbl_sin_iva"] or 0 for r in rs_g), 2),
        "pbl_mediana": _med([r["pbl_sin_iva"] for r in rs_g]),
        "lotes_adj": len(adj),
        "lotes_con_baja": len(bajas),
        "baja_media": _media(bajas), "baja_mediana": _med(bajas),
        "baja_p75": (round(statistics.quantiles(bajas, n=4)[2], 2) if len(bajas) >= 4 else None),
        "ofertas_media": _media(ofertas),
        "pct_desierto": round(100 * des / n_res, 1) if n_res else None,
        "peso_jv_medio": _media([r["pct_juicio_valor"] for r in rs_g if r["pct_juicio_valor"] is not None]),
        "peso_precio_medio": _media([r["pct_precio"] for r in rs_g if r.get("pct_precio") is not None]),
    }


def ficha_organo(rs: list[dict]) -> dict:
    rs = sorted(rs, key=lambda r: (r.get("f_anuncio") or r.get("updated") or ""), reverse=True)
    o = rs[0]
    res = [x for r in rs for x in r["resultados"]]
    res_adj = [x for x in res if x["resultado"] not in RESULTADOS_SIN_ADJ and x["importe_adj_sin_iva"]]
    ids_adj = {id(x) for x in res_adj}
    lic = [r for r in rs if r["estado"] != "ANUL"]

    por_anio = defaultdict(lambda: {"n": 0, "pbl": 0.0, "adj": 0.0})
    for r in lic:
        a = _anio(r)
        por_anio[a]["n"] += 1
        por_anio[a]["pbl"] += r["pbl_sin_iva"] or 0
    for r in lic:
        for x in r["resultados"]:
            if id(x) in ids_adj:
                por_anio[_anio(r)]["adj"] += x["importe_adj_sin_iva"] or 0

    adjudicatarios = defaultdict(lambda: {"nombre": "", "n": 0, "importe": 0.0, "bajas": []})
    for x in res_adj:
        k = x["adjudicatario_nif"] or x["adjudicatario"].upper()
        a = adjudicatarios[k]
        a["nombre"] = a["nombre"] or x["adjudicatario"]
        a["n"] += 1
        a["importe"] += x["importe_adj_sin_iva"] or 0
        if x["baja_pct"] is not None:
            a["bajas"].append(x["baja_pct"])
    top = sorted(adjudicatarios.items(), key=lambda kv: (-kv[1]["n"], -kv[1]["importe"]))[:25]

    plazos_adj = [_dias(r["fin_ofertas"], x["f_adjudicacion"]) for r in rs for x in r["resultados"]
                  if r["fin_ofertas"] and x["f_adjudicacion"]]
    plazos_adj = [d for d in plazos_adj if d is not None and 0 <= d <= 730]
    n_res = len([x for x in res if x["resultado"]])
    desiertos = len([x for x in res if x["resultado"] in RESULTADOS_DESIERTO])
    bajas = [x["baja_pct"] for x in res_adj if x["baja_pct"] is not None]
    ofertas = [x["ofertas"] for x in res_adj if x["ofertas"] is not None]
    jv = [r["pct_juicio_valor"] for r in lic if r["pct_juicio_valor"] is not None]

    def tramo(v):
        if v is None:
            return None
        return "< 200 k€" if v < 2e5 else "200 k€ – 1 M€" if v < 1e6 else "1 – 5,38 M€" if v < 5.538e6 else "≥ 5,38 M€ (SARA)"

    bajas_tramo = defaultdict(list)
    for r in lic:
        for x in r["resultados"]:
            if x["baja_pct"] is not None:
                bajas_tramo[tramo(x["base_sin_iva"])].append(x["baja_pct"])

    provincia = o["org_provincia"]
    if not provincia:  # sin código postal (habitual en plataformas agregadas): provincia más frecuente de las obras
        c = Counter(PROVINCIA_NUTS.get(r["nuts"]) for r in rs if PROVINCIA_NUTS.get(r["nuts"]))
        provincia = c.most_common(1)[0][0] if c else ""
    tipo = TIPO_ADMIN.get(o["org_tipo"]) or (f"Código {o['org_tipo']}" if o["org_tipo"] else "Sin clasificar")
    por_jv = {k: _stats_grupo([r for r in lic if clase_jv(r) == k], ids_adj) for k in CLASES_JV}
    tramos_jv = {}
    for t in ("JV ≤ 25 %", "JV 25–49 %", "JV ≥ 50 %"):
        g = [r for r in lic if clase_jv(r) == "jv" and tramo_jv(r["pct_juicio_valor"]) == t]
        if g:
            tramos_jv[t] = _stats_grupo(g, ids_adj)
    clasif = por_jv["jv"]["n"] + por_jv["auto"]["n"]
    return {
        "id": o["org_id"], "nombre": o["org_nombre"], "nif": o["org_nif"], "dir3": o["org_dir3"],
        "tipo": tipo, "ciudad": o["org_ciudad"],
        "provincia": provincia, "cp": o["org_cp"], "web": o["org_web"],
        "email": o["org_email"], "dependencia": re.sub(r"^Sector P[úu]blico › ", "", o["org_dependencia"], flags=re.I), "perfil": o["org_perfil"],
        "fuente": o["fuente"],
        "resumen": {
            "expedientes": len(lic),
            "anulados": len(rs) - len(lic),
            "en_plazo": len([r for r in rs if r["estado"] == "PUB"]),
            "pbl_total": round(sum(r["pbl_sin_iva"] or 0 for r in lic), 2),
            "pbl_mediana": _med([r["pbl_sin_iva"] for r in lic]),
            "adjudicado_total": round(sum(x["importe_adj_sin_iva"] or 0 for x in res_adj), 2),
            "lotes_adjudicados": len(res_adj),
            "baja_media": _media(bajas), "baja_mediana": _med(bajas),
            "baja_p75": (round(statistics.quantiles(bajas, n=4)[2], 2) if len(bajas) >= 4 else None),
            "ofertas_media": _media(ofertas), "ofertas_mediana": _med(ofertas),
            "pct_desierto": round(100 * desiertos / n_res, 1) if n_res else None,
            "juicio_valor_medio": _media(jv),
            "pct_solo_automaticos": round(100 * len([v for v in jv if v == 0]) / len(jv), 1) if jv else None,
            "pct_con_jv": round(100 * por_jv["jv"]["n"] / clasif, 1) if clasif else None,
            "exp_con_jv": por_jv["jv"]["n"], "exp_solo_auto": por_jv["auto"]["n"], "exp_sin_criterios": por_jv["sd"]["n"],
            "dias_fin_ofertas_a_adjudicacion": _med(plazos_adj),
            "pct_pyme_adjudicataria": (round(100 * len([x for x in res_adj if x["pyme"] == "true"]) / len(res_adj), 1)
                                        if res_adj else None),
            "ultima_publicacion": max((r.get("f_anuncio") or "" for r in rs), default=""),
        },
        "por_anio": {k: {"n": v["n"], "pbl": round(v["pbl"], 2), "adj": round(v["adj"], 2)}
                     for k, v in sorted(por_anio.items()) if k},
        "por_juicio_valor": {CLASES_JV[k]: v for k, v in por_jv.items()},
        "jv_por_peso": tramos_jv,
        "procedimientos": dict(Counter(PROCEDIMIENTO.get(r["procedimiento"], r["procedimiento"] or "—") for r in lic).most_common()),
        "bajas_por_tramo": {k: {"n": len(v), "media": _media(v), "mediana": _med(v)}
                            for k, v in bajas_tramo.items() if k},
        "lugares": dict(Counter(r["lugar"] for r in lic if r["lugar"]).most_common(10)),
        "cpv": dict(Counter(c for r in lic for c in r["cpv"][:1]).most_common(10)),
        "adjudicatarios": [
            {"nif": k, "nombre": v["nombre"], "n": v["n"], "importe": round(v["importe"], 2),
             "baja_media": _media(v["bajas"])} for k, v in top
        ],
        "expedientes": [
            {
                "exp": r["expediente"], "objeto": r["objeto"][:300], "estado": ESTADO.get(r["estado"], r["estado"]),
                "proc": PROCEDIMIENTO.get(r["procedimiento"], r["procedimiento"]),
                "f_anuncio": r["f_anuncio"], "fin_ofertas": r["fin_ofertas"],
                "pbl": r["pbl_sin_iva"], "ve": r["valor_estimado"], "lotes": r["n_lotes"],
                "jv": r["pct_juicio_valor"], "cjv": clase_jv(r), "precio": r.get("pct_precio"), "plazo": (r["plazo_ejecucion"] + " " + UNIDAD.get(r["plazo_unidad"], r["plazo_unidad"])).strip() if r["plazo_ejecucion"] else "",
                "lugar": r["lugar"], "url": r["url"], "pcap": r["pcap"],
                "res": [
                    {"lote": x["lote"], "r": RESULTADO.get(x["resultado"], x["resultado"]),
                     "adj": x["adjudicatario"], "nif": x["adjudicatario_nif"], "imp": x["importe_adj_sin_iva"],
                     "baja": x["baja_pct"], "of": x["ofertas"], "f": x["f_adjudicacion"]}
                    for x in r["resultados"]
                ],
            }
            for r in rs[:400]
        ],
    }


def cmd_construir(args):
    regs = cargar_registros()
    if not regs:
        sys.exit("No hay datos en data/raw. Ejecute primero: python placsp.py descargar")
    if args.desde:
        regs = [r for r in regs if _anio(r) >= args.desde]

    # Tabla plana de expedientes y adjudicaciones (CSV para Excel)
    SALIDA_DATA.mkdir(parents=True, exist_ok=True)
    cols = ["expediente", "org_id", "org_nombre", "org_provincia", "org_tipo", "estado", "objeto",
            "procedimiento", "f_anuncio", "fin_ofertas", "valor_estimado", "pbl_sin_iva", "n_lotes",
            "clase_jv", "pct_juicio_valor", "pct_precio", "nuts", "lugar", "url", "pcap", "updated", "fuente"]
    with gzip.open(SALIDA_DATA / "expedientes_obra.csv.gz", "wt", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for r in regs:
            r["clase_jv"] = CLASES_JV[clase_jv(r)]
            w.writerow([r.get(c, "") if not isinstance(r.get(c), float) else str(r[c]).replace(".", ",") for c in cols])
    rcols = ["lote", "resultado", "f_adjudicacion", "ofertas", "ofertas_pyme", "adjudicatario",
             "adjudicatario_nif", "pyme", "base_sin_iva", "importe_adj_sin_iva", "baja_pct"]
    with gzip.open(SALIDA_DATA / "adjudicaciones_obra.csv.gz", "wt", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["expediente", "org_id", "org_nombre", "org_provincia"] + rcols + ["url"])
        for r in regs:
            for x in r["resultados"]:
                fila = [r["expediente"], r["org_id"], r["org_nombre"], r["org_provincia"]]
                fila += [str(x[c]).replace(".", ",") if isinstance(x[c], float) else x[c] for c in rcols]
                w.writerow(fila + [r["url"]])

    # Fichas por órgano
    grupos = defaultdict(list)
    for r in regs:
        grupos[r["org_id"]].append(r)
    destino = SALIDA_WEB / "o"
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    indice = []
    for oid, rs in grupos.items():
        fi = ficha_organo(rs)
        (destino / f"{oid}.json").write_text(json.dumps(fi, ensure_ascii=False, separators=(",", ":")), "utf-8")
        s = fi["resumen"]
        indice.append([oid, fi["nombre"], fi["provincia"], fi["tipo"], fi["dependencia"][:120],
                       s["expedientes"], round(s["pbl_total"]), s["baja_media"], s["ofertas_media"],
                       s["juicio_valor_medio"], s["ultima_publicacion"], s["en_plazo"],
                       s["pct_con_jv"], fi["por_juicio_valor"]["Con juicio de valor"]["baja_media"],
                       fi["por_juicio_valor"]["Solo criterios automáticos"]["baja_media"]])
    indice.sort(key=lambda x: -x[5])
    meta = {
        "generado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "expedientes": len(regs), "organos": len(indice),
        "periodos": sorted(p.name.replace(".jsonl.gz", "") for p in RAW.glob("*.jsonl.gz")),
        "campos": ["id", "nombre", "provincia", "tipo", "dependencia", "expedientes", "pbl_total",
                   "baja_media", "ofertas_media", "juicio_valor_medio", "ultima_publicacion", "en_plazo",
                   "pct_con_jv", "baja_media_con_jv", "baja_media_solo_auto"],
    }
    (SALIDA_WEB / "indice.json").write_text(
        json.dumps({"meta": meta, "organos": indice}, ensure_ascii=False, separators=(",", ":")), "utf-8")
    with open(SALIDA_DATA / "organos_obra.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(meta["campos"])
        for fila in indice:
            w.writerow([str(v).replace(".", ",") if isinstance(v, float) else v for v in fila])
    log(f"Fichas generadas: {len(indice)} órganos · {len(regs)} expedientes")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("descargar")
    d.add_argument("--periodos", default="auto")
    d.add_argument("--fuentes", default="placsp,agregadas")
    d.add_argument("--hilos", type=int, default=10, help="Descargas simultáneas")
    d.add_argument("--forzar", action="store_true", help="Repetir periodos ya descargados")
    d.set_defaults(func=cmd_descargar)
    c = sub.add_parser("construir")
    c.add_argument("--desde", default="", help="Año mínimo (AAAA) a incluir en las fichas")
    c.set_defaults(func=cmd_construir)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
