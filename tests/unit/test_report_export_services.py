import datetime

import pytest

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient, ReportExportAudit
from apps.core.services import download_report_export, generate_report_export


pytestmark = pytest.mark.django_db


def _seed_report_data():
    doctor = Doctor.objects.create(full_name="Dr Export", specialty="General Medicine")
    slot_date = datetime.date(2026, 5, 5)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(10, 0), end_time=datetime.time(10, 10))
    patient = Patient.objects.create(first_name="Report", last_name="Pat", dob=datetime.date(1990, 1, 1), gender="M", phone="9999999991")
    Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(10, 0),
        end_time=datetime.time(10, 10),
        visit_type="NEW",
        channel="WALK_IN",
        status="BOOKED",
    )
    return slot_date


def test_generate_csv_export_creates_artifact_and_generate_audit():
    report_date = _seed_report_data()

    export = generate_report_export("CSV", {"date": str(report_date)}, "admin_user")

    assert export.format == "CSV"
    assert export.artifact_name.endswith(".csv")
    assert "metric,value" in export.artifact_content
    assert ReportExportAudit.objects.filter(report_export=export, action="GENERATE").exists()


def test_generate_pdf_export_creates_artifact():
    report_date = _seed_report_data()

    export = generate_report_export("PDF", {"date": str(report_date)}, "admin_user")

    assert export.format == "PDF"
    assert export.artifact_name.endswith(".pdf")
    assert "OPD Daily KPI Report" in export.artifact_content


def test_generate_export_rejects_invalid_format():
    with pytest.raises(ValueError, match="invalid_export_format"):
        generate_report_export("XLS", {}, "admin_user")


def test_download_export_updates_count_and_writes_download_audit():
    report_date = _seed_report_data()
    export = generate_report_export("CSV", {"date": str(report_date)}, "admin_user")

    updated = download_report_export(export.id, "admin_user")

    assert updated.download_count == 1
    assert updated.last_downloaded_at is not None
    assert ReportExportAudit.objects.filter(report_export=export, action="DOWNLOAD").exists()
