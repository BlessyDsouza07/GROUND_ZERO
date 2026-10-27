# -*- coding: utf-8 -*-
"""
Language packs for the companion voice, safety messages and Ask Engine fallbacks.

Languages: en (English), kn (Kannada), kok (Konkani, Devanagari script), hi (Hindi).

NOTE FOR THE TEAM: the kn / kok / hi strings are careful first drafts and MUST be reviewed by a
native speaker before a public demo. You can fix any string without touching code by dropping a
JSON file at  layer3/data_output/i18n_overrides.json  (or the path in LAYER3_I18N_OVERRIDES) with
the same structure, e.g.  {"kn": {"whisper_prefix": "..."}}  — overrides are merged on load.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

# --------------------------------------------------------------------------- kinds of place
KINDS: Dict[str, Dict[str, tuple]] = {
    # key: {lang: (noun, noun_with_indefinite_article)}
    "church":   {"en": ("church", "a church"), "kn": ("ಚರ್ಚ್",) * 2, "hi": ("गिरजाघर",) * 2, "kok": ("इग्रज",) * 2},
    "temple":   {"en": ("temple", "a temple"), "kn": ("ದೇವಸ್ಥಾನ",) * 2, "hi": ("मंदिर",) * 2, "kok": ("देवूळ",) * 2},
    "mosque":   {"en": ("mosque", "a mosque"), "kn": ("ಮಸೀದಿ",) * 2, "hi": ("मस्जिद",) * 2, "kok": ("मशीद",) * 2},
    "beach":    {"en": ("beach", "a beach"), "kn": ("ಕಡಲತೀರ",) * 2, "hi": ("समुद्र तट",) * 2, "kok": ("दर्यातीर",) * 2},
    "fort":     {"en": ("fort", "a fort"), "kn": ("ಕೋಟೆ",) * 2, "hi": ("किला",) * 2, "kok": ("किल्लो",) * 2},
    "market":   {"en": ("market", "a market"), "kn": ("ಮಾರುಕಟ್ಟೆ",) * 2, "hi": ("बाज़ार",) * 2, "kok": ("बाजार",) * 2},
    "museum":   {"en": ("museum", "a museum"), "kn": ("ವಸ್ತುಸಂಗ್ರಹಾಲಯ",) * 2, "hi": ("संग्रहालय",) * 2, "kok": ("संग्रहालय",) * 2},
    "park":     {"en": ("park", "a park"), "kn": ("ಉದ್ಯಾನ",) * 2, "hi": ("उद्यान",) * 2, "kok": ("बाग",) * 2},
    "eatery":   {"en": ("eatery", "an eatery"), "kn": ("ಊಟದ ತಾಣ",) * 2, "hi": ("खाने की जगह",) * 2, "kok": ("जेवणाची जागा",) * 2},
    "heritage": {"en": ("heritage site", "a heritage site"), "kn": ("ಪಾರಂಪರಿಕ ತಾಣ",) * 2, "hi": ("विरासत स्थल",) * 2, "kok": ("वारसा जागा",) * 2},
    "nature":   {"en": ("nature spot", "a nature spot"), "kn": ("ಪ್ರಕೃತಿ ತಾಣ",) * 2, "hi": ("प्राकृतिक स्थल",) * 2, "kok": ("निसर्ग जागा",) * 2},
    "shrine":   {"en": ("sacred spot", "a sacred spot"), "kn": ("ಪವಿತ್ರ ತಾಣ",) * 2, "hi": ("पवित्र स्थल",) * 2, "kok": ("पवित्र जागा",) * 2},
    "shop":     {"en": ("shop", "a shop"), "kn": ("ಅಂಗಡಿ",) * 2, "hi": ("दुकान",) * 2, "kok": ("दुकान",) * 2},
    "local":    {"en": ("local spot", "a local spot"), "kn": ("ಸ್ಥಳೀಯ ತಾಣ",) * 2, "hi": ("स्थानीय जगह",) * 2, "kok": ("स्थानीक जागा",) * 2},
    "event":    {"en": ("event", "an event"), "kn": ("ಕಾರ್ಯಕ್ರಮ",) * 2, "hi": ("आयोजन",) * 2, "kok": ("कार्यक्रम",) * 2},
    "place":    {"en": ("place", "a place"), "kn": ("ತಾಣ",) * 2, "hi": ("जगह",) * 2, "kok": ("जागा",) * 2},
}

# keyword (in name / subcategory / tags) -> kind key ; first match wins
KIND_KEYWORDS = [
    ("church", "church"), ("cathedral", "church"), ("chapel", "church"), ("basilica", "church"),
    ("temple", "temple"), ("mandir", "temple"), ("devasthana", "temple"), ("shrine", "shrine"),
    ("mosque", "mosque"), ("masjid", "mosque"), ("dargah", "mosque"),
    ("beach", "beach"), ("fort", "fort"), ("battery", "fort"),
    ("market", "market"), ("bazaar", "market"), ("bazar", "market"), ("museum", "museum"),
    ("park", "park"), ("garden", "park"), ("nisargadhama", "park"),
    ("kitchen", "eatery"), ("restaurant", "eatery"), ("cafe", "eatery"), ("café", "eatery"), ("idli", "eatery"),
    ("hotel", "eatery"), ("canteen", "eatery"), ("mess", "eatery"),
]
KIND_BY_CATEGORY = {
    "EXPLORE": "heritage", "NATURE": "nature", "SPIRITUAL": "shrine", "FOOD": "eatery",
    "SHOPPING": "shop", "LOCAL_LIFE": "local", "EVENTS": "event",
}

# --------------------------------------------------------------------------- voice templates
# TEMPLATES[lang][personality][hook]   hooks: age | hidden | generic
# placeholders: {name} {kind} {age} {minutes}    ({kind} already includes the article in English)
TEMPLATES: Dict[str, Dict[str, Dict[str, str]]] = {
    "en": {
        "warm": {
            "age": "{name} is a {age}-year-old {kind_n} right ahead of you — worth about {minutes} minutes.",
            "hidden": "{name} is {kind} most visitors walk straight past — worth about {minutes} minutes.",
            "generic": "{name} is {kind} right ahead — worth about {minutes} minutes.",
        },
        "historian": {
            "age": "{name}, {kind} dating back about {age} years, stands just ahead. Allow around {minutes} minutes.",
            "hidden": "{name} is {kind} that rarely appears in guidebooks. Allow around {minutes} minutes.",
            "generic": "{name}, {kind}, stands just ahead. Allow around {minutes} minutes.",
        },
        "witty": {
            "age": "{age} years old and still standing: {name}, {kind}. Give it about {minutes} minutes.",
            "hidden": "{name}: {kind} the crowds forgot. Give it about {minutes} minutes.",
            "generic": "Look up — {name}, {kind}. Give it about {minutes} minutes.",
        },
    },
    "hi": {
        "warm": {
            "age": "{name} — {age} साल पुराना {kind}, बिल्कुल सामने है। यहाँ लगभग {minutes} मिनट रुकना बनता है।",
            "hidden": "{name} एक ऐसा {kind} है जिसके पास से ज़्यादातर लोग बिना देखे निकल जाते हैं — लगभग {minutes} मिनट ज़रूर दीजिए।",
            "generic": "{name}, एक {kind}, बस सामने है — लगभग {minutes} मिनट रुकना अच्छा रहेगा।",
        },
        "historian": {
            "age": "{name}, लगभग {age} वर्ष पुराना {kind}, आपके ठीक सामने है। यहाँ लगभग {minutes} मिनट का समय रखें।",
            "hidden": "{name} ऐसा {kind} है जो गाइडबुक में कम ही मिलता है। लगभग {minutes} मिनट का समय रखें।",
            "generic": "{name}, एक {kind}, पास ही है। लगभग {minutes} मिनट का समय रखें।",
        },
        "witty": {
            "age": "{age} साल पुराना और आज भी डटा हुआ — {name}, एक {kind}। {minutes} मिनट तो बनते हैं।",
            "hidden": "{name}: भीड़ जिसे भूल गई, ऐसा एक {kind}। {minutes} मिनट दीजिए।",
            "generic": "ऊपर देखिए — {name}, एक {kind}। {minutes} मिनट दीजिए।",
        },
    },
    "kn": {
        "warm": {
            "age": "{name} — {age} ವರ್ಷ ಹಳೆಯ {kind}, ನಿಮ್ಮ ಎದುರಿಗೇ ಇದೆ. ಸುಮಾರು {minutes} ನಿಮಿಷ ಕಳೆಯಲು ಯೋಗ್ಯ.",
            "hidden": "{name} ಒಂದು {kind}; ಹೆಚ್ಚಿನ ಪ್ರವಾಸಿಗರು ಇದನ್ನು ನೋಡದೇ ಮುಂದೆ ಹೋಗುತ್ತಾರೆ — ಸುಮಾರು {minutes} ನಿಮಿಷ ಕೊಡಿ.",
            "generic": "{name}, ಒಂದು {kind}, ಇಲ್ಲೇ ಹತ್ತಿರದಲ್ಲಿದೆ — ಸುಮಾರು {minutes} ನಿಮಿಷ ಕಳೆಯಲು ಚೆನ್ನಾಗಿರುತ್ತದೆ.",
        },
        "historian": {
            "age": "{name}, ಸುಮಾರು {age} ವರ್ಷಗಳ ಹಿಂದಿನ {kind}, ನಿಮ್ಮ ಮುಂದೆಯೇ ಇದೆ. ಸುಮಾರು {minutes} ನಿಮಿಷ ಮೀಸಲಿಡಿ.",
            "hidden": "{name} ಮಾರ್ಗದರ್ಶಿ ಪುಸ್ತಕಗಳಲ್ಲಿ ಅಪರೂಪವಾಗಿ ಕಾಣುವ {kind}. ಸುಮಾರು {minutes} ನಿಮಿಷ ಮೀಸಲಿಡಿ.",
            "generic": "{name}, ಒಂದು {kind}, ಹತ್ತಿರದಲ್ಲೇ ಇದೆ. ಸುಮಾರು {minutes} ನಿಮಿಷ ಮೀಸಲಿಡಿ.",
        },
        "witty": {
            "age": "{age} ವರ್ಷ ಆದರೂ ಇನ್ನೂ ಗಟ್ಟಿಯಾಗಿ ನಿಂತಿದೆ — {name}, ಒಂದು {kind}. {minutes} ನಿಮಿಷ ಕೊಡಿ.",
            "hidden": "{name}: ಜನಸಂದಣಿ ಮರೆತುಹೋದ {kind}. {minutes} ನಿಮಿಷ ಕೊಡಿ.",
            "generic": "ಒಮ್ಮೆ ಮೇಲೆ ನೋಡಿ — {name}, ಒಂದು {kind}. {minutes} ನಿಮಿಷ ಕೊಡಿ.",
        },
    },
    "kok": {
        "warm": {
            "age": "{name} — {age} वर्सां जुनें {kind}, तुमच्या मुखार आसा. सुमार {minutes} मिनिटां दिवपाक योग्य.",
            "hidden": "{name} एक {kind}; चड पर्यटक हांगा पळोवंक नासतना वतात — सुमार {minutes} मिनिटां दियात.",
            "generic": "{name}, एक {kind}, लागीच आसा — सुमार {minutes} मिनिटां घालपाक बरें.",
        },
        "historian": {
            "age": "{name}, सुमार {age} वर्सां आदींचें {kind}, तुमच्या मुखार आसा. सुमार {minutes} मिनिटां दवरात.",
            "hidden": "{name} एक {kind}, जें मार्गदर्शक पुस्तकांनी क्वचित दिसता. सुमार {minutes} मिनिटां दवरात.",
            "generic": "{name}, एक {kind}, लागीच आसा. सुमार {minutes} मिनिटां दवरात.",
        },
        "witty": {
            "age": "{age} वर्सां जाल्लीं तरी उबें — {name}, एक {kind}. {minutes} मिनिटां दियात.",
            "hidden": "{name}: गर्दीक विसरलेलें {kind}. {minutes} मिनिटां दियात.",
            "generic": "वयर पळय — {name}, एक {kind}. {minutes} मिनिटां दियात.",
        },
    },
}

# --------------------------------------------------------------------------- misc strings
STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "whisper_prefix": "Quick note:",
        "not_in_record": "I don't have that in my records for this place.",
        "no_more_detail": "I don't have more stored detail about this place yet.",
        "live_unavailable": "I can't check live conditions right now.",
        "nearest_help": "Nearest help:",
        "swim_no_data": "I can't check live sea conditions right now, so I can't tell you it's safe to swim. Please follow lifeguard flags and local advice.",
        "swim_unsafe": "Sea conditions look rough right now (waves about {wave} m) — I'd stay out of the water.",
        "swim_ok": "Live sea data shows waves of about {wave} m, which is on the calmer side — still follow lifeguard flags and local advice.",
        "swim_weather": "There is severe weather in the area right now — please stay out of the water.",
        "swim_no_wave": "I have a sea reading but no wave height, so I can't judge swimming safety. Please follow lifeguard flags.",
        "safety_weather": "Safety alert: {reason}. Please move to a sheltered indoor spot and stay away from open areas, beaches and trees until it passes.",
        "safety_advisory": "Travel advisory: {reason}. Please follow local authority instructions and reconsider outdoor plans.",
        "safety_sos": "Help request received. If this is an emergency, call 112 now.",
        "reason_thunderstorm": "a thunderstorm is in your area",
        "reason_heavy_rain": "very heavy rain is in your area",
        "reason_high_wind": "dangerously strong winds are in your area",
    },
    "hi": {
        "whisper_prefix": "एक छोटी बात:",
        "not_in_record": "इस जगह के बारे में यह जानकारी मेरे पास नहीं है।",
        "no_more_detail": "इस जगह के बारे में मेरे पास अभी और जानकारी नहीं है।",
        "live_unavailable": "अभी मैं लाइव स्थिति नहीं जाँच सकता।",
        "nearest_help": "नज़दीकी मदद:",
        "swim_no_data": "अभी मैं समुद्र की लाइव स्थिति नहीं जाँच सकता, इसलिए तैरना सुरक्षित है या नहीं यह नहीं बता सकता। कृपया लाइफगार्ड के झंडों और स्थानीय सलाह का पालन करें।",
        "swim_unsafe": "समुद्र अभी अशांत लग रहा है (लहरें लगभग {wave} मीटर) — पानी में न उतरें।",
        "swim_ok": "लाइव डेटा में लहरें लगभग {wave} मीटर हैं, जो अपेक्षाकृत शांत है — फिर भी लाइफगार्ड के झंडों और स्थानीय सलाह का पालन करें।",
        "swim_weather": "इलाके में अभी खराब मौसम है — कृपया पानी से दूर रहें।",
        "swim_no_wave": "मेरे पास समुद्र की जानकारी है पर लहरों की ऊँचाई नहीं, इसलिए तैरने की सुरक्षा नहीं आँक सकता। कृपया लाइफगार्ड के झंडों का पालन करें।",
        "safety_weather": "सुरक्षा चेतावनी: {reason}। कृपया किसी सुरक्षित बंद जगह में चले जाएँ और खुले इलाकों, समुद्र तट और पेड़ों से दूर रहें।",
        "safety_advisory": "यात्रा सलाह: {reason}। कृपया स्थानीय प्रशासन के निर्देशों का पालन करें और बाहर की योजनाओं पर पुनर्विचार करें।",
        "safety_sos": "मदद का अनुरोध मिल गया है। अगर यह आपात स्थिति है तो अभी 112 पर कॉल करें।",
        "reason_thunderstorm": "आपके इलाके में आँधी-तूफ़ान (बिजली) है",
        "reason_heavy_rain": "आपके इलाके में बहुत तेज़ बारिश है",
        "reason_high_wind": "आपके इलाके में बहुत तेज़ हवाएँ चल रही हैं",
    },
    "kn": {
        "whisper_prefix": "ಒಂದು ಸಣ್ಣ ಸೂಚನೆ:",
        "not_in_record": "ಈ ಸ್ಥಳದ ಬಗ್ಗೆ ಆ ಮಾಹಿತಿ ನನ್ನ ಬಳಿ ಇಲ್ಲ.",
        "no_more_detail": "ಈ ಸ್ಥಳದ ಬಗ್ಗೆ ಇನ್ನಷ್ಟು ಮಾಹಿತಿ ನನ್ನ ಬಳಿ ಇನ್ನೂ ಇಲ್ಲ.",
        "live_unavailable": "ಈಗ ನನಗೆ ಲೈವ್ ಪರಿಸ್ಥಿತಿ ಪರಿಶೀಲಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "nearest_help": "ಹತ್ತಿರದ ಸಹಾಯ:",
        "swim_no_data": "ಈಗ ಸಮುದ್ರದ ಲೈವ್ ಸ್ಥಿತಿ ಪರಿಶೀಲಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ, ಆದ್ದರಿಂದ ಈಜುವುದು ಸುರಕ್ಷಿತ ಎಂದು ಹೇಳಲಾರೆ. ದಯವಿಟ್ಟು ಲೈಫ್‌ಗಾರ್ಡ್ ಧ್ವಜಗಳು ಮತ್ತು ಸ್ಥಳೀಯ ಸಲಹೆಯನ್ನು ಪಾಲಿಸಿ.",
        "swim_unsafe": "ಸಮುದ್ರ ಈಗ ಪ್ರಕ್ಷುಬ್ಧವಾಗಿದೆ (ಅಲೆಗಳು ಸುಮಾರು {wave} ಮೀ) — ನೀರಿಗೆ ಇಳಿಯಬೇಡಿ.",
        "swim_ok": "ಲೈವ್ ಮಾಹಿತಿಯ ಪ್ರಕಾರ ಅಲೆಗಳು ಸುಮಾರು {wave} ಮೀ, ತುಲನಾತ್ಮಕವಾಗಿ ಶಾಂತ — ಆದರೂ ಲೈಫ್‌ಗಾರ್ಡ್ ಧ್ವಜಗಳನ್ನು ಪಾಲಿಸಿ.",
        "swim_weather": "ಈ ಪ್ರದೇಶದಲ್ಲಿ ಈಗ ತೀವ್ರ ಹವಾಮಾನವಿದೆ — ದಯವಿಟ್ಟು ನೀರಿನಿಂದ ದೂರವಿರಿ.",
        "swim_no_wave": "ನನ್ನ ಬಳಿ ಸಮುದ್ರದ ಮಾಹಿತಿ ಇದೆ ಆದರೆ ಅಲೆಯ ಎತ್ತರ ಇಲ್ಲ, ಆದ್ದರಿಂದ ಈಜುವ ಸುರಕ್ಷತೆ ಹೇಳಲಾರೆ. ಲೈಫ್‌ಗಾರ್ಡ್ ಧ್ವಜಗಳನ್ನು ಪಾಲಿಸಿ.",
        "safety_weather": "ಸುರಕ್ಷತಾ ಎಚ್ಚರಿಕೆ: {reason}. ದಯವಿಟ್ಟು ಸುರಕ್ಷಿತ ಒಳಾಂಗಣ ಸ್ಥಳಕ್ಕೆ ಹೋಗಿ; ಬಯಲು ಪ್ರದೇಶ, ಕಡಲತೀರ ಮತ್ತು ಮರಗಳಿಂದ ದೂರವಿರಿ.",
        "safety_advisory": "ಪ್ರವಾಸ ಸಲಹೆ: {reason}. ದಯವಿಟ್ಟು ಸ್ಥಳೀಯ ಅಧಿಕಾರಿಗಳ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ ಮತ್ತು ಹೊರಾಂಗಣ ಯೋಜನೆಗಳನ್ನು ಪುನರ್ ಪರಿಶೀಲಿಸಿ.",
        "safety_sos": "ಸಹಾಯದ ವಿನಂತಿ ಸ್ವೀಕರಿಸಲಾಗಿದೆ. ಇದು ತುರ್ತು ಪರಿಸ್ಥಿತಿಯಾಗಿದ್ದರೆ ಈಗಲೇ 112 ಗೆ ಕರೆ ಮಾಡಿ.",
        "reason_thunderstorm": "ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಗುಡುಗು ಸಹಿತ ಮಳೆ ಇದೆ",
        "reason_heavy_rain": "ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಅತಿ ಭಾರೀ ಮಳೆ ಇದೆ",
        "reason_high_wind": "ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಅಪಾಯಕಾರಿ ಬಲವಾದ ಗಾಳಿ ಇದೆ",
    },
    "kok": {
        "whisper_prefix": "एक ल्हान सुचोवणी:",
        "not_in_record": "ह्या जाग्येविशीं ती म्हायती म्हजेकडेन ना.",
        "no_more_detail": "ह्या जाग्येविशीं चड म्हायती म्हजेकडेन अजून ना.",
        "live_unavailable": "आतां म्हाका लाइव्ह परिस्थिती पळोवंक जायना.",
        "nearest_help": "लागीचें मजत:",
        "swim_no_data": "आतां म्हाका दर्याची लाइव्ह परिस्थिती पळोवंक जायना, म्हणून पोंवप सुरक्षित म्हूण सांगूंक जायना. लाइफगार्ड निशाण आनी स्थानीक सल्लो पाळात.",
        "swim_unsafe": "दर्या आतां खवळ्ळो दिसता (लाटो सुमार {wave} मी) — उदकांत उतरूं नाकात.",
        "swim_ok": "लाइव्ह म्हायती प्रमाण लाटो सुमार {wave} मी, तुलनेन शांत — तरी लाइफगार्ड निशाण पाळात.",
        "swim_weather": "ह्या वाठारांत आतां वायट हवामान आसा — उदकापसून पयस रावात.",
        "swim_no_wave": "म्हजेकडेन दर्याची म्हायती आसा पूण लाटांची उंचाय ना, म्हणून पोंवपाची सुरक्षा सांगूंक जायना. लाइफगार्ड निशाण पाळात.",
        "safety_weather": "सुरक्षा शिटकावणी: {reason}. मेहरबानी करून सुरक्षित आंतरगृह जाग्यार वचात आनी उगडे वाठार, दर्यातीर आनी झाडांपसून पयस रावात.",
        "safety_advisory": "प्रवास सल्लो: {reason}. स्थानीक अधिकाऱ्यांच्यो सुचोवण्यो पाळात आनी भायलें येवजण परत तपासात.",
        "safety_sos": "मजतीची विनंती मेळ्ळी. ही आपत्काळाची परिस्थिती जाल्यार आतांच 112 वयर फोन करात.",
        "reason_thunderstorm": "तुमच्या वाठारांत गडगड्याचो पावस आसा",
        "reason_heavy_rain": "तुमच्या वाठारांत जबरदस्त पावस आसा",
        "reason_high_wind": "तुमच्या वाठारांत धोकादायक वारो आसा",
    },
}

# etiquette phrases: normalised English token -> {lang: phrase}
ETIQUETTE: Dict[str, Dict[str, str]] = {
    "remove footwear": {"en": "shoes off at the entrance", "hi": "प्रवेश द्वार पर जूते उतारें", "kn": "ಪ್ರವೇಶದ್ವಾರದಲ್ಲಿ ಚಪ್ಪಲಿ ಬಿಡಿ", "kok": "प्रवेशाक पादत्राणां काड"},
    "cover shoulders": {"en": "shoulders should be covered before entering", "hi": "प्रवेश से पहले कंधे ढकें", "kn": "ಒಳಗೆ ಹೋಗುವ ಮೊದಲು ಹೆಗಲು ಮುಚ್ಚಿಕೊಳ್ಳಿ", "kok": "भितर सरचे पयलीं खांदे धांपात"},
    "no photography": {"en": "no photography inside", "hi": "अंदर फ़ोटो लेना मना है", "kn": "ಒಳಗೆ ಛಾಯಾಚಿತ್ರ ತೆಗೆಯಬಾರದು", "kok": "भितर फोटो काडपाक मनाय"},
    "no leather": {"en": "no leather items inside", "hi": "अंदर चमड़े की वस्तुएँ न ले जाएँ", "kn": "ಒಳಗೆ ಚರ್ಮದ ವಸ್ತುಗಳನ್ನು ಒಯ್ಯಬೇಡಿ", "kok": "भितर चामड्याचीं वस्तू व्हरूं नाकात"},
    "dress modestly": {"en": "please dress modestly", "hi": "कृपया शालीन कपड़े पहनें", "kn": "ದಯವಿಟ್ಟು ಸಭ್ಯ ಉಡುಪು ಧರಿಸಿ", "kok": "मेहरबानी करून सभ्य कापड घालात"},
    "cover head": {"en": "cover your head", "hi": "सिर ढकें", "kn": "ತಲೆ ಮುಚ್ಚಿಕೊಳ್ಳಿ", "kok": "तकली धांपात"},
    "silence": {"en": "please keep quiet inside", "hi": "अंदर शांति बनाए रखें", "kn": "ಒಳಗೆ ಮೌನವಾಗಿರಿ", "kok": "भितर शांत रावात"},
}
ETIQUETTE_ALIASES = {
    "footwear": "remove footwear", "shoes": "remove footwear", "chappal": "remove footwear", "barefoot": "remove footwear",
    "shoulder": "cover shoulders", "sleeveless": "cover shoulders",
    "photography": "no photography", "photo": "no photography", "camera": "no photography",
    "leather": "no leather", "modest": "dress modestly", "dress": "dress modestly",
    "head": "cover head", "quiet": "silence", "silent": "silence",
}


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> None:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def load_overrides(path: Path | None = None) -> None:
    """Merge optional JSON overrides (see module docstring). Safe to call repeatedly."""
    p = Path(path or os.getenv("LAYER3_I18N_OVERRIDES") or (Path(__file__).resolve().parent / "data_output" / "i18n_overrides.json"))
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for section, target in (("strings", STRINGS), ("templates", TEMPLATES), ("etiquette", ETIQUETTE)):
        if isinstance(data.get(section), dict):
            _merge(target, data[section])
    # convenience: top-level {"kn": {...}} merges into STRINGS
    for lang in ("en", "kn", "kok", "hi"):
        if isinstance(data.get(lang), dict):
            _merge(STRINGS.setdefault(lang, {}), data[lang])


def t(lang: str, key: str, **kw: Any) -> str:
    pack = STRINGS.get(lang) or STRINGS["en"]
    s = pack.get(key) or STRINGS["en"].get(key, key)
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError):
        return s


load_overrides()
