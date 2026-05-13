from django.db import models


class Patient(models.Model):
	GENDER_CHOICES = [
		("M", "Male"),
		("F", "Female"),
		("O", "Other"),
	]

	first_name = models.CharField(max_length=100)
	last_name = models.CharField(max_length=100)
	mrn = models.CharField(max_length=30, unique=True, blank=True, default="")
	opd_number = models.CharField(max_length=30, unique=True, blank=True, default="")
	dob = models.DateField()
	gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
	phone = models.CharField(max_length=20)
	weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	known_history = models.TextField(blank=True, default="")
	national_id = models.CharField(max_length=50, blank=True, default="")
	address_line1 = models.CharField(max_length=255, blank=True, default="")
	city = models.CharField(max_length=80, blank=True, default="")
	state = models.CharField(max_length=80, blank=True, default="")
	postal_code = models.CharField(max_length=20, blank=True, default="")
	created_at = models.DateTimeField(auto_now_add=True)
	# Denormalized search field — lowercase "first last" for fast equality/prefix lookups
	searchable_full_name = models.CharField(max_length=205, blank=True, default="", db_index=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["phone"], name="idx_patient_phone"),
			models.Index(fields=["last_name", "first_name"], name="idx_patient_name"),
			models.Index(fields=["created_at"], name="idx_patient_created_at"),
		]

	def __str__(self):
		return f"{self.first_name} {self.last_name} ({self.phone})"

	@property
	def salutation(self):
		if self.gender == "M":
			return "Mr"
		if self.gender == "F":
			return "Miss"
		return ""

	@property
	def titled_full_name(self):
		name = f"{self.first_name} {self.last_name}".strip()
		salutation = self.salutation
		if salutation:
			return f"{salutation} {name}".strip()
		return name

	def save(self, *args, **kwargs):
		new_record = self.pk is None
		# Keep denormalized search field in sync
		self.searchable_full_name = f"{self.first_name} {self.last_name}".strip().lower()
		super().save(*args, **kwargs)
		update_fields = []
		if new_record and not self.mrn:
			self.mrn = f"MRN-{self.pk:06d}"
			update_fields.append("mrn")
		if new_record and not self.opd_number:
			self.opd_number = f"OPDP-{self.pk:06d}"
			update_fields.append("opd_number")
		if update_fields:
			super().save(update_fields=update_fields)


class SearchAuditLog(models.Model):
	actor_username = models.CharField(max_length=150)
	query_type = models.CharField(max_length=50)
	query_value = models.CharField(max_length=255)
	result_count = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]


class Doctor(models.Model):
	user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="doctor_profile", blank=True, null=True)
	suffix = models.CharField(max_length=20, blank=True, default="Dr")
	full_name = models.CharField(max_length=150)
	specialty = models.CharField(max_length=100)
	phone = models.CharField(max_length=20, blank=True, default="")
	reg_number = models.CharField(max_length=100, blank=True, default="")
	qualification = models.CharField(max_length=200, blank=True, default="")
	daily_patient_capacity = models.PositiveIntegerField(default=50)
	opd_new_patient_fee = models.DecimalField(max_digits=10, decimal_places=2, default=200.00)
	opd_existing_patient_fee = models.DecimalField(max_digits=10, decimal_places=2, default=100.00)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["full_name"]

	@property
	def display_name(self):
		name = (self.full_name or "").strip()
		suffix = (self.suffix or "").strip()
		if not suffix:
			return name
		if not name:
			return suffix
		normalized_name = name.lower().replace(".", "")
		normalized_suffix = suffix.lower().replace(".", "")
		if normalized_name == normalized_suffix or normalized_name.startswith(f"{normalized_suffix} "):
			return name
		return f"{suffix} {name}"

	def __str__(self):
		return self.display_name


