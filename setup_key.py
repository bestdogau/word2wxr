"""Save OpenRouter API key to config.json."""
import json, sys, os

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

def has_valid_key():
    try:
        with open(config_path, 'r') as f:
            c = json.load(f)
        key = c.get('api_key', '')
        return bool(key and 'YOUR_' not in key and len(key) > 10)
    except Exception:
        return False

def save_key(key):
    config = {"api_key": key.strip(), "model": "deepseek/deepseek-v3.2"}
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)
    print("  API key saved to config.json")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--check':
        sys.exit(0 if has_valid_key() else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == '--save':
        key = input("  Paste your OpenRouter API key: ").strip()
        if key:
            save_key(key)
        else:
            print("  ERROR: No key entered.")
            sys.exit(1)
