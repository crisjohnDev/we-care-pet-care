import requests
from openai import OpenAI
from django.conf import settings
import base64
import json
client = OpenAI(api_key=settings.OPENAI_API_KEY)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import ChatSession, ChatMessage, Customer, QuestionAnswer,Dog, Breed
from datetime import date
from .sms import notify_vet
from django.contrib.auth import logout
from django.contrib import messages
client = OpenAI()

@login_required
def customer_dashboard(request):
    session = ChatSession.objects.create(
        user=request.user,
        title="New Chat"
    )

    return redirect("chat_session", session.id)

@login_required
def new_chat(request):
    session = ChatSession.objects.create(
        user=request.user,
        title="New Chat"
    )

    return redirect("chat_session", session_id=session.id)


@login_required
def chat_session(request, session_id):
    session = get_object_or_404(
        ChatSession,
        id=session_id,
        user=request.user
    )

    recent_chats = (
        ChatSession.objects
        .filter(user=request.user)
        .order_by("-is_pinned", "-updated_at")
    )

    return render(request, "pages/dashboard.html", {
        "session": session,
        "messages": session.messages.all(),
        "recent_chats": recent_chats,
    })


@login_required
@require_POST
def toggle_pin_chat(request, session_id):
    chat = get_object_or_404(
        ChatSession,
        id=session_id,
        user=request.user
    )

    chat.is_pinned = not chat.is_pinned
    chat.save(update_fields=["is_pinned"])

    return _redirect_to_owned_chat(
        request,
        fallback_session_id=session_id
    )


@login_required
@require_POST
def delete_chat(request, session_id):
    chat = get_object_or_404(
        ChatSession,
        id=session_id,
        user=request.user
    )

    # Delete this session and its related messages.
    chat.delete()

    return _redirect_to_owned_chat(request)


def _redirect_to_owned_chat(
    request,
    fallback_session_id=None
):
    """
    Redirect to a valid chat owned by the current user.
    Never redirect to a chat belonging to another user.
    """
    return_to = request.POST.get("return_to", "")

    if return_to.isdigit():
        target = ChatSession.objects.filter(
            id=int(return_to),
            user=request.user
        ).first()

        if target:
            return redirect("chat_session", session_id=target.id)

    if fallback_session_id is not None:
        target = ChatSession.objects.filter(
            id=fallback_session_id,
            user=request.user
        ).first()

        if target:
            return redirect("chat_session", session_id=target.id)

    # Prefer the most recent pinned or regular chat.
    target = (
        ChatSession.objects
        .filter(user=request.user)
        .order_by("-is_pinned", "-updated_at")
        .first()
    )

    if target:
        return redirect("chat_session", session_id=target.id)

    # Create a new chat if the user has deleted their last session.
    target = ChatSession.objects.create(
        user=request.user,
        title="New Chat"
    )

    return redirect("chat_session", session_id=target.id)


@login_required
def customer_logout(request):
    if request.method == "POST":
        logout(request)
        return redirect("login")

    return redirect("chat_session", session_id=request.session.get("chat_session_id"))



@login_required
def view_profile(request):
    try:
        customer = (
            Customer.objects
            .prefetch_related("dogs__breed")
            .get(user=request.user)
        )
    except Customer.DoesNotExist:
        customer = None

    return render(
        request,
        "pages/view_profile.html",
        {
            "customer": customer,
        },
    )


# =========================================================
# VETERINARY CLINIC CONTACT DETAILS
# =========================================================

VETERINARY_CLINIC_NAME = "Pioduran PetCare and Veterinary Clinic"
VETERINARY_CONTACT_NUMBER = "09559688069"
VETERINARY_DISPLAY_NUMBER = "0955 968 8069"
VETERINARY_CLINIC_ADDRESS = (
    "Purok 2, Caratagan, Pio Duran, Albay, Philippines"
)



