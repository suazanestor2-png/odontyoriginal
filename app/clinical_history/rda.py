"""Resumen Digital de Atencion (RDA) de consulta externa en HL7 FHIR R4.

Resolucion 1888 de 2025 y guia de implementacion RDA del Ministerio de Salud
(https://vulcano.ihcecol.gov.co/guia/RDA-consulta.html).

VERSION PRELIMINAR: arma el documento con la estructura de la guia (Bundle tipo
"document" con Composition, Patient, Practitioner, Organization, Encounter, Condition,
Procedure, AllergyIntolerance y notas aclaratorias), pero NO se ha validado con el
validador oficial del Ministerio. Los valores marcados "POR CONFIRMAR" deben revisarse
contra la pagina de terminologias de la guia antes de enviar un RDA real.
"""
import uuid
from datetime import datetime, timezone

from app.appointments.models import Appointment
from app.clinical_history.models import ClinicalEntry, ClinicalNote
from app.clinics.models import Clinic
from app.core.dates import BOGOTA_TZ
from app.identity.models import User
from app.odontogram.models import OdontogramEntry
from app.patients.models import Patient

PERFIL = "https://fhir.minsalud.gov.co/rda/StructureDefinition/"
LOINC = "http://loinc.org"

# --- Sistemas de codificacion -------------------------------------------------
# POR CONFIRMAR con https://vulcano.ihcecol.gov.co/terminologias.html
SISTEMA = {
    "documento": "https://fhir.minsalud.gov.co/rda/NamingSystem/TipoDocumento",
    "nit": "https://fhir.minsalud.gov.co/rda/NamingSystem/NIT",
    "reps": "https://fhir.minsalud.gov.co/rda/NamingSystem/CodigoHabilitacion",
    "rethus": "https://fhir.minsalud.gov.co/rda/NamingSystem/RETHUS",
    "eapb": "https://fhir.minsalud.gov.co/rda/NamingSystem/CodigoEAPB",
    "cie10": "https://fhir.minsalud.gov.co/rda/CodeSystem/CIE10",
    "cups": "https://fhir.minsalud.gov.co/rda/CodeSystem/CUPS",
    "divipola": "https://fhir.minsalud.gov.co/rda/CodeSystem/DIVIPOLA",
}
PERFIL_COMPOSITION = PERFIL + "CompositionAmbulatoryRDA"  # POR CONFIRMAR: nombre del perfil de consulta externa
TIPO_DOCUMENTO = {"system": LOINC, "code": "11488-4", "display": "Consult note"}  # POR CONFIRMAR

# Secciones de la guia (codigos LOINC tomados del perfil de hospitalizacion del RDA)
SECCIONES = [
    ("sectionPayers", "48768-6", "Pagadores"),
    ("sectionHistoryOfOccupation", "74208-0", "Ocupacion"),
    ("sectionAttendanceAllowance", "105583-9", "Incapacidad"),
    ("sectionMedications", "10160-0", "Medicamentos"),
    ("sectionAllergies", "48765-2", "Alergias"),
    ("sectionProblems", "11450-4", "Diagnosticos"),
    ("sectionRiskFactors", "75492-9", "Factores de riesgo"),
    ("sectionProceduresHx", "47519-4", "Procedimientos"),
    ("sectionResults", "30954-2", "Resultados"),
    ("sectionServiceRequests", "61146-1", "Ordenes"),
    ("sectionClarificationNotes", "34109-9", "Notas aclaratorias"),
    ("sectionAddendumDocuments", "55107-7", "Documentos soporte"),
]


def _uuid() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def _iso(momento: datetime, local: bool = False) -> str:
    """FHIR exige fecha-hora con zona. Las de la base estan en UTC; las de la cita en hora de Colombia."""
    zona = BOGOTA_TZ if local else timezone.utc
    return momento.replace(tzinfo=zona).isoformat()


def _meta(perfil: str) -> dict:
    return {"profile": [PERFIL + perfil]}


