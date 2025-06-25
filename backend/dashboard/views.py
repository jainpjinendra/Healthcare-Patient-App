from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from patients.models import Patient, MedicalReport
from django.db.models import Count
from datetime import datetime, timedelta

# Create your views here.

class DashboardSummaryView(APIView):
    def get(self, request):
        # Total patients
        total_patients = Patient.objects.count()
        # Total reports
        total_reports = MedicalReport.objects.count()
        # Recent chats (stub: you can replace with real chat model if available)
        recent_chats = []  # Add logic if you have chat history model
        # Recent reports
        recent_reports = list(MedicalReport.objects.order_by('-created_at')[:5].values(
            'id', 'report_type', 'report_date', 'patient__name', 'created_at'))
        # Abnormal parameters count
        abnormal_count = 0
        abnormal_params = {}
        for report in MedicalReport.objects.all():
            for param in report.parameters:
                if isinstance(param, dict) and 'status' in param:
                    # status can be a list or a string
                    statuses = param['status'] if isinstance(param['status'], list) else [param['status']]
                    for s in statuses:
                        if s and s != 'normal':
                            abnormal_count += 1
                            abnormal_params[param['name']] = abnormal_params.get(param['name'], 0) + 1
        # Reports per month (last 6 months)
        today = datetime.today()
        months = [(today - timedelta(days=30*i)).strftime('%b %Y') for i in reversed(range(6))]
        reports_per_month = {m: 0 for m in months}
        for report in MedicalReport.objects.all():
            m = report.created_at.strftime('%b %Y')
            if m in reports_per_month:
                reports_per_month[m] += 1
        # Most common abnormal parameters (top 5)
        top_abnormal = sorted(abnormal_params.items(), key=lambda x: x[1], reverse=True)[:5]
        return Response({
            'total_patients': total_patients,
            'total_reports': total_reports,
            'recent_chats': recent_chats,
            'recent_reports': recent_reports,
            'abnormal_count': abnormal_count,
            'top_abnormal': top_abnormal,
            'reports_per_month': reports_per_month,
        })
