from django.db import migrations, models


MEDICINES_SEED = [
    # Analgesics / Pain Relief
    ("Paracetamol", "analgesic", "500mg"),
    ("Ibuprofen", "analgesic", "400mg"),
    ("Diclofenac", "analgesic", "50mg"),
    ("Ketorolac", "analgesic", "10mg"),
    ("Aspirin", "analgesic", "75mg"),
    ("Tramadol", "analgesic", "50mg"),
    ("Mefenamic Acid", "analgesic", "500mg"),
    ("Aceclofenac", "analgesic", "100mg"),
    ("Naproxen", "analgesic", "250mg"),
    ("Nimesulide", "analgesic", "100mg"),
    ("Etoricoxib", "analgesic", "60mg"),
    ("Piroxicam", "analgesic", "20mg"),
    ("Pentazocine", "analgesic", "25mg"),
    # Antibiotics
    ("Amoxicillin", "antibiotic", "500mg"),
    ("Amoxicillin + Clavulanate", "antibiotic", "625mg"),
    ("Azithromycin", "antibiotic", "500mg"),
    ("Clindamycin", "antibiotic", "300mg"),
    ("Metronidazole", "antibiotic", "400mg"),
    ("Tinidazole", "antibiotic", "500mg"),
    ("Doxycycline", "antibiotic", "100mg"),
    ("Ciprofloxacin", "antibiotic", "500mg"),
    ("Levofloxacin", "antibiotic", "500mg"),
    ("Cephalexin", "antibiotic", "500mg"),
    ("Cefuroxime", "antibiotic", "250mg"),
    ("Cefixime", "antibiotic", "200mg"),
    ("Erythromycin", "antibiotic", "250mg"),
    ("Clarithromycin", "antibiotic", "250mg"),
    ("Tetracycline", "antibiotic", "250mg"),
    ("Ampicillin", "antibiotic", "250mg"),
    ("Co-Trimoxazole", "antibiotic", "960mg"),
    ("Nitrofurantoin", "antibiotic", "100mg"),
    # Antifungals
    ("Fluconazole", "antifungal", "150mg"),
    ("Nystatin", "antifungal", "100000 IU"),
    ("Clotrimazole", "antifungal", "1%"),
    ("Itraconazole", "antifungal", "100mg"),
    ("Miconazole", "antifungal", "2%"),
    ("Terbinafine", "antifungal", "250mg"),
    # Antiseptic / Mouthwash (Dental)
    ("Chlorhexidine Mouthwash", "antiseptic", "0.2%"),
    ("Betadine Mouthwash", "antiseptic", "1%"),
    ("Hexidine Mouthwash", "antiseptic", "0.2%"),
    ("Hydrogen Peroxide Mouthwash", "antiseptic", "3%"),
    # Anti-inflammatory
    ("Prednisolone", "anti_inflammatory", "5mg"),
    ("Dexamethasone", "anti_inflammatory", "0.5mg"),
    ("Methylprednisolone", "anti_inflammatory", "4mg"),
    ("Betamethasone", "anti_inflammatory", "0.5mg"),
    # Antacid / GI
    ("Omeprazole", "antacid", "20mg"),
    ("Pantoprazole", "antacid", "40mg"),
    ("Ranitidine", "antacid", "150mg"),
    ("Domperidone", "antacid", "10mg"),
    ("Ondansetron", "antacid", "4mg"),
    ("Metoclopramide", "antacid", "10mg"),
    ("Esomeprazole", "antacid", "20mg"),
    ("Rabeprazole", "antacid", "20mg"),
    ("Sucralfate", "antacid", "1g"),
    ("Dicyclomine", "antacid", "10mg"),
    # Antihistamines
    ("Cetirizine", "antihistamine", "10mg"),
    ("Loratadine", "antihistamine", "10mg"),
    ("Fexofenadine", "antihistamine", "120mg"),
    ("Chlorpheniramine", "antihistamine", "4mg"),
    ("Levocetirizine", "antihistamine", "5mg"),
    ("Hydroxyzine", "antihistamine", "25mg"),
    ("Montelukast", "antihistamine", "10mg"),
    # Antihypertensives
    ("Amlodipine", "antihypertensive", "5mg"),
    ("Atenolol", "antihypertensive", "50mg"),
    ("Losartan", "antihypertensive", "50mg"),
    ("Telmisartan", "antihypertensive", "40mg"),
    ("Enalapril", "antihypertensive", "5mg"),
    ("Ramipril", "antihypertensive", "2.5mg"),
    ("Metoprolol", "antihypertensive", "25mg"),
    ("Nifedipine", "antihypertensive", "10mg"),
    ("Hydrochlorothiazide", "antihypertensive", "12.5mg"),
    # Antidiabetics
    ("Metformin", "antidiabetic", "500mg"),
    ("Glibenclamide", "antidiabetic", "5mg"),
    ("Glimepiride", "antidiabetic", "1mg"),
    ("Sitagliptin", "antidiabetic", "100mg"),
    ("Vildagliptin", "antidiabetic", "50mg"),
    ("Empagliflozin", "antidiabetic", "10mg"),
    # Vitamins / Supplements
    ("Vitamin B Complex", "vitamin", ""),
    ("Vitamin B12", "vitamin", "500mcg"),
    ("Vitamin C", "vitamin", "500mg"),
    ("Vitamin D3", "vitamin", "60000 IU"),
    ("Calcium + Vitamin D3", "vitamin", "500mg/250 IU"),
    ("Iron + Folic Acid", "vitamin", ""),
    ("Zinc", "vitamin", "20mg"),
    ("Multivitamin", "vitamin", ""),
    ("Folic Acid", "vitamin", "5mg"),
    ("Biotin", "vitamin", "2.5mg"),
    # Dental Specific
    ("Lidocaine", "dental", "2%"),
    ("Benzocaine Gel", "dental", "20%"),
    ("Eugenol", "dental", ""),
    ("Zinc Oxide Eugenol", "dental", ""),
    ("Calcium Hydroxide", "dental", ""),
    ("Fluoride Gel", "dental", "1.23%"),
    ("Povidone Iodine", "dental", "5%"),
    ("Tetracycline Fiber", "dental", ""),
    ("Doxycycline Gel", "dental", "10%"),
    ("Triamcinolone Acetonide Paste", "dental", "0.1%"),
    # Other common medicines
    ("Atorvastatin", "other", "10mg"),
    ("Rosuvastatin", "other", "10mg"),
    ("Clopidogrel", "other", "75mg"),
    ("Levothyroxine", "other", "50mcg"),
    ("Salbutamol Inhaler", "other", "100mcg"),
    ("Budesonide Inhaler", "other", "200mcg"),
    ("Montelukast + Levocetirizine", "other", ""),
    ("Diazepam", "other", "5mg"),
    ("Alprazolam", "other", "0.25mg"),
    ("Gabapentin", "other", "300mg"),
    ("Pregabalin", "other", "75mg"),
    ("Sertraline", "other", "50mg"),
    ("Fluoxetine", "other", "20mg"),
    ("Amitriptyline", "other", "10mg"),
    ("Baclofen", "other", "10mg"),
    ("Thiocolchicoside", "other", "4mg"),
    ("Chlorzoxazone", "other", "500mg"),
]


def seed_medicines(apps, schema_editor):
    Medicine = apps.get_model("core", "Medicine")
    for name, category, default_strength in MEDICINES_SEED:
        Medicine.objects.get_or_create(
            name=name,
            defaults={"category": category, "default_strength": default_strength, "is_active": True},
        )


def unseed_medicines(apps, schema_editor):
    Medicine = apps.get_model("core", "Medicine")
    Medicine.objects.filter(name__in=[m[0] for m in MEDICINES_SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0039_add_follow_up_rct_visit_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="Medicine",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                (
                    "category",
                    models.CharField(
                        choices=[
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
                        ],
                        default="other",
                        max_length=40,
                    ),
                ),
                ("default_strength", models.CharField(blank=True, default="", max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.RunPython(seed_medicines, unseed_medicines),
    ]
