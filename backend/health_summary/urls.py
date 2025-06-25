from django.urls import path
from .views import PatientNameListView, PatientSummaryView
 
urlpatterns = [
    path('patient_names/', PatientNameListView.as_view(), name='patient-names'),
    path('patient_summary/', PatientSummaryView.as_view(), name='patient-summary'),
] 