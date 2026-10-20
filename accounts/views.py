from django.utils import timezone
from datetime import date
from django.contrib import messages
from django.shortcuts import render, redirect
from accounts.utils import create_default_admin
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from customer.models import Customer, Breed, Dog
from django.http import JsonResponse
from django.db import transaction


User = get_user_model()

def keep_alive(request):
    return JsonResponse({
        "status": "ok",
        "service": "Django API",
        "timestamp": timezone.now().isoformat(),
    })

def login_view(request):
    create_default_admin()

    error = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)

            if user.role == 'admin':
                return redirect('admin_dashboard')

            elif user.role == 'customer':
                return redirect('customer-dashboard')

            else:
                error = 'Your account does not have a valid role.'

        else:
            error = 'Incorrect username or password. Please try again.'

    return render(request, 'login.html', {
        'error': error,
    })

def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        form_data = {
            "username": username,
            "email": email,
        }

        # Validate required fields
        if not username or not email or not password:
            return render(request, "signup.html", {
                "error": "Please complete all required fields.",
                "form_data": form_data,
            })

        # Check duplicate username
        if User.objects.filter(username__iexact=username).exists():
            return render(request, "signup.html", {
                "error": "Username already exists. Please choose another.",
                "form_data": form_data,
            })

        # Check duplicate email
        if User.objects.filter(email__iexact=email).exists():
            return render(request, "signup.html", {
                "error": "Email already exists. Please use another email.",
                "form_data": form_data,
            })

        # Validate password length
        if len(password) < 8:
            return render(request, "signup.html", {
                "error": "Password must contain at least 8 characters.",
                "form_data": form_data,
            })

        # Create the account
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        # Log in the newly registered user
        login(request, user)

        return redirect("complete-profile")

    return render(request, "signup.html", {
        "form_data": {},
    })


@login_required
def complete_profile(request):
    if hasattr(request.user, "customer_profile"):
        return redirect("customer-dashboard")

    breeds = Breed.objects.filter(
        is_active=True
    ).order_by("name")

    form_data = {}
    dog_form_data = [
        {
            "pet_name": "",
            "breed": "",
            "sex": "",
            "birthdate": "",
        }
    ]

    if request.method == "POST":
        fullname = request.POST.get(
            "fullname", ""
        ).strip()

        address = request.POST.get(
            "address", ""
        ).strip()

        contact_number = request.POST.get(
            "contact_number", ""
        ).strip()

        # Get every dog submitted by the form.
        pet_names = request.POST.getlist("pet_name[]")
        breed_ids = request.POST.getlist("breed[]")
        sexes = request.POST.getlist("sex[]")
        birthdates = request.POST.getlist("birthdate[]")

        form_data = {
            "fullname": fullname,
            "address": address,
            "contact_number": contact_number,
        }

        # Rebuild the dog fields so values can be restored
        # if validation fails.
        dog_count = max(
            len(pet_names),
            len(breed_ids),
            len(sexes),
            len(birthdates),
            1,
        )

        dog_form_data = []

        for index in range(dog_count):
            dog_form_data.append({
                "pet_name": (
                    pet_names[index]
                    if index < len(pet_names)
                    else ""
                ),
                "breed": (
                    breed_ids[index]
                    if index < len(breed_ids)
                    else ""
                ),
                "sex": (
                    sexes[index]
                    if index < len(sexes)
                    else ""
                ),
                "birthdate": (
                    birthdates[index]
                    if index < len(birthdates)
                    else ""
                ),
            })

        # Validate owner information.
        if not all([
            fullname,
            address,
            contact_number,
        ]):
            return render(
                request,
                "complete_profile.html",
                {
                    "breeds": breeds,
                    "error": (
                        "Please complete all owner information."
                    ),
                    "form_data": form_data,
                    "dog_form_data": dog_form_data,
                },
            )

        # All four dog fields must have the same number
        # of submitted values.
        if not (
            len(pet_names)
            == len(breed_ids)
            == len(sexes)
            == len(birthdates)
        ):
            return render(
                request,
                "complete_profile.html",
                {
                    "breeds": breeds,
                    "error": (
                        "Some dog information is missing. "
                        "Please check every dog entry."
                    ),
                    "form_data": form_data,
                    "dog_form_data": dog_form_data,
                },
            )

        if not pet_names:
            return render(
                request,
                "complete_profile.html",
                {
                    "breeds": breeds,
                    "error": "Please add at least one dog.",
                    "form_data": form_data,
                    "dog_form_data": dog_form_data,
                },
            )

        validated_dogs = []

        # Validate every dog before saving anything.
        for index, values in enumerate(dog_form_data, start=1):
            pet_name = values["pet_name"].strip()
            breed_id = values["breed"].strip()
            sex = values["sex"].strip()
            birthdate = values["birthdate"].strip()

            selected_breed = Breed.objects.filter(
                pk=breed_id,
                is_active=True,
            ).first()

            try:
                parsed_birthdate = date.fromisoformat(
                    birthdate
                )

                valid_birthdate = (
                    parsed_birthdate <= date.today()
                )

            except (ValueError, TypeError):
                parsed_birthdate = None
                valid_birthdate = False

            if not pet_name:
                error = (
                    f"Please enter a name for Dog #{index}."
                )
                break

            if len(pet_name) > 100:
                error = (
                    f"Dog #{index}'s name must not exceed "
                    "100 characters."
                )
                break

            if not selected_breed:
                error = (
                    f"Please select a valid breed for Dog #{index}."
                )
                break

            if sex not in ("Male", "Female"):
                error = (
                    f"Please select the sex for Dog #{index}."
                )
                break

            if not valid_birthdate:
                error = (
                    f"Please provide a valid birthdate for "
                    f"Dog #{index}. Future dates are not allowed."
                )
                break

            validated_dogs.append({
                "pet_name": pet_name,
                "breed": selected_breed,
                "sex": sex,
                "birthdate": parsed_birthdate,
            })

        else:
            error = None

        if error:
            return render(
                request,
                "complete_profile.html",
                {
                    "breeds": breeds,
                    "error": error,
                    "form_data": form_data,
                    "dog_form_data": dog_form_data,
                },
            )

        # Save the owner and all dogs together.
        # If saving fails, the transaction rolls back.
        with transaction.atomic():
            customer = Customer.objects.create(
                user=request.user,
                fullname=fullname,
                address=address,
                contact_number=contact_number,
            )

            Dog.objects.bulk_create([
                Dog(
                    customer=customer,
                    **dog_data,
                )
                for dog_data in validated_dogs
            ])

        messages.success(
            request,
            (
                "Your profile and "
                f"{len(validated_dogs)} dog(s) have been saved."
            ),
        )

        return redirect("customer-dashboard")

    return render(
        request,
        "complete_profile.html",
        {
            "breeds": breeds,
            "form_data": form_data,
            "dog_form_data": dog_form_data,
        },
    )


def logout_view(request):
    logout(request)
    return redirect('login')