class DoctorScheduleTemplate(models.Model):
	DAY_CHOICES = [
		(0, "Monday"),
		(1, "Tuesday"),
		(2, "Wednesday"),
		(3, "Thursday"),
		(4, "Friday"),
		(5, "Saturday"),
		(6, "Sunday"),
	]

	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="schedule_templates")
	day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
	daily_patient_capacity = models.PositiveIntegerField(null=True, blank=True)
	start_time = models.TimeField()
	end_time = models.TimeField()
	break_start = models.TimeField(null=True, blank=True)
	break_end = models.TimeField(null=True, blank=True)
	slot_minutes = models.PositiveSmallIntegerField(default=10)
	version = models.PositiveIntegerField(default=1)
	change_reason = models.CharField(max_length=255)
	updated_by = models.CharField(max_length=150)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = ("doctor", "day_of_week")


class DoctorSlot(models.Model):
	STATUS_CHOICES = [
		("AVAILABLE", "Available"),
		("BLOCKED", "Blocked"),
	]

	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="slots")
	slot_date = models.DateField()
	start_time = models.TimeField()
	end_time = models.TimeField()
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="AVAILABLE")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["slot_date", "start_time"]
		unique_together = ("doctor", "slot_date", "start_time", "end_time")


class Appointment(models.Model):
	STATUS_CHOICES = [
		("BOOKED", "Booked"),
		("RESCHEDULED", "Rescheduled"),
		("COMPLETED", "Completed"),
		("CANCELLED", "Cancelled"),
	]

	VISIT_TYPE_CHOICES = [
		("NEW", "New"),
		("FOLLOW_UP", "Follow Up"),
		("FOLLOW_UP_RCT", "Follow Up (RCT)"),
	]

	CHANNEL_CHOICES = [
		("WALK_IN", "Walk-In"),
		("ONLINE", "Online"),
		("PHONE", "Phone"),
	]

	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="appointments")
	slot_date = models.DateField()
	start_time = models.TimeField()
	end_time = models.TimeField()
	visit_type = models.CharField(max_length=20, choices=VISIT_TYPE_CHOICES, default="NEW")
	channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="WALK_IN")
	opd_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="BOOKED")
	is_emergency = models.BooleanField(default=False)
	marked_emergency_at = models.DateTimeField(null=True, blank=True)
	marked_emergency_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="emergency_appointments_marked")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["patient_id", "slot_date", "status"], name="idx_appt_patient_date_status"),
			models.Index(fields=["doctor_id", "slot_date", "status", "start_time"], name="idx_appt_dr_date_stat_time"),
			models.Index(fields=["slot_date", "status"], name="idx_appt_slot_date_status"),
			models.Index(fields=["created_at"], name="idx_appt_created_at"),
		]

	def save(self, *args, **kwargs):
		new_record = self.pk is None
		super().save(*args, **kwargs)
		if new_record and not self.opd_number:
			self.opd_number = f"OPD-{self.pk:08d}"
			super().save(update_fields=["opd_number"])


class AppointmentEvent(models.Model):
	ACTION_CHOICES = [
		("BOOK", "Book"),
		("RESCHEDULE", "Reschedule"),
		("COMPLETE", "Complete"),
		("CANCEL", "Cancel"),
	]

	appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="events")
	action = models.CharField(max_length=20, choices=ACTION_CHOICES)
	previous_status = models.CharField(max_length=20, blank=True, default="")
	new_status = models.CharField(max_length=20)
	reason = models.CharField(max_length=255, blank=True, default="")
	actor_username = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]


class Consultation(models.Model):
	STATUS_CHOICES = [
		("DRAFT", "Draft"),
		("FINALIZED", "Finalized"),
	]

	appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="consultation")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="consultations")
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="consultations")
	chief_complaint = models.TextField(blank=True, default="")
	findings = models.TextField(blank=True, default="")
	diagnosis = models.TextField(blank=True, default="")
	notes = models.TextField(blank=True, default="")
	follow_up_date = models.DateField(null=True, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
	finalized_by = models.CharField(max_length=150, blank=True, default="")
	finalized_at = models.DateTimeField(null=True, blank=True)
	created_by = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]


