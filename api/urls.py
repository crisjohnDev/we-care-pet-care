from django.urls import path
from .views import CustomerLoginView, CustomerRegisterView, CustomerProfileCreateView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # ... your other urls
    path('api/login/customer/', CustomerLoginView.as_view(), name='customer_login'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/register/customer/', CustomerRegisterView.as_view(), name='customer_register'),
    path('v1/api/customer/profile/', CustomerProfileCreateView.as_view(), name='customer_profile')
]