
from django.contrib import admin

from .models import (
    Customer,
    Dog,
    ChatSession,
    ChatMessage,
    QuestionAnswer,
    Breed,
)


@admin.register(Breed)
class BreedAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    ordering = ("name",)

    fieldsets = (
        ("Breed Information", {
            "fields": (
                "name",
                "description",
                "is_active",
            )
        }),
    )


class DogInline(admin.TabularInline):
    model = Dog
    extra = 1


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "fullname",
        "contact_number",
        "address",
        "created_at",
    )

    search_fields = (
        "fullname",
        "contact_number",
        "address",
        "user__username",
    )

    list_filter = (
        "created_at",
    )

    inlines = (DogInline,)


@admin.register(Dog)
class DogAdmin(admin.ModelAdmin):
    list_display = (
        "pet_name",
        "customer",
        "breed",
        "sex",
        "birthdate",
        "created_at",
    )

    search_fields = (
        "pet_name",
        "customer__fullname",
        "breed__name",
    )

    list_filter = (
        "sex",
        "breed",
        "created_at",
    )

    ordering = ("pet_name",)


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
