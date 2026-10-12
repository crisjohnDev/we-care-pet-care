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
from .models import ChatSession, ChatMessage, Customer, QuestionAnswer
from datetime import date
from .sms import notify_vet

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
        .order_by("-updated_at")
    )

    return render(request, "pages/dashboard.html", {
        "session": session,
        "messages": session.messages.all(),
        "recent_chats": recent_chats,
    })


# import base64
# import json
# from datetime import date

# from django.contrib.auth.decorators import login_required
# from django.http import JsonResponse
# from django.shortcuts import get_object_or_404
# from django.views.decorators.http import require_POST

# from openai import OpenAI

# from .models import ChatSession, ChatMessage, Customer, QuestionAnswer
# from .sms import notify_vet



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
            image_analysis.setdefault(
                "breed",
                "Unknown"
            )
            image_analysis.setdefault(
                "detected_breed",
                image_analysis.get("breed", "Unknown")
            )
            image_analysis.setdefault(
                "confidence",
                "low"
            )
            image_analysis.setdefault(
                "breed_percentages",
                []
            )
            image_analysis.setdefault(
                "description",
                "No description available."
            )
            image_analysis.setdefault(
                "possible_health_observations",
                ""
            )
            image_analysis.setdefault(
                "comparison",
                ""
            )
            image_analysis.setdefault(
                "dog_visible",
                None
            )
            image_analysis.setdefault(
                "visible_blood",
                "uncertain"
            )
            image_analysis.setdefault(
                "bleeding_observation",
                "The image cannot establish whether bleeding is active."
            )
            image_analysis.setdefault(
                "wound_visible",
                "uncertain"
            )
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

            # Only normalize valid model output. Do not silently
            # invent percentages if the model returned invalid data.
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

RISK LEVELS:

LOW:
The available information suggests a mild concern without warning signs.

MEDIUM:
More information or veterinary assessment is needed, but an immediate
life-threatening emergency has not been established.

HIGH:
Available information indicates a serious or potentially life-threatening
condition.

Do not classify a situation as an emergency merely because a message
contains the words blood, bleeding, vomiting, diarrhea, or pain.

Potential emergencies include:
- Severe breathing difficulty.
- Collapse or unconsciousness.
- Severe seizures.
- Spurting or uncontrolled bleeding.
- Serious trauma.
- Suspected poisoning with concerning symptoms.
- Significant blood loss or signs of shock.
- Other clearly life-threatening conditions.

A still photograph cannot reliably establish active bleeding or blood loss.

For uncertain external bleeding, ask whether bleeding is continuing,
where it is coming from, and whether continuous pressure controls it.

For external bleeding, recommend clean gauze or cloth with continuous
pressure. Do not repeatedly remove it to inspect the wound. Severe,
spurting, or uncontrolled bleeding needs immediate veterinary care.

Never recommend human medications or unsafe home remedies.

If a clear emergency exists:
- emergency=true
- risk_level="high"
- needs_more_information=false
- follow_up_question=""

If more information is needed:
- ask the most important question
- do not automatically classify the case as an emergency

Return ONLY valid JSON:

{
  "risk_level": "low|medium|high",
  "emergency": false,
  "reason": "Brief explanation",
  "needs_more_information": true,
  "follow_up_question": "Most important next question",
  "recommended_action": "Safe immediate action"
}
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

    emergency = triage_result.get("emergency") is True

    needs_more_information = (
        triage_result.get("needs_more_information") is True
    )

    reason = str(
        triage_result.get(
            "reason",
            "More information is needed."
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

    if emergency:
        risk_level = "high"
        needs_more_information = False
        follow_up_question = ""

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
        "image_analysis": image_analysis
    })