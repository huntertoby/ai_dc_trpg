# db/storage.py
import os
import json
from typing import Optional, List
from core.models import CharacterSchema

class CharacterRepository:
    # 使用絕對路徑確保在不同環境下都能正確讀取
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DB_ROOT = os.path.join(PROJECT_ROOT, "characters_db")

    @classmethod
    def _get_user_folder(cls, user_id: str) -> str:
        folder = os.path.join(cls.DB_ROOT, user_id)
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        return folder

    @classmethod
    def save(cls, data: CharacterSchema, user_id: str):
        """存檔：儲存在使用者資料夾下"""
        folder = cls._get_user_folder(user_id)
        file_path = os.path.join(folder, f"{data.name}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data.model_dump_json(indent=4))
        # 預設將新儲存的角色設為當前活躍角色
        cls.set_active_character(user_id, data.name)

    @classmethod
    def load_active(cls, user_id: str) -> Optional[CharacterSchema]:
        """讀取該使用者目前「活躍」的角色"""
        active_name = cls.get_active_character_name(user_id)
        
        # 防呆：如果活躍名稱是 settings 或為空，重新找一個有效的
        if not active_name or active_name == "settings":
            chars = cls.list_characters(user_id)
            if chars:
                # 確保不選到 settings
                valid_chars = [c for c in chars if c != "settings"]
                if valid_chars:
                    cls.set_active_character(user_id, valid_chars[0])
                    return cls.load_by_name(user_id, valid_chars[0])
            return None
            
        char = cls.load_by_name(user_id, active_name)
        # 如果讀取失敗（例如檔案損壞），也嘗試切換到其他角色
        if not char:
            settings = cls.get_user_settings(user_id)
            if "active_character" in settings:
                del settings["active_character"]
                cls.save_user_settings(user_id, settings)
            return cls.load_active(user_id)
            
        return char

    @classmethod
    def load_by_name(cls, user_id: str, char_name: str) -> Optional[CharacterSchema]:
        """讀取指定名稱的角色"""
        if char_name == "settings":
            return None
            
        folder = cls._get_user_folder(user_id)
        file_path = os.path.join(folder, f"{char_name}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    return CharacterSchema(**data)
                except Exception as e:
                    print(f"解析角色 {char_name} 失敗: {e}")
                    return None
        return None

    @classmethod
    def list_characters(cls, user_id: str) -> List[str]:
        """列出使用者所有角色的名稱 (排除 settings.json, warehouse.json 等系統檔案)"""
        folder = cls._get_user_folder(user_id)
        if not os.path.exists(folder):
            return []
        
        excluded_files = ["settings.json", "warehouse.json"]
        return [
            f.replace(".json", "") 
            for f in os.listdir(folder) 
            if f.endswith(".json") and f not in excluded_files
        ]

    @classmethod
    def delete_character(cls, user_id: str, char_name: str) -> bool:
        """刪除指定角色"""
        folder = cls._get_user_folder(user_id)
        file_path = os.path.join(folder, f"{char_name}.json")
        if os.path.exists(file_path):
            os.remove(file_path)
            # 如果刪除的是活躍角色，清除活躍紀錄
            if cls.get_active_character_name(user_id) == char_name:
                settings = cls.get_user_settings(user_id)
                if "active_character" in settings:
                    del settings["active_character"]
                    cls.save_user_settings(user_id, settings)
            return True
        return False

    @classmethod
    def set_active_character(cls, user_id: str, char_name: str):
        """設定活躍角色 (儲存在 settings.json 中)"""
        settings = cls.get_user_settings(user_id)
        settings["active_character"] = char_name
        cls.save_user_settings(user_id, settings)

    @classmethod
    def get_active_character_name(cls, user_id: str) -> Optional[str]:
        """獲取活躍角色名稱"""
        settings = cls.get_user_settings(user_id)
        return settings.get("active_character")

    @classmethod
    def save_user_settings(cls, user_id: str, settings: dict):
        """儲存使用者設定"""
        folder = cls._get_user_folder(user_id)
        path = os.path.join(folder, "settings.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)

    @classmethod
    def get_user_settings(cls, user_id: str) -> dict:
        """獲取使用者設定，若無則回傳預設值 (具備容錯處理)"""
        folder = cls._get_user_folder(user_id)
        path = os.path.join(folder, "settings.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"讀取 settings.json 失敗: {e}")
        
        # 嘗試從舊版 active.txt 恢復活躍角色
        active_txt = os.path.join(folder, "active.txt")
        if os.path.exists(active_txt):
            try:
                with open(active_txt, "r", encoding="utf-8") as f:
                    name = f.read().strip()
                    if name:
                        return {"public_mode": False, "active_character": name}
            except:
                pass
                
        return {"public_mode": False} # 預設為私有模式

    # --- 倉庫 (Warehouse) 相關功能 ---

    @classmethod
    def load_warehouse(cls, user_id: str) -> 'WarehouseSchema':
        """讀取使用者的虛空倉庫 (跨角色共享)"""
        from core.models import WarehouseSchema
        folder = cls._get_user_folder(user_id)
        path = os.path.join(folder, "warehouse.json")
        
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return WarehouseSchema(**data)
        
        # 若不存在，建立一個新的
        new_warehouse = WarehouseSchema(user_id=user_id)
        cls.save_warehouse(new_warehouse)
        return new_warehouse

    @classmethod
    def save_warehouse(cls, warehouse: 'WarehouseSchema'):
        """儲存虛空倉庫資料"""
        folder = cls._get_user_folder(warehouse.user_id)
        path = os.path.join(folder, "warehouse.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(warehouse.model_dump_json(indent=4))

