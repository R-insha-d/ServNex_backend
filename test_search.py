import requests

BASE_URL = "http://127.0.0.1:8000/api/search/"

def test_search():
    print("Testing Global Search API...")
    
    # 1. Test basic keyword search
    try:
        response = requests.get(f"{BASE_URL}?q=pool&type=hotel")
        print(f"Hotel Search Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Results found: {len(data)}")
            for item in data[:2]:
                print(f"- {item.get('name')} in {item.get('city')}")
    except Exception as e:
        print(f"Connection failed: {e}")

    # 2. Test proximity search
    try:
        # Mock coordinates (e.g., somewhere in a city)
        params = {
            'q': '',
            'type': 'all',
            'lat': 12.9716,
            'lng': 77.5946
        }
        res = requests.get(BASE_URL, params=params)
        print(f"\nProximity Search Status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            print(f"Results found: {len(data)}")
            for item in data[:3]:
                dist = item.get('distance')
                dist_str = f"{dist:.2f} km" if dist is not None else "N/A"
                print(f"- {item.get('name')} ({item.get('result_type')}) - Distance: {dist_str}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_search()
