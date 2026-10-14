
from django.contrib import admin
from django.urls import path, include

admin.site.site_header = "We Care Pet Care Administration"
admin.site.site_title = "We Care Pet Care Admin"
admin.site.index_title = "Welcome to We Care Pet Care Management"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('customer/', include('customer.urls')),
    path('v1/', include('api.urls')),
]
