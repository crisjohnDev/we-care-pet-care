import requests

from django.conf import settings


def send_sms(number, message):

    url = "https://api.semaphore.co/api/v4/messages"

    payload = {
        "apikey": settings.SEMAPHORE_API_KEY,
        "number": number,
        "message": message
    }

    response = requests.post(
        url,
        data=payload
    )

    return response.json()


def notify_vet(customer, symptoms, reason):

    message = f"""
DOG EMERGENCY

Owner: {customer.fullname}

Phone: {customer.contact_number}

Address:
{customer.address}

Dog Name: {customer.pet_name}

Breed: {customer.breed}

Sex: {customer.sex}

Symptoms:
{symptoms}

AI Assessment:
{reason}

Please contact the owner immediately.
"""

    return send_sms(
        settings.VETERINARY_PHONE,
        message
    )