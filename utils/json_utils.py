import json
import re
from typing import Optional, List, Any

def repair_and_parse_json(text: str) -> Optional[Any]:
    """
    強大的 JSON 提取器：支援多塊提取、Markdown 優先、自動合體與結構修復。
    """
    if not text:
        return None

    # 1. 移除 <think> 思考區塊
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # 2. 優先尋找 Markdown 代碼塊 ```json ... ```
    code_blocks = re.findall(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    clean_text = "".join(code_blocks) if code_blocks else text

    # 3. 提取所有頂層對象 (平衡大括號算法)
    blocks = []
    depth = 0
    start = -1
    for i, char in enumerate(clean_text):
        if char == '{':
            if depth == 0: start = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and start != -1:
                blocks.append(clean_text[start:i+1])
    
    # 如果沒找到 {} 但有 []
    if not blocks:
        match = re.search(r'(\[.*\])', clean_text, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: pass

    # 4. 解析與合體
    parsed_results = []
    for b in blocks:
        try:
            # 修復常見 JSON 錯誤
            b = re.sub(r',\s*\}', '}', b)
            b = re.sub(r',\s*\]', ']', b)
            parsed_results.append(json.loads(b))
        except:
            continue

    if not parsed_results:
        return None

    # 5. 根據結果類型回傳
    if len(parsed_results) == 1:
        return parsed_results[0]
    else:
        if all(isinstance(r, dict) for r in parsed_results):
            # 檢查是否有重複的 key (例如都有 'name')，如果有，代表應該是 List
            keys_overlap = False
            seen_keys = set()
            for r in parsed_results:
                if any(k in seen_keys for k in r.keys()):
                    keys_overlap = True
                    break
                seen_keys.update(r.keys())
                
            if keys_overlap:
                return parsed_results
            else:
                merged = {}
                for r in parsed_results: merged.update(r)
                return merged
        else:
            return parsed_results
