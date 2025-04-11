import os
import json
import re
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

json_path = os.path.join(os.path.dirname(__file__), 'archibald_knowledge.json')
with open(json_path, 'r', encoding='utf-8') as file:
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
        return lang if lang in ["fr", "en", "es", "de", "it","pt","nl"] else "en"
    except Exception as e:
        print(f"Erreur de détection de langue: {e}")
        return "en"

def extract_info(user_message):
    try:
        user_message = user_message.lower()
        is_schedule = any(word in user_message for word in ["horaire", "ouvert", "fermé", "heures", "temps", "jours","Zeitplan", "geöffnet", "geschlossen", "Stunden", "Zeit", "Tage","schedule", "open", "closed", "hours", "time", "days","horario", "abierto", "cerrado", "horas", "tiempo", "días","horário", "aberto", "fechado", "horas", "tempo", "dias",
"schema", "open", "gesloten", "uren", "tijd", "dagen"])
        is_price = any(word in user_message for word in ["tarif", "prix", "combien", "coût", "entrée","tarief", "prijs", "hoeveel", "kosten", "toegang","Fahrpreis", "Preis", "Wie viel", "Kosten", "Eintritt","tarifa", "precio", "cuánto", "costo", "entrada","tarifa", "preço", "quanto", "custo", "entrada",
"fare", "price", "how much", "cost", "entrance"])
        is_pet = any(word in user_message for word in ["chien", "chat", "oiseau", "animaux", "animal", "perroquet", "hamster", "lapin", "dog", "cat", "bird", "animals", "parrot", "rabbit", "Hund", "Katze", "Vogel", "Tiere", "Tier", "Papagei", "Kaninchen","perro", "gato", "pájaro", "animales", "loro", "hámster", "conejo","cachorro", "gato", "pássaro", "animais", "papagaio", "hamster", "coelho", "hond", "kat", "vogel", "dieren", "dier", "papegaai", "konijn"])
        is_parking = any(word in user_message for word in ["parking", "garer", "stationnement", "se garer", "place de parking", "poser la voiture", "stationner","parkeerplaats", "parkeer de auto", "parkeren","Parkplatz", "Auto parken", "Park","Parken","aparcamiento", "estacionamiento", "estacionar", "plaza de aparcamiento", "estacionar el coche", "estacionar","parking space", "park the car", "park"])
        date = parse_relative_date(user_message) if is_schedule else None
        return {
            "date": date.isoformat() if date else None,
            "is_schedule": is_schedule,
            "is_price": is_price,
            "is_pet": is_pet,
            "is_parking": is_parking
        }
    except Exception as e:
        print(f"Erreur lors de l'extraction des informations: {e}")
        return {}

def create_prompt(user_message_translated, extracted_info, lang):
    is_schedule = extracted_info.get("is_schedule", False)
    is_price = extracted_info.get("is_price", False)
    is_pet = extracted_info.get("is_pet", False)
    is_parking = extracted_info.get("is_parking", False)

    response_parts = []

    if is_schedule:
        response_parts.append("📌 Les horaires du phare peuvent varier selon la saison. Consultez-les ici : [🕒 Voir les horaires et tarifs](https://phareducapferret.com/horaires-et-tarifs/).")
    if is_price:
        response_parts.append("🎟️ Le tarif d’entrée est de **7€ pour les adultes** et **4€ pour les enfants**.\n📌 Consultez tous les détails ici : [🕒 Voir les horaires et tarifs](https://phareducapferret.com/horaires-et-tarifs/).")
    if is_pet:
        response_parts.append("🐾 **Les animaux de compagnie sont autorisés dans le parc et la boutique**, mais **interdits dans la tour et le blockhaus**.\n📌 Ils doivent rester sous surveillance humaine au pied du phare pendant la visite.")
    if is_parking:
        response_parts.append(
            "🅿️ Il n’y a pas de grand parking au pied du phare. "
            "Quelques places sont disponibles à proximité, mais elles sont souvent prises rapidement.\n"
            "📌 Le stationnement est gratuit dans le Cap Ferret, sur le bas-côté, tant que vous ne gênez pas la circulation."
         )
    # Recherche d'une réponse dans la base de connaissances
    search_results = []
    for item in knowledge_base["faq"] + knowledge_base["questions_and_responses"]:
        if user_message_translated.lower() in item["question"].lower():
            search_results.append(item["answer"] if "answer" in item else item["response"])

    if search_results:
        response_parts.append(search_results[0])
    else:
        response_parts.append(
            "Ahoy, cher visiteur ! 🌊 Je n’ai pas trouvé l’info exacte, mais vous pouvez consulter les "
            "[Infos du phare](https://phareducapferret.com/horaires-et-tarifs/)."
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
    print("📨 Requête POST reçue sur /chat")  # Ajout du log

    user_message = request.json.get("message")
    if not user_message:
        print("⚠️ Aucun message trouvé dans la requête.")
        return jsonify({"error": "No message provided"}), 400

    print(f"📩 Message utilisateur : {user_message}")  # Log du contenu du message

    lang = detect_language(user_message)
    print(f"🌍 Langue détectée : {lang}")

    if lang != "fr":
        try:
            translator_to_french = Translator(to_lang="fr")
            user_message_translated = translator_to_french.translate(user_message)
        except Exception as e:
            print(f"❌ Erreur de traduction : {e}")
            return jsonify({"error": "An error occurred while translating the message."}), 500
    else:
        user_message_translated = user_message

    extracted_info = extract_info(user_message_translated)
    print(f"🧠 Infos extraites : {extracted_info}")

    prompt = create_prompt(user_message_translated, extracted_info, lang=lang)
    print("🛠️ Prompt généré, appel à OpenAI...")

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
        print(f"✅ Réponse générée : {chat_response[:100]}...")  # Log partiel pour éviter un énorme bloc

        if lang != "fr":
            translator_to_user_lang = Translator(to_lang=lang)
            chat_response_translated = translator_to_user_lang.translate(chat_response)
            return jsonify({"response": chat_response_translated})
        else:
            return jsonify({"response": chat_response})
    except Exception as e:
        print(f"❌ Erreur lors de l’appel à OpenAI : {e}")
        return jsonify({"error": "An error occurred while processing your request."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="100.0.0.98", port=5000)