class ConsultationAmendment(models.Model):
	consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name="amendments")
	field_name = models.CharField(max_length=100)
	previous_value = models.TextField(blank=True, default="")
	new_value = models.TextField(blank=True, default="")
	reason = models.CharField(max_length=255)
	actor_username = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]


class Vitals(models.Model):
	consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE, related_name="vitals")
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="vitals")
	temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
	pulse_bpm = models.PositiveSmallIntegerField(null=True, blank=True)
	bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
	bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
	spo2_pct = models.PositiveSmallIntegerField(null=True, blank=True)
	weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	recorded_by = models.CharField(max_length=150)
	recorded_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-recorded_at"]


class Prescription(models.Model):
	"""
	Indian prescription format.
	items[] each entry:
	  drug (generic name), dosage_form, strength, dose, frequency
	  (OD/BD/TDS/QID), duration, timing (before_food/after_food/with_food),
	  route (oral/topical/iv/im/s/c), instructions
	"""
	consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE, related_name="prescription")
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="prescriptions")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="prescriptions")
	# Doctor header (filled from Doctor profile + consultation context)
	doctor_qualification = models.CharField(max_length=200, blank=True, default="")
	doctor_reg_number = models.CharField(max_length=100, blank=True, default="")
	clinic_name = models.CharField(max_length=255, blank=True, default="")
	clinic_address = models.TextField(blank=True, default="")
	clinic_logo_url = models.CharField(max_length=500, blank=True, default="")
	clinic_registration_number = models.CharField(max_length=100, blank=True, default="")
	clinic_registration_authority = models.CharField(max_length=255, blank=True, default="")
	# Rx items - Indian format fields enforced at service layer
	items = models.JSONField(default=list)
	# Patient-level context at time of issue
	patient_age_at_issue = models.PositiveSmallIntegerField(null=True, blank=True)
	patient_weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	# Rx metadata
	rx_number = models.CharField(max_length=30, unique=True, blank=True, default="")
	special_instructions = models.TextField(blank=True, default="")
	validity_days = models.PositiveSmallIntegerField(default=30)
	issued_by = models.CharField(max_length=150)
	issued_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-issued_at"]
		indexes = [
			models.Index(fields=["patient_id", "issued_at"], name="idx_rx_patient_issued"),
			models.Index(fields=["doctor_id", "issued_at"], name="idx_rx_doctor_issued"),
			models.Index(fields=["consultation_id"], name="idx_rx_consultation"),
		]

	def save(self, *args, **kwargs):
		new_record = self.pk is None
		super().save(*args, **kwargs)
		if new_record and not self.rx_number:
			self.rx_number = f"RX-{self.pk:08d}"
			super().save(update_fields=["rx_number"])


class MedicalOrder(models.Model):
	ORDER_TYPE_CHOICES = [
		("LAB", "Lab"),
		("RADIOLOGY", "Radiology"),
	]
	STATUS_CHOICES = [
		("PENDING", "Pending"),
		("SENT", "Sent"),
	]

	consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name="orders")
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="orders")
	order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES)
	description = models.CharField(max_length=500)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
	created_by = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]


class QueueItem(models.Model):
	STATUS_CHOICES = [
		("WAITING", "Waiting"),
		("CALLED", "Called"),
		("PAUSED", "Paused"),
		("RESUMED", "Resumed"),
		("SKIPPED", "Skipped"),
		("COMPLETED", "Completed"),
		("NO_SHOW", "No Show"),
	]

	appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="queue_item")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="queue_items")
	slot_date = models.DateField()
	token_number = models.PositiveIntegerField()
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="WAITING")
	called_at = models.DateTimeField(null=True, blank=True)
	paused_at = models.DateTimeField(null=True, blank=True)
	paused_by = models.ForeignKey(Doctor, null=True, blank=True, on_delete=models.SET_NULL, related_name="paused_consultations")
	resume_order_position = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["slot_date", "token_number"]
		unique_together = ("doctor", "slot_date", "token_number")
		indexes = [
			models.Index(fields=["doctor_id", "slot_date", "status", "token_number"], name="idx_queue_dr_date_stat_tok"),
		]


