"""Renaming an assistant (and making it private) keeps it visible to its
owner, and its files follow it. Run: python -m unittest tests.test_rename_assistant
(from the AuraVox folder, with python\\python.exe or any Python with requirements.txt).

Uses a temporary config folder (AURAVOX_CONFIG), never the real one.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="auravox-test-")
os.environ["AURAVOX_CONFIG"] = TMP
sys.path.insert(0, ROOT)

from app.core import config_store as store  # noqa: E402
from app.skills import knowledge, reminders, routines  # noqa: E402
from app.webui import chat_store  # noqa: E402

ADMIN = {"id": "p11111111", "guest": False, "role": "admin"}
OTHER = {"id": "p22222222", "guest": False, "role": "user"}


def can_see(a, sess):
    from app.webui.config_ui import can_see as real
    return real(a, sess)


class RenameAssistant(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def _state(self, name):
        return next((a for a in store.load_state()["assistants"] if a["name"] == name), None)

    def test_rename_private_keeps_owner_and_files(self):
        state = store.load_state()
        old = next(a for a in state["assistants"] if not a["owner"])["name"]
        before = self._state(old)
        self.assertTrue(before["shared"])
        # What belongs to it, under the old name.
        os.makedirs(os.path.join(TMP, "chats", ADMIN["id"]), exist_ok=True)
        chat_store.save(old, {"messages": [{"role": "user", "text": "hola"}], "history": []}, ADMIN["id"])
        os.makedirs(knowledge._dir(old), exist_ok=True)
        reminders.add(ADMIN["id"], None, "test", "test", "reminder", 9e9, "", old, {"label": old}, "es")
        routines.save(ADMIN["id"], [{"name": "r", "time": "08:00", "days": [], "assistant": old, "blocks": ["date"]}])

        # Rename it, change every field and make it private, as the page does.
        draft = {**before, "name": "chepe", "label": "Chepe", "shared": False, "color": "#ff0000", "temperature": 1.05,
                 "personality": "You are Chepe.", "expressiveness": "some"}
        name = store.save_assistant(old, draft, store.load_state()["version"],
                                   sorted(set(before["languages"]) | {before["language"]}), owner=ADMIN["id"])
        self.assertEqual(name, "chepe")
        if True:  # same calls as config_ui's PUT /api/assistants/<name>
            knowledge.rename_assistant(old, name)
            chat_store.rename_assistant(old, name)
            reminders.rename_assistant(old, name)
            routines.rename_assistant(old, name)

        after = self._state("chepe")
        self.assertIsNotNone(after)
        self.assertIsNone(self._state(old))
        self.assertFalse(after["shared"])
        self.assertEqual(after["owner"], ADMIN["id"])
        self.assertEqual((after["label"], after["color"], after["temperature"], after["expressiveness"]),
                         ("Chepe", "#ff0000", 1.05, "some"))
        self.assertTrue(can_see(after, ADMIN))
        self.assertFalse(can_see(after, OTHER))

        self.assertEqual(chat_store.load("chepe", ADMIN["id"])["messages"][0]["text"], "hola")
        self.assertFalse(os.path.exists(os.path.join(TMP, "chats", ADMIN["id"], f"{old}.json")))
        self.assertTrue(os.path.isdir(knowledge._dir("chepe")))
        self.assertTrue(any(r["assistant"] == "chepe" for r in reminders.list_for(ADMIN["id"])))
        self.assertEqual(routines.load(ADMIN["id"])[0]["assistant"], "chepe")

    def test_private_without_owner_is_visible_to_admins(self):
        legacy = {"shared": False, "owner": ""}
        self.assertTrue(can_see(legacy, ADMIN))
        self.assertFalse(can_see(legacy, OTHER))
        self.assertFalse(can_see(legacy, {"id": "g", "guest": True, "role": "guest"}))


if __name__ == "__main__":
    unittest.main()
