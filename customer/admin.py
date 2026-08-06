from django.contrib import admin
from .models import (
    Customer,
    ChatSession,
    ChatMessage,
    QuestionAnswer
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "fullname",
        "pet_name",
        "breed",
        "sex",
        "contact_number",
        "created_at",
    )
    search_fields = (
        "fullname",
        "pet_name",
        "breed",
        "contact_number",
    )
    list_filter = (
        "sex",
        "breed",
        "created_at",
    )


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "user",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "title",
        "user__username",
    )
    list_filter = (
        "created_at",
    )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "role",
        "created_at",
    )
    search_fields = (
        "message",
        "session__title",
    )
    list_filter = (
        "role",
        "created_at",
    )


@admin.register(QuestionAnswer)
class QuestionAnswerAdmin(admin.ModelAdmin):
    list_display = (
        "question",
        "is_active",
        "created_at",
    )
    search_fields = (
        "question",
        "answer",
    )
    list_filter = (
        "is_active",
        "created_at",
    )