def construir_rda(
    entry: ClinicalEntry,
    appt: Appointment,
    patient: Patient,
    dentist: User,
    clinic: Clinic,
    procedimientos: list[OdontogramEntry],
    notas: list[ClinicalNote],
) -> tuple[dict, list[str]]:
    """Devuelve el Bundle FHIR (dict listo para JSON) y la lista de datos que faltan para completarlo."""
    ids = {k: _uuid() for k in ("composition", "patient", "practitioner", "organization", "encounter", "condition")}
    recursos: list[tuple[str, dict]] = []
    por_seccion: dict[str, list[str]] = {nombre: [] for nombre, _, _ in SECCIONES}
    pendientes: list[str] = []

    # --- Paciente
    paciente = {
        "resourceType": "Patient",
        "meta": _meta("PatientRDA"),
        "identifier": [{
            "type": {"coding": [{"system": SISTEMA["documento"], "code": patient.document_type}]},
            "system": SISTEMA["documento"] + "/" + patient.document_type,
            "value": patient.document_number,
        }],
        "name": [{"text": patient.full_name}],
        "gender": {"Masculino": "male", "Femenino": "female"}.get(patient.gender, "unknown"),
        "birthDate": patient.birth_date.isoformat() if patient.birth_date else None,
        "telecom": [t for t in (
            {"system": "phone", "value": patient.phone_number} if patient.phone_number else None,
            {"system": "email", "value": patient.email} if patient.email else None,
        ) if t],
    }
    if patient.residence_municipality_code:
        paciente["address"] = [{
            "text": patient.address,
            "city": patient.residence_municipality_code,
            "extension": [{"url": SISTEMA["divipola"], "valueCode": patient.residence_municipality_code}],
        }]
    else:
        pendientes.append("municipio de residencia del paciente (DIVIPOLA)")
    if patient.ethnicity is None:
        pendientes.append("pertenencia etnica del paciente")
    recursos.append((ids["patient"], {k: v for k, v in paciente.items() if v not in (None, [])}))

    # --- Profesional
    identificadores = [{"system": SISTEMA["documento"] + "/CC", "value": dentist.document_number}]
    if dentist.professional_registry:
        identificadores.insert(0, {"system": SISTEMA["rethus"], "value": dentist.professional_registry})
    else:
        pendientes.append("registro ReTHUS del odontologo")
    recursos.append((ids["practitioner"], {
        "resourceType": "Practitioner",
        "meta": _meta("PractitionerRDA"),
        "identifier": identificadores,
        "name": [{"text": dentist.full_name}],
    }))

    # --- Prestador (IPS)
    org_ident = []
    if clinic.nit:
        org_ident.append({"system": SISTEMA["nit"], "value": f"{clinic.nit}-{clinic.nit_dv or ''}".rstrip("-")})
    if clinic.reps_code:
        org_ident.append({"system": SISTEMA["reps"], "value": clinic.reps_code + (clinic.reps_site_number or "")})
    else:
        pendientes.append("codigo de habilitacion REPS de la clinica")
    recursos.append((ids["organization"], {
        "resourceType": "Organization",
        "meta": _meta("CareDeliveryOrganizationRDA"),
        "identifier": org_ident,
        "name": clinic.name,
    }))

    # --- Encuentro (la consulta)
    inicio = datetime.combine(appt.scheduled_date, appt.start_time)
    fin = datetime.combine(appt.scheduled_date, appt.end_time)
    recursos.append((ids["encounter"], {
        "resourceType": "Encounter",
        "meta": _meta("EncounterAmbulatoryRDA"),
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"},
        "subject": {"reference": ids["patient"]},
        "participant": [{"individual": {"reference": ids["practitioner"]}}],
        "period": {"start": _iso(inicio, local=True), "end": _iso(fin, local=True)},
        "reasonCode": [{"text": entry.motivo_consulta}],
        "serviceProvider": {"reference": ids["organization"]},
    }))

    # --- Diagnostico (CIE-10)
    if entry.diagnosis_code:
        recursos.append((ids["condition"], {
            "resourceType": "Condition",
            "meta": _meta("ConditionRDA"),
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
            "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category", "code": "encounter-diagnosis"}]}],
            "code": {
                "coding": [{"system": SISTEMA["cie10"], "code": entry.diagnosis_code,
                            "display": entry.diagnosis.name if entry.diagnosis else None}],
                "text": entry.diagnostico,
            },
            "subject": {"reference": ids["patient"]},
            "encounter": {"reference": ids["encounter"]},
            "recordedDate": _iso(entry.created_at),
            "recorder": {"reference": ids["practitioner"]},
        }))
        por_seccion["sectionProblems"].append(ids["condition"])
    else:
        pendientes.append("diagnostico CIE-10 (consulta registrada antes de existir el campo)")

    # --- Procedimientos (CUPS) del odontograma de esta cita
    for p in procedimientos:
        if not p.cups_code:
            continue
        pid = _uuid()
        superficie = getattr(p.surface, "value", p.surface)
        recursos.append((pid, {
            "resourceType": "Procedure",
            "meta": _meta("ProcedureRDA"),
            "status": "completed",
            "code": {"coding": [{"system": SISTEMA["cups"], "code": p.cups_code,
                                 "display": p.cups.name if p.cups else None}]},
            "subject": {"reference": ids["patient"]},
            "encounter": {"reference": ids["encounter"]},
            "performedDateTime": _iso(p.created_at),
            "performer": [{"actor": {"reference": ids["practitioner"]}}],
            "bodySite": [{"text": f"Diente {p.tooth_fdi} (FDI)" + (f", superficie {superficie}" if superficie else "")}],
            "note": [{"text": p.notes}] if p.notes else None,
        }))
        por_seccion["sectionProceduresHx"].append(pid)

    # --- Alergias (texto libre: aun no se codifican)
    if patient.allergies and patient.allergies.strip():
        aid = _uuid()
        recursos.append((aid, {
            "resourceType": "AllergyIntolerance",
            "meta": _meta("AllergyIntoleranceRDA"),
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
            "code": {"text": patient.allergies.strip()},
            "patient": {"reference": ids["patient"]},
        }))
        por_seccion["sectionAllergies"].append(aid)

    # --- Ocupacion
    if patient.occupation:
        oid = _uuid()
        recursos.append((oid, {
            "resourceType": "Observation",
            "meta": _meta("PatientOccupationAtEncounterRDA"),
            "status": "final",
            "code": {"coding": [{"system": LOINC, "code": "11341-5", "display": "History of Occupation"}]},
            "subject": {"reference": ids["patient"]},
            "encounter": {"reference": ids["encounter"]},
            "valueString": patient.occupation,
        }))
        por_seccion["sectionHistoryOfOccupation"].append(oid)

    # --- Notas aclaratorias
    for n in notas:
        nid = _uuid()
        recursos.append((nid, {
            "resourceType": "Observation",
            "meta": _meta("ObservationClarificationNoteRDA"),
            "status": "final",
            "code": {"coding": [{"system": LOINC, "code": "34109-9", "display": "Note"}]},
            "subject": {"reference": ids["patient"]},
            "encounter": {"reference": ids["encounter"]},
            "effectiveDateTime": _iso(n.created_at),
            "valueString": n.text,
        }))
        por_seccion["sectionClarificationNotes"].append(nid)

    # --- Composition (indice del documento)
    secciones = []
    for nombre, codigo, titulo in SECCIONES:
        refs = por_seccion[nombre]
        if nombre == "sectionClarificationNotes" and not refs:
            continue  # es 0..1 en la guia
        seccion = {"title": titulo, "code": {"coding": [{"system": LOINC, "code": codigo}]}}
        if refs:
            seccion["entry"] = [{"reference": r} for r in refs]
        else:
            seccion["emptyReason"] = {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/list-empty-reason", "code": "nilknown"}]}
        secciones.append(seccion)

    composition = {
        "resourceType": "Composition",
        "meta": {"profile": [PERFIL_COMPOSITION]},
        "status": "final",
        "type": {"coding": [TIPO_DOCUMENTO]},
        "subject": {"reference": ids["patient"]},
        "encounter": {"reference": ids["encounter"]},
        "date": _iso(entry.created_at),
        "author": [{"reference": ids["practitioner"]}],
        "custodian": {"reference": ids["organization"]},
        "title": "Resumen Digital de Atencion en Salud - Consulta externa",
        "section": secciones,
    }

    entradas = [(ids["composition"], composition)] + recursos
    bundle = {
        "resourceType": "Bundle",
        "meta": {"tag": [{"code": "preliminar", "display": "RDA preliminar: no validado con el validador del Ministerio"}]},
        "identifier": {"system": "urn:ietf:rfc:3986", "value": _uuid()},
        "type": "document",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": [{"fullUrl": url, "resource": {k: v for k, v in r.items() if v is not None}} for url, r in entradas],
    }
    return bundle, pendientes
