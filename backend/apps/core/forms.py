from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Patient


class PatientRegistrationForm(forms.ModelForm):
    age = forms.IntegerField(min_value=0, max_value=130)
    weight_kg = forms.DecimalField(required=False, min_value=0, max_digits=5, decimal_places=2)
    known_history = forms.CharField(required=False, widget=forms.Textarea)
    address = forms.CharField(required=False, max_length=255)
    dob = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    national_id = forms.CharField(required=False, max_length=50)

    class Meta:
        model = Patient
        fields = [
            "first_name",
            "last_name",
            "age",
            "weight_kg",
            "known_history",
            "gender",
            "phone",
            "address",
        ]

    def _dob_from_age(self, age):
        today = timezone.localdate()
        try:
            return today.replace(year=today.year - age)
        except ValueError:
            # Handle leap day edge case by falling back to Feb 28.
            return today.replace(month=2, day=28, year=today.year - age)

    def clean(self):
        cleaned = super().clean()
        age = cleaned.get("age")
        dob = cleaned.get("dob")
        if age is None and not dob:
            self.add_error("age", "age is required")
            return cleaned
        if not dob and age is not None:
            cleaned["dob"] = self._dob_from_age(age)
        return cleaned

    def clean_phone(self):
        phone = str(self.cleaned_data.get("phone", "")).strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError("Phone number must be exactly 10 digits")
        return phone

    def save(self, commit=True):
        patient = super().save(commit=False)
        patient.dob = self.cleaned_data.get("dob")
        patient.national_id = self.cleaned_data.get("national_id", "")
        patient.address_line1 = self.cleaned_data.get("address", "")
        patient.city = ""
        patient.state = ""
        patient.postal_code = ""
        if commit:
            patient.save()
        return patient


class PatientUpdateForm(forms.ModelForm):
    age = forms.IntegerField(min_value=0, max_value=130, required=False)
    weight_kg = forms.DecimalField(required=False, min_value=0, max_digits=5, decimal_places=2)
    known_history = forms.CharField(required=False, widget=forms.Textarea)
    address = forms.CharField(required=False, max_length=255)
    dob = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    national_id = forms.CharField(required=False, max_length=50)

    class Meta:
        model = Patient
        fields = [
            "first_name",
            "last_name",
            "age",
            "weight_kg",
            "known_history",
            "gender",
            "phone",
            "address",
        ]

    def _dob_from_age(self, age):
        today = timezone.localdate()
        try:
            return today.replace(year=today.year - age)
        except ValueError:
            return today.replace(month=2, day=28, year=today.year - age)

    def clean_phone(self):
        phone = str(self.cleaned_data.get("phone", "")).strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError("Phone number must be exactly 10 digits")
        return phone

    def save(self, commit=True):
        patient = super().save(commit=False)
        age = self.cleaned_data.get("age")
        dob = self.cleaned_data.get("dob")
        if age is not None:
            patient.dob = self._dob_from_age(age)
        elif dob:
            patient.dob = dob
        patient.national_id = self.cleaned_data.get("national_id", patient.national_id)
        patient.address_line1 = self.cleaned_data.get("address", "")
        patient.city = ""
        patient.state = ""
        patient.postal_code = ""
        if commit:
            patient.save()
        return patient


class ScheduleUpsertForm(forms.Form):
    doctor_name = forms.CharField(max_length=150)
    specialty = forms.CharField(max_length=100)
    daily_patient_capacity = forms.IntegerField(min_value=1, required=False)
    day_of_week = forms.IntegerField(min_value=0, max_value=6)
    start_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"])
    end_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"])
    break_start = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"], required=False)
    break_end = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"], required=False)
    slot_minutes = forms.IntegerField(min_value=5, max_value=60)
    range_start = forms.DateField(input_formats=["%Y-%m-%d"])
    range_end = forms.DateField(input_formats=["%Y-%m-%d"])
    reason = forms.CharField(max_length=255)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start_time") and cleaned.get("end_time") and cleaned["start_time"] >= cleaned["end_time"]:
            self.add_error("end_time", "end_time must be after start_time")

        if cleaned.get("range_start") and cleaned.get("range_end") and cleaned["range_start"] > cleaned["range_end"]:
            self.add_error("range_end", "range_end must be on or after range_start")

        if cleaned.get("break_start") and cleaned.get("break_end") and cleaned["break_start"] >= cleaned["break_end"]:
            self.add_error("break_end", "break_end must be after break_start")

        return cleaned


class AppointmentBookForm(forms.Form):
    patient_id = forms.IntegerField(min_value=1)
    doctor_id = forms.IntegerField(min_value=1)
    slot_date = forms.DateField(input_formats=["%Y-%m-%d"])
    start_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"], required=False)
    token = forms.IntegerField(min_value=1, required=False)
    visit_type = forms.ChoiceField(choices=[("NEW", "New"), ("FOLLOW_UP", "Follow Up"), ("FOLLOW_UP_RCT", "Follow Up (RCT)")])
    channel = forms.ChoiceField(choices=[("WALK_IN", "Walk-In"), ("PHONE", "Mobile")])

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("start_time") and not cleaned.get("token"):
            self.add_error("token", "token is required")
        return cleaned


