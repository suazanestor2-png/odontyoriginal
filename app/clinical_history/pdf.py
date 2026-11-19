"""Copia de la historia clinica en PDF (el paciente es titular de su historia: Ley 2015 de 2020)."""
from datetime import datetime, timezone

from fpdf import FPDF

from app.clinical_history.schemas import ClinicalEntryOut
from app.clinics.models import Clinic
from app.core.dates import BOGOTA_TZ
from app.odontogram.schemas import OdontogramEntryOut
from app.patients.models import Patient


def _local(momento: datetime) -> datetime:
    """Las fechas se guardan en UTC; en el documento se muestran en hora de Colombia."""
    return momento.replace(tzinfo=timezone.utc).astimezone(BOGOTA_TZ)


def _txt(texto) -> str:
    # Las fuentes base del PDF son latin-1: se reemplaza lo que no se pueda representar
    return str(texto or "").encode("latin-1", "replace").decode("latin-1")


class _HistoriaPDF(FPDF):
    pie = ""

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 5, _txt(self.pie), align="L")
        self.cell(0, 5, f"Pagina {self.page_no()}/{{nb}}", align="R")


def _titulo(pdf: FPDF, texto: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(238, 242, 255)
    pdf.cell(0, 7, _txt(texto), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def _campo(pdf: FPDF, etiqueta: str, valor) -> None:
    if valor in (None, ""):
        return
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(42, 5, _txt(etiqueta))
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _txt(valor), new_x="LMARGIN", new_y="NEXT")


def render_historia_pdf(
    clinic: Clinic,
    patient: Patient,
    consultas: list[ClinicalEntryOut],
    odontograma: list[OdontogramEntryOut],
    generado_por: str,
    generado_en: datetime,
) -> bytes:
    pdf = _HistoriaPDF(format="Letter")
    pdf.pie = f"Copia de historia clinica generada el {generado_en:%d/%m/%Y %H:%M} por {generado_por}. Documento confidencial."
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Prestador
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _txt(clinic.name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    linea = f"NIT {clinic.nit}-{clinic.nit_dv or ''}" if clinic.nit else ""
    if clinic.reps_code:
        linea += f"   Codigo REPS {clinic.reps_code}" + (f" sede {clinic.reps_site_number}" if clinic.reps_site_number else "")
    if linea.strip():
        pdf.cell(0, 5, _txt(linea.strip()), new_x="LMARGIN", new_y="NEXT")
    direccion = ", ".join(x for x in (clinic.address, clinic.city) if x)
    if direccion:
        pdf.cell(0, 5, _txt(direccion), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "HISTORIA CLINICA ODONTOLOGICA", align="C", new_x="LMARGIN", new_y="NEXT")

    # Paciente
    _titulo(pdf, "Identificacion del paciente")
    _campo(pdf, "Nombre", patient.full_name)
    _campo(pdf, "Documento", f"{patient.document_type} {patient.document_number}")
    _campo(pdf, "Fecha de nacimiento", patient.birth_date.strftime("%d/%m/%Y") if patient.birth_date else None)
    _campo(pdf, "Sexo", patient.gender)
    _campo(pdf, "EPS", " - ".join(x for x in (patient.eps_code, patient.eps) if x))
    _campo(pdf, "Municipio (DIVIPOLA)", patient.residence_municipality_code)
    _campo(pdf, "Direccion", patient.address)
    _campo(pdf, "Telefono", patient.phone_number)
    _campo(pdf, "Alergias", patient.allergies)
    _campo(pdf, "Medicamentos", patient.current_medications)
    _campo(pdf, "Condiciones medicas", patient.medical_conditions)
    if patient.guardian_full_name:
        _campo(pdf, "Acudiente", f"{patient.guardian_full_name} ({patient.guardian_relationship or 'acudiente'})"
                                 f" - doc. {patient.guardian_document_number or ''}")

    # Consultas (de la mas antigua a la mas reciente, como en la historia en papel)
    _titulo(pdf, f"Consultas ({len(consultas)})")
    if not consultas:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, "Sin consultas registradas.", new_x="LMARGIN", new_y="NEXT")
    for c in sorted(consultas, key=lambda x: x.created_at):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _txt(f"{_local(c.created_at):%d/%m/%Y %H:%M}  -  Odontologo: {c.dentist_name}"),
                 new_x="LMARGIN", new_y="NEXT")
        _campo(pdf, "Motivo de consulta", c.motivo_consulta)
        _campo(pdf, "Antecedentes", c.antecedentes)
        _campo(pdf, "Examen", c.examen)
        diag = c.diagnostico
        if c.diagnosis_code:
            diag = f"{c.diagnosis_code} {c.diagnosis_name or ''} - {c.diagnostico}"
        _campo(pdf, "Diagnostico", diag)
        _campo(pdf, "Tratamiento", c.tratamiento)
        if c.next_control_date:
            _campo(pdf, "Proximo control", c.next_control_date.strftime("%d/%m/%Y"))
        for n in c.clarifications:
            _campo(pdf, "Nota aclaratoria", f"{_local(n.created_at):%d/%m/%Y %H:%M} ({n.created_by_name}): {n.text}")
        pdf.ln(2)

    # Odontograma actual
    _titulo(pdf, "Odontograma (estado actual)")
    if not odontograma:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, "Sin registros en el odontograma.", new_x="LMARGIN", new_y="NEXT")
    else:
        anchos = (16, 28, 52, 52, 48)
        pdf.set_font("Helvetica", "B", 8)
        for ancho, t in zip(anchos, ("Diente", "Superficie", "Hallazgo", "Procedimiento", "CUPS")):
            pdf.cell(ancho, 6, t, border=1, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for e in odontograma:
            surface = getattr(e.surface, "value", e.surface) or "completo"
            fila = (e.tooth_fdi, surface, e.condition_name or "", e.procedure_name or "", e.cups_code or "")
            for ancho, valor in zip(anchos, fila):
                pdf.cell(ancho, 6, _txt(valor)[:34], border=1)
            pdf.ln()

    return bytes(pdf.output())
