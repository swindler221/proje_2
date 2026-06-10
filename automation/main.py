import sys
import requests
import time
import hashlib
import urllib3
from PIL import Image
from deep_translator import GoogleTranslator

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import config
except ImportError:
    print("Error: config.py file not found in the automation directory.")
    sys.exit(1)

def check_config():
    if not config.STRAPI_API_TOKEN:
        print("=" * 80)
        print("ERROR: STRAPI_API_TOKEN is empty in automation/config.py!")
        print("Please follow these steps to proceed:")
        print("1. Start your Strapi backend (npm run develop)")
        print("2. Open the Admin Panel at http://localhost:1337/admin")
        print("3. Navigate to Settings -> API Tokens -> Create new token")
        print("4. Set Token Name, Token Type to 'Full Access' (or Custom with upload/create rights), and Save")
        print("5. Copy the generated token and paste it into automation/config.py")
        print("=" * 80)
        sys.exit(1)

def get_existing_city(city_name, api_url, token):
    url = f"{api_url}/api/cities"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"filters[name][$eq]": city_name, "locale": "tr", "populate": "localizations"}
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data:
                tr_city_id = data[0]['id']
                en_city_id = None
                localizations = data[0]['attributes'].get('localizations', {}).get('data', [])
                for loc in localizations:
                    if loc['attributes']['locale'] == 'en':
                        en_city_id = loc['id']
                        break
                return tr_city_id, en_city_id
    except Exception as e:
        print(f"Error checking existing city: {e}")
    return None, None

def get_existing_place(place_name, api_url, token):
    url = f"{api_url}/api/places"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"filters[name][$eq]": place_name, "locale": "tr", "populate": "localizations"}
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data:
                tr_place_id = data[0]['id']
                en_place_id = None
                localizations = data[0]['attributes'].get('localizations', {}).get('data', [])
                for loc in localizations:
                    if loc['attributes']['locale'] == 'en':
                        en_place_id = loc['id']
                        break
                return tr_place_id, en_place_id
    except Exception as e:
        print(f"Error checking existing place: {e}")
    return None, None

PROMPT_MAP = {
    'Ayasofya Camii': 'Hagia Sophia exterior, historical mosque building, architectural photography',
    'Galata Kulesi': 'Galata Tower Istanbul, medieval stone tower, city landscape',
    'Peri Bacaları': 'Cappadocia fairy chimneys, natural rock formations, turkey landscape',
    'Efes Antik Kenti': 'Ephesus ancient city ruins, historical marble columns'
}

def get_place_image(place_name, api_url, token):
    time.sleep(3.5)
    print(f"AI görseli oluşturuluyor: {place_name}")
    place_name_slug = place_name.replace(' ', '_').lower()
    
    img_bytes = None
    try:
        prompt_details = PROMPT_MAP.get(place_name)
        prompt = f"{place_name}, {prompt_details}" if prompt_details else f"{place_name}, historical landmark in Turkey"
        
        response = requests.post(
            "https://aihorde.net/api/v2/generate/async",
            headers={"apikey": "0000000000", "Content-Type": "application/json"},
            json={
                "prompt": prompt + ", highly detailed realistic 8k photograph",
                "params": {"n": 1, "steps": 20},
                "models": ["ICBINP - I Can't Believe It's Not Photography"]
            },
            verify=False,
            timeout=20
        )
        job_id = response.json().get('id')
        if not job_id:
            raise Exception("No job ID received from Horde.")
            
        image_url = None
        for _ in range(20):
            time.sleep(5)
            status_resp = requests.get(f"https://aihorde.net/api/v2/generate/status/{job_id}", verify=False, timeout=15)
            if status_resp.status_code == 200 and status_resp.json().get('done'):
                image_url = status_resp.json().get('generations', [{}])[0].get('img')
                break
                
        if not image_url:
            raise Exception("AI Horde generation timed out or failed.")
            
        img_bytes = requests.get(image_url, verify=False, timeout=20).content
    except Exception as e:
        print(f"   AI Horde request failed: {e}. Falling back to Picsum Photos...")
        try:
            seed = hashlib.sha256(place_name.encode('utf-8')).hexdigest()
            picsum_resp = requests.get(f"https://picsum.photos/seed/{seed}/800/600", verify=False, timeout=20)
            if picsum_resp.status_code == 200:
                img_bytes = picsum_resp.content
        except Exception as picsum_err:
            print(f"   Picsum fallback failed: {picsum_err}")

    if not img_bytes:
        return None

    try:
        import io
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)
        
        upload_resp = requests.post(
            f"{api_url}/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={'files': (f'{place_name_slug}.jpg', img_io, 'image/jpeg')},
            verify=False,
            timeout=30
        )
        if upload_resp.status_code == 200:
            media_id = upload_resp.json()[0]['id']
            print(f"   Upload successful. Media ID: {media_id}")
            return media_id
        else:
            print(f"   Upload failed (HTTP {upload_resp.status_code}): {upload_resp.text}")
    except Exception as upload_err:
        print(f"   Upload error: {upload_err}")
    return None

