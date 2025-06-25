from django.db import models
import os
import uuid
from django.utils import timezone

# For Django 3.1+ use models.JSONField, for older use from django.contrib.postgres.fields import JSONField

def patient_report_upload_path(instance, filename):
    # Use a safe version of the patient name for the folder
    safe_name = instance.patient.name or "unknown"
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
    return f'reports/{safe_name}/{filename}'

def patient_profile_photo_upload_path(instance, filename):
    # Use patient ID for profile photo upload
    return f'profile_photos/{instance.id}/{filename}'

class Patient(models.Model):
    # Basic Information
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    sex = models.CharField(max_length=10)
    mobile = models.CharField(max_length=15)
    
    # Enhanced Personal Information
    full_name = models.CharField(max_length=200, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    profile_photo = models.ImageField(upload_to=patient_profile_photo_upload_path, blank=True, null=True)
    
    # General Physique Parameters
    height_cm = models.FloatField(blank=True, null=True)
    weight_kg = models.FloatField(blank=True, null=True)
    blood_type = models.CharField(max_length=5, blank=True, null=True)
    waist_cm = models.FloatField(blank=True, null=True)
    hip_cm = models.FloatField(blank=True, null=True)
    dominant_hand = models.CharField(max_length=10, blank=True, null=True)
    
    # Appearance Details
    skin_tone = models.CharField(max_length=30, blank=True, null=True)
    hair_color = models.CharField(max_length=30, blank=True, null=True)
    eye_color = models.CharField(max_length=30, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def bmi(self):
        """Calculate BMI if height and weight are available"""
        if self.height_cm and self.weight_kg:
            height_m = self.height_cm / 100
            return round(self.weight_kg / (height_m ** 2), 1)
        return None
    
    @property
    def bmi_category(self):
        """Get BMI category"""
        bmi = self.bmi
        if not bmi:
            return None
        if bmi < 18.5:
            return 'underweight'
        elif bmi < 25:
            return 'normal'
        elif bmi < 30:
            return 'overweight'
        else:
            return 'obese'
    
    @property
    def age_from_dob(self):
        """Calculate age from date of birth"""
        if self.date_of_birth:
            from datetime import date
            today = date.today()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return self.age

class MedicalReport(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='reports')
    report_file = models.FileField(upload_to=patient_report_upload_path)
    report_type = models.CharField(max_length=100)
    report_date = models.DateField()
    report_id = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    report_dates = models.JSONField(default=list, blank=True)  # List of all dates for this report type
    parameters = models.JSONField(default=list, blank=True)
    observations = models.JSONField(default=list, blank=True)
    advise = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.report_dates and len(self.report_dates) > 1:
            return f"{self.report_type} (dates: {self.report_dates}) for {self.patient.name}"
        return f"{self.report_type} ({self.report_date}) for {self.patient.name}"




