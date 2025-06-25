from django.urls import path
from .views import PatientListCreateView, PatientDeleteView, MedicalReportListCreateView, MedicalReportDetailView, MedicalReportDeleteView, PatientChatAssistantView, PatientProfileView

urlpatterns = [
    path('', PatientListCreateView.as_view(), name='patient-list-create'),
    path('<int:pk>/', PatientDeleteView.as_view(), name='patient-delete'),
    path('<int:patient_id>/reports/', MedicalReportListCreateView.as_view(), name='medical-report-list-create'),
    path('<int:patient_id>/profile/', PatientProfileView.as_view(), name='patient-profile'),
    path('chat_assistant/', PatientChatAssistantView.as_view(), name='patient-chat-assistant'),
]

# Separate pattern for report detail
report_detail_patterns = [
    path('<int:pk>/', MedicalReportDetailView.as_view(), name='medical-report-detail'),
    path('<int:pk>/delete/', MedicalReportDeleteView.as_view(), name='medical-report-delete'),
]