@login_required
@require_POST
def send_message(request, session_id):

    # =========================================================
    # 1. GET CHAT SESSION
    # =========================================================

    try:
        session = ChatSession.objects.get(
            id=session_id,
            user=request.user
        )
    except ChatSession.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Chat session not found."
        }, status=404)

    # =========================================================
    # 2. GET CUSTOMER PROFILE
    # =========================================================

    try:
        customer = Customer.objects.get(user=request.user)
    except Customer.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Customer profile not found."
        }, status=404)

    # =========================================================
    # 3. GET MESSAGE AND IMAGE
    # =========================================================

    message = request.POST.get("message", "").strip()
    image = request.FILES.get("image")

    if not message and not image:
        return JsonResponse({
            "success": False,
            "error": "Enter a message or upload an image."
        }, status=400)

    if image:
        if image.size > 10 * 1024 * 1024:
            return JsonResponse({
                "success": False,
                "error": "Image size must not exceed 10 MB."
            }, status=400)

        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif"
        }

        if image.content_type not in allowed_types:
            return JsonResponse({
                "success": False,
                "error": "Upload a JPEG, PNG, WEBP, or GIF image."
            }, status=400)

    # =========================================================
    # 4. CALCULATE DOG AGE
    # =========================================================

    dog_age = "Unknown"

    if getattr(customer, "birthdate", None):
        try:
            today = date.today()
            birthdate = customer.birthdate

            years = (
                today.year
                - birthdate.year
                - (
                    (today.month, today.day)
                    < (birthdate.month, birthdate.day)
                )
            )

            dog_age = (
                "Less than 1 year old"
                if years < 1
                else f"{years} years old"
            )

        except Exception as exc:
            print("DOG AGE ERROR:", exc)

    # =========================================================
    # 5. SAVE USER MESSAGE
    # =========================================================

    if message:
        ChatMessage.objects.create(
            session=session,
            role="user",
            message=message
        )

    if session.title == "New Chat" and message:
        session.title = message[:50]
        session.save(update_fields=["title"])

    # =========================================================
    # 6. LOAD CONVERSATION HISTORY
    # =========================================================

    previous_messages = list(
        ChatMessage.objects
        .filter(session=session)
        .order_by("-created_at")[:20]
    )

    previous_messages.reverse()

    conversation_history = []

    for chat_message in previous_messages:
        if chat_message.role in ("user", "assistant"):
            conversation_history.append({
                "role": chat_message.role,
                "content": chat_message.message
            })

    # =========================================================
    # 7. IMAGE ANALYSIS AND BREED PERCENTAGES
    # =========================================================

    image_analysis = None

    if image:
        try:
            image_bytes = image.read()
            image_base64 = base64.b64encode(
                image_bytes
            ).decode("utf-8")

            content_type = image.content_type

            image_system_prompt = """
You are the dog breed identification and image analysis assistant
for We Care Pet Care.

Analyze the actual newly uploaded image.

Return ONLY valid JSON with this structure:

{
  "breed": "Most likely primary breed or Unknown",
  "detected_breed": "Most likely breed or mix",
  "confidence": "low|medium|high",
  "breed_percentages": [
    {
      "breed": "Labrador Retriever",
      "percentage": 70,
      "evidence": "Visible characteristics supporting this estimate"
    },
    {
      "breed": "Other or uncertain ancestry",
      "percentage": 30,
      "evidence": "Characteristics that cannot be assigned confidently"
    }
  ],
  "description": "Description of the visible dog",
  "possible_health_observations": "Visible observations only",
  "comparison": "Comparison with registered breed if available",
  "dog_visible": true,
  "visible_blood": "yes|no|uncertain",
  "bleeding_observation": "What the image actually shows",
  "wound_visible": "yes|no|uncertain",
  "limitations": "Limitations of this image assessment"
}

BREED IDENTIFICATION:

1. Identify the most likely breed or breed mix from visible
   characteristics such as coat, color, ears, muzzle, body shape,
   and other recognizable physical features.

2. Include up to three plausible breed categories when supported
   by the photograph.

3. breed_percentages must be a list of objects containing:
   breed, percentage, and evidence.

4. Percentages must be whole numbers from 0 to 100 and must total
   exactly 100 when a dog is visible.

5. Do not invent additional breeds just to fill the list.
   Use "Other or uncertain ancestry" for an uncertain remainder.

6. If one breed appears most likely, it can receive 100% as a
   visual resemblance estimate when appropriate.

7. Be cautious with puppies, blurry images, unusual angles,
   mixed breeds, and images where the dog's body is obscured.

8. Set confidence to low when the breed cannot be determined
   reliably from the photograph.

9. These are visual estimates of breed resemblance, NOT DNA
   ancestry percentages. Do not claim genetic certainty.

10. If multiple dogs appear, explain that the image contains
    multiple dogs. Do not combine their breed estimates into
    one dog's percentages.

11. If no dog is visible, set dog_visible=false, breed="Unknown",
    detected_breed="Unknown", and breed_percentages=[].

HEALTH AND BLEEDING:

1. Describe only what is actually visible.
2. Red fur, red objects, food, paint, and stains are not
   automatically blood.
3. Never assume blood is visible because an earlier message
   mentioned bleeding.
4. Use visible_blood="uncertain" when the image is inconclusive.
5. Visible blood does not prove active or severe bleeding.
6. A photograph cannot establish whether bleeding is ongoing.
7. Do not invent wounds, symptoms, or injuries.
8. Do not diagnose medical conditions from a photograph.
9. A normal-looking photo does not prove that a dog is healthy.
10. Do not mistake uncertainty for proof that no injury exists.

Return valid JSON only. Do not include Markdown.
"""

            image_response = client.chat.completions.create(
                model="gpt-4.1-mini",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": image_system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this newly uploaded image "
                                    "independently.\n"
                                    f"Registered dog name: "
                                    f"{getattr(customer, 'pet_name', '') or 'Unknown'}\n"
                                    f"Registered breed: "
                                    f"{getattr(customer, 'breed', '') or 'Unknown'}\n"
                                    f"Registered sex: "
                                    f"{getattr(customer, 'sex', '') or 'Unknown'}\n"
                                    f"Registered age: {dog_age}\n\n"
                                    "Identify the likely breed or mix, "
                                    "estimate visual breed percentages, "
                                    "and describe visible health observations. "
                                    "Do not treat earlier conversation details "
                                    "as observations from this photograph."
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        f"data:{content_type};base64,"
                                        f"{image_base64}"
                                    )
                                }
                            }
                        ]
                    }
                ],
                temperature=0
            )

            image_analysis = json.loads(
                image_response.choices[0].message.content
            )

            # Normalize image-analysis fields.
            image_analysis.setdefault("breed", "Unknown")
            image_analysis.setdefault(
                "detected_breed",
                image_analysis.get("breed", "Unknown")
            )
            image_analysis.setdefault("confidence", "low")
            image_analysis.setdefault("breed_percentages", [])
            image_analysis.setdefault(
                "description",
                "No description available."
            )
            image_analysis.setdefault(
                "possible_health_observations",
                ""
            )
            image_analysis.setdefault("comparison", "")
            image_analysis.setdefault("dog_visible", None)
            image_analysis.setdefault("visible_blood", "uncertain")
            image_analysis.setdefault(
                "bleeding_observation",
                "The image cannot establish whether bleeding is active."
            )
            image_analysis.setdefault("wound_visible", "uncertain")
            image_analysis.setdefault(
                "limitations",
                "Visual identification is not a DNA test."
            )

            # Validate the breed percentage list.
            breed_percentages = image_analysis.get(
                "breed_percentages"
            )

            if not isinstance(breed_percentages, list):
                breed_percentages = []

            cleaned_breeds = []

            for item in breed_percentages:
                if not isinstance(item, dict):
                    continue

                breed_name = str(
                    item.get("breed", "Unknown")
                ).strip()

                try:
                    percentage = int(item.get("percentage", 0))
                except (TypeError, ValueError):
                    continue

                if not breed_name:
                    continue

                if percentage < 0 or percentage > 100:
                    continue

                cleaned_breeds.append({
                    "breed": breed_name,
                    "percentage": percentage,
                    "evidence": str(
                        item.get("evidence", "")
                    )
                })

            total_percentage = sum(
                item["percentage"]
                for item in cleaned_breeds
            )

            if (
                image_analysis.get("dog_visible") is True
                and cleaned_breeds
                and total_percentage == 100
            ):
                image_analysis["breed_percentages"] = cleaned_breeds
            else:
                image_analysis["breed_percentages"] = []

            if image_analysis.get("dog_visible") is False:
                image_analysis["breed"] = "Unknown"
                image_analysis["detected_breed"] = "Unknown"
                image_analysis["breed_percentages"] = []

            print(
                "IMAGE ANALYSIS RESULT:",
                json.dumps(
                    image_analysis,
                    ensure_ascii=False
                )
            )

        except Exception as exc:
            print("IMAGE ANALYSIS ERROR:", exc)

            image_analysis = {
                "breed": "Unable to determine",
                "detected_breed": "Unable to determine",
                "confidence": "low",
                "breed_percentages": [],
                "description": (
                    "The uploaded image could not be analyzed."
                ),
                "possible_health_observations": "",
                "comparison": "",
                "dog_visible": None,
                "visible_blood": "uncertain",
                "bleeding_observation": (
                    "The image could not be assessed."
                ),
                "wound_visible": "uncertain",
                "limitations": (
                    "Please try uploading the image again."
                )
            }

    # =========================================================
    # 8. VETERINARY TRIAGE SYSTEM
    # =========================================================

    triage_system_prompt = """
You are the veterinary safety triage assistant for We Care Pet Care.

You are not a replacement for a veterinarian.

Review the entire conversation and the latest image analysis.
Differentiate between owner-reported symptoms, earlier symptoms,
and observations from the newly uploaded image.

IMAGE RULES:

- The image analysis describes the newly uploaded photograph.
- Do not assume an earlier symptom is visible in the new image.
- If visible_blood="no", do not claim that blood is visible in the photo.
- If visible_blood="uncertain", explain that the image is inconclusive.
- If visible_blood="yes", do not assume bleeding is ongoing or severe.
- Do not dismiss an emergency just because the photo looks normal.
- Breed percentages are visual estimates, not DNA results.
- Breed identification alone does not establish medical risk.

=========================================================
LOW URGENCY
=========================================================

Use "low" only for mild symptoms without warning signs, when the dog
otherwise appears comfortable and behaves normally.

Examples that may be low urgency:
- Occasional sneezing with normal behavior.
- Mild itching without wounds or swelling.
- One episode of soft stool in an otherwise active dog.
- A mild symptom that has resolved and has no concerning associated signs.

Recommend safe monitoring and explain which changes require veterinary care.
Do not classify persistent or worsening symptoms as low automatically.

=========================================================
MEDIUM URGENCY
=========================================================

Use "medium" when veterinary advice or assessment is warranted but an
immediate life-threatening emergency has not been established.

Examples may include:
- Repeated vomiting without collapse or severe weakness.
- Persistent diarrhea without signs of shock.
- Reduced appetite combined with unusual behavior.
- Persistent lethargy.
- Limping or pain affecting normal activity.
- A wound that needs assessment without severe uncontrolled bleeding.
- Persistent coughing without obvious severe breathing difficulty.
- Eye redness or discharge.
- Symptoms that recur, persist, or progressively worsen.
- Unclear symptoms that require more information.

Recommend prompt veterinary advice or assessment. Same-day care may
be appropriate depending on the symptoms and their duration.

=========================================================
HIGH URGENCY
=========================================================

Use "high" for symptoms that could indicate a life-threatening
condition, serious injury, rapid deterioration, or severe suffering.

Potential emergencies include:
- Difficulty breathing, choking, or gasping.
- Collapse, unconsciousness, or inability to stand.
- Severe or repeated seizures.
- Severe, spurting, or uncontrolled bleeding.
- Major trauma or serious wounds.
- Suspected poisoning or overdose.
- Pale, white, gray, or blue gums with weakness or distress.
- A swollen abdomen with repeated unproductive retching.
- Inability to urinate, especially with straining or distress.
- Severe pain or signs of shock.
- Vomiting accompanied by marked weakness, collapse, or severe pain.
- Vomiting blood, blood in vomit, bloody vomit, or owner-reported blood in vomit must be classified as HIGH urgency.
- For vomiting blood, set risk_level="high", emergency=true, needs_more_information=false, and follow_up_question="".
- Do not downgrade reported blood in vomit because an image is unclear or the dog appears normal.
- Significant bloody diarrhea, especially with weakness, also requires urgent assessment.
- Heatstroke signs such as collapse, confusion, or severe distress.
- Any other symptoms that reasonably suggest an immediate threat to life.

Tell the owner to seek emergency veterinary care immediately.
Do not delay care while collecting more information or waiting for SMS.

=========================================================
SYMPTOM CLASSIFICATION RULES
=========================================================

1. Consider severity, duration, frequency, progression, combinations
   of symptoms, and the dog's overall condition.

2. Do not classify symptoms based on a keyword alone. Vomiting,
   diarrhea, blood, pain, or coughing does not automatically mean high.

3. Repeated or worsening symptoms may require greater urgency.

4. Multiple symptoms together may indicate greater risk.

5. If information is missing and no emergency is apparent, use medium
   and ask a focused follow-up question instead of assuming the dog is safe.

6. Do not downgrade an apparent emergency because a photograph looks
   normal or because the owner has not supplied every detail.

7. Suspected poisoning, severe breathing difficulty, collapse,
   serious trauma, and uncontrolled bleeding require immediate action.

8. Puppies, elderly dogs, and dogs with known health conditions may
   be more vulnerable. Recommend assessment sooner when appropriate.

9. Do not diagnose a specific disease solely from symptoms or images.

10. Do not recommend human medication or unsafe home remedies.

=========================================================
IMAGE AND BLEEDING RULES
=========================================================

- Do not assume earlier symptoms are visible in a new image.
- If visible_blood="no", do not claim blood is visible in the photograph.
- If visible_blood="uncertain", explain that the image is inconclusive.
- If visible_blood="yes", do not assume bleeding is active or severe.
- A photograph cannot establish whether bleeding is ongoing.
- Owner-reported severe bleeding must be considered even if the image
  is unclear or does not visibly show blood.
- A normal-looking image cannot rule out illness or injury.

For external bleeding, recommend clean gauze or cloth with firm,
continuous pressure while arranging veterinary care. Do not repeatedly
remove it to inspect the wound. Severe or uncontrolled bleeding
requires immediate emergency care.

=========================================================
FOLLOW-UP QUESTIONS
=========================================================

When urgency is uncertain and no emergency is apparent, ask the most
important question needed to assess risk.

Examples:
- When did the symptoms begin?
- How often has vomiting or diarrhea occurred?
- Is the dog alert and responding normally?
- Is the dog breathing normally?
- Can the dog urinate?
- Is bleeding continuing?
- Could the dog have eaten medication, chemicals, or another toxin?

Do not delay emergency recommendations to ask additional questions.

Return ONLY valid JSON:

{
  "risk_level": "low|medium|high",
  "emergency": false,
  "reason": "Brief explanation of the urgency classification",
  "needs_more_information": true,
  "follow_up_question": "Most important next question or empty string",
  "recommended_action": "Clear and safe next step"
}

Consistency requirements:
- A clear potential emergency must use risk_level="high",
  emergency=true, needs_more_information=false, and an empty
  follow_up_question.
- For non-emergencies, use emergency=false and choose low or medium.
- If important information is missing and no emergency is apparent,
  use medium and ask a focused question.

Return valid JSON only. Do not include Markdown.
"""

    # =========================================================
    # 9. BUILD TRIAGE MESSAGES
    # =========================================================

    triage_messages = [
        {
            "role": "system",
            "content": triage_system_prompt
        }
    ]

    triage_messages.extend(conversation_history)

    if image_analysis:
        triage_messages.append({
            "role": "user",
            "content": (
                "NEWLY UPLOADED IMAGE ANALYSIS:\n"
                + json.dumps(
                    image_analysis,
                    ensure_ascii=False
                )
                + "\nAssess this new image alongside the conversation. "
                "Do not assume that earlier symptoms are visible in "
                "this photograph. Distinguish visible blood from "
                "active bleeding. If the status is unknown, ask the owner."
            )
        })

    # =========================================================
    # 10. RUN TRIAGE
    # =========================================================

    triage_result = {
        "risk_level": "medium",
        "emergency": False,
        "reason": "More information is needed.",
        "needs_more_information": True,
        "follow_up_question": (
            "Can you describe what is happening with your dog?"
        ),
        "recommended_action": (
            "Please provide more information about your dog's condition."
        )
    }

    try:
        triage_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=triage_messages,
            temperature=0.1
        )

        triage_result = json.loads(
            triage_response.choices[0].message.content
        )

    except Exception as exc:
        print("TRIAGE ERROR:", exc)

    # =========================================================
    # 11. NORMALIZE TRIAGE RESULT
    # =========================================================

    risk_level = str(
        triage_result.get("risk_level", "medium")
    ).lower().strip()

    if risk_level not in ("low", "medium", "high"):
        risk_level = "medium"

    # High urgency always triggers the existing emergency path.
    emergency = (
        risk_level == "high"
        or triage_result.get("emergency") is True
    )

    if emergency:
        risk_level = "high"

    needs_more_information = (
        triage_result.get("needs_more_information") is True
    )

    reason = str(
        triage_result.get(
            "reason",
            "More information is needed to assess the symptoms."
        )
    ).strip()

    follow_up_question = str(
        triage_result.get(
            "follow_up_question",
            ""
        )
    ).strip()

    recommended_action = str(
        triage_result.get(
            "recommended_action",
            ""
        )
    ).strip()

    # =========================================================
    # HIGH-URGENCY SYMPTOM OVERRIDE
    # =========================================================
    # The backend must not rely only on the AI-generated triage result.
    # Owner-reported blood in vomit is treated as HIGH urgency even if
    # the model incorrectly returns LOW or MEDIUM.
    normalized_message = " ".join(
        message.lower().strip().replace("vomitting", "vomiting").split()
    )

    blood_in_vomit_phrases = [
        "vomiting blood",
        "vomited blood",
        "vomit blood",
        "vomits blood",
        "throwing up blood",
        "threw up blood",
        "blood in vomit",
        "blood in the vomit",
        "blood in his vomit",
        "blood in her vomit",
        "blood in my dog's vomit",
        "blood in my dogs vomit",
        "bloody vomit",
        "hematemesis",
    ]

    blood_in_vomit_reported = any(
        phrase in normalized_message
        for phrase in blood_in_vomit_phrases
    )

    # Avoid treating explicit denials as positive symptom reports.
    explicit_blood_denial = any(
        phrase in normalized_message
        for phrase in [
            "not vomiting blood",
            "isn't vomiting blood",
            "isnt vomiting blood",
            "is not vomiting blood",
            "no blood in vomit",
            "no blood in the vomit",
            "without blood in vomit",
            "without blood in the vomit",
        ]
    )

    if blood_in_vomit_reported and not explicit_blood_denial:
        risk_level = "high"
        emergency = True
        needs_more_information = False
        follow_up_question = ""
        reason = (
            "Vomiting blood can indicate a serious or life-threatening "
            "condition and requires immediate veterinary assessment."
        )
        recommended_action = (
            "Seek emergency veterinary care immediately. "
            "Do not wait for an SMS response."
        )

    if emergency:
        risk_level = "high"
        needs_more_information = False
        follow_up_question = ""

        if not recommended_action:
            recommended_action = (
                "Seek emergency veterinary care immediately."
            )

    elif risk_level == "medium":
        if not recommended_action:
            recommended_action = (
                "Contact a veterinarian promptly for advice "
                "and arrange an assessment as appropriate."
            )

    elif risk_level == "low":
        if not recommended_action:
            recommended_action = (
                "Monitor your dog's symptoms and seek veterinary "
                "advice if they persist or worsen."
            )

    # =========================================================
    # 12. VETERINARIAN SMS
    # =========================================================

    sms_sent = False
    sms_result = None

    if emergency:
        owner_messages = [
            item["content"]
            for item in conversation_history
            if item["role"] == "user"
        ]

        symptoms_for_vet = "\n".join(owner_messages[-8:])

        if image_analysis:
            symptoms_for_vet += (
                "\n\nLatest image analysis:\n"
                + json.dumps(
                    image_analysis,
                    ensure_ascii=False
                )
            )

        try:
            sms_result = notify_vet(
                customer=customer,
                symptoms=symptoms_for_vet,
                reason=reason,
                risk_level=risk_level
            )

            print("VETERINARIAN SMS RESULT:", sms_result)

            if isinstance(sms_result, dict):
                sms_sent = sms_result.get("success") is True

        except Exception as exc:
            print("VETERINARIAN SMS ERROR:", exc)

    # =========================================================
    # 13. KNOWLEDGE BASE
    # =========================================================

    knowledge_answer = None

    if (
        message
        and not emergency
        and risk_level == "low"
        and not needs_more_information
    ):
        try:
            knowledge_answer = (
                QuestionAnswer.objects
                .filter(question__icontains=message)
                .first()
            )
        except Exception as exc:
            print("KNOWLEDGE BASE ERROR:", exc)

    # =========================================================
    # 14. CONVERSATIONAL ASSISTANT PROMPT
    # =========================================================

    assistant_system_prompt = f"""
You are the conversational AI veterinary assistant for We Care Pet Care.

You are not a replacement for a veterinarian.

DOG PROFILE:
Name: {getattr(customer, 'pet_name', '') or 'Unknown'}
Registered breed: {getattr(customer, 'breed', '') or 'Unknown'}
Sex: {getattr(customer, 'sex', '') or 'Unknown'}
Age: {dog_age}
Owner: {getattr(customer, 'fullname', '') or request.user.get_username()}

CURRENT TRIAGE:
Risk level: {risk_level}
Emergency: {emergency}
Reason: {reason}
Needs more information: {needs_more_information}
Follow-up question: {follow_up_question}
Recommended action: {recommended_action}
Veterinarian SMS confirmed sent: {sms_sent}

VETERINARY CLINIC CONTACT INFORMATION:
Clinic name: {VETERINARY_CLINIC_NAME}
Phone number: {VETERINARY_DISPLAY_NUMBER}
Clinic address: {VETERINARY_CLINIC_ADDRESS}

VETERINARY CONTACT RULES:
- If the owner asks for the vet's number, veterinarian's contact,
  clinic phone, clinic address, or how to contact the clinic,
  provide the contact information above.
- Do not invent or change the clinic's phone number or address.
- Do not claim that you called the clinic.
- Do not claim an SMS was sent unless sms_sent is true.
- If the dog may be experiencing an emergency, tell the owner
  to contact the clinic directly and seek immediate veterinary care.
- Do not tell the owner to wait for an SMS reply before seeking care.

SYMPTOM URGENCY GUIDANCE:

LOW:
Explain safe monitoring and warning signs that require escalation.

MEDIUM:
Explain why veterinary advice or assessment is needed and recommend
a prompt assessment appropriate to the symptoms.

HIGH:
Clearly tell the owner to seek emergency veterinary care immediately.
Do not suggest waiting for an SMS response.

Never diagnose a disease based only on symptoms or a photograph.
Do not give false reassurance when important information is missing.

CONVERSATION RULES:
- Speak naturally, empathetically, and clearly.
- Do not display internal JSON or technical reasoning.
- Do not diagnose diseases from a photograph.
- Give safe, practical guidance.
- Do not recommend human medications.
- Ask focused follow-up questions when information is missing.

BREED IDENTIFICATION:
When image-analysis results are provided, explain the likely breed
or breeds and their estimated visual percentages.

Explain that percentages are estimates of visual resemblance,
not confirmed genetic ancestry or DNA test results.

Do not invent breed percentages when the analysis is inconclusive.
Do not claim that a breed has been genetically confirmed.

IMAGE AND BLEEDING:
- Assess the latest uploaded image using its image-analysis results.
- Do not say blood is visible if visible_blood="no".
- If visible_blood="uncertain", explain that the image is inconclusive.
- Visible blood does not establish active or severe bleeding.
- Do not repeat an earlier symptom as an observation of the new image.
- A normal-looking photograph cannot rule out illness or injury.

EMERGENCY:
If emergency=true, calmly tell the owner to seek immediate veterinary care.

If sms_sent=true, you may say the veterinarian was notified by SMS.
If sms_sent=false, do not claim that the veterinarian was notified.
Tell the owner to contact the veterinarian directly.

Do not delay emergency care while waiting for a reply.

STYLE:
Use short paragraphs and natural language.
Do not use emojis.
Do not display internal risk assessment fields.
"""

    # =========================================================
    # 15. ADD IMAGE DETAILS TO ASSISTANT PROMPT
    # =========================================================

    if image_analysis:
        assistant_system_prompt += (
            "\n\nLATEST UPLOADED IMAGE ANALYSIS:\n"
            + json.dumps(
                image_analysis,
                ensure_ascii=False
            )
            + "\nDescribe the actual visible findings. "
              "Include likely breed percentages when available. "
              "Do not mistake visual estimates for DNA results. "
              "Do not infer bleeding from earlier conversation alone."
        )

    # =========================================================
    # 16. ADD KNOWLEDGE BASE ANSWER
    # =========================================================

    if knowledge_answer:
        assistant_system_prompt += (
            "\n\nPOSSIBLE KNOWLEDGE BASE ANSWER:\n"
            + str(knowledge_answer.answer)
            + "\nUse this answer only when relevant. "
              "Do not let it override veterinary safety guidance."
        )

    # =========================================================
    # 17. GENERATE CONVERSATIONAL RESPONSE
    # =========================================================

    try:
        response_messages = [
            {
                "role": "system",
                "content": assistant_system_prompt
            }
        ]

        response_messages.extend(conversation_history)

        if image_analysis:
            response_messages.append({
                "role": "user",
                "content": (
                    "Please analyze my newly uploaded image. "
                    "The image analysis results are:\n"
                    + json.dumps(
                        image_analysis,
                        ensure_ascii=False
                    )
                    + "\nDescribe the likely breed and percentage "
                    "estimates if available, and describe visible "
                    "health observations accurately."
                )
            })

        ai_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=response_messages,
            temperature=0.45
        )

        assistant_message = (
            ai_response.choices[0].message.content or ""
        ).strip()

        if not assistant_message:
            raise ValueError("The AI returned an empty response.")

    except Exception as exc:
        print("AI RESPONSE ERROR:", exc)

        if image_analysis:
            assistant_message = (
                "I received your image, but I couldn't complete "
                "the analysis. Please try uploading it again. "
                "If your dog has a serious injury or difficulty "
                "breathing, seek immediate veterinary care."
            )
        else:
            assistant_message = (
                "I'm sorry, but I couldn't process your message "
                "right now. Please try again."
            )

    # =========================================================
    # 18. ENSURE FOLLOW-UP QUESTION IS DISPLAYED
    # =========================================================

    if (
        not emergency
        and needs_more_information
        and follow_up_question
        and follow_up_question.lower() not in assistant_message.lower()
    ):
        assistant_message += "\n\n" + follow_up_question

    # =========================================================
    # 18A. DETECT VETERINARY CONTACT REQUESTS
    # =========================================================

    contact_keywords = (
        "vet number",
        "veterinarian number",
        "veterinary number",
        "vet contact",
        "veterinarian contact",
        "veterinary contact",
        "clinic number",
        "clinic contact",
        "clinic phone",
        "clinic telephone",
        "phone number",
        "telephone number",
        "contact number",
        "contact details",
        "contact information",
        "how to contact",
        "how can i contact",
        "how do i contact",
        "call the vet",
        "call the veterinarian",
        "call the clinic",
        "vet's number",
        "veterinarian's number",
        "clinic address",
        "where is the clinic",
        "clinic location",
        "vet phone",
        "veterinary phone",
        "number of the vet",
        "number for the vet",
        "contact the vet",
        "contact the veterinarian",
    )

    normalized_message = message.lower().strip()

    contact_requested = any(
        keyword in normalized_message
        for keyword in contact_keywords
    )

    if contact_requested:
        contact_notice = (
            f"Veterinary Clinic Contact\n"
            f"{VETERINARY_CLINIC_NAME}\n"
            f"Phone: {VETERINARY_DISPLAY_NUMBER}\n"
            f"Address: {VETERINARY_CLINIC_ADDRESS}"
        )

        if VETERINARY_DISPLAY_NUMBER not in assistant_message:
            assistant_message += "\n\n" + contact_notice

    # =========================================================
    # 19. EMERGENCY SMS NOTICE
    # =========================================================

    if emergency:
        if sms_sent:
            emergency_notice = (
                "The veterinarian has been notified by SMS. "
                "Please seek immediate veterinary care."
            )
        else:
            emergency_notice = (
                "I couldn't confirm that the veterinarian received "
                "an SMS. Please contact the veterinarian directly "
                "and seek immediate veterinary care."
            )

        if emergency_notice.lower() not in assistant_message.lower():
            assistant_message += "\n\n" + emergency_notice

    # =========================================================
    # 19A. DISPLAY URGENCY IN THE CHAT RESPONSE
    # =========================================================
    # The frontend may currently display only the "response" text field.
    # Include urgency directly in that text as well as in the JSON
    # "risk_level" field, so the owner can see LOW, MEDIUM, or HIGH.
    urgency_label = {
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
    }.get(risk_level, "MEDIUM")

    urgency_notice = (
        f"Urgency: {urgency_label}\n"
        f"Reason: {reason}\n"
        f"Recommended action: {recommended_action}"
    )

    if not assistant_message.lstrip().startswith("Urgency:"):
        assistant_message = (
            urgency_notice + "\n\n" + assistant_message
        )

    # =========================================================
    # 20. SAVE ASSISTANT MESSAGE
    # =========================================================

    ChatMessage.objects.create(
        session=session,
        role="assistant",
        message=assistant_message
    )

    # =========================================================
    # 21. SAVE SAFE KNOWLEDGE BASE ANSWER
    # =========================================================

    if (
        message
        and not emergency
        and risk_level == "low"
        and not needs_more_information
        and not knowledge_answer
    ):
        try:
            QuestionAnswer.objects.create(
                question=message,
                answer=assistant_message
            )
        except Exception as exc:
            print("QUESTION ANSWER SAVE ERROR:", exc)

    # =========================================================
    # 22. RETURN JSON TO FRONTEND
    # =========================================================

    return JsonResponse({
        "success": True,
        "type": "image" if image_analysis else "text",
        "response": assistant_message,
        "emergency": emergency,
        "risk_level": risk_level,
        "reason": reason,
        "needs_more_information": needs_more_information,
        "follow_up_question": follow_up_question,
        "recommended_action": recommended_action,
        "sms_sent": sms_sent,
        "image_analysis": image_analysis,

        "veterinarian_contact": {
            "clinic_name": VETERINARY_CLINIC_NAME,
            "phone": VETERINARY_CONTACT_NUMBER,
            "display_phone": VETERINARY_DISPLAY_NUMBER,
            "address": VETERINARY_CLINIC_ADDRESS,
        }
    })