class DoctorOpdFeeForm(forms.Form):
    doctor_name = forms.CharField(max_length=150)
    opd_new_patient_fee = forms.DecimalField(min_value=0, decimal_places=2)
    opd_existing_patient_fee = forms.DecimalField(min_value=0, decimal_places=2)


class AppointmentRescheduleForm(forms.Form):
    slot_date = forms.DateField(input_formats=["%Y-%m-%d"])
    start_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"], required=False)
    end_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"], required=False)
    token = forms.IntegerField(min_value=1, required=False)
    reason = forms.CharField(max_length=255)
    is_emergency = forms.BooleanField(required=False)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("token") and not (cleaned.get("start_time") and cleaned.get("end_time")):
            self.add_error("token", "token or slot time is required")
        if cleaned.get("start_time") and cleaned.get("end_time") and cleaned["start_time"] >= cleaned["end_time"]:
            self.add_error("end_time", "end_time must be after start_time")
        return cleaned


class AppointmentCancelForm(forms.Form):
    reason = forms.CharField(max_length=255)


class DoctorEmergencyDayRescheduleForm(forms.Form):
    reason = forms.CharField(max_length=255, required=False)
    source_date = forms.DateField(input_formats=["%Y-%m-%d"], required=False)
    doctor_id = forms.IntegerField(min_value=1, required=False)


class ReceptionEmergencyRescheduleDecisionForm(forms.Form):
    action = forms.ChoiceField(choices=[("EXCEED", "EXCEED"), ("CASCADE", "CASCADE")])


class UserCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.CharField(max_length=50, required=False)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    doctor_full_name = forms.CharField(max_length=150, required=False)
    doctor_suffix = forms.CharField(max_length=20, required=False)
    doctor_specialty = forms.CharField(max_length=100, required=False)
    doctor_phone = forms.CharField(max_length=20, required=False)
    doctor_reg_number = forms.CharField(max_length=100, required=False)
    doctor_qualification = forms.CharField(max_length=200, required=False)
    doctor_daily_patient_capacity = forms.IntegerField(min_value=1, required=False)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already exists")
        return username


class UserRoleAssignForm(forms.Form):
    user_id = forms.IntegerField(min_value=1)
    role = forms.CharField(max_length=50)


class QueueBoardForm(forms.Form):
    doctor_id = forms.IntegerField(min_value=1)
    slot_date = forms.DateField(input_formats=["%Y-%m-%d"])


class QueueCallNextForm(forms.Form):
    doctor_id = forms.IntegerField(min_value=1)
    slot_date = forms.DateField(input_formats=["%Y-%m-%d"])


class PauseCurrentConsultationForm(forms.Form):
    doctor_id = forms.IntegerField(min_value=1, required=False)


class AddEmergencyPatientForm(forms.Form):
    doctor_id = forms.IntegerField(min_value=1)
    patient_id = forms.IntegerField(min_value=1, required=False)
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(max_length=100, required=False)
    phone = forms.CharField(max_length=20, required=False)
    visit_type = forms.ChoiceField(choices=[("NEW", "New"), ("FOLLOW_UP", "Follow Up"), ("FOLLOW_UP_RCT", "Follow Up (RCT)")], required=False)

    def clean(self):
        cleaned = super().clean()
        patient_id = cleaned.get("patient_id")
        first_name = (cleaned.get("first_name") or "").strip()
        last_name = (cleaned.get("last_name") or "").strip()
        phone = (cleaned.get("phone") or "").strip()

        if patient_id:
            return cleaned

        if not first_name:
            self.add_error("first_name", "first_name is required when patient_id is not provided")
        if not last_name:
            self.add_error("last_name", "last_name is required when patient_id is not provided")
        if not phone:
            self.add_error("phone", "phone is required when patient_id is not provided")

        cleaned["first_name"] = first_name
        cleaned["last_name"] = last_name
        cleaned["phone"] = phone
        return cleaned


class ConsultationDraftForm(forms.Form):
    chief_complaint = forms.CharField(required=False, max_length=2000)
    findings = forms.CharField(required=False, max_length=2000)
    diagnosis = forms.CharField(required=False, max_length=2000)
    notes = forms.CharField(required=False, max_length=2000)
    follow_up_date = forms.DateField(input_formats=["%Y-%m-%d"], required=False)


class VitalsForm(forms.Form):
    temperature_c = forms.DecimalField(max_digits=4, decimal_places=1, required=False)
    pulse_bpm = forms.IntegerField(min_value=1, max_value=300, required=False)
    bp_systolic = forms.IntegerField(min_value=40, max_value=300, required=False)
    bp_diastolic = forms.IntegerField(min_value=20, max_value=200, required=False)
    spo2_pct = forms.IntegerField(min_value=50, max_value=100, required=False)
    weight_kg = forms.DecimalField(max_digits=5, decimal_places=2, required=False)
    height_cm = forms.DecimalField(max_digits=5, decimal_places=2, required=False)


class ConsultationAmendForm(forms.Form):
    field_name = forms.CharField(max_length=100)
    new_value = forms.CharField(max_length=2000)
    reason = forms.CharField(max_length=255)


class MedicalOrderForm(forms.Form):
    order_type = forms.ChoiceField(choices=[("LAB", "Lab"), ("RADIOLOGY", "Radiology")])
    description = forms.CharField(max_length=500)