class QueueEvent(models.Model):
	ACTION_CHOICES = [
		("CALL_NEXT", "Call Next"),
		("SKIP", "Skip"),
		("RECALL", "Recall"),
		("COMPLETE", "Complete"),
		("NO_SHOW", "No Show"),
	]

	queue_item = models.ForeignKey(QueueItem, on_delete=models.CASCADE, related_name="events")
	action = models.CharField(max_length=20, choices=ACTION_CHOICES)
	previous_status = models.CharField(max_length=20)
	new_status = models.CharField(max_length=20)
	actor_username = models.CharField(max_length=150)
	payload = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]


class BillingHandoff(models.Model):
	STATUS_CHOICES = [
		("PENDING", "Pending"),
		("SUCCESS", "Success"),
		("FAILED", "Failed"),
		("DEAD_LETTER", "Dead Letter"),
	]

	consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE, related_name="billing_handoff")
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="billing_handoffs")
	payload = models.JSONField()
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
	retry_count = models.PositiveIntegerField(default=0)
	failure_reason = models.TextField(blank=True, default="")
	next_retry_at = models.DateTimeField(null=True, blank=True)
	triggered_by = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]


class BillingRetryLog(models.Model):
	handoff = models.ForeignKey(BillingHandoff, on_delete=models.CASCADE, related_name="retry_logs")
	attempt_number = models.PositiveIntegerField()
	outcome = models.CharField(max_length=20)  # SUCCESS / FAILED
	failure_reason = models.TextField(blank=True, default="")
	actor_username = models.CharField(max_length=150, blank=True, default="system")
	attempted_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["attempted_at"]


class BillingLedger(models.Model):
	STATUS_CHOICES = [
		("OPEN", "Open"),
		("FINALIZED", "Finalized"),
	]
	REPEAT_FEE_DECISION_CHOICES = [
		("PENDING", "Pending"),
		("YES", "Yes"),
		("NO", "No"),
	]

	opd_number = models.CharField(max_length=30)
	appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_ledgers")
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="billing_ledgers")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="billing_ledgers")
	visit_date = models.DateField()
	visit_type = models.CharField(max_length=20, choices=Appointment.VISIT_TYPE_CHOICES, default="NEW")
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="OPEN")
	repeat_fee_decision = models.CharField(max_length=20, choices=REPEAT_FEE_DECISION_CHOICES, default="PENDING")
	repeat_fee_reason = models.CharField(max_length=255, blank=True, default="")
	finalized_by = models.CharField(max_length=150, blank=True, default="")
	finalized_at = models.DateTimeField(null=True, blank=True)
	created_by = models.CharField(max_length=150)
	updated_by = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["opd_number"], name="core_billin_opd_num_cdce7a_idx"),
			models.Index(fields=["status"], name="idx_ledger_status"),
			models.Index(fields=["patient_id", "visit_date"], name="idx_ledger_patient_visit"),
			models.Index(fields=["doctor_id", "visit_date", "status"], name="idx_ledger_doctor_visit_status"),
			models.Index(fields=["appointment_id"], name="idx_ledger_appointment"),
			models.Index(fields=["created_at"], name="idx_ledger_created_at"),
		]


class BillingLineItem(models.Model):
	LINE_TYPE_CHOICES = [
		("OPD_NEW_FEE", "OPD New Fee"),
		("OPD_REPEAT_FEE", "OPD Repeat Fee"),
		("LAB", "Lab / Pathology"),
		("RADIOLOGY", "Radiology / Imaging"),
		("PHARMACY", "Pharmacy / Medicine"),
		("PROCEDURE", "Procedure Charges"),
		("MISC", "Miscellaneous"),
		("MANUAL", "Manual"),
		("RCT", "RCT"),
	]

	ledger = models.ForeignKey(BillingLedger, on_delete=models.CASCADE, related_name="line_items")
	line_type = models.CharField(max_length=30, choices=LINE_TYPE_CHOICES)
	description = models.CharField(max_length=255, blank=True, default="")
	amount = models.DecimalField(max_digits=10, decimal_places=2)
	source_order_id = models.CharField(max_length=50, blank=True, default="")
	created_by = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)
	# Multi-sitting RCT recovery fields
	total_case_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=None)
	recovery_stage_percent = models.PositiveSmallIntegerField(null=True, blank=True, default=None)
	sitting_number = models.PositiveSmallIntegerField(null=True, blank=True, default=None)
	total_sittings = models.PositiveSmallIntegerField(null=True, blank=True, default=None)

	class Meta:
		ordering = ["created_at"]
		indexes = [
			models.Index(fields=["ledger", "line_type"], name="idx_lineitem_ledger_line_type"),
			models.Index(fields=["ledger_id", "created_at"], name="idx_lineitem_ledger_created"),
		]


