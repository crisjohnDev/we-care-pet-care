from django.contrib.auth import get_user_model

User = get_user_model()

def create_default_admin():
    user, created = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@example.com",
            "role": "admin",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )

    if created:
        user.set_password("admin123")
        user.save()
    else:
        # Activate and grant staff/admin access to the existing account
        user.role = "admin"
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save(
            update_fields=[
                "role",
                "is_staff",
                "is_superuser",
                "is_active",
            ]
        )