@login_required
def add_dog(request):
    customer = get_object_or_404(
        Customer,
        user=request.user,
    )

    breeds = Breed.objects.filter(
        is_active=True,
    ).order_by("name")

    if request.method == "POST":
        pet_name = request.POST.get("pet_name", "").strip()
        breed_id = request.POST.get("breed", "").strip()
        sex = request.POST.get("sex", "").strip()
        birthdate = request.POST.get("birthdate", "").strip()

        selected_breed = Breed.objects.filter(
            pk=breed_id,
            is_active=True,
        ).first()

        try:
            parsed_birthdate = date.fromisoformat(birthdate)
            valid_birthdate = parsed_birthdate <= date.today()
        except (ValueError, TypeError):
            parsed_birthdate = None
            valid_birthdate = False

        error = None

        if not pet_name:
            error = "Please enter your dog's name."
        elif len(pet_name) > 100:
            error = "The dog's name must not exceed 100 characters."
        elif not selected_breed:
            error = "Please select a valid breed."
        elif sex not in ("Male", "Female"):
            error = "Please select your dog's sex."
        elif not valid_birthdate:
            error = "Please enter a valid birthdate. Future dates are not allowed."

        if error:
            return render(
                request,
                "pages/dog_form.html",
                {
                    "customer": customer,
                    "breeds": breeds,
                    "dog": None,
                    "error": error,
                    "form_data": request.POST,
                    "page_title": "Add a Dog",
                    "button_text": "Save Dog",
                },
            )

        Dog.objects.create(
            customer=customer,
            pet_name=pet_name,
            breed=selected_breed,
            sex=sex,
            birthdate=parsed_birthdate,
        )

        messages.success(
            request,
            f"{pet_name} has been added to your pet records.",
        )
        return redirect("view-profile")

    return render(
        request,
        "pages/dog_form.html",
        {
            "customer": customer,
            "breeds": breeds,
            "dog": None,
            "form_data": {},
            "page_title": "Add a Dog",
            "button_text": "Save Dog",
        },
    )


