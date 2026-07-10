from datetime import datetime
from bson.objectid import ObjectId
from pymongo import ReturnDocument

class TicketManager:
    def __init__(self, db):
        print("📌 Loaded TicketManager from:", __file__)
        self.db = db
        self.tickets = db["tickets"]
        self.transcripts = db["transcripts"]
        self.counters = db["counters"]

    async def next_id(self):
        doc = await self.counters.find_one_and_update(
            {"_id": "ticket_id"},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return f"TK-{doc['value']:05d}"

    async def create_ticket(self, user_id, guild_id, channel_id, topic="Support", ticket_type="support"):
        ticket_id = await self.next_id()

        doc = {
            "ticket_id": ticket_id,
            "ticket_type": ticket_type,
            "user_id": str(user_id),
            "opened_by": str(user_id),
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "topic": topic,
            "status": "open",
            "claimed_by": None,
            "opened_at": datetime.utcnow(),
            "last_updated": datetime.utcnow(),
            "closed_at": None,
            "closed_by": None,
            "transcript_id": None,
        }

        await self.tickets.insert_one(doc)
        return doc

    async def claim(self, ticket_id, staff_id):
        return await self.tickets.find_one_and_update(
            {"ticket_id": ticket_id},
            {"$set": {
                "claimed_by": str(staff_id),
                "status": "claimed",
                "last_updated": datetime.utcnow()
            }},
            return_document=ReturnDocument.AFTER
        )

    async def close(self, ticket_id, staff_id):
        return await self.tickets.find_one_and_update(
            {"ticket_id": ticket_id},
            {"$set": {
                "status": "closed",
                "closed_at": datetime.utcnow(),
                "closed_by": str(staff_id),
                "last_updated": datetime.utcnow()
            }},
            return_document=ReturnDocument.AFTER
        )

    async def save_transcript(self, ticket_id, messages, staff_id):
        doc = {
            "ticket_id": ticket_id,
            "messages": messages,
            "generated_at": datetime.utcnow(),
            "closed_by": str(staff_id),
        }

        result = await self.transcripts.insert_one(doc)
        await self.tickets.update_one(
            {"ticket_id": ticket_id},
            {"$set": {"transcript_id": result.inserted_id}}
        )
        return result.inserted_id

    async def get_by_channel(self, channel_id):
        return await self.tickets.find_one({"channel_id": str(channel_id)})


    async def find_open_ticket(self, user_id: int, ticket_type: str):
        return await self.tickets.find_one({
            "user_id": str(user_id),
            "ticket_type": ticket_type,
            "status": {"$in": ["open", "claimed"]}
        })

