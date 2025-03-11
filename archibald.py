import os
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify, session
from flask_cors import CORS, cross_origin
from langdetect import detect, DetectorFactory

# Configuration de la détection de langue pour des résultats stables
DetectorFactory.seed = 0  

# Charger les variables d'environnement
load_dotenv()
secret_key = os.getenv('SECRET_KEY')

# Flask setup
app = Flask(__name__)
CORS(app, origins=["https://phareducapferret.com"], supports_credentials=True)
app.secret_key = "archi33950baldBOT"

# Charger et prétraiter la base de connaissances JSON
with open('archibald_knowledge.json', 'r', encoding='utf-8') as file:
    knowledge_base = json.load(file)

# Dictionnaire des mois en français pour la gestion des dates
MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
}

def detect_language(user_message):
    """
    Détecte la langue du message utilisateur de manière fiable.
    """
    try:
        lang = detect(user_message)
        return lang if lang in ["fr", "en", "es", "de", "it"] else "fr"
    except:
        return "fr"  # Fallback en français

def parse_relative_date(user_message):
    """
    Détecte et convertit les expressions de date en format YYYY-MM-DD.
    """
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
            return parsed_date if parsed_date >= today.date() else datetime(year + 1, MONTHS_FR[month_name], day).date()

    return None

def extract_info(user_message):
    """
    Analyse le message et détecte :
    - Une demande sur les horaires.
    - Une demande de prix.
    - Une question sur les animaux.
    """
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

def create_prompt(user_message_translated, extracted_info, lang):
    """
    Génère une réponse basée sur `knowledge_base` et l'analyse du message utilisateur.
    """
    is_schedule = extracted_info.get("is_schedule", False)
    is_price = extracted_info.get("is_price", False)
    is_pet = extracted_info.get("is_pet", False)

    response_parts = []

    if is_schedule:
        response_parts.append(
            f"📌 Les horaires du phare peuvent varier. Consultez-les ici : "
            f"[🕒 Voir les horaires et tarifs]({knowledge_base['schedule']['url']})."
        )

    if is_price:
        response_parts.append(
            f"🎟️ Le tarif d’entrée est de **{knowledge_base['pricing']['adult']}€ pour les adultes** et "
            f"**{knowledge_base['pricing']['child']}€ pour les enfants**.\n"
            f"📌 Consultez tous les détails ici : [🕒 Voir les horaires et tarifs]({knowledge_base['pricing']['url']})."
        )

    if is_pet:
        response_parts.append(
            f"🐾 {knowledge_base['general_information']['pet_policy']} "
            f"📌 Pour plus d’informations : [Règles du phare]({knowledge_base['general_information']['url']})."
        )

    if not (is_schedule or is_price or is_pet):
        response_parts.append(
            f"Ahoy, cher visiteur ! 🌊 Consultez les horaires et tarifs ici : "
            f"[Infos du phare]({knowledge_base['general_information']['url']})."
        )

    return " ".join(response_parts)

@app.route("/chat", methods=["POST"])
@cross_origin(origins=["https://phareducapferret.com"], supports_credentials=True)
def chat():
    """
    Point d'entrée API pour répondre aux questions des utilisateurs.
    """
    user_message = request.json.get("message")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    lang = detect_language(user_message)
    user_message_translated = user_message  # Ici, on suppose que tout est en français

    extracted_info = extract_info(user_message_translated)

    response = create_prompt(user_message_translated, extracted_info, lang)

    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(debug=True, host="100.0.0.98", port=5000)