class BillingInvoice(models.Model):
	PAYMENT_STATUS_CHOICES = [
		("PENDING", "Pending"),
		("DONE", "Done"),
	]
	PAYMENT_METHOD_CHOICES = [
		("", "Unknown"),
		("UPI", "UPI"),
		("CASH", "Cash"),
		("CARD", "Card"),
	]

	ledger = models.OneToOneField(BillingLedger, on_delete=models.CASCADE, related_name="invoice")
	bill_number = models.CharField(max_length=30, unique=True, blank=True, default="")
	subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	recovered_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	recovered_percentage = models.PositiveSmallIntegerField(default=0)
	payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PENDING")
	payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, default="")
	upi_txn_ref = models.CharField(max_length=100, blank=True, default="")
	paid_at = models.DateTimeField(null=True, blank=True)
	created_by = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)
	# Denormalized: stores current-visit-only total for FOLLOW_UP_RCT invoices (avoids runtime line-item slicing)
	current_visit_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=None)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["created_at"], name="idx_invoice_created_at"),
			models.Index(fields=["payment_status", "created_at"], name="idx_invoice_status_created"),
			models.Index(fields=["ledger_id"], name="idx_invoice_ledger"),
		]

	def save(self, *args, **kwargs):
		new_record = self.pk is None
		super().save(*args, **kwargs)
		if new_record and not self.bill_number:
			self.bill_number = f"BILL-{self.pk:08d}"
			super().save(update_fields=["bill_number"])


class BillingAuditEvent(models.Model):
	ledger = models.ForeignKey(BillingLedger, on_delete=models.CASCADE, related_name="audit_events")
	action = models.CharField(max_length=50)
	actor_username = models.CharField(max_length=150)
	payload = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]


class ReportExport(models.Model):
	FORMAT_CHOICES = [
		("CSV", "CSV"),
		("PDF", "PDF"),
	]
	STATUS_CHOICES = [
		("GENERATED", "Generated"),
	]

	requested_by = models.CharField(max_length=150)
	format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
	filters = models.JSONField(default=dict)
	artifact_name = models.CharField(max_length=255)
	artifact_content = models.TextField()
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="GENERATED")
	download_count = models.PositiveIntegerField(default=0)
	last_downloaded_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]


class ReportExportAudit(models.Model):
	ACTION_CHOICES = [
		("GENERATE", "Generate"),
		("DOWNLOAD", "Download"),
	]

	report_export = models.ForeignKey(ReportExport, on_delete=models.CASCADE, related_name="audits")
	action = models.CharField(max_length=20, choices=ACTION_CHOICES)
	actor_username = models.CharField(max_length=150)
	payload = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]


class AlertEvent(models.Model):
	SEVERITY_CHOICES = [
		("INFO", "Info"),
		("WARN", "Warn"),
		("CRITICAL", "Critical"),
	]

	metric_name = models.CharField(max_length=100)
	observed_value = models.FloatField()
	threshold_value = models.FloatField()
	severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
	message = models.CharField(max_length=255)
	context = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]


