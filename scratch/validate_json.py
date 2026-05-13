import json

try:
    with open('src/backend/api/data/seera_general_QAs/islamqa_multilingual_en.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print("JSON is valid!")
except json.JSONDecodeError as e:
    print(f"Error: {e}")
    with open('src/backend/api/data/seera_general_QAs/islamqa_multilingual_en.json', 'r', encoding='utf-8') as f:
        content = f.read()
        start = max(0, e.pos - 50)
        end = min(len(content), e.pos + 50)
        print(f"Context: {repr(content[start:end])}")
