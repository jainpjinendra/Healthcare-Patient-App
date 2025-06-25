from django.urls import path
from .views import GeneralLabQueryView, PatientSpecificQueryView

urlpatterns = [
    path('general_query/', GeneralLabQueryView.as_view(), name='general-lab-query'),
    path('patient_query/', PatientSpecificQueryView.as_view(), name='patient-specific-query'),
    # path('patient_names/', ...)  # Removed from here
] 