@login_required
def edit_dog(request, dog_id):
    customer = get_object_or_404(
        Customer,
        user=request.user,
    )

    # Only allow editing a dog belonging to the logged-in customer.
    dog = get_object_or_404(
        Dog,
        pk=dog_id,
        customer=customer,
    )

    breeds = Breed.objects.filter(
        is_active=True,
    ).order_by("name")

    if request.method == "POST":
        pet_name = request.POST.get("pet_name", "").strip()
        breed_id = request.POST.get("breed", "").strip()
        sex = request.POST.get("sex", "").strip()
        birthdate = request.POST.get("birthdate", "").strip()

        selected_breed = Breed.objects.filter(
            pk=breed_id,
        ).first()

        try:
            parsed_birthdate = date.fromisoformat(birthdate)
            valid_birthdate = parsed_birthdate <= date.today()
        except (ValueError, TypeError):
            parsed_birthdate = None
            valid_birthdate = False

        error = None

        if not pet_name:
            error = "Please enter your dog's name."
        elif len(pet_name) > 100:
            error = "The dog's name must not exceed 100 characters."
        elif not selected_breed:
            error = "Please select a valid breed."
        elif sex not in ("Male", "Female"):
            error = "Please select your dog's sex."
        elif not valid_birthdate:
            error = "Please enter a valid birthdate. Future dates are not allowed."

        if error:
            return render(
                request,
                "pages/dog_form.html",
                {
                    "customer": customer,
                    "breeds": breeds,
                    "dog": dog,
                    "error": error,
                    "form_data": request.POST,
                    "page_title": "Edit Dog",
                    "button_text": "Save Changes",
                },
            )

        dog.pet_name = pet_name
        dog.breed = selected_breed
        dog.sex = sex
        dog.birthdate = parsed_birthdate
        dog.save(
            update_fields=[
                "pet_name",
                "breed",
                "sex",
                "birthdate",
            ]
        )

        messages.success(
            request,
            f"{dog.pet_name}'s information has been updated.",
        )
        return redirect("view-profile")

    return render(
        request,
        "pages/dog_form.html",
        {
            "customer": customer,
            "breeds": breeds,
            "dog": dog,
            "form_data": {},
            "page_title": "Edit Dog",
            "button_text": "Save Changes",
        },
    )


@login_required
def delete_dog(request, dog_id):
    customer = get_object_or_404(
        Customer,
        user=request.user,
    )

    # Prevent customers from deleting another customer's dog.
    dog = get_object_or_404(
        Dog,
        pk=dog_id,
        customer=customer,
    )

    if request.method == "POST":
        dog_name = dog.pet_name
        dog.delete()

        messages.success(
            request,
            f"{dog_name} has been removed from your pet records.",
        )
        return redirect("view-profile")

    return render(
        request,
        "pages/delete_dog.html",
        {
            "customer": customer,
            "dog": dog,
        },
    )