class IncidentRecord(models.Model):
	STATUS_CHOICES = [
		("OPEN", "Open"),
		("RESOLVED", "Resolved"),
	]

	severity = models.CharField(max_length=20, choices=AlertEvent.SEVERITY_CHOICES)
	source = models.CharField(max_length=100)
	summary = models.CharField(max_length=255)
	runbook_ref = models.CharField(max_length=255, blank=True, default="")
	details = models.JSONField(default=dict)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="OPEN")
	created_by = models.CharField(max_length=150, default="system")
	resolved_by = models.CharField(max_length=150, blank=True, default="")
	created_at = models.DateTimeField(auto_now_add=True)
	resolved_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-created_at"]


class DoctorDayRescheduleRequest(models.Model):
	STATUS_CHOICES = [
		("PENDING_RECEPTION", "Pending Reception Decision"),
		("EXECUTED_AUTO", "Executed Automatically"),
		("EXECUTED_EXCEED", "Executed With Capacity Exceeded"),
		("EXECUTED_CASCADE", "Executed With Cascade"),
	]

	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="day_reschedule_requests")
	source_date = models.DateField()
	target_date = models.DateField()
	reason = models.CharField(max_length=255, blank=True, default="")
	total_appointments = models.PositiveIntegerField(default=0)
	target_capacity = models.PositiveIntegerField(default=0)
	target_existing = models.PositiveIntegerField(default=0)
	overflow_count = models.PositiveIntegerField(default=0)
	status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="PENDING_RECEPTION")
	requested_by = models.CharField(max_length=150)
	decided_by = models.CharField(max_length=150, blank=True, default="")
	details = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)
	decided_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-created_at"]


class UserProfile(models.Model):
	user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="profile")
	phone = models.CharField(max_length=20, blank=True, default="")
	bio = models.TextField(blank=True, default="")
	department = models.CharField(max_length=100, blank=True, default="")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"Profile of {self.user.username}"


class ClinicSettings(models.Model):
	CLINIC_TYPE_CHOICES = [
		("GENERAL", "General"),
		("DENTIST", "Dentist"),
	]

	clinic_name = models.CharField(max_length=255, default="OPD Clinic")
	clinic_address = models.TextField(blank=True, default="")
	clinic_type = models.CharField(max_length=20, choices=CLINIC_TYPE_CHOICES, default="GENERAL")
	clinic_phone = models.CharField(max_length=20, blank=True, default="")
	clinic_mob = models.CharField(max_length=20, blank=True, default="")
	upi_id = models.CharField(max_length=100, blank=True, default="")
	logo = models.ImageField(upload_to="clinic_logos/", null=True, blank=True)
	registration_number = models.CharField(max_length=100, blank=True, default="")
	registration_authority = models.CharField(max_length=255, blank=True, default="")
	updated_at = models.DateTimeField(auto_now=True)

	@classmethod
	def get_solo(cls):
		obj, _ = cls.objects.get_or_create(
			id=1,
			defaults={
				"clinic_name": "OPD Clinic",
				"clinic_address": "",
				"clinic_type": "GENERAL",
				"clinic_phone": "",
				"clinic_mob": "",
				"upi_id": "",
				"registration_number": "",
				"registration_authority": "",
			},
		)
		return obj

	def save(self, *args, **kwargs):
		self.id = 1
		super().save(*args, **kwargs)

	def __str__(self):
		return self.clinic_name


class Medicine(models.Model):
	"""Lookup table for medicine autocomplete in doctor consultation."""

	CATEGORY_CHOICES = [
		("analgesic", "Analgesic / Pain Relief"),
		("antibiotic", "Antibiotic"),
		("antifungal", "Antifungal"),
		("antiseptic", "Antiseptic / Mouthwash"),
		("anti_inflammatory", "Anti-inflammatory"),
		("antacid", "Antacid / GI"),
		("antihistamine", "Antihistamine"),
		("antihypertensive", "Antihypertensive"),
		("antidiabetic", "Antidiabetic"),
		("vitamin", "Vitamin / Supplement"),
		("dental", "Dental Specific"),
		("other", "Other"),
	]

	name = models.CharField(max_length=200, unique=True)
	category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default="other")
	default_strength = models.CharField(max_length=50, blank=True, default="")
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["name"]

	def __str__(self):
		return self.name
