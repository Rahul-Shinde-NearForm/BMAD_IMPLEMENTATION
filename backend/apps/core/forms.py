from django import forms
from django.contrib.auth.models import User

from .models import Patient


class PatientRegistrationForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "first_name",
            "last_name",
            "dob",
            "gender",
            "phone",
            "national_id",
            "address_line1",
            "city",
            "state",
            "postal_code",
        ]


class PatientUpdateForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "first_name",
            "last_name",
            "dob",
            "gender",
            "phone",
            "national_id",
            "address_line1",
            "city",
            "state",
            "postal_code",
        ]


class ScheduleUpsertForm(forms.Form):
    doctor_name = forms.CharField(max_length=150)
    specialty = forms.CharField(max_length=100)
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
    start_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"])
    end_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"])
    visit_type = forms.ChoiceField(choices=[("NEW", "New"), ("FOLLOW_UP", "Follow Up")])
    channel = forms.ChoiceField(choices=[("WALK_IN", "Walk-In"), ("ONLINE", "Online"), ("PHONE", "Phone")])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start_time") and cleaned.get("end_time") and cleaned["start_time"] >= cleaned["end_time"]:
            self.add_error("end_time", "end_time must be after start_time")
        return cleaned


class AppointmentRescheduleForm(forms.Form):
    slot_date = forms.DateField(input_formats=["%Y-%m-%d"])
    start_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"])
    end_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"])
    reason = forms.CharField(max_length=255)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start_time") and cleaned.get("end_time") and cleaned["start_time"] >= cleaned["end_time"]:
            self.add_error("end_time", "end_time must be after start_time")
        return cleaned


class AppointmentCancelForm(forms.Form):
    reason = forms.CharField(max_length=255)


class UserCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.CharField(max_length=50)

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
