import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, Dict, List, Any
from bson import ObjectId
from pymongo import ReturnDocument

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "telegram_id_store")

class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        if not self.client:
            self.client = AsyncIOMotorClient(MONGODB_URI)
            self.db = self.client[DATABASE_NAME]
            # Existing indexes
            await self.db.users.create_index("user_id", unique=True)
            await self.db.account_services.create_index("name", unique=True)
            await self.db.account_services.create_index("platform")
            await self.db.accounts.create_index("phone", unique=True)
            await self.db.accounts.create_index("service_id")
            await self.db.accounts.create_index("status")
            await self.db.accounts.create_index("sold_to")
            await self.db.session_services.create_index("name", unique=True)
            await self.db.session_items.create_index("session_string", unique=True)
            await self.db.session_items.create_index("service_id")
            await self.db.session_items.create_index("status")
            await self.db.session_items.create_index("sold_to")
            await self.db.payments.create_index("order_id", unique=True)

            # NEW: unified services and claims indexes
            await self.db.services.create_index("name", unique=True)
            await self.db.services.create_index("type")
            await self.db.services.create_index("is_active")
            await self.db.claims.create_index("token", unique=True)
            await self.db.claims.create_index("expires_at", expireAfterSeconds=0)  # TTL

    # ------------------ Users (unchanged) ------------------
    async def get_user(self, user_id: int) -> Optional[Dict]:
        return await self.db.users.find_one({"user_id": user_id})

    async def create_user(self, user_id: int, username: str = "", full_name: str = "") -> Dict:
        user = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "balance": 0.0,
            "is_owner": user_id == int(os.getenv("OWNER_ID")),
            "is_banned": False,
            "joined_channel": False,
            "total_purchases": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await self.db.users.insert_one(user)
        return user

    async def update_user_balance(self, user_id: int, amount: float) -> bool:
        result = await self.db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": amount}, "$set": {"updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    async def get_user_balance(self, user_id: int) -> float:
        user = await self.get_user(user_id)
        return user.get("balance", 0.0) if user else 0.0

    # ------------------ Account Services (unchanged) ------------------
    async def create_account_service(self, name: str, price: float, platform: str = "telegram", description: str = "") -> Dict:
        service = {
            "name": name,
            "price": price,
            "platform": platform,
            "description": description,
            "type": "account",
            "is_active": True,
            "total_items": 0,
            "available_items": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.db.account_services.insert_one(service)
        service["_id"] = str(result.inserted_id)
        return service

    async def get_all_account_services(self, platform: Optional[str] = None) -> List[Dict]:
        query = {"is_active": True, "type": "account"}
        if platform:
            query["platform"] = platform
        cursor = self.db.account_services.find(query).sort("name", 1)
        return await cursor.to_list(length=None)

    async def get_account_service(self, service_id: str) -> Optional[Dict]:
        try:
            return await self.db.account_services.find_one({"_id": ObjectId(service_id)})
        except:
            return await self.db.account_services.find_one({"_id": service_id})

    async def get_account_service_by_name(self, name: str) -> Optional[Dict]:
        return await self.db.account_services.find_one({"name": name, "type": "account"})

    async def update_account_service(self, service_id: str, data: Dict) -> bool:
        data["updated_at"] = datetime.utcnow()
        try:
            result = await self.db.account_services.update_one({"_id": ObjectId(service_id)}, {"$set": data})
        except:
            result = await self.db.account_services.update_one({"_id": service_id}, {"$set": data})
        return result.modified_count > 0

    async def delete_account_service(self, service_id: str) -> bool:
        try:
            result = await self.db.account_services.update_one({"_id": ObjectId(service_id)}, {"$set": {"is_active": False, "updated_at": datetime.utcnow()}})
        except:
            result = await self.db.account_services.update_one({"_id": service_id}, {"$set": {"is_active": False, "updated_at": datetime.utcnow()}})
        return result.modified_count > 0

    async def get_account_service_available_count(self, service_id: str) -> int:
        return await self.db.accounts.count_documents({"service_id": service_id, "status": "available"})

    # ------------------ Accounts (unchanged) ------------------
    async def add_account_to_service(self, service_id: str, phone: str) -> Dict:
        account = {
            "service_id": service_id,
            "phone": phone,
            "status": "available",
            "sold_to": None,
            "sold_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.db.accounts.insert_one(account)
        account["_id"] = str(result.inserted_id)
        await self.db.account_services.update_one({"_id": ObjectId(service_id)}, {"$inc": {"total_items": 1, "available_items": 1}})
        return account

    async def save_account_session(self, phone: str, session_string: str, two_fa_password: str = None) -> bool:
        update_data = {
            "session_string": session_string,
            "updated_at": datetime.utcnow()
        }
        if two_fa_password is not None:
            update_data["two_fa_password"] = two_fa_password
        result = await self.db.accounts.update_one(
            {"phone": phone},
            {"$set": update_data},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    async def get_available_accounts(self, service_id: str, limit: int = 10) -> List[Dict]:
        cursor = self.db.accounts.find({"service_id": service_id, "status": "available"}).limit(limit)
        return await cursor.to_list(length=limit)

    async def purchase_account_from_service(self, service_id: str, user_id: int, price: float) -> Optional[Dict]:
        account = await self.db.accounts.find_one_and_update(
            {"service_id": service_id, "status": "available"},
            {"$set": {"status": "sold", "sold_to": user_id, "sold_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER
        )
        if not account:
            return None
        user_result = await self.db.users.update_one(
            {"user_id": user_id, "balance": {"$gte": price}},
            {"$inc": {"balance": -price, "total_purchases": 1}}
        )
        if user_result.modified_count == 0:
            await self.db.accounts.update_one({"_id": account["_id"]}, {"$set": {"status": "available", "sold_to": None, "sold_at": None}})
            return None
        await self.db.account_services.update_one({"_id": ObjectId(service_id)}, {"$inc": {"available_items": -1}})
        return account

    async def get_account_by_phone(self, phone: str) -> Optional[Dict]:
        return await self.db.accounts.find_one({"phone": phone})

    # ------------------ Session Services (unchanged) ------------------
    async def create_session_service(self, name: str, price: float, description: str = "") -> Dict:
        service = {
            "name": name,
            "price": price,
            "description": description,
            "type": "session",
            "is_active": True,
            "total_items": 0,
            "available_items": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.db.session_services.insert_one(service)
        service["_id"] = str(result.inserted_id)
        return service

    async def get_all_session_services(self) -> List[Dict]:
        cursor = self.db.session_services.find({"is_active": True, "type": "session"}).sort("name", 1)
        return await cursor.to_list(length=None)

    async def get_session_service(self, service_id: str) -> Optional[Dict]:
        try:
            return await self.db.session_services.find_one({"_id": ObjectId(service_id)})
        except:
            return await self.db.session_services.find_one({"_id": service_id})

    async def get_session_service_by_name(self, name: str) -> Optional[Dict]:
        return await self.db.session_services.find_one({"name": name, "type": "session"})

    async def update_session_service(self, service_id: str, data: Dict) -> bool:
        data["updated_at"] = datetime.utcnow()
        try:
            result = await self.db.session_services.update_one({"_id": ObjectId(service_id)}, {"$set": data})
        except:
            result = await self.db.session_services.update_one({"_id": service_id}, {"$set": data})
        return result.modified_count > 0

    async def delete_session_service(self, service_id: str) -> bool:
        try:
            result = await self.db.session_services.update_one({"_id": ObjectId(service_id)}, {"$set": {"is_active": False, "updated_at": datetime.utcnow()}})
        except:
            result = await self.db.session_services.update_one({"_id": service_id}, {"$set": {"is_active": False, "updated_at": datetime.utcnow()}})
        return result.modified_count > 0

    async def get_session_service_available_count(self, service_id: str) -> int:
        return await self.db.session_items.count_documents({"service_id": service_id, "status": "available"})

    # ------------------ Session Items (unchanged) ------------------
    async def add_session_item(self, service_id: str, session_string: str) -> Dict:
        item = {
            "service_id": service_id,
            "session_string": session_string,
            "status": "available",
            "sold_to": None,
            "sold_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.db.session_items.insert_one(item)
        item["_id"] = str(result.inserted_id)
        await self.db.session_services.update_one({"_id": ObjectId(service_id)}, {"$inc": {"total_items": 1, "available_items": 1}})
        return item

    async def get_available_session_items(self, service_id: str, limit: int = 10) -> List[Dict]:
        cursor = self.db.session_items.find({"service_id": service_id, "status": "available"}).limit(limit)
        return await cursor.to_list(length=limit)

    async def purchase_session_from_service(self, service_id: str, user_id: int, price: float) -> Optional[Dict]:
        item = await self.db.session_items.find_one_and_update(
            {"service_id": service_id, "status": "available"},
            {"$set": {"status": "sold", "sold_to": user_id, "sold_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER
        )
        if not item:
            return None
        user_result = await self.db.users.update_one(
            {"user_id": user_id, "balance": {"$gte": price}},
            {"$inc": {"balance": -price, "total_purchases": 1}}
        )
        if user_result.modified_count == 0:
            await self.db.session_items.update_one({"_id": item["_id"]}, {"$set": {"status": "available", "sold_to": None, "sold_at": None}})
            return None
        await self.db.session_services.update_one({"_id": ObjectId(service_id)}, {"$inc": {"available_items": -1}})
        return item

    # ------------------ Payments (unchanged) ------------------
    async def create_payment(self, user_id: int, amount: float, order_id: str, upi_id: str) -> Dict:
        payment = {
            "user_id": user_id,
            "amount": amount,
            "upi_id": upi_id,
            "order_id": order_id,
            "status": "pending",
            "verified": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await self.db.payments.insert_one(payment)
        return payment

    async def get_payment(self, order_id: str) -> Optional[Dict]:
        return await self.db.payments.find_one({"order_id": order_id})

    async def verify_payment(self, order_id: str) -> bool:
        result = await self.db.payments.update_one(
            {"order_id": order_id},
            {"$set": {"status": "verified", "verified_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    # ------------------ Admin (unchanged) ------------------
    async def get_admins(self) -> List[int]:
        cursor = self.db.users.find({"is_owner": True})
        admins = await cursor.to_list(length=None)
        return [admin["user_id"] for admin in admins]

    async def add_admin(self, user_id: int) -> bool:
        existing = await self.get_user(user_id)
        if not existing:
            await self.create_user(user_id, username="", full_name="")
        result = await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_owner": True, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    async def remove_admin(self, user_id: int) -> bool:
        if user_id == int(os.getenv("OWNER_ID")):
            return False
        result = await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_owner": False, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    # ------------------ Settings (unchanged) ------------------
    async def update_settings(self, key: str, value: Any) -> bool:
        result = await self.db.settings.update_one({"key": key}, {"$set": {"value": value, "updated_at": datetime.utcnow()}}, upsert=True)
        return True

    async def get_settings(self, key: str) -> Optional[Any]:
        setting = await self.db.settings.find_one({"key": key})
        return setting.get("value") if setting else None

    # ------------------ Purchase History (unchanged) ------------------
    async def get_purchase_history(self, user_id: int) -> List[Dict]:
        accounts = await self.db.accounts.find({"sold_to": user_id, "status": {"$in": ["sold", "deleted"]}}).to_list(length=None)
        sessions = await self.db.session_items.find({"sold_to": user_id, "status": {"$in": ["sold", "deleted"]}}).to_list(length=None)
        purchases = []
        for acc in accounts:
            service = await self.get_account_service(acc["service_id"])
            purchases.append({
                "type": "account",
                "service_name": service["name"] if service else "Unknown",
                "item": acc["phone"],
                "price": service["price"] if service else 0,
                "sold_at": acc["sold_at"],
                "status": acc["status"]
            })
        for sess in sessions:
            service = await self.get_session_service(sess["service_id"])
            purchases.append({
                "type": "session",
                "service_name": service["name"] if service else "Unknown",
                "item": f"Session #{str(sess['_id'])[:8]}",
                "price": service["price"] if service else 0,
                "sold_at": sess["sold_at"],
                "status": sess["status"]
            })
        purchases.sort(key=lambda x: x["sold_at"], reverse=True)
        return purchases

    # ------------------ NEW: Unified Services (for claims) ------------------
    async def get_service(self, service_id: str) -> Optional[Dict]:
        try:
            return await self.db.services.find_one({"_id": ObjectId(service_id)})
        except:
            return await self.db.services.find_one({"_id": service_id})

    # ------------------ NEW: Claims ------------------
    async def get_claim(self, token: str):
        return await self.db.claims.find_one({"token": token})

    async def mark_claim_used(self, token: str, user_id: int):
        result = await self.db.claims.update_one(
            {"token": token, "used": False},
            {"$set": {"used": True, "used_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    async def claim_account_by_token(self, token: str, user_id: int):
        claim = await self.get_claim(token)
        if not claim:
            return None, "Invalid token"
        if claim.get("used"):
            return None, "Token already used"
        if claim["user_id"] != user_id:
            return None, "Token does not belong to you"
        if claim["expires_at"] < datetime.utcnow():
            return None, "Token expired"

        service_id = claim["service_id"]
        async with self.db.client.start_session() as session:
            async with session.start_transaction():
                account = await self.db.accounts.find_one_and_update(
                    {"service_id": service_id, "status": "available"},
                    {"$set": {"status": "sold", "sold_to": user_id, "sold_at": datetime.utcnow(), "claimed": True}},
                    session=session,
                    return_document=ReturnDocument.AFTER
                )
                if not account:
                    await session.abort_transaction()
                    return None, "No accounts available"
                await self.db.services.update_one(
                    {"_id": ObjectId(service_id)},
                    {"$inc": {"available_items": -1}},
                    session=session
                )
                await self.db.claims.update_one(
                    {"_id": claim["_id"]},
                    {"$set": {"used": True, "used_at": datetime.utcnow()}},
                    session=session
                )
        return account, None

    async def claim_session_by_token(self, token: str, user_id: int):
        claim = await self.get_claim(token)
        if not claim:
            return None, "Invalid token"
        if claim.get("used"):
            return None, "Token already used"
        if claim["user_id"] != user_id:
            return None, "Token does not belong to you"
        if claim["expires_at"] < datetime.utcnow():
            return None, "Token expired"

        service_id = claim["service_id"]
        async with self.db.client.start_session() as session:
            async with session.start_transaction():
                item = await self.db.session_items.find_one_and_update(
                    {"service_id": service_id, "status": "available"},
                    {"$set": {"status": "sold", "sold_to": user_id, "sold_at": datetime.utcnow(), "claimed": True}},
                    session=session,
                    return_document=ReturnDocument.AFTER
                )
                if not item:
                    await session.abort_transaction()
                    return None, "No sessions available"
                await self.db.services.update_one(
                    {"_id": ObjectId(service_id)},
                    {"$inc": {"available_items": -1}},
                    session=session
                )
                await self.db.claims.update_one(
                    {"_id": claim["_id"]},
                    {"$set": {"used": True, "used_at": datetime.utcnow()}},
                    session=session
                )
        return item, None

db = Database()
