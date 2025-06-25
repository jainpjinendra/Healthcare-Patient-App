from rest_framework import serializers
from .models import Patient, MedicalReport

class MedicalReportSerializer(serializers.ModelSerializer):
    report_file = serializers.SerializerMethodField()

    class Meta:
        model = MedicalReport
        fields = '__all__'

    def get_report_file(self, obj):
        request = self.context.get('request')
        if request is not None:
            return request.build_absolute_uri(obj.report_file.url)
        return obj.report_file.url

class PatientSerializer(serializers.ModelSerializer):
    profile_photo = serializers.SerializerMethodField()
    bmi = serializers.ReadOnlyField()
    bmi_category = serializers.ReadOnlyField()
    age_from_dob = serializers.ReadOnlyField()
    
    class Meta:
        model = Patient
        fields = '__all__'
    
    def get_profile_photo(self, obj):
        request = self.context.get('request')
        if obj.profile_photo and request is not None:
            return request.build_absolute_uri(obj.profile_photo.url)
        return obj.profile_photo.url if obj.profile_photo else None 