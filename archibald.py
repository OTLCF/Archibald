import os
import json
import re
import difflib
from dotenv import load_dotenv
from dateutil.parser import parse
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session
from flask_cors import CORS, cross_origin
from langdetect import detect
from translate import Translator
import openai

# Configuration OpenAI
load_dotenv()
secret_key = os.getenv('SECRET_KEY')
openai.api_key = secret_key

# Flask setup
app = Flask(__name__)
CORS(app, origins=["https://phareducapferret.com"], supports_credentials=True)
app.secret_key = "archi33950baldBOT"

def preprocess_knowledge(raw_knowledge):
    knowledge = {
        "questions_and_responses": [],
        "general_information": [],
        "schedule": [],
        "pricing": {},
        "faq": []
    }

    for section, items in raw_knowledge.items():
        if section == "schedule":
            for schedule_item in items:
                if isinstance(schedule_item, dict):
                    knowledge["schedule"].append(schedule_item)
                else:
                    print(f"Unexpected item format in section '{section}': {schedule_item}")

        elif section == "pricing":
            if isinstance(items, dict):
                knowledge["pricing"] = items
            else:
                print(f"Unexpected item format in section '{section}': {items}")

        elif section == "general_information":
            for item in items:
                if isinstance(item, dict) and "key" in item and "value" in item:
                    knowledge["general_information"].append(item)
                else:
                    print(f"Unexpected item format in section '{section}': {item}")

        elif section == "faq":
            for item in items:
                if isinstance(item, dict) and "question" in item and ("answer" in item or "response" in item):
                    knowledge["faq"].append({
                        "question": item["question"],
                        "answer": item.get("answer", item.get("response", ""))
                    })
                else:
                    print(f"Unexpected item format in section '{section}': {item}")

        elif section == "questions_and_responses":
            for item in items:
                if isinstance(item, dict) and "question" in item and "response" in item:
                    knowledge["questions_and_responses"].append({
                        "question": item["question"],
                        "response": item["response"]
                    })
                else:
                    print(f"Unexpected item format in section '{section}': {item}")
        else:
            print(f"Unknown section '{section}', skipping.")

    return knowledge

with open('archibald_knowledge.json', 'r', encoding='utf-8') as file:
    raw_knowledge_base = json.load(file)

knowledge_base = preprocess_knowledge(raw_knowledge_base)

MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
}

def parse_relative_date(user_message):
    today = datetime.today()
    user_message = user_message.lower().strip()

    if "aujourd'hui" in user_message or "aujourdhui" in user_message:
        return today.date()
    if "demain" in user_message:
        return (today + timedelta(days=1)).date()
    if "après-demain" in user_message:
        return (today + timedelta(days=2)).date()

    match_relative = re.search(r"dans (\d+) jours?", user_message)
    if match_relative:
        days_ahead = int(match_relative.group(1))
        return (today + timedelta(days=days_ahead)).date()

    match_explicit = re.search(r"le (\d{1,2}) (\w+)", user_message)
    if match_explicit:
        day = int(match_explicit.group(1))
        month_name = match_explicit.group(2)
        if month_name in MONTHS_FR:
            year = today.year
            parsed_date = datetime(year, MONTHS_FR[month_name], day).date()
            if parsed_date < today.date():
                parsed_date = datetime(year + 1, MONTHS_FR[month_name], day).date()
            return parsed_date

    return None

def detect_language(user_message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Detect the language of this message and return the language code (fr, en, es, etc.)."},
                {"role": "user", "content": user_message}
            ],
            max_tokens=10,
            temperature=0
        )
        lang = response["choices"][0]["message"]["content"].strip().lower()
        return lang if lang in ["fr", "en", "es", "de", "it"] else "fr"
    except Exception as e:
        print(f"Erreur de détection de langue: {e}")
        return "fr"