def create_or_update_city(city, tr_city_id, en_city_id, api_url, token, translator):
    name_tr = city['name']
    country_tr = city['country']
    desc_tr = city['description']
    
    print(f"-> Translating city '{name_tr}' to English...")
    try:
        name_en = translator.translate(name_tr)
        country_en = translator.translate(country_tr)
        desc_en = translator.translate(desc_tr)
    except Exception as e:
        print(f"   Translation error: {e}. Falling back to TR values.")
        name_en, country_en, desc_en = name_tr, country_tr, desc_tr

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    tr_payload = {
        "data": {
            "name": name_tr,
            "country": country_tr,
            "description": desc_tr,
            "locale": "tr"
        }
    }
    
    if tr_city_id:
        print(f"-> Updating City (TR): '{name_tr}' (ID: {tr_city_id})...")
        try:
            response = requests.put(f"{api_url}/api/cities/{tr_city_id}", headers=headers, json=tr_payload)
            if response.status_code not in [200, 201]:
                print(f"   Failed to update TR city: {response.text}")
        except Exception as e:
            print(f"   Exception updating TR city: {e}")
    else:
        print(f"-> Creating City (TR): '{name_tr}'...")
        try:
            response = requests.post(f"{api_url}/api/cities", headers=headers, json=tr_payload)
            if response.status_code in [200, 201]:
                tr_city_id = response.json()['data']['id']
            else:
                print(f"   Failed to create TR city: {response.text}")
        except Exception as e:
            print(f"   Exception creating TR city: {e}")
            
    if tr_city_id:
        if en_city_id:
            print(f"-> Updating City Localization (EN): '{name_en}' (ID: {en_city_id})...")
            en_payload = {
                "data": {
                    "name": name_en,
                    "country": country_en,
                    "description": desc_en
                }
            }
            try:
                response = requests.put(f"{api_url}/api/cities/{en_city_id}", headers=headers, json=en_payload)
                if response.status_code not in [200, 201]:
                    print(f"   Failed to update EN city localization: {response.text}")
            except Exception as e:
                print(f"   Exception updating EN city localization: {e}")
        else:
            print(f"-> Creating City Localization (EN): '{name_en}'...")
            en_payload = {
                "locale": "en",
                "name": name_en,
                "country": country_en,
                "description": desc_en
            }
            try:
                loc_url = f"{api_url}/api/cities/{tr_city_id}/localizations"
                loc_response = requests.post(loc_url, headers=headers, json=en_payload)
                if loc_response.status_code in [200, 201]:
                    loc_data = loc_response.json()
                    en_city_id = loc_data['data']['id'] if 'data' in loc_data else loc_data.get('id')
                else:
                    print(f"   Failed to create EN city localization: {loc_response.text}")
            except Exception as e:
                print(f"   Exception creating EN city localization: {e}")
                
    return tr_city_id, en_city_id

def create_or_update_place(place, tr_place_id, en_place_id, tr_city_id, en_city_id, api_url, token, translator):
    name_tr = place['name']
    desc_tr = place['description']
    rating = place['rating']
    
    print(f"-> Translating place '{name_tr}' to English...")
    try:
        name_en = translator.translate(name_tr)
        desc_en = translator.translate(desc_tr)
    except Exception as e:
        print(f"   Translation error: {e}. Falling back to TR values.")
        name_en, desc_en = name_tr, desc_tr

    media_id = get_place_image(name_tr, api_url, token)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    tr_payload = {
        "data": {
            "name": name_tr,
            "description": desc_tr,
            "rating": rating,
            "city": tr_city_id,
            "locale": "tr"
        }
    }
    if media_id:
        tr_payload["data"]["image"] = media_id
        
    if tr_place_id:
        print(f"-> Updating Place (TR): '{name_tr}' (ID: {tr_place_id})...")
        try:
            response = requests.put(f"{api_url}/api/places/{tr_place_id}", headers=headers, json=tr_payload)
            if response.status_code not in [200, 201]:
                print(f"   Failed to update TR place: {response.text}")
        except Exception as e:
            print(f"   Exception updating TR place: {e}")
    else:
        print(f"-> Creating Place (TR): '{name_tr}'...")
        try:
            response = requests.post(f"{api_url}/api/places", headers=headers, json=tr_payload)
            if response.status_code in [200, 201]:
                tr_place_id = response.json()['data']['id']
            else:
                print(f"   Failed to create TR place: {response.text}")
        except Exception as e:
            print(f"   Exception creating TR place: {e}")
            
    if tr_place_id:
        if en_place_id:
            print(f"-> Updating Place Localization (EN): '{name_en}' (ID: {en_place_id})...")
            en_payload = {
                "data": {
                    "name": name_en,
                    "description": desc_en,
                    "rating": rating,
                    "city": en_city_id
                }
            }
            if media_id:
                en_payload["data"]["image"] = media_id
                
            try:
                response = requests.put(f"{api_url}/api/places/{en_place_id}", headers=headers, json=en_payload)
                if response.status_code not in [200, 201]:
                    print(f"   Failed to update EN place localization: {response.text}")
            except Exception as e:
                print(f"   Exception updating EN place localization: {e}")
        else:
            print(f"-> Creating Place Localization (EN): '{name_en}'...")
            en_payload = {
                "locale": "en",
                "name": name_en,
                "description": desc_en,
                "rating": rating,
                "city": en_city_id
            }
            if media_id:
                en_payload["image"] = media_id
                
            try:
                loc_url = f"{api_url}/api/places/{tr_place_id}/localizations"
                loc_response = requests.post(loc_url, headers=headers, json=en_payload)
                if loc_response.status_code in [200, 201]:
                    print(f"   Successfully created Place '{name_tr}' in TR and EN.")
                    return True
                else:
                    print(f"   Failed to create EN place localization: {loc_response.text}")
            except Exception as e:
                print(f"   Exception creating EN place localization: {e}")
                
    return tr_place_id is not None

