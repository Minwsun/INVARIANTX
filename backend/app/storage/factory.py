import os

from app.storage.firestore import FirestoreStore
from app.storage.memory import InMemoryStore


def create_store():
    backend = os.getenv("INVARIANT_STORE", "memory").casefold()
    if backend == "memory":
        return InMemoryStore()
    if backend == "firestore":
        return FirestoreStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    raise ValueError(f"unsupported INVARIANT_STORE: {backend}")
