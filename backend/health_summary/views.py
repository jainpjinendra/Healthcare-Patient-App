from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from patients.models import Patient
from rest_framework import status
from . import summary_utils
import traceback

# Create your views here.

class PatientNameListView(APIView):
    def get(self, request):
        names = list(Patient.objects.values_list('name', flat=True))
        return Response({'names': names})

class PatientSummaryView(APIView):
    def post(self, request):
        patient_name = request.data.get('patient_name')
        if not patient_name:
            return Response({'error': 'Patient name is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Fetch and process summary using summary_utils
            text = summary_utils.get_patient_reports(patient_name)
            summary = summary_utils.get_patient_summary(text)
            return Response({'summary': summary})
        except Exception as e:
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