def main():
    check_config()
    
    mock_data = [
        {
            "name": "İstanbul",
            "country": "Türkiye",
            "description": "Tarihin ve modernitenin buluştuğu, iki kıtayı birleştiren büyüleyici metropol.",
            "places": [
                {
                    "name": "Ayasofya Camii",
                    "description": "Tarihi yarımadada yer alan, mimarlık tarihinin en önemli eserlerinden biri olan görkemli yapı.",
                    "rating": 9.8
                },
                {
                    "name": "Galata Kulesi",
                    "description": "İstanbul'un panoramik manzarasını sunan, Cenevizliler döneminden kalma tarihi kule.",
                    "rating": 9.3
                }
            ]
        },
        {
            "name": "Kapadokya",
            "country": "Türkiye",
            "description": "Eşsiz kaya oluşumları, yer altı şehirleri ve sıcak hava balonlarıyla masalsı bölge.",
            "places": [
                {
                    "name": "Göreme Açık Hava Müzesi",
                    "description": "Kaya içine oyulmuş kiliseleri, manastırları ve eşsiz freskleriyle ünlü tarihi açık hava müzesi.",
                    "rating": 9.5
                },
                {
                    "name": "Peri Bacaları",
                    "description": "Doğa olayları sonucu oluşmuş, Kapadokya'nın simgesi olan benzersiz kaya oluşumları.",
                    "rating": 9.6
                }
            ]
        },
        {
            "name": "İzmir",
            "country": "Türkiye",
            "description": "Ege'nin incisi, tarihi liman kenti ve canlı kültürüyle bilinen modern sahil şehri.",
            "places": [
                {
                    "name": "Efes Antik Kenti",
                    "description": "Antik dünyanın en önemli metropollerinden biri olan, Celsus Kütüphanesi ve antik tiyatrosuyla ünlü ören yeri.",
                    "rating": 9.7
                },
                {
                    "name": "Saat Kulesi",
                    "description": "İzmir Konak Meydanı'nda yer alan, 1901 yapımı şehrin simgesi olan tarihi saat kulesi.",
                    "rating": 9.0
                }
            ]
        }
    ]
    
    translator = GoogleTranslator(source='tr', target='en')
    api_url = config.STRAPI_API_URL.rstrip('/')
    token = config.STRAPI_API_TOKEN
    
    print("Starting Automation Pipeline...")
    print(f"Connecting to Strapi API at {api_url}")
    
    for city_data in mock_data:
        city_name = city_data['name']
        print("\n" + "=" * 50)
        print(f"Processing City: {city_name}")
        print("=" * 50)
        
        tr_city_id, en_city_id = get_existing_city(city_name, api_url, token)
        
        try:
            tr_city_id, en_city_id = create_or_update_city(city_data, tr_city_id, en_city_id, api_url, token, translator)
        except Exception as e:
            print(f"Error creating/updating city '{city_name}': {e}")
            continue
            
        if not tr_city_id or not en_city_id:
            print(f"Skipping places for '{city_name}' due to city setup failure.")
            continue
        
        for place_data in city_data['places']:
            place_name = place_data['name']
            
            tr_place_id, en_place_id = get_existing_place(place_name, api_url, token)
            
            try:
                create_or_update_place(place_data, tr_place_id, en_place_id, tr_city_id, en_city_id, api_url, token, translator)
            except Exception as e:
                print(f"Error processing place '{place_name}': {e}")
                
    print("\nAutomation Pipeline Completed successfully!")

if __name__ == "__main__":
    main()
