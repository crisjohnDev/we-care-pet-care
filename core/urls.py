from django.urls import path
from . import views

urlpatterns = [
    path('admin-dashboard/', views.core_dashboard, name='admin_dashboard'),
    path(
        'breeds/',
        views.dog_breed_list,
        name='dog_breed_list'
    ),

    path(
        'breeds/<int:pk>/edit/',
        views.dog_breed_edit,
        name='dog_breed_edit'
    ),

    path(
        'breeds/<int:pk>/delete/',
        views.dog_breed_delete,
        name='dog_breed_delete'
    ),
    path(
        'customers/',
        views.customer_list,
        name='customer_list'
    ),

    path(
        'customers/<int:pk>/',
        views.customer_detail,
        name='customer_detail'
    ),

    path(
        'customers/<int:pk>/delete/',
        views.customer_delete,
        name='customer_delete'
    ),

    # Chat Session Management
    path(
        'chat-sessions/',
        views.chat_session_list,
        name='chat_session_list'
    ),

    path(
        'chat-sessions/<int:pk>/',
        views.chat_session_detail,
        name='chat_session_detail'
    ),
path(
    "knowledge-base/",
    views.question_answer_list,
    name="question_answer_list"
),
path(
    "knowledge-base/add/",
    views.question_answer_create,
    name="question_answer_create"
),
path(
    "knowledge-base/<int:pk>/edit/",
    views.question_answer_edit,
    name="question_answer_edit"
),
path(
    "knowledge-base/<int:pk>/toggle/",
    views.question_answer_toggle,
    name="question_answer_toggle"
),
path(
    "knowledge-base/<int:pk>/delete/",
    views.question_answer_delete,
    name="question_answer_delete"
),
path(
    "reports/",
    views.reports_dashboard,
    name="reports"
),
]
