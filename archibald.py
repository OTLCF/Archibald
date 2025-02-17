import os,json,re
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
openai.api_key = os.getenv('SECRET_KEY')

# Flask setup
app = Flask(__name__)
CORS(app, origins=["https://phareducapferret.com"], supports_credentials=True)
app.secret_key = "archi33950baldBOT"

def preprocess_knowledge(raw_knowledge):
    knowledge = {"questions_and_responses": [], "general_information": [], "schedule": [], "pricing": {}, "faq": []}
    for section, items in raw_knowledge.items():
        if section == "schedule":
            knowledge["schedule"] = [item for item in items if isinstance(item, dict)]
        elif section == "pricing":
            if isinstance(items, dict): knowledge["pricing"] = items
        elif section == "general_information":
            knowledge["general_information"] = [item for item in items if isinstance(item, dict) and "key" in item and "value" in item]
        elif section == "faq":
            knowledge["faq"] = [{"question": item["question"], "answer": item.get("answer", item.get("response", ""))} for item in items if isinstance(item, dict) and "question" in item and ("answer" in item or "response" in item)]
        elif section == "questions_and_responses":
            knowledge["questions_and_responses"] = [{"question": item["question"], "response": item["response"]} for item in items if isinstance(item, dict) and "question" in item and "response" in item]
    return knowledge

with open('archibald_knowledge.json', 'r', encoding='utf-8') as file:
    knowledge_base = preprocess_knowledge(json.load(file))

MONTHS_FR = {"janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12}

def parse_date_localized(date_string):
    try:
        match = re.search(r"(\d{1,2})\s(\w+)\s(\d{4})", date_string.strip(), re.IGNORECASE)
        if match:
            day, month, year = int(match.group(1)), MONTHS_FR.get(match.group(2).lower()), int(match.group(3))
            return datetime(year, month, day).date() if month else None
        return parse(date_string, fuzzy=True).date()
    except: return None

def parse_relative_date(user_message):
    today = datetime.today()
    user_message = user_message.lower().strip()
    if "aujourd'hui" in user_message or "aujourdhui" in user_message: return today.date()
    if "demain" in user_message: return (today + timedelta(days=1)).date()
    if "après-demain" in user_message: return (today + timedelta(days=2)).date()
    match_relative = re.search(r"dans (\d+) jours?", user_message)
    if match_relative: return (today + timedelta(days=int(match_relative.group(1)))).date()
    match_explicit = re.search(r"le (\d{1,2}) (\w+)", user_message)
    if match_explicit:
        day, month_name = int(match_explicit.group(1)), match_explicit.group(2)
        if month_name in MONTHS_FR:
            parsed_date = datetime(today.year, MONTHS_FR[month_name], day).date()
            return parsed_date if parsed_date >= today.date() else datetime(today.year + 1, MONTHS_FR[month_name], day).date()
    return None

def detect_language(user_message):
    try:
        return "en" if any(month in user_message.lower() for month in ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]) else detect(user_message)
    except: return "en"

def extract_info(user_message):
    is_schedule, is_price = "horaire" in user_message or "ouvert" in user_message, "tarif" in user_message or "prix" in user_message
    date = parse_relative_date(user_message) if is_schedule else None
    adults = int(re.search(r"(\d+)\sadultes?", user_message).group(1)) if is_price and re.search(r"(\d+)\sadultes?", user_message) else 0
    children = [int(match[0]) for match in re.findall(r"(\d+)\s(enfants?|ans)", user_message)] if is_price else []
    return {"date": date.isoformat() if date else None, "adults": adults, "children": children, "is_schedule": is_schedule, "is_price": is_price}

def get_opening_status(date, schedule):
    if not date: return "Date non spécifiée. Veuillez indiquer une date."
    date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    for period in schedule:
        if period.get("type") == "exceptional":
            for exception in period.get("exceptional_opening", []):
                if datetime.strptime(exception["date"], "%Y-%m-%d").date() == date_obj:
                    return f"Ouverture exceptionnelle le {date} : {exception['hours']} (dernière montée à {exception['last_entry']})."
    for period in schedule:
        if period.get("type") == "regular":
            start_date, end_date = datetime.strptime(period["start_date"], "%Y-%m-%d").date(), datetime.strptime(period["end_date"], "%Y-%m-%d").date()
            if start_date <= date_obj <= end_date and datetime.strftime(date_obj, "%A").lower() in period.get("days_open", []):
                return f"Ouvert le {date} : {period['hours']} (dernière montée à {period['last_entry']})."
    return f"Fermé le {date}."

def calculate_pricing(adults, children):
    adult_price, child_price, free_below_age, adult_age_threshold = 7, 4, 5, 13
    if adults == 0 and children: adults = 1
    total_price = adults * adult_price
    child_details = [f"{c} ans ({child_price}€)" if free_below_age <= c < adult_age_threshold else f"{c} ans ({adult_price}€ - tarif adulte)" for c in children]
    total_price += sum(adult_price if c >= adult_age_threshold else child_price for c in children)
    return total_price, f"🎟️ Tarifs : {adult_price}€ adulte, {child_price}€ enfant. Estimation: {total_price}€ ({', '.join(child_details)})"

@app.route("/chat", methods=["POST"])
@cross_origin(origins=["https://phareducapferret.com"], supports_credentials=True)
def chat():
    user_message = request.json.get("message")
    if not user_message: return jsonify({"error": "No message provided"}), 400
    lang = detect_language(user_message)
    user_message_translated = Translator(to_lang="fr").translate(user_message) if lang != "fr" else user_message
    extracted_info = extract_info(user_message_translated)
    total_price, pricing_response = calculate_pricing(extracted_info["adults"], extracted_info["children"]) if extracted_info["is_price"] else (None, "")
    prompt = f"Tu es Archibald, gardien du phare. Langue: {lang}. Question: '{user_message_translated}'. Réponds de manière chaleureuse et humoristique. {pricing_response}"
    try:
        response = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=300, temperature=0.7)
        return jsonify({"response": response["choices"][0]["message"]["content"].strip()})
    except: return jsonify({"error": "An error occurred"}), 500

if __name__ == "__main__":
    app.run(debug=True, host="100.0.0.98", port=5000)
