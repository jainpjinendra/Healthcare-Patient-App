from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .chat_utils import general_lab_query, get_patient_reports, patient_specific_query
from patients.models import Patient
from datetime import datetime
import json
import traceback
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create your views here.

class GeneralLabQueryView(APIView):
    def post(self, request):
        query = request.data.get('query')
        if not query:
            return Response({'error': 'Query is required.'}, status=status.HTTP_400_BAD_REQUEST)
        answer = general_lab_query(query)
        return Response({'answer': answer})

class PatientSpecificQueryView(APIView):
    def post(self, request):
        patient_name = request.data.get('patient_name')
        query = request.data.get('query')
        if not patient_name or not query:
            return Response({'error': 'Both patient_name and query are required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            report_text = get_patient_reports(patient_name)
            if not report_text.strip():
                return Response({'answer': 'No reports found for this patient.'})
            answer = patient_specific_query(report_text, query)
            return Response({'answer': answer})
        except Exception as e:
            logger.error(f"Error in patient-specific query: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
