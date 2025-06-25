from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from .models import Patient, MedicalReport
from .serializers import PatientSerializer, MedicalReportSerializer
from .report_utils import process_pdf_report, enhance_medical_data
from django.utils.dateparse import parse_date
from datetime import datetime
import os
from django.conf import settings
from rest_framework.generics import RetrieveAPIView
from backend.pinecone_client import upsert_chunks, chunk_text, delete_patient_chunks, delete_report_chunks
import shutil
from .chat_utils import get_patient_reports, patient_specific_query



class PatientListCreateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        patients = Patient.objects.all().order_by('-id')
        serializer = PatientSerializer(patients, many=True)
        return Response(serializer.data)

    def post(self, request):
        mobile = request.data.get('mobile')
        report = request.FILES.get('report')
        if not mobile or not report:
            return Response({'error': 'Mobile and report are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save the patient with temp data to get an ID
        temp_patient = Patient(mobile=mobile, name='temp', age=0, sex='temp')
        temp_patient.save()
        temp_report_path = f"media/temp_{datetime.now().timestamp()}_{report.name}"
        with open(temp_report_path, 'wb+') as destination:
            for chunk in report.chunks():
                destination.write(chunk)
        report_data = process_pdf_report(temp_report_path)
        # print(report_data)

        # Extracted fields
        name = report_data.get('patient_name')
        age = report_data.get('age')
        sex = report_data.get('sex')
        report_type = report_data.get('report_type') or 'Unknown'
        report_date = report_data.get('report_date')
        parameters = report_data.get('parameters', [])
        observations = report_data.get('observations', [])
        advise = report_data.get('advise', [])
        if not name or not age or not sex:
            temp_patient.delete()
            os.remove(temp_report_path)
            return Response({'error': 'Could not extract all required fields from the report.'}, status=status.HTTP_400_BAD_REQUEST)
        temp_patient.name = name
        temp_patient.age = int(age[0]) if isinstance(age, list) else int(age)
        temp_patient.sex = sex
        temp_patient.save()
        # Check for existing report of same type
        existing_report = MedicalReport.objects.filter(patient=temp_patient, report_type=report_type).first()
        from django.core.files import File
        if existing_report:
            # Merge logic
            report_dates = existing_report.report_dates or [str(existing_report.report_date)]
            if str(report_date) not in report_dates:
                report_dates.append(str(report_date))
            # Merge parameters by name
            param_map = {p['name']: p for p in existing_report.parameters}
            for new_param in parameters:
                name = new_param['name']
                if name in param_map:
                    # Append value and status to lists
                    if not isinstance(param_map[name]['value'], list):
                        param_map[name]['value'] = [param_map[name]['value']]
                    if not isinstance(param_map[name]['status'], list):
                        param_map[name]['status'] = [param_map[name]['status']]
                    param_map[name]['value'].append(new_param['value'])
                    param_map[name]['status'].append(new_param['status'])
                else:
                    # New parameter
                    param_map[name] = {
                        **new_param,
                        'value': [new_param['value']],
                        'status': [new_param['status']]
                    }
            merged_params = list(param_map.values())
            # Update existing report
            existing_report.report_dates = report_dates
            existing_report.parameters = merged_params
            existing_report.observations = observations
            existing_report.advise = advise
            existing_report.save()
            # Save new file as latest
            with open(temp_report_path, 'rb') as f:
                existing_report.report_file.save(report.name, File(f, name=report.name), save=True)
            os.remove(temp_report_path)
            serializer = PatientSerializer(temp_patient)
            return Response({'message': 'Patient added successfully! (merged report)', 'patient': serializer.data}, status=status.HTTP_201_CREATED)
        else:
            # Save the report as a MedicalReport
            with open(temp_report_path, 'rb') as f:
                medical_report = MedicalReport.objects.create(
                    patient=temp_patient,
                    report_file=File(f, name=report.name),
                    report_type=report_type,
                    report_date=parse_date(report_date) if report_date else datetime.now().date(),
                    report_dates=[str(report_date)] if report_date else [],
                    parameters=[{**p, 'value': [p['value']], 'status': [p['status']]} for p in parameters],
                    observations=observations,
                    advise=advise
                )
            os.remove(temp_report_path)
            serializer = PatientSerializer(temp_patient)
            return Response({'message': 'Patient added successfully!', 'patient': serializer.data}, status=status.HTTP_201_CREATED)

class MedicalReportListCreateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request, patient_id):
        reports = MedicalReport.objects.filter(patient_id=patient_id).order_by('-created_at')
        serializer = MedicalReportSerializer(reports, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request, patient_id):
        report = request.FILES.get('report')
        if not report:
            return Response({'error': 'Report file is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            return Response({'error': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)
        temp_report_path = f"media/temp_{datetime.now().timestamp()}_{report.name}"
        with open(temp_report_path, 'wb+') as destination:
            for chunk in report.chunks():
                destination.write(chunk)
        report_data = process_pdf_report(temp_report_path)
        report_type = report_data.get('report_type') or 'Unknown'
        report_date = report_data.get('report_date')
        parameters = report_data.get('parameters', [])
        observations = report_data.get('observations', [])
        advise = report_data.get('advise', [])
        from django.core.files import File
        # Check for existing report of same type
        existing_report = MedicalReport.objects.filter(patient=patient, report_type=report_type).first()
        if existing_report:
            # Merge logic
            report_dates = existing_report.report_dates or [str(existing_report.report_date)]
            if str(report_date) not in report_dates:
                report_dates.append(str(report_date))
            # Merge parameters by name
            param_map = {p['name']: p for p in existing_report.parameters}
            for new_param in parameters:
                name = new_param['name']
                if name in param_map:
                    # Append value and status to lists
                    if not isinstance(param_map[name]['value'], list):
                        param_map[name]['value'] = [param_map[name]['value']]
                    if not isinstance(param_map[name]['status'], list):
                        param_map[name]['status'] = [param_map[name]['status']]
                    param_map[name]['value'].append(new_param['value'])
                    param_map[name]['status'].append(new_param['status'])
                else:
                    # New parameter
                    param_map[name] = {
                        **new_param,
                        'value': [new_param['value']],
                        'status': [new_param['status']]
                    }
            merged_params = list(param_map.values())
            # Update existing report
            existing_report.report_dates = report_dates
            existing_report.parameters = merged_params
            existing_report.observations = observations
            existing_report.advise = advise
            existing_report.save()
            # Save new file as latest
            with open(temp_report_path, 'rb') as f:
                existing_report.report_file.save(report.name, File(f, name=report.name), save=True)
            os.remove(temp_report_path)
            serializer = MedicalReportSerializer(existing_report, context={'request': request})
            return Response({'message': 'Report uploaded successfully! (merged report)', 'report': serializer.data}, status=status.HTTP_201_CREATED)
        else:
            with open(temp_report_path, 'rb') as f:
                medical_report = MedicalReport.objects.create(
                    patient=patient,
                    report_file=File(f, name=report.name),
                    report_type=report_type,
                    report_date=parse_date(report_date) if report_date else datetime.now().date(),
                    report_dates=[str(report_date)] if report_date else [],
                    parameters=[{**p, 'value': [p['value']], 'status': [p['status']]} for p in parameters],
                    observations=observations,
                    advise=advise
                )
            os.remove(temp_report_path)
            serializer = MedicalReportSerializer(medical_report, context={'request': request})
            return Response({'message': 'Report uploaded successfully!', 'report': serializer.data}, status=status.HTTP_201_CREATED)

class PatientDeleteView(APIView):
    def delete(self, request, pk):
        try:
            patient = Patient.objects.get(pk=pk)
            # Delete all associated MedicalReport Pinecone data
            delete_patient_chunks(patient.name)
            # Delete all associated MedicalReport files
            for report in patient.reports.all():
                if report.report_file and os.path.isfile(report.report_file.path):
                    os.remove(report.report_file.path)
                    # Optionally, remove the folder if empty
                    folder = os.path.dirname(report.report_file.path)
                    if os.path.isdir(folder) and not os.listdir(folder):
                        os.rmdir(folder)
            # Remove the patient's media folder (if exists)
            patient_folder = os.path.join('media', 'reports', patient.name)
            if os.path.isdir(patient_folder):
                shutil.rmtree(patient_folder)
            patient.delete()
            return Response({'message': 'Patient and all reports deleted.'}, status=status.HTTP_204_NO_CONTENT)
        except Patient.DoesNotExist:
            return Response({'error': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)

class MedicalReportDetailView(RetrieveAPIView):
    queryset = MedicalReport.objects.all()
    serializer_class = MedicalReportSerializer

class MedicalReportDeleteView(APIView):
    def delete(self, request, pk):
        try:
            report = MedicalReport.objects.get(pk=pk)
            # Delete the report's Pinecone data
            delete_report_chunks(str(report.report_id))
            # Delete the report file from disk
            if report.report_file and os.path.isfile(report.report_file.path):
                os.remove(report.report_file.path)
                # Optionally, remove the folder if empty
                folder = os.path.dirname(report.report_file.path)
                if os.path.isdir(folder) and not os.listdir(folder):
                    os.rmdir(folder)
            report.delete()
            return Response({'message': 'Report deleted.'}, status=status.HTTP_204_NO_CONTENT)
        except MedicalReport.DoesNotExist:
            return Response({'error': 'Report not found.'}, status=status.HTTP_404_NOT_FOUND)

class PatientChatAssistantView(APIView):
    def post(self, request):
        patient_id = request.data.get('patient_id')
        query = request.data.get('query')
        if not patient_id or not query:
            return Response({'error': 'Both patient_id and query are required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Get patient name from id
            patient = Patient.objects.get(pk=patient_id)
            report_text = get_patient_reports(patient.name)
            if not report_text.strip():
                return Response({'answer': 'No reports found for this patient.'})
            answer = patient_specific_query(report_text, query)
            return Response({'answer': answer})
        except Patient.DoesNotExist:
            return Response({'error': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PatientProfileView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    def get(self, request, patient_id):
        """Get patient profile information"""
        try:
            patient = Patient.objects.get(pk=patient_id)
            serializer = PatientSerializer(patient, context={'request': request})
            return Response(serializer.data)
        except Patient.DoesNotExist:
            return Response({'error': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    def put(self, request, patient_id):
        """Update patient profile information"""
        try:
            patient = Patient.objects.get(pk=patient_id)
            
            # Handle profile photo upload
            if 'profile_photo' in request.FILES:
                patient.profile_photo = request.FILES['profile_photo']
            
            # Update other fields
            update_fields = [
                'full_name', 'date_of_birth', 'gender', 'email', 'emergency_contact', 
                'address', 'height_cm', 'weight_kg', 'blood_type', 'waist_cm', 
                'hip_cm', 'dominant_hand', 'skin_tone', 'hair_color', 'eye_color'
            ]
            
            for field in update_fields:
                if field in request.data:
                    value = request.data[field]
                    # Handle empty strings as None for optional fields
                    if value == '' and field not in ['full_name', 'emergency_contact', 'address']:
                        value = None
                    # Convert numeric fields
                    if field in ['height_cm', 'weight_kg', 'waist_cm', 'hip_cm'] and value:
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            value = None
                    setattr(patient, field, value)
            
            patient.save()
            serializer = PatientSerializer(patient, context={'request': request})
            return Response({
                'message': 'Profile updated successfully!',
                'patient': serializer.data
            })
        except Patient.DoesNotExist:
            return Response({'error': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)