def extract_info(user_message):
    try:
        user_message = user_message.lower()
        is_schedule = any(word in user_message for word in ["horaire", "ouvert", "fermé", "heures", "temps", "jours"])
        is_price = any(word in user_message for word in ["tarif", "prix", "combien", "coût", "entrée"])
        is_pet = any(word in user_message for word in ["chien", "chat", "oiseau", "animaux", "animal", "perroquet", "hamster", "lapin"])
        date = parse_relative_date(user_message) if is_schedule else None
        return {
            "date": date.isoformat() if date else None,
            "is_schedule": is_schedule,
            "is_price": is_price,
            "is_pet": is_pet
        }
    except Exception as e:
        print(f"Erreur lors de l'extraction des informations: {e}")
        return {}

def create_prompt(user_message_translated, extracted_info, lang):
    is_schedule = extracted_info.get("is_schedule", False)
    is_price = extracted_info.get("is_price", False)
    is_pet = extracted_info.get("is_pet", False)

    response_parts = []

    if is_schedule:
        response_parts.append("📌 Les horaires du phare peuvent varier selon la saison. Consultez-les ici : [🕒 Voir les horaires et tarifs](https://phareducapferret.com/horaires-et-tarifs/).")
    if is_price:
        response_parts.append("🎟️ Le tarif d’entrée est de **7€ pour les adultes** et **4€ pour les enfants**.\n📌 Consultez tous les détails ici : [🕒 Voir les horaires et tarifs](https://phareducapferret.com/horaires-et-tarifs/).")
    if is_pet:
        response_parts.append("🐾 **Les animaux de compagnie sont autorisés dans le parc et la boutique**, mais **interdits dans la tour et le blockhaus**.\n📌 Ils doivent rester sous surveillance humaine au pied du phare pendant la visite.")

    # 🔹 Rechercher une info dans general_information
    if not (is_schedule or is_price or is_pet):
        best_match = None
        best_score = 0

        for item in knowledge_base.get("general_information", []):
            key = item.get("key", "").lower()
            value = item.get("value", "")
            score = difflib.SequenceMatcher(None, user_message_translated.lower(), key).ratio()
            if score > best_score:
                best_score = score
                best_match = value

        if best_score > 0.4 and best_match:
            response_parts.append(f"📘 {best_match}")
        else:
            response_parts.append(
                "Ahoy, cher visiteur ! 🌊 Je n’ai pas trouvé l’info exacte, mais vous pouvez consulter les [Infos du phare](https://phareducapferret.com/horaires-et-tarifs/)."
            )

    final_response = " ".join(response_parts)

    prompt = f"""
    You are Archibald, the wise and slightly grumpy lighthouse keeper.
    Respond in the detected language: {lang}.
    Speak warmly but concisely, using maritime metaphors and humor.
    Here is the user's question: \"{user_message_translated}\"
    Use this information: \"{final_response.strip()}\"
    Respond in the detected language: {lang}.
    """

    return prompt

@app.route("/debug_knowledge", methods=["GET"])
def debug_knowledge():
    return jsonify(knowledge_base)

@app.route("/chat", methods=["POST"])
@cross_origin(origins=["https://phareducapferret.com"], supports_credentials=True)
def chat():
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    lang = detect_language(user_message)

    if lang != "fr":
        try:
            translator_to_french = Translator(to_lang="fr")
            user_message_translated = translator_to_french.translate(user_message)
        except Exception as e:
            print(f"Error during translation: {e}")
            return jsonify({"error": "An error occurred while translating the message."}), 500
    else:
        user_message_translated = user_message

    extracted_info = extract_info(user_message_translated)
    prompt = create_prompt(user_message_translated, extracted_info, lang=lang)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are Archibald, the knowledgeable lighthouse keeper."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        chat_response = response["choices"][0]["message"]["content"].strip()
        if lang != "fr":
            translator_to_user_lang = Translator(to_lang=lang)
            chat_response_translated = translator_to_user_lang.translate(chat_response)
            return jsonify({"response": chat_response_translated})
        else:
            return jsonify({"response": chat_response})
    except Exception as e:
        print(f"Error during OpenAI call: {e}")
        return jsonify({"error": "An error occurred while processing your request."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="100.0.0.98", port=5000)
